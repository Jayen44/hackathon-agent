"""Claims API core: crash bundle or intake form -> sim result + GBP assessment + information requests.

Pure Python (no Modal, no FastAPI) so it is unit-testable. viz/api/app.py wraps it for Modal.

Sim side (ours): montecarlo.estimate / montecarlo.evidence / montecarlo.sensitivity.
GBP side (Jayen + Antonio, branch `insurance`, CONSUMED READ-ONLY): insurance.bridge.assess_bundle and
finance.recovery. Their packages are vendored into the Modal image at build time, never into git.
If they are not importable, the API still returns the sim result and says why it cannot price.

Everything here that is not measured is a named DESIGN ASSUMPTION / DESIGN PRIOR constant. None of it is
from UN R157 (careful-driver models come from montecarlo.estimate.drivers(): R157 Annex 3 PM1 and PM2).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass, replace
from typing import Any

from montecarlo.estimate import drivers, estimate
from montecarlo.evidence import evidence_tier, ranges_from_bundle, timeline_check
from montecarlo.sensitivity import tornado

MPH = 0.44704  # m/s per mph (exact)

# Their conflict.kind -> the crash_type labels montecarlo.evidence reads (same table as insurance/bundle.py
# DEFAULT_CRASH_TYPE; copied, not imported, so the sim path works without their code).
KIND_TO_CRASH_TYPE = {"constant_hazard": "other", "lead_braking": "lead_vehicle_decel", "cut_in": "cut_in"}

# DESIGN ASSUMPTION: +/- half-width applied to a REPORTED lead-vehicle deceleration (m/s^2) and cut-in
# time-to-lane (s) by evidence tier. evidence.py has no tiering for these two facts, so we add it here.
DECEL_HALF_WIDTH = {0: 1.5, 1: 0.75, 2: 0.25}
CUT_IN_TIME_HALF_WIDTH = {0: 0.5, 1: 0.25, 2: 0.1}
TIER_SOURCE = {0: "narrative", 1: "reported", 2: "reported"}

# DESIGN PRIOR: what we assume when the insurer answers "unknown" on the intake form. Tagged `prior`,
# so they lower data sufficiency and show up as information requests.
PRIOR_SPEED_MPH = {"urban": (15.0, 35.0), "a_road": (30.0, 60.0), "motorway": (50.0, 75.0),
                   "unknown": (15.0, 75.0)}
PRIOR_GAP_M = (5.0, 40.0)
PRIOR_TIME_TO_LANE_S = (0.5, 2.5)

# DESIGN ASSUMPTION (rubric A2): below this data-sufficiency score the dashboard says "get more evidence"
# and shows any GBP figure as indicative only.
SUFFICIENCY_MIN = 0.5

# Monte Carlo sizes for the interactive API (CI half-width at n=1000 is <= ~0.026).
N_MAIN = 1000
N_SENS = 300
N_PROJECTION = 600
N_PROJECTION_SENS = 200

DISCLAIMER = ("Triage evidence for a human claims handler. Not a liability ruling and not legal advice. "
              "Careful-driver results come from simulation and carry the stated uncertainty.")
DRIVER_DISPLAY = {"careful_a": "Careful driver A (UN R157 Annex 3, PM1)",
                  "careful_b": "Careful driver B (UN R157 Annex 3, PM2)"}

PARAM_LABEL = {
    "ego_speed": "AV speed at the start of the conflict",
    "other_speed": "other vehicle speed",
    "gap": "gap to the other vehicle when the hazard appeared",
    "lateral_offset": "other vehicle's lateral start position",
    "cut_in_start": "moment the cut-in began",
    "cut_in_duration": "cut-in duration (how quickly the other vehicle entered the lane)",
    "other_decel": "lead vehicle's braking deceleration",
    "other_brake_time": "moment the lead vehicle started braking",
}
PARAM_UNIT = {"ego_speed": "m/s", "other_speed": "m/s", "gap": "m", "lateral_offset": "m", "cut_in_start": "s",
              "cut_in_duration": "s", "other_decel": "m/s^2", "other_brake_time": "s"}
PARAM_SOURCE_HINT = {
    "ego_speed": "AV logs (speed trace) or CCTV/dashcam",
    "other_speed": "CCTV/dashcam or the other vehicle's telematics",
    "gap": "CCTV/dashcam or AV perception logs",
    "lateral_offset": "CCTV/dashcam",
    "cut_in_start": "CCTV/dashcam or AV perception logs",
    "cut_in_duration": "CCTV/dashcam or AV perception logs",
    "other_decel": "AV perception logs or the lead vehicle's data",
    "other_brake_time": "AV perception logs or CCTV/dashcam",
}


# ------------------------------------------------------------------ their code (optional, read-only)

def insurance_available() -> bool:
    try:
        import finance.recovery  # noqa: F401
        import insurance.bridge  # noqa: F401
        return True
    except ImportError:
        return False


class SimCounterfactualEstimator:
    """Adapter: one driver's precomputed montecarlo.estimate result -> their insurance Estimator protocol.

    `estimate(conflict)` ignores the conflict: the result was computed from the whole bundle by our sim
    (ranges, tiering, both careful-driver models). avoids_at_p5/p95 are None because with several uncertain
    inputs there is no single fast/slow-driver axis (see montecarlo/estimate.py).
    """

    def __init__(self, name: str, driver: dict):
        self.name, self.driver = name, driver

    def estimate(self, conflict=None):
        from insurance.counterfactual import CounterfactualResult
        d = self.driver
        return CounterfactualResult(
            p_avoid=float(d["p_avoid"]), avoids_at_p5=d.get("avoids_at_p5"), avoids_at_p50=bool(d["avoids_at_p50"]),
            avoids_at_p95=d.get("avoids_at_p95"), median_impact_speed_mps=float(d["median_impact_speed_mps"]),
            n_samples=int(d["n_samples"]), model=f"{self.name}: {d['model']}",
            notes=list(d.get("notes", [])) + ["computed by montecarlo.estimate (sim branch)",
                                              "avoids_at_p5/p95 not computed (None)"])


def estimators_from_sim(sim: dict) -> dict[str, SimCounterfactualEstimator]:
    """careful_a first: their decide() uses the first estimator for the liability verdict."""
    ds = sim["drivers"]
    return {k: SimCounterfactualEstimator(k, ds[k]) for k in ("careful_a", "careful_b") if k in ds}


def _plain(x):
    if is_dataclass(x):
        return _plain(asdict(x))
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def assess_gbp(bundle: dict, sim: dict | None, engagement_override: str | None = None) -> dict:
    """Their engine on our sim. Returns a JSON-able dict; never invents a figure."""
    if not insurance_available():
        return {"available": False, "decision": "cannot_price",
                "reason": "insurance/finance engine not available in this deployment", "notes": []}
    from finance.recovery import assess
    from insurance.bridge import assess_bundle, claim_facts, to_avoidance_result
    from insurance.bundle import BundleError, load_bundle

    try:
        b = load_bundle(bundle)
    except BundleError as e:
        return {"available": True, "decision": "cannot_price", "reason": f"bundle rejected by engine: {e}", "notes": []}
    if sim is None and b.conflict is not None:
        return {"available": True, "decision": "cannot_price", "reason": "simulation did not run", "notes": []}
    est = estimators_from_sim(sim) if sim else {}
    reproduced = bool(((sim or {}).get("reproduction") or {}).get("reproduced_flag", False))
    br = assess_bundle(b, estimators=est or None, reproduced=reproduced)
    notes = list(br.notes)
    if est:
        notes.append("Both careful-driver estimators come from our sim (montecarlo.estimate); the liability "
                     "verdict uses careful_a.")
    rec = br.recovery
    if rec is not None and engagement_override and est:
        facts = replace(claim_facts(b, reproduced), engagement_status=engagement_override)
        avoid = [to_avoidance_result(n, e.estimate(b.conflict)) for n, e in est.items()]
        rec = assess(facts, avoid)
        notes.append(f"Engagement status set to '{engagement_override}' from the claim file "
                     "(not verified from vehicle data).")
    out = {"available": True, "verdict": _plain(br.verdict), "notes": notes,
           "recovery": None if rec is None else _plain(rec)}
    if rec is None:
        # Their engine left it unpriced. Human-driver liability or no collision is a "not an AV recovery" outcome
        # (badge: Don't pursue); anything else (integrity, no conflict) is "cannot price".
        not_av = br.verdict.liable == "HUMAN_DRIVER" or not b.outcome.collided
        out["decision"] = "not_av_recovery" if not_av else "cannot_price"
        out["reason"] = br.notes[0] if br.notes else "not priced"
    else:
        out["decision"] = rec.decision
        out["reason"] = "; ".join(rec.reasons) if rec.decision == "cannot_price" else None
    return out


def run_debate_for(bundle: dict, sim: dict | None, meta: dict | None = None, client=None) -> dict:
    """Antonio's adjuster -> defence counsel -> rebuttal debate (agents/debate.py, read-only) on this claim.

    We only build its inputs: ClaimFacts + both careful-driver AvoidanceResults from our sim, and the case file.
    client=None runs his scripted stand-ins ('scripted'); with an Anthropic client it runs the Claude agents.
    Every GBP figure in the debate is recomputed by finance/, never by a model.
    """
    try:
        from agents.debate import Claim, case_file, run_debate
        from insurance.bridge import assess_bundle, claim_facts, to_avoidance_result
        from insurance.bundle import load_bundle
    except ImportError as e:
        return {"available": False, "reason": f"debate agents not available in this deployment ({e.name})"}
    if not sim or not sim.get("drivers"):
        return {"available": False, "reason": "no simulation result to debate"}
    from types import SimpleNamespace
    b = load_bundle(bundle)
    est = estimators_from_sim(sim)
    reproduced = bool((sim.get("reproduction") or {}).get("reproduced_flag", False))
    ba = assess_bundle(b, estimators=est, reproduced=reproduced)
    if ba.recovery is None or ba.recovery.expected_recovery is None:
        return {"available": False, "reason": "claim not priced, nothing to debate"}
    facts = claim_facts(b, reproduced)
    override = (meta or {}).get("engagement_override")
    if override:
        facts = replace(facts, engagement_status=override)
    avoid = [to_avoidance_result(n, e.estimate(b.conflict)) for n, e in est.items()]
    cf = case_file(SimpleNamespace(bundle=b, source=None), ba, est)
    cf["provenance"]["driver_models"] = "; ".join(d["model"] for d in sim["drivers"].values()) + \
        " (montecarlo.estimate on the sim branch)"
    claim = Claim(facts, avoid, case_file=cf)
    import datetime as _dt
    stamped: list[dict] = []
    try:
        d = run_debate(claim, client, lambda row: stamped.append(
            {**row, "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")}))
    except ValueError as e:
        return {"available": False, "reason": str(e)}
    out = _plain(d.to_dict())
    out["trace"] = _plain(stamped) or out["trace"]
    out["available"] = True
    out["mode_label"] = "scripted (no model credentials on the API)" if client is None else "Claude agents"
    return out


# ------------------------------------------------------------------ bundle normalisation (our side)

def sim_bundle(bundle: dict, tier: int | None = None) -> dict:
    """Copy of `bundle` that montecarlo.evidence reads correctly.

    - fills conflict.crash_type from their conflict.kind (evidence.py keys on crash_type);
    - turns a reported lead-vehicle deceleration / cut-in time-to-lane into tiered ranges (conflict_ranges),
      unless the bundle already gives explicit conflict_ranges for them.
    """
    b = copy.deepcopy(bundle)
    c = b.get("conflict")
    if not c:
        return b
    kind = c.get("kind", "constant_hazard")
    c.setdefault("crash_type", KIND_TO_CRASH_TYPE.get(kind, "other"))
    t = evidence_tier(b) if tier is None else tier
    cr = b.setdefault("conflict_ranges", {}) or {}
    b["conflict_ranges"] = cr
    src = TIER_SOURCE[t]
    if c.get("hazard_decel_mps2") and c["crash_type"] == "lead_vehicle_decel":
        d, hw = float(c["hazard_decel_mps2"]), DECEL_HALF_WIDTH[t]
        cr.setdefault("other_decel", {"lo": max(0.0, d - hw), "hi": d + hw, "source": src})
        cr.setdefault("other_brake_time", {"lo": 0.0, "hi": 0.0, "source": src})
    if c["crash_type"] == "cut_in" and c.get("t_in_path_s") is not None and "t_in_path_s" in c:
        tt, hw = float(c["t_in_path_s"]), CUT_IN_TIME_HALF_WIDTH[t]
        cr.setdefault("cut_in_start", {"lo": 0.0, "hi": 0.0, "source": src})
        cr.setdefault("cut_in_duration", {"lo": max(0.1, tt - hw), "hi": max(0.1, tt + hw), "source": src})
    if not cr:
        b.pop("conflict_ranges")
    return b


def project_bundle(bundle: dict) -> dict:
    """What-if for the next evidence tier: facts that are currently `prior` (unknown on the intake form) are
    assumed to be pinned by the new evidence AT THEIR CURRENT CENTRAL VALUE. This is a projection, labelled so."""
    b = copy.deepcopy(bundle)
    cr = b.get("conflict_ranges") or {}
    for k in [k for k, v in cr.items() if v.get("source") == "prior" and not k.startswith("_")]:
        cr.pop(k)
    return b


def projection_pins(bundle: dict) -> list[str]:
    """Human-readable list of the currently-unknown facts that project_bundle() pins at mid-range."""
    out = []
    for k, v in (bundle.get("conflict_ranges") or {}).items():
        if v.get("source") == "prior":
            out.append(f"{PARAM_LABEL.get(k, k)} {(v['lo'] + v['hi']) / 2:.3g} {PARAM_UNIT.get(k, '')}".strip())
    return out


# ------------------------------------------------------------------ intake form -> bundle

FORM_CRASH_KIND = {"cut_in": "cut_in", "lead_vehicle_decel": "lead_braking", "stationary_hazard": "constant_hazard",
                   "other": "constant_hazard", "unknown": "constant_hazard"}
SEVERITIES = ("Fatal", "Serious", "Slight", "Damage only", "Unknown")


def _num_or_none(x) -> float | None:
    if x is None or x == "" or (isinstance(x, str) and x.strip().lower() == "unknown"):
        return None
    v = float(x)
    if not math.isfinite(v):
        raise ValueError(f"not a finite number: {x!r}")
    return v


def _tri(x, default="unknown") -> str:
    if x is True or (isinstance(x, str) and x.lower() in ("yes", "true")):
        return "yes"
    if x is False or (isinstance(x, str) and x.lower() in ("no", "false")):
        return "no"
    return default


def claim_id_for(obj: dict) -> str:
    h = hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:8]
    return f"CLM-{h.upper()}"


def form_to_bundle(form: dict) -> tuple[dict, dict]:
    """Simplified intake form -> (bundle schema 0.1, meta).

    Every field may be "unknown"/null. Unknown kinematics become wide `prior` ranges (DESIGN PRIORS above) via
    conflict_ranges, so they lower data sufficiency and become information requests. meta carries the forced
    evidence tier, the engagement code for finance and the list of unknowns.
    """
    ev = form.get("evidence") or {}
    loc = form.get("location_type") or "unknown"
    if loc not in PRIOR_SPEED_MPH:
        loc = "unknown"
    crash = form.get("crash_type") or "unknown"
    if crash not in FORM_CRASH_KIND:
        crash = "unknown"
    kind = FORM_CRASH_KIND[crash]
    unknowns: list[str] = []
    cr: dict[str, dict] = {}

    def speed(field: str, name: str, prior: tuple[float, float]) -> float:
        v = _num_or_none(form.get(field))
        if v is None:
            unknowns.append(field)
            lo, hi = prior[0] * MPH, prior[1] * MPH
            cr[name] = {"lo": lo, "hi": hi, "source": "prior"}
            return (lo + hi) / 2
        if v < 0:
            raise ValueError(f"{field} must be >= 0")
        return v * MPH

    ego = speed("ego_speed_mph", "ego_speed", PRIOR_SPEED_MPH[loc])
    if crash == "stationary_hazard" and _num_or_none(form.get("other_speed_mph")) is None:
        other = 0.0   # stationary by definition, not a prior
    else:
        hi = PRIOR_SPEED_MPH[loc][1]
        other = speed("other_speed_mph", "other_speed", (0.0, hi))
    gap = _num_or_none(form.get("gap_m"))
    if gap is None:
        unknowns.append("gap_m")
        cr["gap"] = {"lo": PRIOR_GAP_M[0], "hi": PRIOR_GAP_M[1], "source": "prior"}
        gap = sum(PRIOR_GAP_M) / 2
    elif gap < 0:
        raise ValueError("gap_m must be >= 0")
    if crash == "unknown":
        unknowns.append("crash_type")

    conflict: dict[str, Any] = {"hazard_id": "other_vehicle", "t_start": 0.0, "ego_speed_mps": ego, "gap_m": gap,
                                "hazard_speed_mps": other, "friction_mu": 0.7, "kind": kind,
                                "crash_type": {"cut_in": "cut_in", "lead_vehicle_decel": "lead_vehicle_decel"}.get(crash, "other")}
    if kind == "lead_braking":
        d = _num_or_none(form.get("lead_decel_mps2"))
        if d is None:
            unknowns.append("lead_decel_mps2")
            # evidence.py applies its own labelled prior for the lead deceleration; the engine needs a value > 0
            conflict["hazard_decel_mps2"] = 5.0
            cr["other_decel"] = {"lo": 3.0, "hi": 7.0, "source": "prior"}
        else:
            conflict["hazard_decel_mps2"] = d
    if kind == "cut_in":
        tt = _num_or_none(form.get("cut_in_time_s"))
        if tt is None:
            unknowns.append("cut_in_time_s")
            cr["cut_in_duration"] = {"lo": PRIOR_TIME_TO_LANE_S[0], "hi": PRIOR_TIME_TO_LANE_S[1], "source": "prior"}
            conflict["t_in_path_s"] = sum(PRIOR_TIME_TO_LANE_S) / 2
        else:
            conflict["t_in_path_s"] = tt

    tti = _num_or_none(form.get("time_to_impact_s"))
    engaged = _tri(form.get("av_engaged"))
    odd = _tri(form.get("within_odd"))
    for k, v in (("av_engaged", engaged), ("within_odd", odd)):
        if v == "unknown":
            unknowns.append(k)
    sev = form.get("injury_severity") or "Unknown"
    if sev not in SEVERITIES:
        sev = "Unknown"
    if sev == "Unknown":
        unknowns.append("injury_severity")
    paid = _num_or_none(form.get("claim_paid_gbp"))
    if paid is not None and paid < 0:
        raise ValueError("claim_paid_gbp must be >= 0")
    lo_s, hi_s = _num_or_none(form.get("injured_party_share_low_pct")), _num_or_none(form.get("injured_party_share_high_pct"))
    share = None
    if lo_s is not None and hi_s is not None:
        lo_s, hi_s = sorted((lo_s / 100, hi_s / 100))
        if not 0 <= lo_s <= hi_s <= 1:
            raise ValueError("injured party share must be within 0-100%")
        share = [lo_s, hi_s]
    imp = _num_or_none(form.get("impact_speed_mph"))
    collided = _tri(form.get("collided"), "yes") != "no"

    av_logs, video = bool(ev.get("av_logs")), bool(ev.get("cctv") or ev.get("dashcam"))
    tier = 2 if av_logs else 1 if video else 0
    engagement_code = {"yes": "engaged_verified" if av_logs else "engaged_alleged", "no": "not_engaged",
                       "unknown": "unknown"}[engaged]
    secured = _tri(form.get("evidence_secured")) == "yes"

    t_crash = tti if tti is not None else 0.0
    bundle = {
        "schema_version": "0.1",
        "case_id": form.get("claim_ref") or "",
        "synthetic": False,
        "t_crash": t_crash,
        "jurisdiction": "UK",
        "intake": {"source": "insurer_form", "incident_datetime": form.get("incident_datetime"),
                   "location_type": loc, "time_to_impact_known": tti is not None},
        "vehicle": {
            "software_version": "unknown", "approved_software": [],
            "occupant": "user_in_charge" if form.get("occupant") == "user_in_charge" else "none",
            # unknown engagement is modelled as automated for the engine's control-state step; finance gets
            # engagement 'unknown' (see meta) so it never counts as verified.
            "mode_events": [{"t": t_crash - 60.0, "mode": "manual" if engaged == "no" else "automated"}],
            "odd_inside": {"yes": True, "no": False, "unknown": None}[odd],
            "software_verified": _tri(form.get("software_verified")) == "yes",
        },
        "perception": {"sensors": [], "objects": [], "decision_log_present": av_logs},
        "external": {"cctv": [x for x in ("cctv", "dashcam") if ev.get(x)], "witnesses": 1 if ev.get("witnesses") else 0,
                     "police_report": bool(ev.get("police_report"))},
        "integrity": {"hashes_present": secured, "chain_of_custody": secured},
        "conflict": conflict,
        "outcome": {"collided": collided, "impact_speed_mps": None if imp is None else imp * MPH,
                    "injury_severity": sev, "paid_claim_gbp": paid, "third_party_share": share},
    }
    if cr:
        bundle["conflict_ranges"] = cr
    if not bundle["case_id"]:
        bundle["case_id"] = claim_id_for({k: v for k, v in form.items() if k != "narrative"})
    meta = {"tier": tier, "engagement_override": None if engagement_code == "engaged_verified" else engagement_code,
            "unknowns": unknowns, "has_crash_time": tti is not None,
            "evidence": {k: bool(ev.get(k)) for k in ("cctv", "dashcam", "av_logs", "police_report", "witnesses")}}
    return bundle, meta


# ------------------------------------------------------------------ CCTV bundles (from the Sim Lab)

_HEX32, _HEX12 = re.compile(r"^[0-9a-f]{32}$"), re.compile(r"^[0-9a-f]{12}$")


def cctv_meta(bundle: dict) -> dict:
    """meta for a bundle the Sim Lab built from CCTV + the insurer's claim file (viz/lab/cctv_claim.py).

    Tier 1 (video). Engagement from the claim file is at most 'engaged_alleged': only AV logs verify it.
    """
    ce = bundle.get("cctv_evidence") or {}
    cf = ce.get("claim_file") or {}
    eng = _tri(cf.get("av_engaged"))
    logs = bool((bundle.get("perception") or {}).get("decision_log_present"))
    code = {"yes": "engaged_verified" if logs else "engaged_alleged", "no": "not_engaged", "unknown": "unknown"}[eng]
    unknowns = [k for k in ("av_engaged", "within_odd", "software_verified") if _tri(cf.get(k)) == "unknown"]
    if (cf.get("injury_severity") or "Unknown") == "Unknown":
        unknowns.append("injury_severity")
    if cf.get("paid_gbp") is None:
        unknowns.append("claim_paid_gbp")
    if cf.get("cn_pct") is None:
        unknowns.append("contributory_negligence")
    return {"tier": evidence_tier(bundle), "engagement_override": None if code == "engaged_verified" else code,
            "unknowns": unknowns, "has_crash_time": True,
            "evidence": {"cctv": True, "dashcam": False, "av_logs": logs, "police_report": False, "witnesses": False}}


def cctv_summary(bundle: dict) -> dict | None:
    """Display-only CCTV provenance for the dashboard. Untrusted input: whitelisted keys, checked ids, numbers only."""
    ce = bundle.get("cctv_evidence")
    if not isinstance(ce, dict):
        return None
    vid, rid = str(ce.get("video_id", "")), str(ce.get("run_id", ""))
    if not _HEX32.match(vid) or not _HEX12.match(rid):
        return None

    def num(x):
        return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None

    def vs(x):
        return {"value": num(x.get("value")), "sd": num(x.get("sd"))} if isinstance(x, dict) else None

    def pts(xs, n):
        out = []
        for p in (xs or [])[:n]:
            if isinstance(p, (list, tuple)) and len(p) == 2 and num(p[0]) is not None and num(p[1]) is not None:
                out.append([num(p[0]), num(p[1])])
        return out

    m = ce.get("measured") or {}
    fr = ce.get("frame") or {}
    cal = ce.get("calibration") or {}
    sha = str(ce.get("sha256") or "")
    return {
        "video_id": vid, "run_id": rid, "tier": 1,
        "sha256": sha if re.fullmatch(r"[0-9a-f]{64}", sha) else None,
        "measured": {k: vs(m.get(k)) for k in ("ego_speed_mps", "other_speed_mps", "gap_m",
                                                "ego_speed_before_impact_mps") if isinstance(m.get(k), dict)},
        "min_gap_m": num(m.get("min_gap_m")),
        "ego_ids": [int(i) for i in (ce.get("ego_ids") or []) if isinstance(i, int)][:20],
        "other_ids": [int(i) for i in (ce.get("other_ids") or []) if isinstance(i, int)][:20],
        "frame": {"width": num(fr.get("width")), "height": num(fr.get("height"))},
        "calibration": {"mode": cal.get("mode") if cal.get("mode") in ("rectangle", "points") else None,
                        "img_pts": pts(cal.get("img_pts"), 50), "reprojection_rms_m": num(cal.get("reprojection_rms_m"))},
        "paths": {k: pts((ce.get("paths") or {}).get(k), 200) for k in ("av", "other")},
    }


# ------------------------------------------------------------------ sim

def bracket(sim: dict) -> tuple[float, float] | None:
    """A/B bracket: lowest CI end to highest CI end across both careful-driver models."""
    ds = (sim or {}).get("drivers") or {}
    if not ds:
        return None
    return min(d["ci90"][0] for d in ds.values()), max(d["ci90"][1] for d in ds.values())


def evidence_band(sim: dict) -> tuple[float, float] | None:
    """P(avoid) range given what is still unknown: envelope over both careful-driver models of the 90% CI and
    of P(avoid) with each non-reported fact pinned at either end of its range (one at a time, from the
    sensitivity run). Wide = the answer still depends on facts we have not got; narrow = evidence settles it."""
    b = bracket(sim)
    if b is None:
        return None
    lo, hi = b
    for row in sim.get("sensitivity") or []:
        if row["source"] == "reported":
            continue
        for end in ("p_at_lo", "p_at_hi"):
            vals = list(row[end].values())
            lo, hi = min(lo, *vals), max(hi, *vals)
    return lo, hi


def run_sim(bundle: dict, tier: int | None, map_fn=None, n: int = N_MAIN, seed: int = 0) -> dict | None:
    if not bundle.get("conflict"):
        return None
    sb = sim_bundle(bundle, tier)
    if "t_crash" in sb and not (bundle.get("intake") or {}).get("time_to_impact_known", True):
        sb.pop("t_crash")
    ranges, _ = ranges_from_bundle(sb, tier=tier)
    facts, _ = drivers()
    # The two are independent; with Modal fan-out both wait on remote workers, so overlap them.
    with ThreadPoolExecutor(2) as ex:
        f_est = ex.submit(estimate, sb, tier=tier, n=n, seed=seed, map_fn=map_fn, sensitivity=False, replays=True)
        f_tor = ex.submit(tornado, ranges, facts, n=N_SENS, seed=seed, map_fn=map_fn)
        res, t = f_est.result(), f_tor.result()
    res["sensitivity"] = t["rows"]
    res["go_get"] = t["go_get"]
    res["evidence_band"] = evidence_band(res)
    res["timeline_check"] = timeline_check(sb) if "t_crash" in sb else {
        "consistent": None, "reason": "time from hazard to impact not supplied"}
    return res


def _band_at(bundle: dict, tier: int, map_fn, seed: int) -> dict:
    sb = sim_bundle(bundle, tier)
    r = estimate(sb, tier=tier, n=N_PROJECTION, seed=seed, map_fn=map_fn, sensitivity=False)
    ranges, _ = ranges_from_bundle(sb, tier=tier)
    facts, _ = drivers()
    r["sensitivity"] = tornado(ranges, facts, n=N_PROJECTION_SENS, seed=seed, map_fn=map_fn)["rows"]
    return {"band": evidence_band(r), "p_avoid": {k: d["p_avoid"] for k, d in r["drivers"].items()},
            "data_sufficiency": r["data_sufficiency"]["score"]}


def tier_projection(bundle: dict, tier: int, sim: dict | None = None, map_fn=None, seed: int = 0) -> dict | None:
    """P(avoid) evidence band now vs at each higher tier. Projection, see project_bundle()."""
    if not bundle.get("conflict") or tier >= 2:
        return None
    out = {"tier": tier, "band_now": (sim or {}).get("evidence_band"), "next": {}}
    pb = project_bundle(bundle)
    for t in range(tier + 1, 3):
        out["next"][t] = _band_at(pb, t, map_fn, seed)
    return out


# ------------------------------------------------------------------ information requests

def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def _rng(b) -> str:
    return f"{_pct(b[0])}-{_pct(b[1])}"


TIER_EVIDENCE = {1: ("cctv_or_dashcam", "Obtain CCTV or dashcam footage of the conflict",
                     "Video-derived trajectories replace report estimates (tier 0 -> 1)."),
                 2: ("av_logs", "Obtain the AV's data logs (decision log, perception and control inputs)",
                     "Telemetry-grade speeds and gap, plus verified engagement and AV braking (tier -> 2).")}


def information_requests(bundle: dict, sim: dict | None, gbp: dict, projection: dict | None,
                         meta: dict | None = None) -> list[dict]:
    """Ranked list of what the insurer should obtain next and why.

    rank: 1) items that block pricing, 2) by `impact` = expected narrowing / swing in P(avoid) (0..1), with
    fixed DESIGN weights for legal gates that do not move P(avoid) but hold the decision.
    """
    meta = meta or {}
    reqs: list[dict] = []

    def add(id_, title, why, effect, impact, blocks=False, category="evidence"):
        reqs.append({"id": id_, "title": title, "why": why, "expected_effect": effect,
                     "impact": round(float(impact), 4), "blocks_pricing": blocks, "category": category})

    ext, per, veh = bundle.get("external") or {}, bundle.get("perception") or {}, bundle.get("vehicle") or {}
    out = bundle.get("outcome") or {}

    # Tier upgrades, with projected CI narrowing.
    if projection and projection.get("band_now"):
        now = projection["band_now"]
        for t, p in sorted(projection["next"].items()):
            if p["band"] is None:
                continue
            id_, title, why = TIER_EVIDENCE[int(t)]
            new = p["band"]
            narrowing = (now[1] - now[0]) - (new[1] - new[0])
            verb = "narrows" if narrowing > 0.005 else "does not narrow" if narrowing >= -0.005 else "widens"
            pins = projection.get("pinned_at_mid_range") or []
            cond = "the new evidence confirms today's central estimates"
            if pins:
                cond += " and finds each unknown fact at the middle of its current range (" + "; ".join(pins) + ")"
            add(id_, title, why, f"P(avoid) range {verb} from {_rng(now)} to {_rng(new)} (projection: assumes {cond})",
                max(0.0, narrowing), category="evidence_tier")

    # Facts that most move the answer (sensitivity), and prior-tagged facts.
    seen = set()
    for row in (sim or {}).get("sensitivity") or []:
        if row["source"] == "reported" or row["swing"] <= 0:
            continue
        p = row["param"]
        seen.add(p)
        add(f"fact:{p}", f"Establish the {PARAM_LABEL.get(p, p)}",
            f"Currently a {row['source']} range {row['lo']:.3g}-{row['hi']:.3g}; source: {PARAM_SOURCE_HINT.get(p, 'evidence')}.",
            f"Pinning it moves P(avoid) by up to {_pct(row['swing'])}", row["swing"], category="fact")
    for p, r in ((sim or {}).get("ranges") or {}).items():
        if r["source"] == "prior" and p not in seen and p in PARAM_LABEL:
            add(f"fact:{p}", f"Establish the {PARAM_LABEL[p]}",
                f"No evidence yet: generic prior {r['lo']:.3g}-{r['hi']:.3g}; source: {PARAM_SOURCE_HINT.get(p, 'evidence')}.",
                "No measurable effect on P(avoid) at the current ranges; lowers data sufficiency", 0.0, category="fact")

    if sim and sim.get("reproduction") and not sim["reproduction"].get("reproduced_flag"):
        rr = sim["reproduction"]
        add("reproduction", "Reconcile the reported crash with the reconstruction",
            f"The sim reproduces the reported outcome in {_pct(rr['rate'])} of runs "
            f"(mismatches: {', '.join(rr.get('mismatches', {})) or 'none listed'}). Finance holds 'pursue' until it does.",
            "Lifts the reproduction gate on the recovery decision", 0.5, category="gate")
    tl = (sim or {}).get("timeline_check") or {}
    if tl.get("consistent") is False:
        add("timeline", "Resolve the timeline contradiction", tl.get("reason") or "timeline inconsistent",
            "Removes a contradiction the defence would exploit", 0.45, category="gate")

    # Gates in their engine that do not move P(avoid).
    if not bundle.get("conflict"):
        add("conflict", "Reconstruct the conflict (speeds, gap, crash type)",
            "No reconstructed conflict: the careful-driver test cannot run.", "Enables P(avoid) and pricing", 1.0, True, "gate")
    if "crash_type" in (meta.get("unknowns") or []):
        add("crash_type", "Establish the crash type (cut-in, lead vehicle braking, stationary hazard)",
            "UN R157 driver models cover cut-in, cut-out and lead-vehicle deceleration; unknown type runs a generic hazard.",
            "Selects the right scenario model", 0.4, category="fact")
    if veh.get("odd_inside") is None:
        add("odd", "Confirm whether the AV was inside its operational design domain (ODD)",
            "Unknown ODD holds 'pursue'; outside ODD may move the recovery target to the operator.",
            "Lifts the ODD gate", 0.35, category="gate")
    if meta.get("engagement_override") in ("engaged_alleged", "unknown"):
        add("engagement", "Verify self-driving engagement from the vehicle's data storage (DSSAD)",
            "Engagement is reported, not verified. Finance holds 'pursue' until verified.",
            "Lifts the engagement gate", 0.35, category="gate")
    if out.get("third_party_share") is None and out.get("paid_claim_gbp") is None:
        add("contributory_negligence", "Assess the injured party's contributory negligence",
            "Not assessed (AEVA s.3(1)): finance applies 0-100%, which widens the GBP range and holds 'pursue'.",
            "Narrows the AV share and the GBP range", 0.3, category="gate")
    if not veh.get("software_verified"):
        add("software", "Confirm no unauthorised software change or missed safety-critical update",
            "Required before proceedings (AEVA s.4).", "Lifts the s.4 caveat", 0.15, category="gate")
    if not (bundle.get("integrity") or {}).get("hashes_present", True):
        add("integrity", "Secure tamper-evident copies of the evidence (hashes, chain of custody)",
            "The engine will not price evidence that is not tamper-evident.", "Allows pricing", 1.0, True, "gate")
    if out.get("injury_severity", "Unknown") == "Unknown" and out.get("paid_claim_gbp") is None:
        add("claim_value", "Record the injury severity or the amount paid",
            "No sourced claim value: the engine cannot produce a GBP figure.", "Allows pricing", 1.0, True, "gate")
    if not ext.get("police_report"):
        add("police_report", "Obtain the police report", "Independent account of the scene and parties.",
            "Corroborates speeds, positions and fault", 0.1)
    if not ext.get("witnesses"):
        add("witnesses", "Identify witnesses", "Independent corroboration of the conflict.",
            "Corroborates the reconstruction", 0.05)

    # Anything else the engine said blocks pricing.
    if gbp.get("decision") == "cannot_price" and gbp.get("reason") and not any(r["blocks_pricing"] for r in reqs):
        add("pricing", "Resolve what blocks pricing", gbp["reason"], "Allows pricing", 1.0, True, "gate")

    reqs.sort(key=lambda r: (not r["blocks_pricing"], -r["impact"]))
    for i, r in enumerate(reqs, 1):
        r["rank"] = i
    return reqs


# ------------------------------------------------------------------ viewer JSON

def viewer_json(claim_id: str, sim: dict | None, title: str) -> dict | None:
    if not sim or not sim.get("replays"):
        return None
    runs = {}
    for k, r in sim["replays"].items():
        r = copy.deepcopy(r)
        if r["result"].get("collided"):
            r["result"].setdefault("other_actor", "other")
        runs[k] = r
    t = runs["av"]["t"]
    return {
        "scenario": {"duration": t[-1] if t else 10.0, "dt": (t[1] - t[0]) if len(t) > 1 else 0.04,
                     "ego_geometry": {"length": 4.6, "width": 1.9},
                     "actors": [{"name": "other", "length": 4.6, "width": 1.9}],
                     "id": claim_id, "title": title, "crash_type": sim.get("scenario_type"),
                     "label": "median sample; " + "; ".join(sorted({d["model"] for d in sim["drivers"].values()})),
                     "notes": "Every uncertain range at its median. AV panel replays the reported AV braking."},
        "runs": runs,
        "p_avoid": {k: {"p": d["p_avoid"], "ci90": d["ci90"], "n": d["n_samples"]} for k, d in sim["drivers"].items()},
    }


# ------------------------------------------------------------------ one claim end to end

DECISION_LABEL = {"pursue": "Pursue", "dont_pursue": "Don't pursue", "pull_logs_first": "Get more evidence",
                  "not_av_recovery": "Don't pursue", "cannot_price": "Cannot price",
                  "get_more_evidence": "Get more evidence"}


def assess_claim(bundle: dict, meta: dict | None = None, map_fn=None, seed: int = 0, debate_client=None) -> dict:
    meta = meta or {}
    tier = meta.get("tier")
    tier_used = tier if tier is not None else evidence_tier(bundle)
    sim, sim_error, projection = None, None, None
    if bundle.get("conflict"):
        with ThreadPoolExecutor(3) as ex:
            f_sim = ex.submit(run_sim, bundle, tier, map_fn=map_fn, seed=seed)
            pb = project_bundle(bundle)
            f_next = {t: ex.submit(_band_at, pb, t, map_fn, seed) for t in range(tier_used + 1, 3)}
            try:
                sim = f_sim.result()
            except (ValueError, KeyError) as e:
                sim_error = f"simulation could not run: {e}"
            nxt = {}
            for t, f in f_next.items():
                try:
                    nxt[t] = f.result()
                except (ValueError, KeyError):
                    pass
        if sim and nxt:
            projection = {"tier": tier_used, "band_now": sim.get("evidence_band"), "next": nxt,
                          "pinned_at_mid_range": projection_pins(bundle)}
    gbp = assess_gbp(bundle, sim, meta.get("engagement_override")) if not sim_error else {
        "available": insurance_available(), "decision": "cannot_price", "reason": sim_error, "notes": []}

    decision = gbp["decision"]
    suff = (sim or {}).get("data_sufficiency", {}).get("score")
    gated = suff is not None and suff < SUFFICIENCY_MIN and decision in ("pursue", "dont_pursue")
    final = "get_more_evidence" if gated else decision
    cid = bundle.get("case_id") or claim_id_for(bundle)
    replay = sim.pop("replays", None) if sim else None
    if sim is not None:
        sim["replays"] = replay
    view = viewer_json(cid, sim, title=f"{cid}: {(sim or {}).get('scenario_type', '')}".strip(": "))
    if sim is not None:
        sim.pop("replays", None)
    rec = (gbp.get("recovery") or {})
    return _plain({
        "claim_id": cid,
        "synthetic": bundle.get("synthetic"),
        "source": "form" if bundle.get("intake") else "cctv" if bundle.get("cctv_evidence") else "bundle",
        "cctv": cctv_summary(bundle),
        "crash_type": (bundle.get("conflict") or {}).get("crash_type")
                      or KIND_TO_CRASH_TYPE.get((bundle.get("conflict") or {}).get("kind", "constant_hazard")) if bundle.get("conflict") else None,
        "evidence_tier": tier_used,
        "sim": sim, "sim_error": sim_error,
        "timeline_check": (sim or {}).get("timeline_check"),
        "data_sufficiency": (sim or {}).get("data_sufficiency"),
        "sufficiency_gate": {"threshold": SUFFICIENCY_MIN, "score": suff, "applied": gated},
        "projection": projection,
        "gbp": gbp,
        "decision": final, "decision_label": DECISION_LABEL.get(final, final),
        "engine_decision": decision,
        "expected_recovery_gbp": rec.get("expected_recovery"),
        "information_requests": information_requests(bundle, sim, gbp, projection, meta),
        "debate": run_debate_for(bundle, sim, meta, debate_client) if gbp.get("recovery") else
                  {"available": False, "reason": "claim not priced, nothing to debate"},
        "unknowns": meta.get("unknowns", []),
        "assumptions": ((sim or {}).get("assumptions") or []) + [
            "Unknown intake fields use labelled design priors (viz/api/claims.py)",
            "Reported lead-vehicle deceleration and cut-in time get tiered half-widths (design assumption)",
            f"Data sufficiency below {SUFFICIENCY_MIN} -> 'get more evidence' (design assumption)",
            "P(avoid) CI covers Monte Carlo sampling only; A/B models bracket driver-model uncertainty",
            "Sim is 2D kinematic, straight-line braking; sim-to-real gap not quantified",
        ],
        "disclaimer": DISCLAIMER,
        "viewer": view,
    })


def summary_row(r: dict) -> dict:
    ds = (r.get("sim") or {}).get("drivers") or {}
    return {"claim_id": r["claim_id"], "crash_type": r.get("crash_type"), "evidence_tier": r.get("evidence_tier"),
            "synthetic": r.get("synthetic"), "source": r.get("source"),
            "p_avoid": {k: {"p": d["p_avoid"], "ci90": d["ci90"]} for k, d in ds.items()},
            "evidence_band": (r.get("sim") or {}).get("evidence_band"),
            "expected_recovery_gbp": r.get("expected_recovery_gbp"),
            "decision": r["decision"], "decision_label": r["decision_label"],
            "reason": (r.get("gbp") or {}).get("reason")}
