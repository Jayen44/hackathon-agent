"""Real-crash evaluation: R157 careful drivers A and B on real rear-end crashes and near-crashes
from the 100-Car Naturalistic Driving Study (VTTI, CC0 1.0; see sim/data/hundredcar.py).

For every lead-vehicle rear-end event (subject strikes / nearly strikes the vehicle ahead):
1. Reconstruct initial conditions at t0 = (min radar range) - 5 s (or as far back as the radar
   track goes, >= 2.5 s): ego speed, lead speed (ego speed + range rate), bumper gap (range),
   lead acceleration piecewise per 0.5 s from the radar-derived lead speed.
2. Reproduction check (rubric B1/B2): replay the recorded human acceleration (AVReplayPolicy)
   against the lead's measured motion. Reproduced = sim collision matches the coded outcome
   (Crash -> contact, Near-Crash -> no contact). Reconstructor loop: if not reproduced, shift
   gap and lead speed by one sensor-uncertainty step toward the coded outcome, up to 5
   attempts total (never beyond +/- SENSOR bounds). Also gap RMSE vs radar (B2).
3. Counterfactual: careful driver A (R157 PM1 CCDM) and B (R157 PM2 FSM) from
   montecarlo.estimate.drivers(), Monte Carlo over the reconstructed values +/- sensor
   uncertainty (source "reported"). The careful driver owns the brake; the throttle follows the
   recorded human when the human was off the brake ("human_throttle", main result) or holds
   speed ("hold_speed", the literal R157 assumption, sensitivity).
4. Headline: share of real crashes each careful driver avoids (event avoided if P(avoid) >= 0.5),
   Wilson 90% CI over events; same for near-crashes (sanity: should be high).

    .venv/bin/python -I eval/real_crash_eval.py --data-dir <dir with crash.txt nearcrash.txt events.txt>

Outputs eval/results/real_crash_eval.json. Human drivers, not AVs; see eval/REAL_CRASH_EVAL.md.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from montecarlo.counterfactual import wilson  # noqa: E402
from montecarlo.estimate import drivers  # noqa: E402
from sim.data import hundredcar as hc  # noqa: E402
from sim.policies.av_replay import AVReplayPolicy  # noqa: E402
from sim.scenario import ScriptedActor, SimScenario, piecewise_constant  # noqa: E402
from sim.vehicle import Geometry, VehicleState  # noqa: E402
from sim.world import Observation, run  # noqa: E402

# DESIGN ASSUMPTION: generic passenger-car geometry for both vehicles (the 100-Car fleet is
# mid-size sedans/SUVs; target type is mostly "Automobile"). Radar range = bumper gap.
CAR = Geometry(length=4.6, width=1.9, wheelbase=2.8)
# DESIGN ASSUMPTION: +/- measurement uncertainty, tagged "reported" (sensor-measured).
# Radar range resolution/noise ~0.5 m; composite speed is reported in whole mph (0.45 m/s);
# lead speed = ego speed + range rate carries both errors.
SENSOR = {"gap": 0.5, "ego_speed": 0.3, "lead_speed": 0.5}
MAX_ATTEMPTS = 5
AVOID_THRESHOLD = 0.5
DT = 0.02


@dataclass(frozen=True)
class Offsets:
    gap: float = 0.0
    ego_speed: float = 0.0
    lead_speed: float = 0.0


def build(ev: hc.LeadEvent, off: Offsets = Offsets(), lead_profile=None) -> SimScenario:
    i = ev.initial
    lead_profile = hc.lead_accel_profile(ev) if lead_profile is None else lead_profile
    gap = max(0.05, i["gap"] + off.gap)
    lead = ScriptedActor("lead", CAR, VehicleState(gap + CAR.length, 0.0, 0.0, max(0.0, i["lead_speed"] + off.lead_speed)),
                         accel_profile=lead_profile)
    return SimScenario(CAR, VehicleState(0.0, 0.0, 0.0, max(0.0, i["ego_speed"] + off.ego_speed)), [lead],
                       duration=float(ev.t[-1]), dt=DT)


def human_throttle_profile(ev: hc.LeadEvent, seg: float = 0.1) -> list[tuple[float, float]]:
    """Recorded human accel while the brake pedal is off; 0 (hold speed) while it is on, so the
    careful driver never inherits the human's own braking."""
    out = []
    t0 = 0.0
    brk = ev.ego_brake if ev.ego_brake is not None else np.zeros_like(ev.t)
    while t0 < ev.t[-1] - 1e-9:
        m = (ev.t >= t0) & (ev.t < t0 + seg)
        if m.any():
            a = 0.0 if brk[m].max() > 0 else float(np.mean(ev.ego_a[m]))
        else:
            a = out[-1][1] if out else 0.0
        out.append((round(t0, 6), a))
        t0 += seg
    return out


