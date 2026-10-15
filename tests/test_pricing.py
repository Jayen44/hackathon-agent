"""viz/api/pricing.py: insurer profiles, webhook contract + fallback, rules engine (only more conservative)."""
from __future__ import annotations

import copy
import itertools

import pytest

from viz.api import pricing as P

IV = lambda lo, mid, hi: {"low": lo, "mid": mid, "high": hi}  # noqa: E731


def ev(**kw):
    e = {"p_avoid": {"careful_a": {"p": 0.8, "ci90": [0.77, 0.83]}, "careful_b": {"p": 0.9, "ci90": [0.88, 0.92]}},
         "reproduced": True, "reproduction_rate": 0.9, "evidence_tier": 1, "data_sufficiency": 0.8,
         "r157_scope": True, "crash_type": "cut_in", "timeline_check": True}
    e.update(kw)
    return e


def out(cv=IV(60000, 60000, 60000), er=IV(10000, 30000, 40000), lc=IV(5000, 8000, 12000), decision="pursue"):
    return {"claim_value_gbp": cv, "expected_recovery_gbp": er, "legal_cost_gbp": lc, "decision": decision,
            "reasons": [], "model_version": "t"}


def fired(applied, name):
    return next(a for a in applied if a["rule"] == name)["fired"]


# ------------------------------------------------------------------ profiles

def test_default_profiles_validate():
    for p in P.DEFAULT_PROFILES:
        assert P.validate_profile(copy.deepcopy(p)) == p


@pytest.mark.parametrize("bad", [
    {"id": "x", "name": "X", "pricing": {"type": "builtin"}, "rules": [], "extra": 1},
    {"id": "x", "name": "X", "pricing": {"type": "builtin", "url": "https://a"}, "rules": []},
    {"id": "x", "name": "X", "pricing": {"type": "code", "src": "import os"}, "rules": []},
    {"id": "x", "name": "X", "pricing": {"type": "builtin"}, "rules": [{"rule": "eval", "value": "1"}]},
    {"id": "x", "name": "X", "pricing": {"type": "builtin"}, "rules": [{"rule": "min_net_recovery_gbp", "value": -1}]},
    {"id": "x", "name": "X", "pricing": {"type": "builtin"}, "rules": [{"rule": "min_net_recovery_gbp", "value": True}]},
    {"id": "x", "name": "X", "pricing": {"type": "builtin"}, "rules": [{"rule": "flag_if_model_spread_above", "value": 2}]},
    {"id": "x", "name": "X", "pricing": {"type": "builtin"}, "rules": [{"rule": "require_reproduced", "value": 1}]},
    {"id": "x", "name": "X", "pricing": {"type": "builtin"}, "rules": [{"rule": "outside_r157_scope_action", "value": "pursue"}]},
    {"id": "x", "name": "X", "pricing": {"type": "builtin"}, "rules": [{"rule": "require_reproduced", "value": True, "x": 1}]},
    {"id": "x", "name": "X", "pricing": {"type": "builtin"},
     "rules": [{"rule": "require_reproduced", "value": True}, {"rule": "require_reproduced", "value": False}]},
    {"id": "x", "name": "X", "pricing": {"type": "webhook", "url": "http://" + P.OWN_API_HOST + "/m", "version": "1"}, "rules": []},
    {"id": "x", "name": "X", "pricing": {"type": "webhook", "url": "https://evil.example.com/m", "version": "1"}, "rules": []},
    {"id": "x", "name": "X", "pricing": {"type": "webhook", "url": "https://u:p@" + P.OWN_API_HOST + "/m", "version": "1"}, "rules": []},
    {"id": "x y", "name": "X", "pricing": {"type": "builtin"}, "rules": []},
    {"name": "X", "pricing": {"type": "builtin"}, "rules": []},
])
def test_profile_schema_rejects(bad):
    with pytest.raises(ValueError):
        P.validate_profile(bad)


def test_allowlist_env_extends(monkeypatch):
    monkeypatch.setenv("ACCEL_WEBHOOK_ALLOWED_HOSTS", "pricing.insurer.example")
    assert P.check_webhook_url("https://pricing.insurer.example/v1/price")


# ------------------------------------------------------------------ webhook response validation and fallback

