"""viz/api/claims.py: intake form -> bundle, information-request ranking, adapter to the insurance engine.

The insurance/finance code lives on branch origin/insurance and is never copied into git. Tests that need it run
only when it is importable (e.g. ACCEL_INSURANCE_DIR points at a `git archive origin/insurance insurance finance`
export); otherwise they are skipped.
"""
from __future__ import annotations

import os
import sys

import pytest

from viz.api import claims
from viz.api.claims import (MPH, PRIOR_GAP_M, PRIOR_SPEED_MPH, SimCounterfactualEstimator, form_to_bundle,
                            information_requests, project_bundle, sim_bundle)

if os.environ.get("ACCEL_INSURANCE_DIR"):
    sys.path.insert(0, os.environ["ACCEL_INSURANCE_DIR"])
needs_insurance = pytest.mark.skipif(not claims.insurance_available(),
                                     reason="insurance/finance not vendored (set ACCEL_INSURANCE_DIR)")


def base_form(**kw):
    f = {"claim_ref": "T-1", "location_type": "urban", "av_engaged": "yes", "within_odd": "yes",
         "ego_speed_mph": 30, "other_speed_mph": 10, "gap_m": 12, "crash_type": "cut_in", "cut_in_time_s": 1.2,
         "injury_severity": "Slight", "evidence": {"police_report": True}, "evidence_secured": "yes"}
    f.update(kw)
    return f


# ------------------------------------------------------------------ form -> bundle

def test_form_known_values_map_to_si_and_no_priors():
    b, meta = form_to_bundle(base_form())
    c = b["conflict"]
    assert b["schema_version"] == "0.1" and b["case_id"] == "T-1"
    assert c["ego_speed_mps"] == pytest.approx(30 * MPH) and c["hazard_speed_mps"] == pytest.approx(10 * MPH)
    assert c["gap_m"] == 12 and c["kind"] == "cut_in" and c["t_in_path_s"] == 1.2
    assert "conflict_ranges" not in b
    assert meta["tier"] == 0 and meta["unknowns"] == []
    assert meta["engagement_override"] == "engaged_alleged"   # reported on the form, not verified from logs


def test_form_unknowns_become_prior_ranges():
    b, meta = form_to_bundle(base_form(ego_speed_mph="unknown", gap_m=None, other_speed_mph="",
                                       within_odd="unknown", cut_in_time_s=None))
    cr = b["conflict_ranges"]
    lo, hi = PRIOR_SPEED_MPH["urban"]
    assert cr["ego_speed"] == {"lo": pytest.approx(lo * MPH), "hi": pytest.approx(hi * MPH), "source": "prior"}
    assert cr["gap"]["lo"] == PRIOR_GAP_M[0] and cr["gap"]["source"] == "prior"
    assert cr["other_speed"]["source"] == "prior" and cr["cut_in_duration"]["source"] == "prior"
    assert b["vehicle"]["odd_inside"] is None
    assert {"ego_speed_mph", "gap_m", "other_speed_mph", "within_odd", "cut_in_time_s"} <= set(meta["unknowns"])


def test_form_evidence_sets_tier_and_engagement():
    _, m1 = form_to_bundle(base_form(evidence={"dashcam": True}))
    b2, m2 = form_to_bundle(base_form(evidence={"av_logs": True}))
    _, m3 = form_to_bundle(base_form(av_engaged="no"))
    _, m4 = form_to_bundle(base_form(av_engaged="unknown"))
    assert m1["tier"] == 1 and m2["tier"] == 2
    assert m2["engagement_override"] is None and b2["perception"]["decision_log_present"] is True
    assert m3["engagement_override"] == "not_engaged" and m4["engagement_override"] == "unknown"


def test_form_stationary_hazard_is_zero_speed_not_prior():
    b, meta = form_to_bundle(base_form(crash_type="stationary_hazard", other_speed_mph=None))
    assert b["conflict"]["hazard_speed_mps"] == 0.0
    assert "other_speed" not in (b.get("conflict_ranges") or {})
    assert "other_speed_mph" not in meta["unknowns"]


