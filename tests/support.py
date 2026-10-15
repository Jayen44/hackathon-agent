"""Test doubles for the counterfactual. These are NOT physics: they return the probability you ask for."""
from insurance.counterfactual import CounterfactualResult, FixedEstimator


def stub_result(p: float, model: str = "stub", p5=None, p95=None, n: int = 400) -> CounterfactualResult:
    return CounterfactualResult(p_avoid=p, avoids_at_p5=p5, avoids_at_p50=p >= 0.5, avoids_at_p95=p95,
                                median_impact_speed_mps=0.0 if p >= 0.5 else 8.0, n_samples=n, model=model)


def stub(p: float, **kw) -> FixedEstimator:
    return FixedEstimator(stub_result(p, **kw))


def two(p_a: float, p_b: float) -> dict:
    """Stand-ins for the sim's careful drivers A and B."""
    return {"careful_a": stub(p_a, model="stub A"), "careful_b": stub(p_b, model="stub B")}