def test_validate_response_ok_and_strict():
    good = P.demo_insurer_model(P.SAMPLE_PAYLOAD)
    v = P.validate_response(good)
    assert v["decision"] in P.WEBHOOK_DECISIONS and v["model_version"].startswith("Demo Insurer Ltd")
    for mutate in (lambda d: d.update(extra=1), lambda d: d.update(decision="sue"),
                   lambda d: d.update(claim_value_gbp=IV(3, 2, 1)), lambda d: d.update(claim_value_gbp=IV(-1, 0, 1)),
                   lambda d: d.update(expected_recovery_gbp=IV(0, float("nan"), 1)), lambda d: d.pop("reasons"),
                   lambda d: d.update(reasons=["x" * 501]), lambda d: d.update(reasons="<script>"),
                   lambda d: d.update(model_version=""), lambda d: d.update(expected_recovery_gbp=None)):
        bad = copy.deepcopy(good)
        mutate(bad)
        with pytest.raises(ValueError):
            P.validate_response(bad)
    assert P.validate_response({"claim_value_gbp": None, "expected_recovery_gbp": None, "decision": "cannot_price",
                                "reasons": [], "model_version": "x"})["decision"] == "cannot_price"


def claim(decision="pursue", gbp_recovery=True):
    rec = {"claim_value": IV(50000, 60000, 70000), "expected_recovery": IV(5000, 20000, 30000),
           "legal_cost": IV(5000, 8000, 12000), "reasons": ["engine reason"]} if gbp_recovery else None
    return {"claim_id": "C1", "crash_type": "cut_in", "evidence_tier": 1,
            "sim": {"drivers": {"careful_a": {"p_avoid": 0.8, "ci90": [0.77, 0.83]},
                                "careful_b": {"p_avoid": 0.9, "ci90": [0.88, 0.92]}},
                    "reproduction": {"rate": 0.9, "reproduced_flag": True}},
            "data_sufficiency": {"score": 0.8}, "timeline_check": {"consistent": True},
            "gbp": {"decision": decision, "recovery": rec, "reason": None}}


FACTS = {"severity": "Serious", "paid_gbp": 60000, "cn_range": [0, 0.1], "engagement": "engaged_verified",
         "odd": "inside", "software": "unknown"}
DEMO = next(p for p in P.DEFAULT_PROFILES if p["id"] == "demo-insurer")
BUILTIN = next(p for p in P.DEFAULT_PROFILES if p["id"] == "builtin")


def test_webhook_success_compares_both():
    seen = {}

    def post(url, payload):
        seen.update(payload)
        return P.demo_insurer_model(payload)
    r = P.price_claim(claim(), FACTS, DEMO, post=post)
    p = r["pricing"]
    assert p["source"] == "webhook" and p["insurer"]["model_version"] == P.DEMO_MODEL_VERSION
    assert seen["evidence"]["p_avoid"]["careful_a"]["p"] == 0.8 and seen["claim_facts"] == FACTS
    assert seen["our_reference_assessment"]["claim_value_gbp"] == IV(50000, 60000, 70000)
    assert p["builtin"]["expected_recovery_gbp"] == IV(5000, 20000, 30000)   # reference always present
    assert p["comparison"] is not None and isinstance(p["comparison"]["why"], list)
    # demo rules: claim value 67,200 > 50,000 at tier 1 -> logs first
    assert r["decision_final"] == "pull_logs_first"
    assert fired(r["rules_applied"], "require_av_logs_above_gbp")


@pytest.mark.parametrize("post", [
    lambda u, p: (_ for _ in ()).throw(TimeoutError()),
    lambda u, p: (_ for _ in ()).throw(OSError("down")),
    lambda u, p: {"decision": "pursue"},
    lambda u, p: "<html>",
    lambda u, p: {**P.demo_insurer_model(p), "decision": "approve_everything"},
])
def test_webhook_failure_falls_back_to_builtin(post):
    r = P.price_claim(claim(), FACTS, DEMO, post=post)
    p = r["pricing"]
    assert p["source"] == "fallback" and p["insurer"] is None and p["fallback_reason"]
    assert p["output"] == p["builtin"]


