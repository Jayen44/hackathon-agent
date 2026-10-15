"""`simulate_claim_cost`: the callable interface for the AI claims agent.

Two entry points:
  simulate_claim_cost(claim, ...)   Python API for trusted callers: a full, validated claim record.
  make_tool(claims, ...)            (definition, execute) for Claude tool use. The model can only name a
                                    claim record the host already holds and pick which of its scenarios to
                                    run. It cannot pass amounts, limits, liability shares or probabilities,
                                    so it cannot change them, invent them or hide the warnings.

The tool never approves, denies or settles a claim. It flags claims above the human-review threshold.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable

from claimsim import distributions as dist
from claimsim.liability import can_probability_weight
from claimsim.models import MODEL_VERSION, ClaimInput, InputError, claim_from_dict
from claimsim.sensitivity import one_way, rank_correlation
from claimsim.simulation import DEFAULT_N, simulate

LIMITATIONS = [
    "All distribution parameters are SYNTHETIC placeholders, not calibrated to UK claims data: results are "
    "illustrative, not forecasts.",
    "Liability shares and scenario probabilities are inputs. The simulation does not decide fault.",
    "Conditional scenario results must not be averaged unless sourced scenario probabilities are supplied.",
    "Dependence is a single latent collision-severity factor; other variables are independent given it.",
    "Legal and handling costs sit outside policy limits; compulsory-cover exclusions and recovery from the "
    "insured are not modelled.",
    "Recovery timing (AEVA s.5 recovery only after settlement) and discounting are not modelled.",
    "Decision support for a human claims handler; it does not approve, deny or settle claims.",
]


def missing_information(c: ClaimInput) -> list[dict]:
    m = []

    def add(item, why, evidence):
        m.append({"item": item, "why_it_matters": why, "evidence_that_would_resolve_it": evidence})

    if c.insured_repair_estimate is None:
        add("insured vehicle repair estimate", "own-damage cost excluded from the simulation", "engineer's estimate")
    if c.third_party_repair_estimate is None:
        add("third-party vehicle repair estimate", "third-party property cost excluded", "third party's repair estimate")
    if c.injury_outcome == "unknown":
        add("bodily-injury outcome", "injury frequency and severity are modelled with synthetic parameters",
            "confirmation of any injury claim and medical evidence")
    if c.third_party_property_estimate is None:
        add("other third-party property damage", "modelled with a synthetic probability", "scene report, photos")
    if c.collision_severity is None:
        add("collision severity", "injury probability uses the synthetic 'unknown' rate", "impact speed, damage photos")
    if len(c.scenarios) > 1 and not can_probability_weight(c.scenarios)[0]:
        add("liability allocation", "liability is unresolved: only conditional results are reported",
            "vehicle event data (DSSAD), CCTV, dashcam, witnesses, police report")
    p = c.policy
    if p.own_damage_covered and p.own_damage_limit is None:
        add("own-damage limit (vehicle value)", "no total-loss cap applied", "market valuation of the insured vehicle")
    if p.third_party_property_limit is None:
        add("third-party property limit", "no cap applied", "policy schedule")
    if c.third_party_recovery_probability is None or c.manufacturer_recovery_probability is None:
        add("recovery prospects", "synthetic default recovery probabilities used",
            "third-party insurer's liability position; manufacturer's response")
    return m


def simulate_claim_cost(claim: dict | ClaimInput, *, n_simulations: int = DEFAULT_N, seed: int | None = 0,
                        scenarios: list[str] | None = None, include_sensitivity: bool = True,
                        assumptions: dist.Assumptions | None = None) -> dict:
    """Simulate the claim's cost distribution under each liability scenario. Returns JSON-ready data."""
    c = claim if isinstance(claim, ClaimInput) else claim_from_dict(claim)
    if scenarios:
        unknown = set(scenarios) - {s.name for s in c.scenarios}
        if unknown:
            raise InputError(f"unknown scenarios {sorted(unknown)}; the claim has {[s.name for s in c.scenarios]}")
        c = dataclasses.replace(c, scenarios=tuple(s for s in c.scenarios if s.name in scenarios))
    a = assumptions or dist.load()
    out = simulate(c, a, n_simulations, seed)
    out["claim_id"] = c.claim_id
    out["synthetic_input"] = c.synthetic
    if a.synthetic:
        out["warnings"].insert(0, "ILLUSTRATIVE: uncalibrated synthetic assumptions; not a real-world forecast")
    if c.synthetic:
        out["warnings"].insert(0, "ILLUSTRATIVE INPUT: not a real claim")
    out["missing_information"] = missing_information(c)
    if include_sensitivity:
        out["sensitivity"] = {s.name: {"one_way": one_way(c, s.name, a, min(n_simulations, 10_000), seed or 0),
                                       "rank_correlation": rank_correlation(c, s.name, a, min(n_simulations, 10_000),
                                                                            seed or 0)}
                              for s in c.scenarios}
    review = []
    if c.human_review_threshold is not None:
        for name, s in out["scenarios"].items():
            if s["net_exposure_percentiles"]["p95"] > c.human_review_threshold:
                review.append(f"{name}: 95th percentile net exposure £{s['net_exposure_percentiles']['p95']:,.0f} "
                              f"exceeds the review threshold £{c.human_review_threshold:,.0f}")
    out["human_review"] = {"required": bool(review), "reasons": review, "threshold": c.human_review_threshold,
                           "note": "This tool does not approve, deny or settle claims."}
    out["limitations"] = LIMITATIONS
    out["model_version"] = MODEL_VERSION
    return out


TOOL_DEFINITION = {
    "name": "simulate_claim_cost",
    "description": ("Monte Carlo distribution of the insurer's cost for a claim record held by the claims system: "
                    "expected and percentile insurer payment and net exposure (after recoveries), cost breakdown, "
                    "results per liability scenario, sensitivity drivers, missing information and warnings. "
                    "Amounts, policy limits, liability shares and probabilities come from the claim record and "
                    "cannot be changed here. Report the warnings and limitations with any figure you use."),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "claim_ref": {"type": "string", "description": "id of a claim record held by the host"},
            "scenarios": {"type": "array", "items": {"type": "string"},
                          "description": "names of the claim's liability scenarios to run; empty = all"},
            "include_sensitivity": {"type": "boolean"},
        },
        "required": ["claim_ref", "scenarios", "include_sensitivity"],
        "additionalProperties": False,
    },
}


def make_tool(claims: dict[str, dict | ClaimInput], *, n_simulations: int = DEFAULT_N,
              seed: int = 0) -> tuple[dict, Callable[[str, dict], Any]]:
    """(tool definition, executor) for agents.llm.run_agent. The host fixes n_simulations and seed."""
    def execute(name: str, args: dict) -> Any:
        from agents.llm import ToolInputError   # the agent loop returns these to the model as tool errors
        if name != TOOL_DEFINITION["name"]:
            raise ToolInputError(f"unknown tool {name!r}")
        ref = args.get("claim_ref")
        if ref not in claims:
            raise ToolInputError(f"unknown claim_ref {ref!r}; available: {sorted(claims)}")
        try:
            return simulate_claim_cost(claims[ref], n_simulations=n_simulations, seed=seed,
                                       scenarios=args.get("scenarios") or None,
                                       include_sensitivity=bool(args.get("include_sensitivity")))
        except InputError as e:
            raise ToolInputError(str(e)) from e
    return TOOL_DEFINITION, execute
