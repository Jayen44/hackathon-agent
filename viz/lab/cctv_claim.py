"""CCTV run + insurer claim file -> full crash bundle (insurance schema 0.1) for the claims API.

Pure functions (no Modal, no FastAPI, no network) so they are unit-testable (tests/test_cctv_to_claim.py).

The measured part (conflict, conflict_ranges, outcome, t_crash) comes from sim/video via the Sim Lab CCTV page.
The claim-file part is what an insurer knows from its own file: AV engaged, within ODD, injury severity, amount
paid, injured party contributory negligence, software verified. Every claim-file field may be 'unknown'; nothing
is filled in for the insurer. CCTV is evidence tier 1: there is no AV decision log, so engagement stays
'alleged' (never 'verified') until the AV logs are obtained, which the claims API then asks for (tier-2 upgrade).

Uploaded videos, claim-file fields and the return URL are UNTRUSTED input: ids are checked against fixed
patterns, numbers are range-checked, enums are whitelisted, and the return URL must be one of our dashboards.
"""
from __future__ import annotations

import math
import re
from urllib.parse import urlsplit

VID_RE = re.compile(r"^[0-9a-f]{32}$")
RID_RE = re.compile(r"^[0-9a-f]{12}$")
CLAIM_REF_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")

SEVERITIES = ("Fatal", "Serious", "Slight", "Damage only", "Unknown")   # same as the dashboard intake form
TRI = ("yes", "no", "unknown")

# Their conflict.kind for our measured crash types (insurance/bundle.py KINDS).
CRASH_TYPE_TO_KIND = {"cut_in": "cut_in", "lead_vehicle_decel": "lead_braking"}
# DESIGN ASSUMPTION: no friction measured from video; same default as insurance/bundle.py Conflict.friction_mu.
FRICTION_MU = 0.7
# DESIGN ASSUMPTION (same as the dashboard intake form): the mode event that records "engaged" is placed this
# long before the crash, so the engine's control-state step sees one state throughout the conflict.
MODE_EVENT_LEAD_S = 60.0

DASHBOARD_ORIGINS = re.compile(r"^(https://accel-claims-dashboard[a-z0-9-]*\.vercel\.app|http://localhost:\d+|"
                               r"http://127\.0\.0\.1:\d+)$")
DEFAULT_DASHBOARD = "https://accel-claims-dashboard.vercel.app"


class ClaimFileError(ValueError):
    """A claim-file field is malformed."""


def _tri(x) -> str:
    if x is True:
        return "yes"
    if x is False:
        return "no"
    s = str(x or "unknown").strip().lower()
    return s if s in TRI else "unknown"


def _num(x, name: str, lo: float = 0.0, hi: float = math.inf) -> float | None:
    if x is None or (isinstance(x, str) and x.strip().lower() in ("", "unknown")):
        return None
    if isinstance(x, bool):
        raise ClaimFileError(f"{name}: expected a number")
    try:
        v = float(str(x).replace(",", "").replace("£", "").strip()) if isinstance(x, str) else float(x)
    except (TypeError, ValueError):
        raise ClaimFileError(f"{name}: expected a number, got {x!r}")
    if not math.isfinite(v) or not lo <= v <= hi:
        raise ClaimFileError(f"{name}: must be between {lo:g} and {hi:g}")
    return v


def parse_claim_file(f: dict | None) -> dict:
    """Normalise the insurer's claim-file fields. Unknown stays unknown."""
    f = f or {}
    sev = f.get("injury_severity") or "Unknown"
    if sev not in SEVERITIES:
        raise ClaimFileError(f"injury_severity must be one of {SEVERITIES}")
    lo = _num(f.get("cn_low_pct"), "contributory negligence low %", 0, 100)
    hi = _num(f.get("cn_high_pct"), "contributory negligence high %", 0, 100)
    if (lo is None) != (hi is None):
        raise ClaimFileError("contributory negligence: give both ends of the range, or neither")
    cn = None if lo is None else sorted((lo, hi))
    ref = (f.get("claim_ref") or "").strip() or None
    if ref is not None and not CLAIM_REF_RE.match(ref):
        raise ClaimFileError("claim reference: 1-64 letters, digits, _ . -")
    sw = _tri(f.get("software_verified"))
    return {
        "claim_ref": ref,
        "av_engaged": _tri(f.get("av_engaged")),
        "within_odd": _tri(f.get("within_odd")),
        "injury_severity": sev,
        "paid_gbp": _num(f.get("paid_gbp"), "amount paid (GBP)", 0, 1e9),
        "cn_pct": cn,
        # Only a positive confirmation counts; anything else is 'unknown' (insurance/bridge.software_status).
        "software_verified": "yes" if sw == "yes" else "unknown",
    }


def claim_id_for_run(video_id: str, run_id: str) -> str:
    """Deterministic claim id for one CCTV run: resending the same run updates the same claim."""
    if not VID_RE.match(video_id or "") or not RID_RE.match(run_id or ""):
        raise ClaimFileError("bad video or run id")
    return f"CCTV-{video_id[:8]}-{run_id[:6]}"


def safe_return_url(url: str | None) -> str:
    """Only our dashboards (prod / preview / localhost). Anything else falls back to the prod dashboard."""
    if not url:
        return DEFAULT_DASHBOARD
    try:
        p = urlsplit(url)
    except ValueError:
        return DEFAULT_DASHBOARD
    origin = f"{p.scheme}://{p.netloc}"
    return origin if DASHBOARD_ORIGINS.match(origin) else DEFAULT_DASHBOARD