def test_form_rejects_bad_numbers():
    with pytest.raises(ValueError):
        form_to_bundle(base_form(gap_m=-3))
    with pytest.raises(ValueError):
        form_to_bundle(base_form(injured_party_share_low_pct=10, injured_party_share_high_pct=140))


def test_form_without_ref_gets_stable_id():
    f = base_form(); f.pop("claim_ref")
    a, _ = form_to_bundle(f)
    b, _ = form_to_bundle(dict(f, narrative="different free text"))
    assert a["case_id"].startswith("CLM-") and a["case_id"] == b["case_id"]


# ------------------------------------------------------------------ bundle normalisation

def test_sim_bundle_maps_kind_and_reported_decel():
    b = {"conflict": {"kind": "lead_braking", "hazard_decel_mps2": 6.0, "ego_speed_mps": 20, "gap_m": 30,
                      "t_start": 0}, "external": {"cctv": ["c"]}}
    s = sim_bundle(b, tier=1)
    assert s["conflict"]["crash_type"] == "lead_vehicle_decel"
    assert s["conflict_ranges"]["other_decel"] == {"lo": 5.25, "hi": 6.75, "source": "reported"}
    assert "conflict_ranges" not in b   # input untouched


def test_project_bundle_drops_only_priors():
    b, _ = form_to_bundle(base_form(gap_m=None))
    b["conflict_ranges"]["other_decel"] = {"lo": 1, "hi": 2, "source": "reported"}
    p = project_bundle(b)
    assert "gap" not in p["conflict_ranges"] and "other_decel" in p["conflict_ranges"]


# ------------------------------------------------------------------ information requests

def _sim(rows, prior=()):
    return {"drivers": {"careful_a": {"ci90": [0.4, 0.5]}, "careful_b": {"ci90": [0.3, 0.45]}},
            "sensitivity": rows, "ranges": {p: {"lo": 0, "hi": 1, "source": "prior"} for p in prior},
            "reproduction": {"rate": 0.9, "reproduced_flag": True}, "timeline_check": {"consistent": True}}


def test_information_requests_ordering():
    b, meta = form_to_bundle(base_form(within_odd="unknown", evidence_secured="no"))
    rows = [{"param": "gap", "source": "prior", "lo": 5, "hi": 40, "swing": 0.6},
            {"param": "other_speed", "source": "narrative", "lo": 0, "hi": 9, "swing": 0.2},
            {"param": "ego_speed", "source": "reported", "lo": 10, "hi": 12, "swing": 0.9}]
    proj = {"band_now": [0.2, 0.9], "next": {1: {"band": [0.5, 0.7]}, 2: {"band": [0.55, 0.6]}}}
    reqs = information_requests(b, _sim(rows, prior=("cut_in_start",)), {"decision": "cannot_price"}, proj, meta)
    ids = [r["id"] for r in reqs]
    assert reqs[0]["blocks_pricing"] and ids[0] == "integrity"            # blockers first
    # narrowing: AV logs 0.70 - 0.05 = 0.65, CCTV 0.70 - 0.20 = 0.50; gap swing 0.60
    assert ids.index("av_logs") < ids.index("fact:gap") < ids.index("cctv_or_dashcam")
    assert "fact:ego_speed" not in ids                                     # reported facts are not requested
    assert ids.index("fact:gap") < ids.index("fact:other_speed")
    assert "fact:cut_in_start" in ids and "odd" in ids
    assert [r["rank"] for r in reqs] == list(range(1, len(reqs) + 1))
    impacts = [r["impact"] for r in reqs if not r["blocks_pricing"]]
    assert impacts == sorted(impacts, reverse=True)
    logs = next(r for r in reqs if r["id"] == "av_logs")
    assert "narrows from 20%-90% to 55%-60%" in logs["expected_effect"]


def test_information_requests_no_conflict_blocks():
    b, meta = form_to_bundle(base_form())
    b["conflict"] = None
    reqs = information_requests(b, None, {"decision": "cannot_price", "reason": "x"}, None, meta)
    assert reqs[0]["id"] == "conflict" and reqs[0]["blocks_pricing"]


