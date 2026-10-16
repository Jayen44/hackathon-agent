"""viz/lab/cctv_claim.py: CCTV run + insurer claim file -> full schema 0.1 bundle for the claims API.

Bundles here come from the real measurement code (sim/video.trajectories.analyse) on synthetic camera tracks.
The insurance engine (branch origin/insurance) is only used when importable (ACCEL_INSURANCE_DIR), as in
tests/test_claims_api.py.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

from montecarlo.evidence import evidence_tier
from sim.video.calibrate import calibrate_from_request, project, rectangle_world_points
from sim.video.trajectories import Track, analyse
from viz.api import claims
from viz.lab.cctv_claim import (DEFAULT_DASHBOARD, ClaimFileError, build_claim_bundle, claim_id_for_run,
                                parse_claim_file, safe_return_url)

if os.environ.get("ACCEL_INSURANCE_DIR"):
    sys.path.insert(0, os.environ["ACCEL_INSURANCE_DIR"])

FPS = 25.0
VID = "ce5730a6facc4e34885a1a4f5c405fbc"
RID = "0123456789ab"
SHA = "a" * 64


def _cam_H(height=10.0, pitch_deg=20.0, back=15.0, f=1400.0, y_cam=1.75):
    p = math.radians(pitch_deg)
    right = np.array([0.0, -1.0, 0.0])
    fwd = np.array([math.cos(p), 0.0, -math.sin(p)])
    down = np.cross(fwd, right)
    R = np.vstack([right, down, fwd])
    C = np.array([-back, y_cam, height])
    K = np.array([[f, 0, 960.0], [0, f, 540.0], [0, 0, 1.0]])
    H = K @ np.c_[R[:, 0], R[:, 1], -R @ C]
    return H / H[2, 2]


H = _cam_H()
RECT_PX = project(H, rectangle_world_points(20.0, 3.5) + np.array([5.0, 0.0]))


def _track(tid, xy, seed):
    px = project(H, xy) + np.random.default_rng(seed).normal(0, 1.0, (len(xy), 2))
    boxes = np.c_[px[:, 0] - 40, px[:, 1] - 60, px[:, 0] + 40, px[:, 1]]
    return Track(tid, "car", np.arange(len(xy)), boxes)


def _lead_brake_analysis(collided=None):
    t = np.arange(0, 4.0, 1 / FPS)
    ego = np.c_[5 + 15 * t, np.zeros_like(t)]
    tt = np.clip(t - 1.0, 0, 10.0 / 6.0)
    other = np.c_[5 + 24.6 + 10 * np.minimum(t, 1.0) + 10 * tt - 3.0 * tt ** 2, np.zeros_like(t)]
    calib_req = {"mode": "rectangle", "img_pts": RECT_PX.tolist(), "length_m": 20.0, "width_m": 3.5,
                 "click_sigma_px": 1.0}
    a = analyse({1: _track(1, ego, 1), 2: _track(2, other, 2)}, calibrate_from_request(calib_req), FPS, ego_id=1,
                lane_width_m=3.5, case_id=f"cctv-{VID[:8]}", video_sha256=SHA, synthetic=True, collided=collided)
    run = {"measured": a["measured"], "calibration": a["calibration"],
           "calibration_input": {"mode": "rectangle", "img_pts": calib_req["img_pts"]},
           "ego_ids": a["ego_ids"], "other_ids": a["other_ids"], "frame": {"width": 1920, "height": 1080},
           "paths": {"av": project(H, ego)[::5].tolist(), "other": project(H, other)[::5].tolist()}}
    return a, run


DEMO_FILE = {"av_engaged": "yes", "within_odd": "yes", "injury_severity": "Serious", "paid_gbp": "60000",
             "cn_low_pct": "0", "cn_high_pct": "10", "software_verified": "unknown"}


@pytest.fixture(scope="module")
def lead():
    return _lead_brake_analysis()


def test_full_bundle_from_cctv_and_claim_file(lead):
    a, run = lead
    b = build_claim_bundle(a["bundle"], run, {"sha256": SHA, "synthetic": True}, DEMO_FILE, VID, RID, "https://lab")
    assert b["schema_version"] == "0.1" and "schema" not in b
    assert b["case_id"] == claim_id_for_run(VID, RID) == f"CCTV-{VID[:8]}-{RID[:6]}"
    # measured part is carried over unchanged
    assert b["conflict_ranges"] == a["bundle"]["conflict_ranges"]
    assert b["conflict"]["ego_speed_mps"] == a["bundle"]["conflict"]["ego_speed_mps"]
    assert b["conflict"]["crash_type"] == "lead_vehicle_decel" and b["conflict"]["kind"] == "lead_braking"
    assert b["conflict"]["hazard_decel_mps2"] > 0
    assert b["t_crash"] == a["bundle"]["t_crash"]
    # claim file
    v = b["vehicle"]
    assert v["mode_events"] == [{"t": b["t_crash"] - 60.0, "mode": "automated"}]
    assert v["odd_inside"] is True and v["software_verified"] is False
    o = b["outcome"]
    assert o["collided"] is True and o["injury_severity"] == "Serious" and o["paid_claim_gbp"] == 60000.0
    assert o["third_party_share"] == [0.0, 0.1]
    # tier 1: video, no AV logs; integrity from the video hash
    assert b["perception"]["decision_log_present"] is False
    assert b["external"]["cctv"] == [VID]
    assert b["integrity"] == {"hashes_present": True, "chain_of_custody": False, "video_sha256": SHA}
    assert evidence_tier(b) == 1
    ce = b["cctv_evidence"]
    assert ce["video_id"] == VID and ce["run_id"] == RID and ce["sha256"] == SHA
    assert ce["measured"]["ego_speed_mps"]["sd"] > 0 and len(ce["calibration"]["img_pts"]) == 4
    assert ce["paths"]["av"] and ce["paths"]["other"]


def test_unknowns_stay_unknown(lead):
    a, run = lead
    b = build_claim_bundle(a["bundle"], run, {"sha256": None}, {}, VID, RID)
    v, o = b["vehicle"], b["outcome"]
    assert v["odd_inside"] is None and v["software_verified"] is False
    assert v["mode_events"][0]["mode"] == "automated"   # modelled as automated; finance gets 'unknown' via meta
    assert o["injury_severity"] == "Unknown" and o["paid_claim_gbp"] is None and o["third_party_share"] is None
    assert b["integrity"]["hashes_present"] is False
    meta = claims.cctv_meta(b)
    assert meta["tier"] == 1 and meta["engagement_override"] == "unknown"
    assert {"av_engaged", "within_odd", "injury_severity", "claim_paid_gbp", "contributory_negligence"} <= set(meta["unknowns"])


def test_engagement_never_verified_without_logs(lead):
    a, run = lead
    yes = build_claim_bundle(a["bundle"], run, {"sha256": SHA}, DEMO_FILE, VID, RID)
    assert claims.cctv_meta(yes)["engagement_override"] == "engaged_alleged"
    no = build_claim_bundle(a["bundle"], run, {"sha256": SHA}, {**DEMO_FILE, "av_engaged": "no"}, VID, RID)
    assert no["vehicle"]["mode_events"][0]["mode"] == "manual"
    assert claims.cctv_meta(no)["engagement_override"] == "not_engaged"


def test_no_contact_uses_closest_approach_time():
    a, run = _lead_brake_analysis(collided=False)
    b = build_claim_bundle(a["bundle"], run, {"sha256": SHA}, DEMO_FILE, VID, RID)
    assert b["outcome"]["collided"] is False and b["outcome"]["impact_speed_mps"] is None
    assert b["t_crash"] == pytest.approx(a["measured"]["t_closest"])


def test_cut_in_time_in_path_from_measured_ranges(lead):
    a, run = lead
    cb = {**a["bundle"], "conflict": {**a["bundle"]["conflict"], "crash_type": "cut_in"},
          "conflict_ranges": {"cut_in_start": {"lo": 0.2, "hi": 0.4, "source": "reported"},
                              "cut_in_duration": {"lo": 1.5, "hi": 2.5, "source": "reported"}}}
    b = build_claim_bundle(cb, run, {"sha256": SHA}, DEMO_FILE, VID, RID)
    assert b["conflict"]["kind"] == "cut_in" and b["conflict"]["t_in_path_s"] == pytest.approx(2.3)


def test_lead_without_measured_braking_is_constant_speed_lead(lead):
    a, run = lead
    cb = {**a["bundle"], "conflict_ranges": {**a["bundle"]["conflict_ranges"],
                                             "other_decel": {"lo": 0.0, "hi": 0.0, "source": "reported"}}}
    b = build_claim_bundle(cb, run, {"sha256": SHA}, DEMO_FILE, VID, RID)
    assert b["conflict"]["kind"] == "constant_hazard" and "hazard_decel_mps2" not in b["conflict"]
    assert b["conflict"]["crash_type"] == "lead_vehicle_decel"


@pytest.mark.parametrize("bad", [{"injury_severity": "Minor"}, {"paid_gbp": "-5"}, {"paid_gbp": "lots"},
                                 {"cn_low_pct": "0"}, {"cn_low_pct": "0", "cn_high_pct": "150"},
                                 {"claim_ref": "../../etc"}, {"paid_gbp": True}])
def test_bad_claim_file_rejected(bad):
    with pytest.raises(ClaimFileError):
        parse_claim_file(bad)


def test_claim_file_normalisation():
    cf = parse_claim_file({"paid_gbp": "£60,000", "cn_low_pct": 10, "cn_high_pct": 0, "av_engaged": "YES",
                           "software_verified": "no", "within_odd": "maybe"})
    assert cf["paid_gbp"] == 60000.0 and cf["cn_pct"] == [0.0, 10.0] and cf["av_engaged"] == "yes"
    assert cf["software_verified"] == "unknown"   # only a positive confirmation counts
    assert cf["within_odd"] == "unknown"


def test_bad_ids_rejected(lead):
    a, run = lead
    with pytest.raises(ClaimFileError):
        build_claim_bundle(a["bundle"], run, {}, {}, "../x", RID)
    with pytest.raises(ClaimFileError):
        claim_id_for_run(VID, "zz")


def test_return_url_only_our_dashboards():
    assert safe_return_url("https://accel-claims-dashboard.vercel.app/new") == DEFAULT_DASHBOARD
    assert safe_return_url("https://accel-claims-dashboard-git-x-team.vercel.app/") == \
        "https://accel-claims-dashboard-git-x-team.vercel.app"
    assert safe_return_url("http://localhost:3000/claims") == "http://localhost:3000"
    for evil in ("https://evil.example", "javascript:alert(1)", "https://accel-claims-dashboard.vercel.app.evil.io",
                 "//evil.example", None, ""):
        assert safe_return_url(evil) == DEFAULT_DASHBOARD


def test_cctv_summary_is_sanitised(lead):
    a, run = lead
    b = build_claim_bundle(a["bundle"], run, {"sha256": SHA}, DEMO_FILE, VID, RID)
    s = claims.cctv_summary(b)
    assert s["video_id"] == VID and s["run_id"] == RID and s["tier"] == 1 and s["sha256"] == SHA
    assert s["measured"]["ego_speed_mps"]["sd"] > 0 and s["paths"]["av"]
    evil = {**b, "cctv_evidence": {**b["cctv_evidence"], "video_id": "<script>"}}
    assert claims.cctv_summary(evil) is None
    junk = {**b, "cctv_evidence": {**b["cctv_evidence"], "paths": {"av": [["x", 1], [1, 2, 3], [1.0, 2.0]]}}}
    assert claims.cctv_summary(junk)["paths"]["av"] == [[1.0, 2.0]]


@pytest.mark.skipif(not claims.insurance_available(), reason="insurance/finance not vendored (set ACCEL_INSURANCE_DIR)")
def test_engine_accepts_bundle(lead):
    from insurance.bundle import load_bundle
    a, run = lead
    b = load_bundle(build_claim_bundle(a["bundle"], run, {"sha256": SHA}, DEMO_FILE, VID, RID))
    assert b.conflict.kind == "lead_braking" and b.outcome.third_party_share == (0.0, 0.1)
    assert b.vehicle.odd_inside is True and b.integrity.hashes_present


# ------------------------------------------------------------------ intake form + CCTV (claims API merge_cctv)

MPH = claims.MPH


def _form_from_measured(a, **kw):
    m, c = a["measured"], a["bundle"]["conflict"]
    f = {"claim_ref": "T-CCTV", "location_type": "urban", "av_engaged": "yes", "within_odd": "yes",
         "crash_type": c["crash_type"], "ego_speed_mph": round(m["ego_speed_mps"]["value"] / MPH, 1),
         "other_speed_mph": round(m["other_speed_mps"]["value"] / MPH, 1), "gap_m": round(m["gap_m"]["value"], 1),
         "injury_severity": "Serious", "claim_paid_gbp": 60000, "injured_party_share_low_pct": 0,
         "injured_party_share_high_pct": 10, "evidence": {"cctv": True}}
    f.update(kw)
    return f


def _merge(a, run, form):
    b, meta = claims.form_to_bundle(form)
    return claims.merge_cctv(b, meta, form, a["bundle"], run, VID, RID)


def test_merge_uses_measured_ranges_when_form_matches(lead):
    a, run = lead
    b, meta = _merge(a, run, _form_from_measured(a))
    cr = b["conflict_ranges"]
    for k in ("ego_speed", "gap", "other_speed", "other_decel", "other_brake_time"):
        assert cr[k] == {**a["bundle"]["conflict_ranges"][k], "source": "reported"}
    assert b["external"]["cctv"] == [VID]
    assert b["integrity"]["hashes_present"] is True and b["integrity"]["video_sha256"] == SHA
    assert meta["tier"] == 1 and meta["engagement_override"] == "engaged_alleged"
    assert evidence_tier(b) == 1
    s = claims.cctv_summary(b)
    assert s["video_id"] == VID and "ego_speed" in s["ranges_used"] and s["overridden_by_insurer"] == []


def test_merge_insurer_override_wins(lead):
    a, run = lead
    b, _ = _merge(a, run, _form_from_measured(a, ego_speed_mph=80))
    assert "ego_speed" not in b["conflict_ranges"]
    assert b["conflict"]["ego_speed_mps"] == pytest.approx(80 * MPH)
    assert b["cctv_evidence"]["overridden_by_insurer"] == ["ego_speed"]


def test_merge_unknown_form_field_filled_from_cctv(lead):
    a, run = lead
    b, meta = _merge(a, run, _form_from_measured(a, gap_m=None))
    assert b["conflict_ranges"]["gap"]["source"] == "reported" and "gap_m" not in meta["unknowns"]


def test_merge_drops_ranges_of_other_crash_type(lead):
    a, run = lead
    b, _ = _merge(a, run, _form_from_measured(a, crash_type="cut_in", cut_in_time_s=1.5))
    assert "other_decel" not in b["conflict_ranges"] and "other_brake_time" not in b["conflict_ranges"]


def test_merge_rejects_bad_ids(lead):
    a, run = lead
    b, meta = claims.form_to_bundle(_form_from_measured(a))
    with pytest.raises(ValueError):
        claims.merge_cctv(b, meta, {}, a["bundle"], run, "../etc", RID)


@pytest.mark.skipif(not claims.insurance_available(), reason="insurance/finance not vendored (set ACCEL_INSURANCE_DIR)")
def test_engine_accepts_merged_bundle(lead):
    from insurance.bundle import load_bundle
    a, run = lead
    b, _ = _merge(a, run, _form_from_measured(a))
    lb = load_bundle(b)
    assert lb.external.cctv == [VID] and lb.integrity.hashes_present