class CarefulWithThrottle:
    """Careful-driver policy owns the brake; when it does not brake, apply `throttle` (a
    piecewise accel profile, e.g. the recorded human off-brake accel) or hold speed (None)."""

    def __init__(self, inner, throttle: list[tuple[float, float]] | None):
        self.inner, self.throttle = inner, throttle

    def reset(self) -> None:
        self.inner.reset()

    def act(self, obs: Observation) -> tuple[float, float]:
        a, steer = self.inner.act(obs)
        if a < 0 or self.throttle is None:
            return a, steer
        return piecewise_constant(self.throttle, obs.t), steer


def gap_rmse(ev: hc.LeadEvent, res) -> float | None:
    """RMSE between the replay's bumper gap and the radar range, where both exist (B2)."""
    tt = np.asarray(res.trace["t"])
    ego = np.asarray(res.trace["ego"])
    lead = np.asarray(res.trace["lead"])
    sim_gap = lead[:, 0] - ego[:, 0] - CAR.length
    meas = np.interp(tt, ev.t, ev.gap, left=np.nan, right=np.nan)
    m = np.isfinite(meas)
    if m.sum() < 3:
        return None
    return float(np.sqrt(np.mean((sim_gap[m] - meas[m]) ** 2)))


def reproduce(ev: hc.LeadEvent, lead_profile, ego_profile) -> dict:
    """Reconstructor loop, bounded by sensor uncertainty."""
    want = ev.severity == "Crash"
    attempts = []
    off = Offsets()
    for k in range(MAX_ATTEMPTS):
        res = run(build(ev, off, lead_profile), AVReplayPolicy(ego_profile))
        ok = res.collided == want
        attempts.append({"offsets": off.__dict__, "collided": res.collided})
        if ok:
            break
        # Toward the coded outcome: crash -> less gap / slower lead; near-crash -> the reverse.
        s = -1.0 if want else 1.0
        step = (k + 1) / (MAX_ATTEMPTS - 1)
        off = Offsets(gap=s * SENSOR["gap"] * step, ego_speed=-s * SENSOR["ego_speed"] * step,
                      lead_speed=s * SENSOR["lead_speed"] * step)
    return {"reproduced": ok, "attempts": len(attempts), "first_attempt": attempts[0]["collided"] == want,
            "offsets": attempts[-1]["offsets"], "gap_rmse_m": gap_rmse(ev, res),
            "sim_impact_rel_speed_mps": res.relative_speed_at_impact if res.collided else None,
            "sim_t_collision_s": res.t_collision}


def counterfactual(ev: hc.LeadEvent, centre: dict, factories: dict, lead_profile, throttle,
                   n: int, seed: int) -> dict:
    """P(avoid) per driver over centre +/- SENSOR (uniform, common random numbers)."""
    rng = np.random.default_rng([seed, ev.event_id])
    u = rng.random((n, 3)) * 2 - 1
    pols = {k: CarefulWithThrottle(f(), throttle) for k, f in factories.items()}
    out = {}
    for k, pol in pols.items():
        avoided = 0
        for row in u:
            off = Offsets(gap=centre["gap"] + row[0] * SENSOR["gap"],
                          ego_speed=centre["ego_speed"] + row[1] * SENSOR["ego_speed"],
                          lead_speed=centre["lead_speed"] + row[2] * SENSOR["lead_speed"])
            r = run(build(ev, off, lead_profile), pol, record_trace=False)
            avoided += not (r.collided or r.ended_closing)
        lo, hi = wilson(avoided, n)
        out[k] = {"p_avoid": avoided / n, "ci90": [lo, hi], "n": n}
    return out


def share(events: list[dict], key: str, variant: str) -> dict:
    flags = [e["counterfactual"][variant][key]["p_avoid"] >= AVOID_THRESHOLD for e in events]
    k, n = int(sum(flags)), len(flags)
    lo, hi = wilson(k, n)
    mean_p = float(np.mean([e["counterfactual"][variant][key]["p_avoid"] for e in events])) if events else float("nan")
    return {"avoided": k, "n": n, "share": k / n if n else float("nan"), "ci90": [lo, hi], "mean_p_avoid": mean_p}