def test_builtin_profile_never_calls_webhook():
    def post(u, p):
        raise AssertionError("called")
    r = P.price_claim(claim(), FACTS, BUILTIN, post=post)
    assert r["pricing"]["source"] == "builtin" and r["decision_final"] == "pursue" and r["rules_applied"] == []


def test_insurer_cannot_override_not_av_recovery():
    r = P.price_claim(claim("not_av_recovery", gbp_recovery=False), FACTS, DEMO, post=lambda u, p: P.demo_insurer_model(p))
    assert r["decision_final"] == "not_av_recovery"


def test_url_checks_before_network():
    res = P.call_webhook("https://evil.example.com/x", P.SAMPLE_PAYLOAD)
    assert not res["ok"] and "allowlist" in res["error"]


def test_demo_model_deterministic_and_labelled():
    a, b = P.demo_insurer_model(P.SAMPLE_PAYLOAD), P.demo_insurer_model(copy.deepcopy(P.SAMPLE_PAYLOAD))
    assert a == b and "DEMO MODEL" in a["model_version"] and "DEMO MODEL" in a["reasons"][0]
    # reserve 60,000 x 1.12 = 67,200; lower model A mid 0.82; CN high 0.1; Serious budget 40,000
    assert a["expected_recovery_gbp"]["mid"] == pytest.approx(67200 * 0.82 * 0.9 - 40000)


# ------------------------------------------------------------------ rules engine

def test_each_rule_fires():
    R = lambda n, v: [{"rule": n, "value": v}]  # noqa: E731
    d, a = P.apply_rules("pursue", out(er=IV(-1000, 2000, 4000)), ev(), R("min_net_recovery_gbp", 5000))
    assert d == "dont_pursue" and fired(a, "min_net_recovery_gbp")
    d, a = P.apply_rules("pursue", out(er=IV(-1000, 2000, 9000)), ev(), R("min_net_recovery_gbp", 5000))
    assert d == "pull_logs_first"
    d, a = P.apply_rules("pursue", out(), ev(), R("min_net_recovery_gbp", 5000))
    assert d == "pursue" and not fired(a, "min_net_recovery_gbp")
    d, _ = P.apply_rules("pursue", out(), ev(), R("max_legal_spend_gbp", 10000))
    assert d == "pursue_after_signoff"
    d, _ = P.apply_rules("pursue", out(), ev(), R("require_av_logs_above_gbp", 50000))
    assert d == "pull_logs_first"
    d, _ = P.apply_rules("pursue", out(), ev(evidence_tier=2), R("require_av_logs_above_gbp", 50000))
    assert d == "pursue"
    d, _ = P.apply_rules("pursue", out(), ev(), R("human_signoff_above_gbp", 50000))
    assert d == "pursue_after_signoff"
    d, _ = P.apply_rules("pursue", out(), ev(), R("human_signoff_above_gbp", 100000))
    assert d == "pursue"
    spread = ev(p_avoid={"careful_a": {"p": 0.2, "ci90": [0.1, 0.3]}, "careful_b": {"p": 0.9, "ci90": [0.8, 0.95]}})
    d, a = P.apply_rules("pursue", out(), spread, R("flag_if_model_spread_above", 0.3))
    assert d == "pursue_after_signoff" and fired(a, "flag_if_model_spread_above")
    d, a = P.apply_rules("pull_logs_first", out(), spread, R("flag_if_model_spread_above", 0.3))
    assert d == "pull_logs_first" and fired(a, "flag_if_model_spread_above")
    d, _ = P.apply_rules("pursue", out(), ev(reproduced=False), R("require_reproduced", True))
    assert d == "pull_logs_first"
    d, _ = P.apply_rules("pursue", out(), ev(reproduced=False), R("require_reproduced", False))
    assert d == "pursue"
    d, _ = P.apply_rules("pursue", out(), ev(r157_scope=False), R("outside_r157_scope_action", "dont_pursue"))
    assert d == "dont_pursue"
    d, _ = P.apply_rules("pursue", out(), ev(r157_scope=False), R("outside_r157_scope_action", "flag"))
    assert d == "pursue_after_signoff"


