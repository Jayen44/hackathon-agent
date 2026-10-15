import copy
import json
from pathlib import Path

import pytest

from insurance.bundle import BundleError, load_bundle, load_bundle_file
from insurance.counterfactual import KinematicEstimator
from insurance.engine import Policy, decide

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"


def verdict(name: str, **kw):
    return decide(load_bundle_file(EX / f"{name}.json"), **kw)


def raw(name: str) -> dict:
    return json.loads((EX / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,liable,confidence", [
    ("01_av_late_detection", "TECH_COMPANY", "HIGH"),
    ("02_human_driving_manual", "HUMAN_DRIVER", "HIGH"),
    ("03_handover_ignored_by_human", "HUMAN_DRIVER", "MEDIUM"),
    ("04_handover_too_short", "TECH_COMPANY", "MEDIUM"),
    ("05_unavoidable_close_cutin", "NO_FAULT_DRIVING", "HIGH"),
    ("06_borderline_needs_review", "NEEDS_REVIEW", "LOW"),
    ("07_outside_odd", "TECH_COMPANY", "MEDIUM"),
    ("08_integrity_failure", "NEEDS_REVIEW", "LOW"),
    ("09_human_override", "HUMAN_DRIVER", "MEDIUM"),
    ("10_critical_fault", "TECH_COMPANY", "MEDIUM"),
])
def test_example_verdicts(name, liable, confidence):
    v = verdict(name)
    assert (v.liable, v.confidence) == (liable, confidence)
    assert v.recovery_case == (liable == "TECH_COMPANY")
    assert v.steps, "every verdict must show its reasoning"


def test_deterministic():
    assert verdict("06_borderline_needs_review") == verdict("06_borderline_needs_review")


def test_integrity_failure_stops_before_any_liability_step():
    v = verdict("08_integrity_failure")
    assert [s.name for s in v.steps] == ["integrity"]
    assert any("Tamper" in r for r in v.review_items)


def test_late_detection_is_reported():
    v = verdict("01_av_late_detection")
    assert any("1.8s after" in f for f in v.findings)


def test_driver_eyes_off_reported_for_ignored_handover():
    v = verdict("03_handover_ignored_by_human")
    assert any("eyes off" in f for f in v.findings)
    assert v.review_items, "human liability for an ignored handover must be flagged for review"


def test_no_collision_means_no_claim():
    d = raw("01_av_late_detection")
    d["outcome"] = {"collided": False}
    v = decide(load_bundle(d))
    assert v.liable == "NO_FAULT_DRIVING" and not v.recovery_case


def test_missing_conflict_needs_review():
    d = raw("01_av_late_detection")
    d["conflict"] = None
    v = decide(load_bundle(d))
    assert v.liable == "NEEDS_REVIEW"
    assert any("conflict" in m for m in v.evidence_missing)


def test_unapproved_software_points_at_tech_company():
    d = raw("01_av_late_detection")
    d["vehicle"]["software_version"] = "9.9.9-dev"
    v = decide(load_bundle(d))
    assert v.liable == "TECH_COMPANY" and v.steps[-1].name == "software"


def test_human_response_before_crash_shifts_to_human():
    d = raw("01_av_late_detection")
    d["vehicle"]["handover"] = {"demand_t": 90.0, "human_response_t": 95.0}
    assert decide(load_bundle(d)).liable == "HUMAN_DRIVER"


def test_very_late_human_response_does_not_blame_human():
    d = raw("01_av_late_detection")
    d["vehicle"]["handover"] = {"demand_t": 99.0, "human_response_t": 99.5}
    assert decide(load_bundle(d)).liable != "HUMAN_DRIVER"


def test_thresholds_are_configurable():
    strict = Policy(p_system_fell_short=1.01)  # nothing can reach it
    assert verdict("01_av_late_detection", policy=strict).liable == "NEEDS_REVIEW"


def test_estimator_is_pluggable():
    class AlwaysAvoids:
        def estimate(self, c):
            r = KinematicEstimator().estimate(c)
            return type(r)(**{**r.__dict__, "p_avoid": 1.0, "avoids_at_p95": True, "model": "stub"})
    v = verdict("06_borderline_needs_review", estimator=AlwaysAvoids())
    assert v.liable == "TECH_COMPANY" and v.counterfactual.model == "stub"


def test_missing_evidence_listed():
    d = raw("01_av_late_detection")
    d["perception"]["sensors"] = ["camera"]
    d["external"]["cctv"] = []
    v = decide(load_bundle(d))
    assert "lidar data" in v.evidence_missing and "independent CCTV" in v.evidence_missing


# ---- counterfactual physics sanity
def test_faster_means_harder_to_avoid():
    c = load_bundle(raw("01_av_late_detection")).conflict
    slow = KinematicEstimator().estimate(c)
    fast = KinematicEstimator().estimate(type(c)(**{**c.__dict__, "ego_speed_mps": 25.0}))
    assert fast.p_avoid < slow.p_avoid
    assert fast.median_impact_speed_mps > 0


def test_wet_road_lowers_avoidance():
    c = load_bundle(raw("06_borderline_needs_review")).conflict
    dry = KinematicEstimator().estimate(c)
    wet = KinematicEstimator().estimate(type(c)(**{**c.__dict__, "friction_mu": 0.4}))
    assert wet.p_avoid < dry.p_avoid


def test_not_closing_on_hazard_is_always_avoided():
    c = load_bundle(raw("01_av_late_detection")).conflict
    r = KinematicEstimator().estimate(type(c)(**{**c.__dict__, "hazard_speed_mps": c.ego_speed_mps}))
    assert r.p_avoid == 1.0


# ---- bundle validation
def test_rejects_wrong_schema_version():
    d = raw("01_av_late_detection")
    d["schema_version"] = "9"
    with pytest.raises(BundleError):
        load_bundle(d)


@pytest.mark.parametrize("mutate", [
    lambda d: d["vehicle"].update(mode_events=[]),
    lambda d: d["vehicle"]["mode_events"].append({"t": 1.0, "mode": "flying"}),
    lambda d: d["vehicle"].update(occupant="dog"),
    lambda d: d["conflict"].update(gap_m=-1.0),
    lambda d: d["conflict"].update(friction_mu=0.0),
    lambda d: d.pop("integrity"),
    lambda d: d.update(t_crash="soon"),
])
def test_rejects_malformed_bundles(mutate):
    d = copy.deepcopy(raw("01_av_late_detection"))
    mutate(d)
    with pytest.raises(BundleError):
        load_bundle(d)


def test_none_extremes_from_sim_give_medium_not_high():
    """sim's estimate() reports a CI, not fast/slow driver outcomes (avoids_at_p5/p95 = None)."""
    class NoExtremes:
        def estimate(self, c):
            r = KinematicEstimator().estimate(c)
            return type(r)(**{**r.__dict__, "p_avoid": 1.0, "avoids_at_p5": None, "avoids_at_p95": None})
    v = verdict("01_av_late_detection", estimator=NoExtremes())
    assert v.liable == "TECH_COMPANY" and v.confidence == "MEDIUM"
    class NoExtremesLow(NoExtremes):
        def estimate(self, c):
            r = super().estimate(c)
            return type(r)(**{**r.__dict__, "p_avoid": 0.0})
    v = verdict("05_unavoidable_close_cutin", estimator=NoExtremesLow())
    assert v.liable == "NO_FAULT_DRIVING" and v.confidence == "MEDIUM"
