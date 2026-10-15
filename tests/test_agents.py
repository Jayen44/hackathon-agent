"""Tests for agents/. A fake client stands in for Claude, so no API calls. Fixtures are made-up test values."""
import json
from types import SimpleNamespace as NS

import pytest

from agents import debate as d
from agents.llm import AgentError
from finance import recovery as r

AV = [r.AvoidanceResult("careful_a", 0.85, (0.78, 0.91)), r.AvoidanceResult("careful_b", 0.95, (0.90, 0.98))]


def claim(**kw):
    base = dict(claim_id="TEST-1", crash_type="cut_in", injury_severity="Damage only",
                engagement_status="engaged_verified", within_odd="inside", reproduced=True,
                paid_claim_gbp=50_000, legal_cost_gbp=(2_000, 6_000), software_status="compliant")
    return d.Claim(r.ClaimFacts(**{**base, **kw}), AV)


def tool_use(name, args, i=0):
    return NS(stop_reason="tool_use", content=[NS(type="tool_use", id=f"t{i}", name=name, input=args)])


def answer(obj):
    return NS(stop_reason="end_turn", content=[NS(type="text", text=json.dumps(obj))])


class FakeClient:
    """Replays scripted responses and records every request."""
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        return self.responses.pop(0)


def change(**kw):
    return {**r.blank_change(), **kw}


def test_offline_debate_runs_and_recomputes_numbers():
    deb = d.run_debate(claim(), None)
    assert deb.mode == "offline" and deb.original["decision"] == "pursue"
    assert deb.challenged == d.summary(claim().assess(deb.challenge["change"]))
    assert [t["agent"] for t in deb.trace] == ["adjuster", "defence_counsel", "adjuster_rebuttal", "orchestrator"]


def test_claude_debate_tool_loop_and_final_from_finance():
    ch = change(cn_low=0.5, cn_high=0.5)
    client = FakeClient([
        tool_use("assess_claim", {}), answer({"recommendation": "pursue", "key_assumptions": ["x"]}),
        tool_use("find_weak_assumptions", {}), tool_use("what_if", ch, 1),
        answer({"assumption": "injured party half at fault", "argument": "...", "change": ch}),
        tool_use("what_if", change(cn_low=0.2, cn_high=0.2), 2),
        answer({"verdict": "partially_accept", "reasoning": "20% is supported",
                "accepted_change": change(cn_low=0.2, cn_high=0.2)}),
    ])
    deb = d.run_debate(claim(paid_claim_gbp=None, injury_severity="Fatal"), client)
    assert deb.mode == "claude" and len(client.requests) == 7
    final = claim(paid_claim_gbp=None, injury_severity="Fatal").assess(change(cn_low=0.2, cn_high=0.2))
    assert deb.final["expected_recovery"] == d.summary(final)["expected_recovery"]
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["output_config"]["format"]["type"] == "json_schema"
    assert "<claim_data>" in req["messages"][0]["content"]
    tools_used = [t["step"] for t in deb.trace if t["step"].startswith("tool:")]
    assert tools_used == ["tool:assess_claim", "tool:find_weak_assumptions", "tool:what_if", "tool:what_if"]


def test_out_of_bounds_what_if_is_returned_as_tool_error():
    client = FakeClient([tool_use("what_if", change(claim_value_gbp=10_000_000)),
                         answer({"recommendation": "r", "key_assumptions": []}),
                         answer({"assumption": "a", "argument": "b", "change": change()}),
                         answer({"verdict": "reject", "reasoning": "c", "accepted_change": change()})])
    deb = d.run_debate(claim(), client)
    err = deb.trace[0]
    assert err["step"] == "tool:what_if" and err["detail"]["is_error"] and "outside" in err["detail"]["output"]["error"]
    assert client.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_rejecting_a_decision_flipping_challenge_is_contested():
    flip = change(keep_model="careful_a", p_avoid_at_low_bound=True, legal_cost_low=60_000, legal_cost_high=60_000)
    client = FakeClient([answer({"recommendation": "r", "key_assumptions": []}),
                         answer({"assumption": "a", "argument": "b", "change": flip}),
                         answer({"verdict": "reject", "reasoning": "no", "accepted_change": flip})])
    deb = d.run_debate(claim(), client)
    assert deb.challenged["decision"] != deb.original["decision"]
    assert deb.contested and deb.final["decision"] == deb.original["decision"]
    assert any("CONTESTED" in x for x in deb.final["reasons"])


def test_refusal_raises():
    client = FakeClient([NS(stop_reason="refusal", content=[], stop_details=None)])
    with pytest.raises(AgentError):
        d.run_debate(claim(), client)


def test_apply_change_bounds():
    c = claim()
    with pytest.raises(r.ChangeError):
        c.assess({"keep_model": "careful_z"})
    with pytest.raises(r.ChangeError):
        c.assess({"cn_low": 0.5})
    with pytest.raises(r.ChangeError):
        c.assess({"surprise": 1})
    assert c.assess({"keep_model": "careful_a"}).decision == "pull_logs_first"   # one model -> gate


def test_attacks_carry_a_change_that_reproduces_them():
    c = claim()
    for atk in r.weakest_assumption(c.facts, c.avoidance):
        assert (c.assess(atk.change).decision != c.assess().decision) == atk.flips_decision


def test_unpriced_claim_is_not_debated():
    with pytest.raises(ValueError):
        d.run_debate(claim(injury_severity="Unknown", paid_claim_gbp=None), None)


def test_invalid_what_if_is_a_tool_error_not_a_crash():
    from agents.llm import ToolInputError
    with pytest.raises(ToolInputError):
        claim().execute("what_if", change(legal_cost_low=0, legal_cost_high=0))
    zero = change(legal_cost_low=0, legal_cost_high=0)
    client = FakeClient([answer({"recommendation": "r", "key_assumptions": []}),
                         answer({"assumption": "a", "argument": "b", "change": zero}),
                         answer({"verdict": "accept", "reasoning": "c", "accepted_change": zero})])
    deb = d.run_debate(claim(), client)          # completes; both bad changes are logged, not applied
    assert [t["step"] for t in deb.trace].count("invalid_change") == 2
    assert deb.final["decision"] == deb.original["decision"]