def test_rules_missing_figures_do_not_fire():
    rules = [{"rule": n, "value": 1000} for n in ("min_net_recovery_gbp", "max_legal_spend_gbp",
                                                   "require_av_logs_above_gbp", "human_signoff_above_gbp")]
    d, a = P.apply_rules("cannot_price", out(cv=None, er=None, lc=None, decision="cannot_price"), ev(), rules)
    assert d == "cannot_price" and not any(x["fired"] for x in a)
    assert all("not checked" in x["reason"] for x in a)


def test_rules_only_more_conservative_property():
    """Exhaustive over decisions x evidence variants x every rule subset: never less conservative."""
    rule_pool = [{"rule": "min_net_recovery_gbp", "value": 5000}, {"rule": "max_legal_spend_gbp", "value": 10000},
                 {"rule": "require_av_logs_above_gbp", "value": 50000}, {"rule": "human_signoff_above_gbp", "value": 100},
                 {"rule": "flag_if_model_spread_above", "value": 0.05}, {"rule": "require_reproduced", "value": True},
                 {"rule": "outside_r157_scope_action", "value": "flag"}]
    outs = [out(), out(er=IV(-9000, -100, 100)), out(cv=None, er=None, lc=None)]
    evs = [ev(), ev(reproduced=False, r157_scope=False, evidence_tier=0), ev(evidence_tier=2, p_avoid={})]
    for d0 in P.DECISION_RANK:
        for o, e in itertools.product(outs, evs):
            for k in range(len(rule_pool) + 1):
                for sub in itertools.combinations(rule_pool, k):
                    d, a = P.apply_rules(d0, o, e, list(sub))
                    assert P.DECISION_RANK[d] >= P.DECISION_RANK[d0], (d0, d, sub)
                    assert len(a) == len(sub)


def test_rules_do_not_invent_numbers():
    o = out()
    before = copy.deepcopy(o)
    P.apply_rules("pursue", o, ev(), [{"rule": "min_net_recovery_gbp", "value": 5000}])
    assert o == before


def test_compare_flags_disagreement():
    b = out(cv=IV(1000, 2000, 3000), er=IV(-5000, -1000, 500), decision="dont_pursue")
    i = out(cv=IV(6500, 6500, 6500), er=IV(1000, 2000, 3000), decision="pull_logs_first")
    c = P.compare(b, i, "dont_pursue", "pull_logs_first")
    assert c["agree"] is False and c["decision_differs"] and c["claim_value_overlap"] is False
    assert any("claim value" in w for w in c["why"])
    c2 = P.compare(out(), out(), "pursue", "pursue")
    assert c2["agree"] is True and c2["why"] == []


# ------------------------------------------------------------------ end to end with the finance engine (optional)

def _needs_insurance():
    import os
    import sys
    if os.environ.get("ACCEL_INSURANCE_DIR") and os.environ["ACCEL_INSURANCE_DIR"] not in sys.path:
        sys.path.insert(0, os.environ["ACCEL_INSURANCE_DIR"])
    from viz.api import claims
    if not claims.insurance_available():
        pytest.skip("insurance/finance not vendored (set ACCEL_INSURANCE_DIR)")
    return claims


def test_assess_claim_with_demo_profile_end_to_end():
    import json
    import os
    claims = _needs_insurance()
    d = os.environ.get("ACCEL_INSURANCE_DIR", "")
    path = os.path.join(d, "insurance", "examples", "22_pursue_lead_braking.json")
    if not os.path.exists(path):
        pytest.skip("example bundle not available")
    b = json.load(open(path))
    r = claims.assess_claim(b, profile=DEMO, post=lambda u, p: P.demo_insurer_model(json.loads(json.dumps(p))))
    assert r["claim_facts"]["severity"] == "Serious"
    p = r["pricing"]
    assert p["source"] == "webhook" and p["builtin"]["decision"] == r["engine_decision"]
    assert r["decision"] == r["decision_final"] == p["insurer_final"]
    assert P.DECISION_RANK[r["decision"]] >= P.DECISION_RANK[p["insurer"]["decision"]] or r["decision"] == "get_more_evidence"
    row = claims.summary_row(r)
    pc = claims.portfolio_comparison([row], "demo-insurer")
    assert pc["n_compared"] == 1 and pc["insurer_total_gbp"]["mid"] == p["insurer"]["expected_recovery_gbp"]["mid"]
    json.dumps(r)