def evaluate_events(evs: list[hc.LeadEvent], n: int = 200, seed: int = 0,
                    variants: tuple[str, ...] = ("human_throttle", "hold_speed")) -> dict:
    facts, labels = drivers()
    rows = []
    for ev in evs:
        lead_profile = hc.lead_accel_profile(ev)
        ego_profile = hc.ego_accel_profile(ev)
        rep = reproduce(ev, lead_profile, ego_profile)
        centre = rep["offsets"]
        cf = {}
        for var in variants:
            thr = human_throttle_profile(ev) if var == "human_throttle" else None
            cf[var] = counterfactual(ev, centre, facts, lead_profile, thr, n, seed)
        rows.append({"event_id": ev.event_id, "severity": ev.severity, "precipitating_event": ev.precipitating_event,
                     "initial": {k: round(v, 3) for k, v in ev.initial.items()},
                     "pre_s": ev.meta.get("pre_s"), "radar_min_gap_m": round(ev.min_gap_m, 2),
                     "stitched_tracks": ev.meta.get("stitched_tracks"),
                     "accel_bias_mps2": ev.meta.get("accel_bias_mps2"),
                     "ranges": {k: {"lo": round(ev.initial[k] + centre[k] - SENSOR[k], 3),
                                    "hi": round(ev.initial[k] + centre[k] + SENSOR[k], 3), "source": "reported"}
                                for k in SENSOR},
                     "reproduction": rep, "counterfactual": cf})

    def summary(sev: str) -> dict:
        ev_s = [r for r in rows if r["severity"] == sev]
        rep_ok = sum(r["reproduction"]["reproduced"] for r in ev_s)
        rep_first = sum(r["reproduction"]["first_attempt"] for r in ev_s)
        rmse = [r["reproduction"]["gap_rmse_m"] for r in ev_s if r["reproduction"]["gap_rmse_m"] is not None]
        reproduced = [r for r in ev_s if r["reproduction"]["reproduced"]]
        return {
            "n_events": len(ev_s),
            "reproduction": {"within_5_attempts": rep_ok, "first_attempt": rep_first,
                             "rate": rep_ok / len(ev_s) if ev_s else float("nan"),
                             "ci90": list(wilson(rep_ok, len(ev_s))),
                             "rate_first_attempt": rep_first / len(ev_s) if ev_s else float("nan"),
                             "gap_rmse_m_median": float(np.median(rmse)) if rmse else None},
            "avoidance_all": {v: {d: share(ev_s, d, v) for d in facts} for v in variants},
            "avoidance_reproduced_only": {v: {d: share(reproduced, d, v) for d in facts} for v in variants},
        }

    return {"driver_models": labels, "summary": {"crash": summary("Crash"), "near_crash": summary("Near-Crash")},
            "events": rows}


def load_events(data_dir: Path) -> tuple[list[hc.LeadEvent], dict]:
    meta = hc.load_event_table(data_dir / "events.txt")
    lead = meta[meta.apply(hc.is_lead_rear_end, axis=1)]
    evs, skipped = [], {}
    for fname, sev in (("crash.txt", "Crash"), ("nearcrash.txt", "Near-Crash")):
        ts = hc.load_timeseries(data_dir / fname)
        cand = lead[lead["severity"] == sev]
        sk: dict[str, int] = {}
        for eid, row in cand.iterrows():
            if eid not in ts:
                sk["no time series"] = sk.get("no time series", 0) + 1
                continue
            ev, why = hc.extract_lead_event(ts[eid], row, int(eid))
            if ev is None:
                key = why.split(" (")[0].split(" only ")[0]
                sk[key] = sk.get(key, 0) + 1
            else:
                evs.append(ev)
        skipped[sev] = {"candidates": int(len(cand)), "skipped": sk}
    return evs, skipped


def _fmt(s: dict) -> str:
    return f"{s['avoided']}/{s['n']} = {100 * s['share']:.0f}% (CI90 {100 * s['ci90'][0]:.0f}-{100 * s['ci90'][1]:.0f}%)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--n", type=int, default=200, help="Monte Carlo samples per event and driver")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "results" / "real_crash_eval.json")
    a = ap.parse_args(argv)
    t0 = time.time()
    evs, skipped = load_events(a.data_dir)
    res = evaluate_events(evs, n=a.n, seed=a.seed)
    res["dataset"] = {
        "name": "100-Car Naturalistic Driving Study, crash and near-crash time series (VTTI)",
        "doi": "https://doi.org/10.15787/VTT1/CEU6RB", "licence": "CC0 1.0 (VTTI Dataverse dataset metadata)",
        "files_from": "github.com/Yiru-Jiao/Reconstruct100CarNDSData RawData/ (MIT repo; CC0 data copies; "
                      "Dataverse file store returned 404 on 2026-10-15)",
        "selection": "event nature 'Conflict with a lead vehicle', incident 'Rear-end, striking', "
                     "precipitating event 'Other vehicle ahead - ...'",
        "selection_counts": skipped,
    }
    res["method"] = {"sensor_uncertainty": SENSOR, "max_attempts": MAX_ATTEMPTS, "avoid_threshold": AVOID_THRESHOLD,
                     "pre_s": hc.PRE_REF_S, "min_pre_s": hc.MIN_PRE_REF_S, "post_s": hc.POST_REF_S,
                     "n_mc_per_event": a.n, "seed": a.seed, "ci": "Wilson 90%",
                     "main_variant": "human_throttle"}
    res["disclaimer"] = ("Human drivers in 2001-2004 Virginia, not AVs. Supporting evidence for the method, "
                         "not a liability ruling or legal advice.")
    res["runtime_s"] = round(time.time() - t0, 1)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1, default=float))
    for sev in ("crash", "near_crash"):
        s = res["summary"][sev]
        r = s["reproduction"]
        print(f"{sev}: N={s['n_events']} reproduced {r['within_5_attempts']}/{s['n_events']} "
              f"(first attempt {r['first_attempt']}), gap RMSE median {r['gap_rmse_m_median']}")
        for v, d in s["avoidance_all"].items():
            print(f"  {v}: A {_fmt(d['careful_a'])} | B {_fmt(d['careful_b'])}")
    print(f"wrote {a.out} in {res['runtime_s']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
