"""Counterfactual analyst: Monte Carlo P(avoid) for careful-driver models.

Common random numbers: every driver is evaluated on the SAME sampled crashes
(same uniform rows -> same SimScenario), so A vs B is a paired comparison and
the A-B difference is not polluted by sampling noise.

Determinism: results depend only on (ranges, drivers, seed, n / adaptive
settings). Chunking (local or Modal fan-out) does not change results, because
sample i is a pure function of (seed, i) and each run resets the policy.

Uncertainty: P(avoid) comes with a Wilson score interval (90% by default).
This is Monte Carlo uncertainty over the parameter ranges only; it does not
cover sim-to-real gap or driver-model choice (that is what the A/B bracket is for).
"""
from __future__ import annotations

import math
from collections import Counter
from statistics import NormalDist
from typing import Callable, Iterable

import numpy as np

from montecarlo.ranges import (ScenarioRanges, av_replay_policy, build_scenario, draw_uniforms,
                               values_from_u)
from sim.reproduce import ReportedOutcome, check
from sim.world import Policy, run

PolicyFactory = Callable[[], Policy]
# map_fn(ranges, factories, chunks) -> per-chunk evaluate_chunk() results, in order.
MapFn = Callable[[ScenarioRanges, dict, list], Iterable]

DEFAULT_CHUNK = 250


def wilson(k: int, n: int, conf: float = 0.90) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials."""
    if n == 0:
        return 0.0, 1.0
    z = NormalDist().inv_cdf(1 - (1 - conf) / 2)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def evaluate_chunk(ranges: ScenarioRanges, factories: dict[str, PolicyFactory],
                   u: np.ndarray) -> dict[str, list[bool]]:
    """Collision outcome per driver for each uniform row. Pure; safe to run remotely.

    A run that ends still closing on an in-lane vehicle counts as NOT avoided
    (conservative: it lowers P(avoid), i.e. never overstates the recovery case).
    """
    policies = {name: f() for name, f in factories.items()}
    out: dict[str, list[bool]] = {name: [] for name in factories}
    for row in u:
        scenario = build_scenario(ranges, values_from_u(ranges, row))
        for name, pol in policies.items():
            r = run(scenario, pol, record_trace=False)
            out[name].append(r.collided or r.ended_closing)
    return out


def _chunks(u: np.ndarray, size: int) -> list[np.ndarray]:
    return [u[i:i + size] for i in range(0, len(u), size)]


def _evaluate(ranges, factories, u, map_fn: MapFn | None, chunk: int) -> dict[str, np.ndarray]:
    if len(u) == 0:
        return {n: np.zeros(0, bool) for n in factories}
    chunks = _chunks(u, chunk)
    if map_fn is None:
        parts = [evaluate_chunk(ranges, factories, c) for c in chunks]
    else:
        parts = list(map_fn(ranges, factories, chunks))
    return {n: np.array([x for p in parts for x in p[n]], dtype=bool) for n in factories}


def summarise(collided: np.ndarray, conf: float = 0.90) -> dict:
    n = int(len(collided))
    collisions = int(collided.sum())
    lo, hi = wilson(n - collisions, n, conf)
    return {"p": (n - collisions) / n if n else float("nan"), "ci90": (lo, hi), "n": n,
            "collisions": collisions, "half_width": (hi - lo) / 2}


def compare(ranges: ScenarioRanges, factories: dict[str, PolicyFactory], n: int = 1000, seed: int = 0,
            *, target_half_width: float | None = None, n_max: int = 20000, batch: int = 500,
            map_fn=None, chunk: int = DEFAULT_CHUNK, keep_outcomes: bool = False) -> dict:
    """P(avoid) for several drivers on the same samples (common random numbers).

    Fixed mode (target_half_width=None): exactly n samples.
    Adaptive mode: start with n, add `batch` samples at a time until every
    driver's CI90 half-width <= target_half_width, or n_max is reached. The
    samples used are always a prefix of the same seeded stream, so adaptive
    and fixed runs with the same final n agree exactly.

    map_fn: optional fan-out, called as map_fn(ranges, factories, chunks) and
    returning per-chunk evaluate_chunk() results in order (see modal_fanout).
    """
    if not factories:
        raise ValueError("no drivers")
    total = n if target_half_width is None else max(n, n_max)
    u_all = draw_uniforms(total, seed)
    outcomes = _evaluate(ranges, factories, u_all[:n], map_fn, chunk)
    used = n
    if target_half_width is not None:
        while used < n_max and any(summarise(c)["half_width"] > target_half_width
                                   for c in outcomes.values()):
            step = min(batch, n_max - used)
            more = _evaluate(ranges, factories, u_all[used:used + step], map_fn, chunk)
            outcomes = {k: np.concatenate([outcomes[k], more[k]]) for k in outcomes}
            used += step

    res: dict = {"n": used, "seed": seed, "adaptive": target_half_width is not None,
                 "target_half_width": target_half_width,
                 "drivers": {k: summarise(c) for k, c in outcomes.items()}}
    names = list(factories)
    if len(names) >= 2:
        a, b = names[0], names[1]
        av_a, av_b = ~outcomes[a], ~outcomes[b]
        res["paired"] = {"drivers": (a, b),
                         "both_avoid": int((av_a & av_b).sum()),
                         f"only_{a}_avoids": int((av_a & ~av_b).sum()),
                         f"only_{b}_avoids": int((~av_a & av_b).sum()),
                         "neither_avoids": int((~av_a & ~av_b).sum()),
                         "p_diff": float(av_a.mean() - av_b.mean())}
    if keep_outcomes:
        res["outcomes"] = {k: v.tolist() for k, v in outcomes.items()}
    return res


def p_avoid(ranges: ScenarioRanges, policy_factory: PolicyFactory, n: int = 1000, seed: int = 0,
            *, target_half_width: float | None = None, n_max: int = 20000, **kw) -> dict:
    """{p, ci90: (lo, hi), n, collisions, half_width} for one driver. See compare()."""
    return compare(ranges, {"driver": policy_factory}, n, seed, target_half_width=target_half_width,
                   n_max=n_max, **kw)["drivers"]["driver"]


def p_avoid_adaptive(ranges: ScenarioRanges, policy_factory: PolicyFactory, seed: int = 0,
                     target_half_width: float = 0.05, n_start: int = 200, n_max: int = 20000,
                     **kw) -> dict:
    return p_avoid(ranges, policy_factory, n_start, seed, target_half_width=target_half_width,
                   n_max=n_max, **kw)


def reproduce_rate(ranges: ScenarioRanges, av_policy: Policy | None, reported: ReportedOutcome,
                   n: int = 200, seed: int = 0) -> dict:
    """Share of samples where the AV replay reproduces the reported outcome.

    av_policy=None builds the AV replay per sample from ranges.av_brake_start /
    av_decel (constant speed if unset). Returns {rate, ci90, n, reproduced,
    mismatches: {kind: count}} for the Reconstructor to decide which range to revise.
    """
    u = draw_uniforms(n, seed)
    ok = 0
    mism: Counter = Counter()
    for row in u:
        v = values_from_u(ranges, row)
        pol = av_policy if av_policy is not None else av_replay_policy(ranges, v)
        c = check(run(build_scenario(ranges, v), pol, record_trace=False), reported)
        ok += c.reproduced
        mism.update(m.split(":", 1)[0] for m in c.mismatches)
    return {"rate": ok / n if n else float("nan"), "ci90": wilson(ok, n), "n": n,
            "reproduced": ok, "mismatches": dict(mism)}