def test_evidence_band_envelope():
    sim = _sim([{"param": "gap", "source": "prior", "lo": 0, "hi": 1, "swing": 0.5,
                 "p_at_lo": {"careful_a": 0.1, "careful_b": 0.05}, "p_at_hi": {"careful_a": 0.95, "careful_b": 0.7}},
                {"param": "ego_speed", "source": "reported", "lo": 0, "hi": 1, "swing": 0.9,
                 "p_at_lo": {"careful_a": 0.0, "careful_b": 0.0}, "p_at_hi": {"careful_a": 1.0, "careful_b": 1.0}}])
    assert claims.evidence_band(sim) == (0.05, 0.95)


# ------------------------------------------------------------------ adapter to their engine

DRIVER = {"p_avoid": 0.82, "ci90": [0.8, 0.84], "n_samples": 1000, "avoids_at_p5": None, "avoids_at_p50": True,
          "avoids_at_p95": None, "median_impact_speed_mps": 0.0, "model": "careful_a_r157_pm1_ccdm", "notes": ["x"]}


@needs_insurance
def test_adapter_returns_their_counterfactual_result():
    from insurance.counterfactual import CounterfactualResult
    r = SimCounterfactualEstimator("careful_a", DRIVER).estimate(None)
    assert isinstance(r, CounterfactualResult)
    assert r.p_avoid == 0.82 and r.n_samples == 1000 and r.avoids_at_p50 is True
    assert "careful_a_r157_pm1_ccdm" in r.model


@needs_insurance
def test_assess_gbp_uses_both_sim_estimators():
    b, meta = form_to_bundle(base_form(evidence={"av_logs": True}, injured_party_share_low_pct=0,
                                       injured_party_share_high_pct=10))
    sim = {"drivers": {"careful_a": DRIVER, "careful_b": dict(DRIVER, p_avoid=0.6, model="careful_b_r157_pm2_fsm")},
           "reproduction": {"reproduced_flag": True}}
    g = claims.assess_gbp(b, sim, meta["engagement_override"])
    assert g["available"] and g["recovery"] is not None
    assert g["recovery"]["p_avoid"]["low"] < g["recovery"]["p_avoid"]["high"]
    assert g["verdict"]["counterfactual"]["model"].startswith("careful_a")
    assert g["decision"] in ("pursue", "dont_pursue", "pull_logs_first", "cannot_price", "not_av_recovery")


def _agents_available():
    try:
        import agents.debate  # noqa: F401
        return claims.insurance_available()
    except ImportError:
        return False


@pytest.mark.skipif(not _agents_available(), reason="agents/ (insurance branch) not vendored")
def test_debate_scripted_runs_on_our_sim():
    b, meta = form_to_bundle(base_form(evidence={"av_logs": True}))
    sim = {"drivers": {"careful_a": DRIVER, "careful_b": dict(DRIVER, p_avoid=0.6, model="careful_b_r157_pm2_fsm")},
           "reproduction": {"reproduced_flag": True}}
    d = claims.run_debate_for(b, sim, meta)
    assert d["available"] and d["mode"] == "offline" and d["mode_label"].startswith("scripted")
    assert [t["agent"] for t in d["trace"]][:3] == ["adjuster", "defence_counsel", "adjuster_rebuttal"]
    assert d["final"]["decision"] in ("pursue", "dont_pursue", "pull_logs_first", "cannot_price", "not_av_recovery")


def test_debate_needs_sim():
    b, meta = form_to_bundle(base_form())
    assert claims.run_debate_for(b, None, meta)["available"] is False


@needs_insurance
def test_assess_gbp_reports_why_unpriced():
    b, meta = form_to_bundle(base_form(evidence_secured="no"))
    g = claims.assess_gbp(b, {"drivers": {"careful_a": DRIVER, "careful_b": DRIVER}}, meta["engagement_override"])
    assert g["decision"] == "cannot_price" and "integrity" in g["reason"]