def _mid(r: dict | None) -> float | None:
    if not r:
        return None
    return (float(r["lo"]) + float(r["hi"])) / 2


def _pts(xs, n: int = 200) -> list[list[float]]:
    """At most n [u, v] pixel points, rounded (keeps the request small)."""
    xs = list(xs or [])
    step = max(1, math.ceil(len(xs) / n))
    return [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in xs[::step]]


def build_claim_bundle(cctv_bundle: dict, run: dict, video_meta: dict, claim_file: dict, video_id: str,
                       run_id: str, lab_base: str = "") -> dict:
    """Measured CCTV bundle + run summary + insurer claim file -> full schema 0.1 bundle for POST /api/assess.

    cctv_bundle: the bundle sim/video wrote for this run (conflict, conflict_ranges, outcome, t_crash).
    run: what the Sim Lab saved with the run (measured speeds with sigma, calibration clicks, AV/other track
         ids and pixel paths, frame size). Display-only: it never changes a number the engine uses.
    video_meta: the upload's meta.json (sha256, synthetic).
    """
    cf = parse_claim_file(claim_file)
    cid = cf["claim_ref"] or claim_id_for_run(video_id, run_id)
    c = dict(cctv_bundle.get("conflict") or {})
    if not c:
        raise ClaimFileError("the CCTV run has no conflict")
    cr = {k: dict(v) for k, v in (cctv_bundle.get("conflict_ranges") or {}).items()}
    ctype = c.get("crash_type")
    kind = CRASH_TYPE_TO_KIND.get(ctype, "constant_hazard")
    conflict = {
        "hazard_id": c.get("hazard_id", "other_vehicle"), "t_start": float(c["t_start"]),
        "ego_speed_mps": float(c["ego_speed_mps"]), "gap_m": float(c["gap_m"]),
        "hazard_speed_mps": float(c.get("hazard_speed_mps", 0.0)), "friction_mu": FRICTION_MU,
        "crash_type": ctype or "other", "kind": kind,
    }
    if kind == "lead_braking":
        d = _mid(cr.get("other_decel"))
        if d and d > 0:
            conflict["hazard_decel_mps2"] = round(d, 3)
        else:   # no braking measured: the engine's lead_braking needs a decel > 0, so it is a constant-speed lead
            conflict["kind"] = "constant_hazard"
    if kind == "cut_in":
        s, dur = _mid(cr.get("cut_in_start")), _mid(cr.get("cut_in_duration"))
        if dur is not None:
            conflict["t_in_path_s"] = round((s or 0.0) + dur, 3)

    o = cctv_bundle.get("outcome") or {}
    collided = bool(o.get("collided"))
    measured = run.get("measured") or {}
    t_crash = cctv_bundle.get("t_crash")
    if t_crash is None:   # no contact: the closest approach is the reference time
        t_crash = measured.get("t_closest", conflict["t_start"])
    t_crash = float(t_crash)

    engaged = cf["av_engaged"]
    sha = video_meta.get("sha256")
    cn = cf["cn_pct"]
    bundle = {
        "schema_version": "0.1",
        "case_id": cid,
        "synthetic": bool(video_meta.get("synthetic", cctv_bundle.get("synthetic", False))),
        "t_crash": t_crash,
        "jurisdiction": "UK",
        "source": "CCTV video measured by the Sim Lab (sim/video), claim file from the insurer",
        "vehicle": {
            "software_version": "unknown", "approved_software": [], "occupant": "none",
            # 'unknown' is modelled as automated for the engine's control-state step (same as the intake form);
            # finance gets the engagement status from the claims API meta, never 'verified' at tier 1.
            "mode_events": [{"t": t_crash - MODE_EVENT_LEAD_S, "mode": "manual" if engaged == "no" else "automated"}],
            "odd_inside": {"yes": True, "no": False, "unknown": None}[cf["within_odd"]],
            "software_verified": cf["software_verified"] == "yes",
        },
        # Tier 1: video only. No AV decision log, perception or control inputs.
        "perception": {"sensors": [], "objects": [], "decision_log_present": False},
        "external": {"cctv": [video_id], "witnesses": 0, "police_report": False},
        "integrity": {"hashes_present": bool(sha), "chain_of_custody": False, "video_sha256": sha},
        "conflict": conflict,
        "conflict_ranges": cr,
        "outcome": {
            "collided": collided,
            "impact_speed_mps": o.get("impact_speed_mps") if collided else None,
            "injury_severity": cf["injury_severity"],
            "paid_claim_gbp": cf["paid_gbp"],
            "third_party_share": None if cn is None else [cn[0] / 100, cn[1] / 100],
        },
        "cctv_evidence": {
            "video_id": video_id, "run_id": run_id, "sha256": sha, "lab_base": lab_base,
            "tier": 1,
            "measured": {k: measured.get(k) for k in ("ego_speed_mps", "other_speed_mps", "gap_m",
                                                      "ego_speed_before_impact_mps", "min_gap_m", "av_braking")
                         if measured.get(k) is not None},
            "ego_ids": [int(i) for i in run.get("ego_ids") or []],
            "other_ids": [int(i) for i in run.get("other_ids") or []],
            "frame": run.get("frame"),
            "calibration": {"mode": (run.get("calibration_input") or {}).get("mode"),
                            "img_pts": _pts((run.get("calibration_input") or {}).get("img_pts"), 50),
                            "reprojection_rms_m": (run.get("calibration") or {}).get("reprojection_rms_m")},
            "paths": {"av": _pts((run.get("paths") or {}).get("av")),
                      "other": _pts((run.get("paths") or {}).get("other"))},
            "claim_file": cf,
        },
    }
    return bundle
