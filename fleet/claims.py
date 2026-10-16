"""The claims queue: insurance team bundles + TGSIM near-miss events wrapped as synthetic claims.

Sources (each claim carries `_fleet_source`, shown everywhere in the trace and findings):
  insurance_example   insurance/examples/*.json (synthetic, hand-built by the insurance team)
  insurance_synthetic insurance/synth_bundles.py generator (synthetic UK portfolio)
  tgsim_near_miss     REAL US traffic near-miss geometry (FHWA TGSIM, public domain) inside a
                      SYNTHETIC claim wrapper: the collision, injury and AV logs are made up.

    python -m fleet.claims build-tgsim <events_dir_or_glob>...   # writes fleet/data/tgsim_claims.json
"""
from __future__ import annotations

import glob
import json
import math
import sys
from pathlib import Path

from fleet import insurance_link

HERE = Path(__file__).resolve().parent
TGSIM_CLAIMS = HERE / "data" / "tgsim_claims.json"
T_CRASH = 1000.0
TGSIM_LABEL = "real US traffic near-miss (FHWA TGSIM), synthetic claim wrapper"
MAX_TGSIM_DECEL = 9.0   # DESIGN ASSUMPTION: clip measured lead decel (tracking noise) to a physical value


def _at(samples: list, t: float) -> list:
    return min(samples, key=lambda s: abs(s[0] - t))


def bundle_from_tgsim(ev: dict, n: int) -> dict | None:
    """One TGSIM event (sim.data.citysim.event_to_dict form) -> bundle dict, or None if unusable."""
    meta = ev.get("meta", {})
    if meta.get("bbox_overlap"):
        return None   # boxes overlap but nothing crashed: tracking artefact, skip (see sim/data/tgsim.py)
    e, o = _at(ev["ego"]["samples"], ev["t_key"]), _at(ev["other"]["samples"], ev["t_key"])
    ve, vo = abs(e[4]), abs(o[4])
    gap = abs(o[1] - e[1]) - (ev["ego"]["length"] + ev["other"]["length"]) / 2
    if ev["kind"] == "cut_in":
        gap = meta.get("gap_at_cut_in_m", gap)
    if not (math.isfinite(gap) and gap > 0.5 and ve > 1.0):
        return None
    t_start = T_CRASH - 3.0
    case_id = f"tgsim_{ev['kind']}_{meta.get('run', 0)}_{meta.get('frame_start', n)}"
    conflict = {"hazard_id": "h1", "t_start": t_start, "ego_speed_mps": round(ve, 2), "gap_m": round(gap, 1),
                "hazard_speed_mps": round(vo, 2), "friction_mu": 0.7}
    if ev["kind"] == "cut_in":
        conflict.update(kind="cut_in", crash_type="cut_in", t_in_path_s=0.5)
    else:
        decel = min(MAX_TGSIM_DECEL, abs(float(meta.get("min_lead_accel_mps2", -4.0))))
        conflict.update(kind="lead_braking", crash_type="lead_vehicle_decel", hazard_decel_mps2=round(decel, 1))
    return {
        "schema_version": "0.1", "case_id": case_id, "synthetic": True, "t_crash": T_CRASH, "jurisdiction": "UK",
        "_fleet_source": "tgsim_near_miss", "_fleet_label": TGSIM_LABEL,
        "_tgsim": {"location": ev["location"], "t_key": ev["t_key"], "min_ttc_s": ev.get("min_ttc_s"),
                   "min_gap_m": ev.get("min_gap_m"), "real_outcome": "near miss, no collision recorded"},
        "narrative": (f"Synthetic claim built on a real {ev['kind'].replace('_', ' ')} near miss recorded by "
                      f"FHWA TGSIM at {ev['location']}. Ego {ve:.1f} m/s, other vehicle {vo:.1f} m/s, "
                      f"gap {gap:.1f} m. Collision, injury and AV logs are hypothetical."),
        "vehicle": {"software_version": "synthetic-1.0", "approved_software": ["synthetic-1.0"], "occupant": "none",
                    "software_verified": True, "mode_events": [{"t": 0.0, "mode": "automated"}],
                    "odd_inside": True, "control_inputs": []},
        "perception": {"sensors": ["camera", "lidar", "radar"], "decision_log_present": False,
                       "objects": [{"id": "h1", "cls": "vehicle", "first_detected_t": t_start, "confidence": 0.9}]},
        "external": {"cctv": ["TGSIM overhead video (FHWA)"], "witnesses": 0, "police_report": False,
                     "weather": "dry", "lighting": "daylight"},
        "integrity": {"hashes_present": True, "chain_of_custody": True, "clock_offsets_s": {"vehicle_log": 0.0},
                      "log_gaps": [], "tamper_flag": False},
        "conflict": conflict,
        "outcome": {"collided": True, "injury_severity": "Slight"},
    }


def build_tgsim(paths: list[str], limit: int = 40) -> list[dict]:
    files = sorted(f for p in paths for f in (glob.glob(str(Path(p) / "*.json")) if Path(p).is_dir() else glob.glob(p)))
    out, n = [], 0
    for f in files:
        if not any(k in Path(f).name for k in ("cut_in", "lead_brake")):
            continue
        for ev in json.loads(Path(f).read_text()):
            n += 1
            b = bundle_from_tgsim(ev, n)
            if b:
                out.append(b)
    cut = [b for b in out if b["conflict"]["kind"] == "cut_in"]
    rest = [b for b in out if b["conflict"]["kind"] != "cut_in"]
    return (cut + rest)[:limit]


def tagged(b: dict, source: str, label: str) -> dict:
    b = dict(b)
    b.setdefault("_fleet_source", source)
    b.setdefault("_fleet_label", label)
    return b


def load_queue(n_synthetic: int = 30, seed: int = 7, n_tgsim: int = 30, examples: bool = True) -> list[dict]:
    q: list[dict] = []
    demo = HERE / "data" / "demo_claims.json"
    if demo.exists():
        q += json.loads(demo.read_text())  # self-consistent synthetic demo claims (fleet/demo_claims.py)
    if examples:
        q += [tagged(b, "insurance_example", "synthetic example bundle (insurance team)")
              for b in insurance_link.example_bundles()]
    q += [tagged(b, "insurance_synthetic", "synthetic UK claim (insurance team generator)")
          for b in insurance_link.synthetic_bundles(n_synthetic, seed)]
    if TGSIM_CLAIMS.exists() and n_tgsim:
        q += json.loads(TGSIM_CLAIMS.read_text())[:n_tgsim]
    seen, out = set(), []
    for b in q:
        if b.get("case_id") and b["case_id"] not in seen and b.get("conflict"):
            seen.add(b["case_id"])
            out.append(b)
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "build-tgsim":
        bs = build_tgsim(sys.argv[2:])
        TGSIM_CLAIMS.parent.mkdir(parents=True, exist_ok=True)
        TGSIM_CLAIMS.write_text(json.dumps(bs, indent=1) + "\n")
        print(f"wrote {len(bs)} TGSIM claims to {TGSIM_CLAIMS}")
    else:
        q = load_queue()
        print(len(q), "claims:", {s: sum(b["_fleet_source"] == s for b in q) for s in {b["_fleet_source"] for b in q}})
