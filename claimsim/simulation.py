"""Monte Carlo execution: sample losses once, then evaluate every liability scenario on the same draws.

Per iteration:
  1. sample repair severities (correlated through the common collision-severity shock)
  2. sample injury occurrence, then severity (two-stage)
  3. apply the liability scenario (attributable loss)
  4. apply policy terms (covered loss -> insurer payment; the insured keeps the excess)
  5. add legal and handling expense
  6. sample recoveries, capped at what is recoverable from each source
  7. net exposure = insurer payment + expenses - recoveries

Common random numbers: each random component has its own seeded stream, so scenarios and sensitivity
runs differ only by the input being varied, not by sampling noise.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from claimsim import distributions as dist
from claimsim.liability import attributable, can_probability_weight, recoverable
from claimsim.models import LOSS_CATEGORIES, MODEL_VERSION, ClaimInput, InputError, LiabilityScenario
from claimsim.policy import PolicyRules, rules_for

DEFAULT_N = 10_000
STREAMS = ("shock", "insured_repair", "tp_repair", "injury", "tp_property", "legal", "rec_tp", "rec_mfr", "mix")
EPS = 1e-6


@dataclass
class Draws:
    """Everything random for one simulation run, drawn once and shared by all scenarios."""
    n: int
    gross: dict[str, np.ndarray]
    legal_noise_property: np.ndarray
    legal_noise_injury: np.ndarray
    rec_u: dict[str, np.ndarray]       # uniform draws for recovery success
    rec_frac: dict[str, np.ndarray]    # beta fractions on success
    mix_u: np.ndarray
    drivers: dict[str, np.ndarray]     # per-iteration sampled drivers, for global sensitivity
    warnings: list[str]


def _streams(seed: int | None) -> dict[str, np.random.Generator]:
    ss = np.random.SeedSequence(seed)
    return {name: np.random.default_rng(child) for name, child in zip(STREAMS, ss.spawn(len(STREAMS)))}


def draw(claim: ClaimInput, a: dist.Assumptions, n: int, seed: int | None) -> Draws:
    if not isinstance(n, int) or n < 100:
        raise InputError("n_simulations must be an integer >= 100")
    r, g = a.raw, _streams(seed)
    warnings: list[str] = []
    shock = g["shock"].standard_normal(n)
    load = r["common_shock"]["repair_loading"]
    rep = r["repair"]

    def repair(est, stream, label):
        if est is None:
            warnings.append(f"{label} estimate unknown: excluded from the simulation, so costs are understated")
            return np.zeros(n)
        return dist.lognormal_around(g[stream], est * rep["median_to_estimate"], rep["sigma"], n, shock, load)

    own = repair(claim.insured_repair_estimate, "insured_repair", "insured vehicle repair")
    tp = repair(claim.third_party_repair_estimate, "tp_repair", "third-party vehicle repair")

    inj = r["injury"]
    if claim.injury_outcome == "none":
        bi, occurred = np.zeros(n), np.zeros(n, bool)
    elif claim.injury_outcome == "known":
        bi = dist.lognormal_around(g["injury"], claim.injury_cost_estimate, inj["known_sigma"], n)
        occurred = np.ones(n, bool)
    else:
        key = claim.collision_severity or "unknown"
        p = dist.injury_probability(inj["probability_by_severity"][key], shock, r["common_shock"]["injury_logit_loading"])
        occurred = g["injury"].random(n) < p
        sev, _ = dist.tiered_lognormal(g["injury"], inj["tiers"], n)
        bi = np.where(occurred, sev, 0.0)
        warnings.append("bodily-injury outcome unknown: modelled with SYNTHETIC frequency and severity")

    tpp = r["third_party_property"]
    if claim.third_party_property_estimate is None:
        happened = g["tp_property"].random(n) < tpp["probability"]
        prop = np.where(happened, dist.lognormal_around(g["tp_property"], tpp["median"], tpp["sigma"], n), 0.0)
    elif claim.third_party_property_estimate == 0:
        prop = np.zeros(n)
    else:
        prop = dist.lognormal_around(g["tp_property"], claim.third_party_property_estimate, tpp["known_sigma"], n)

    gross = {"insured_vehicle_repair": own, "third_party_vehicle_repair": tp, "bodily_injury": bi,
             "third_party_property": prop, "other": np.full(n, float(claim.other_expenses_estimate))}
    rec_u, rec_frac = {}, {}
    for src, stream in (("third_party_insurer", "rec_tp"), ("manufacturer", "rec_mfr")):
        a_, b_ = r["recovery"][src]["fraction_beta"]
        rec_u[src] = g[stream].random(n)
        rec_frac[src] = g[stream].beta(a_, b_, n)
    drivers = {"collision_severity_shock": shock, "repair_cost": own + tp, "injury_occurred": occurred.astype(float),
               "injury_cost": bi, "third_party_property_cost": prop}
    return Draws(n, gross, g["legal"].standard_normal(n), g["legal"].standard_normal(n), rec_u, rec_frac,
                 g["mix"].random(n), drivers, warnings)


def recovery_probabilities(claim: ClaimInput, a: dist.Assumptions) -> tuple[dict[str, float], list[str]]:
    p = {"third_party_insurer": claim.third_party_recovery_probability,
         "manufacturer": claim.manufacturer_recovery_probability}
    w = []
    for k, v in p.items():
        if v is None:
            p[k] = a.raw["recovery"][k]["probability"]
            w.append(f"recovery probability from {k.replace('_', ' ')} is the SYNTHETIC default {p[k]:.2f}")
    return p, w


def evaluate(claim: ClaimInput, s: LiabilityScenario, d: Draws, a: dist.Assumptions, rules: PolicyRules,
             p_rec: dict[str, float]) -> dict[str, np.ndarray]:
    """Per-iteration arrays for one scenario."""
    att = attributable(s, d.gross)
    pol = rules.apply(att, claim.policy)
    lh = a.raw["legal_and_handling"]
    prop_paid = pol.paid["insured_vehicle_repair"] + pol.paid["third_party_vehicle_repair"] + pol.paid["third_party_property"]
    legal = (lh["handling_fixed"]
             + lh["property_legal_share"] * prop_paid * np.exp(lh["sigma"] * d.legal_noise_property)
             + lh["injury_legal_share"] * pol.paid["bodily_injury"] * np.exp(lh["sigma"] * d.legal_noise_injury))
    rec_max = recoverable(s, pol.paid)
    recovered = {k: np.where(d.rec_u[k] < p_rec[k], d.rec_frac[k], 0.0) * rec_max[k] for k in rec_max}
    paid_total = sum(pol.paid[c] for c in LOSS_CATEGORIES)
    rec_total = sum(recovered.values())
    out = {f"gross.{c}": d.gross[c] for c in LOSS_CATEGORIES}
    out.update({f"attributable.{c}": att[c] for c in LOSS_CATEGORIES})
    out.update({f"covered.{c}": pol.covered[c] for c in LOSS_CATEGORIES})
    out.update({f"paid.{c}": pol.paid[c] for c in LOSS_CATEGORIES})
    out.update({f"recoverable.{k}": v for k, v in rec_max.items()})
    out.update({f"recovered.{k}": v for k, v in recovered.items()})
    out.update({
        "gross_loss": sum(d.gross[c] for c in LOSS_CATEGORIES),
        "attributable_loss": sum(att[c] for c in LOSS_CATEGORIES),
        "covered_loss": sum(pol.covered[c] for c in LOSS_CATEGORIES),
        "insurer_payment": paid_total,
        "insured_retained": pol.insured_retained,
        "legal_and_handling": legal,
        "recoveries": rec_total,
        "net_exposure": paid_total + legal - rec_total,
    })
    out["_notes"] = pol.notes   # type: ignore[assignment]
    return out


def reconcile(x: dict[str, np.ndarray]) -> dict:
    """Accounting identities that must hold in every iteration (no double counting, recoveries capped)."""
    checks = {
        "net = payment + expenses - recoveries":
            np.allclose(x["net_exposure"], x["insurer_payment"] + x["legal_and_handling"] - x["recoveries"]),
        "categories sum to totals":
            np.allclose(x["insurer_payment"], sum(x[f"paid.{c}"] for c in LOSS_CATEGORIES)),
        "payment <= covered <= attributable (per category)":
            all(np.all(x[f"paid.{c}"] <= x[f"covered.{c}"] + EPS) and np.all(x[f"covered.{c}"] <= x[f"attributable.{c}"] + EPS)
                for c in LOSS_CATEGORIES),
        "recovered <= recoverable (per source)":
            all(np.all(x[f"recovered.{k}"] <= x[f"recoverable.{k}"] + EPS) for k in ("third_party_insurer", "manufacturer")),
        "recoveries <= insurer payment":
            bool(np.all(x["recoveries"] <= x["insurer_payment"] + EPS)),
        "own damage: payment + insured retained = covered":
            np.allclose(x["paid.insured_vehicle_repair"] + x["insured_retained"], x["covered.insured_vehicle_repair"]),
    }
    return {"passed": all(checks.values()), "checks": {k: bool(v) for k, v in checks.items()}}


def _se_quantile(v: np.ndarray, q: float, batches: int = 20) -> float:
    """Batch-means standard error of a quantile estimate."""
    parts = np.array_split(v, batches)
    est = np.array([np.quantile(p, q) for p in parts])
    return float(est.std(ddof=1) / np.sqrt(batches))


def stats(x: dict[str, np.ndarray], thresholds: tuple[float, ...]) -> dict:
    net = x["net_exposure"]
    n = len(net)
    m = lambda k: float(np.mean(x[k]))  # noqa: E731
    return {
        "expected_gross_loss": m("gross_loss"),
        "expected_attributable_loss": m("attributable_loss"),
        "expected_covered_loss": m("covered_loss"),
        "expected_insurer_payment": m("insurer_payment"),
        "expected_insured_retained": m("insured_retained"),
        "expected_legal_and_handling": m("legal_and_handling"),
        "expected_recoveries": m("recoveries"),
        "expected_net_exposure": float(np.mean(net)),
        "insurer_payment_percentiles": {f"p{q}": float(np.percentile(x["insurer_payment"], q)) for q in (50, 90, 95)},
        "net_exposure_percentiles": {f"p{q}": float(np.percentile(net, q)) for q in (50, 90, 95, 99)},
        "prob_net_exposure_exceeds": {f"{t:,.0f}": float(np.mean(net > t)) for t in thresholds},
        "breakdown": {c: {"gross": m(f"gross.{c}"), "attributable": m(f"attributable.{c}"),
                          "covered": m(f"covered.{c}"), "insurer_payment": m(f"paid.{c}")} for c in LOSS_CATEGORIES}
                     | {"legal_and_handling": {"insurer_expense": m("legal_and_handling")}},
        "recoveries_by_source": {k: {"recoverable": m(f"recoverable.{k}"), "expected_recovered": m(f"recovered.{k}")}
                                 for k in ("third_party_insurer", "manufacturer")},
        "monte_carlo_error": {"n": n, "se_expected_net_exposure": float(np.std(net, ddof=1) / np.sqrt(n)),
                              "se_net_p95_batch_means": _se_quantile(net, 0.95)},
        "reconciliation": reconcile(x),
    }


def simulate(claim: ClaimInput, assumptions: dist.Assumptions | None = None, n: int = DEFAULT_N,
             seed: int | None = None, keep_arrays: bool = False) -> dict:
    """Conditional results for every liability scenario, plus a weighted mix only if probabilities were supplied."""
    a = assumptions or dist.load()
    rules = rules_for(claim.policy.jurisdiction)
    d = draw(claim, a, n, seed)
    p_rec, rec_warn = recovery_probabilities(claim, a)
    per = {s.name: evaluate(claim, s, d, a, rules, p_rec) for s in claim.scenarios}
    notes = sorted({note for x in per.values() for note in x.pop("_notes")})
    result = {
        "model_version": MODEL_VERSION,
        "assumptions_version": a.version,
        "assumptions_synthetic": a.synthetic,
        "config": {"n_simulations": n, "seed": seed, "jurisdiction": claim.policy.jurisdiction},
        "scenarios": {name: {"liability": _scenario_desc(s), **stats(per[name], claim.exceedance_thresholds)}
                      for name, s in zip(per, claim.scenarios)},
        "warnings": d.warnings + rec_warn + notes,
    }
    ok, why = can_probability_weight(claim.scenarios)
    if ok:
        probs = np.array([s.probability for s in claim.scenarios])
        idx = np.searchsorted(np.cumsum(probs), d.mix_u, side="right").clip(max=len(probs) - 1)
        mix = {k: np.choose(idx, [per[s.name][k] for s in claim.scenarios]) for k in per[claim.scenarios[0].name]}
        result["probability_weighted"] = {"basis": why, **stats(mix, claim.exceedance_thresholds)}
    else:
        result["probability_weighted"] = None
        result["conditional_only"] = why
    if keep_arrays:
        result["_arrays"] = {"draws": d, "per_scenario": per}
    return result


def _scenario_desc(s: LiabilityScenario) -> dict:
    return {"insured_driver_share": s.insured_driver_share, "av_system_share": s.av_system_share,
            "third_party_share": s.third_party_share, "probability": s.probability,
            "probability_source": s.probability_source, "description": s.description}


def stability(claim: ClaimInput, scenario: str, ns: tuple[int, ...] = (2_500, 5_000, 10_000, 40_000),
              seed: int = 0, assumptions: dist.Assumptions | None = None) -> list[dict]:
    """How the estimates and their standard errors move as the iteration count grows."""
    out = []
    for n in ns:
        s = simulate(claim, assumptions, n, seed)["scenarios"][scenario]
        out.append({"n": n, "expected_net_exposure": s["expected_net_exposure"],
                    "se_expected": s["monte_carlo_error"]["se_expected_net_exposure"],
                    "net_p95": s["net_exposure_percentiles"]["p95"],
                    "se_p95": s["monte_carlo_error"]["se_net_p95_batch_means"]})
    return out
