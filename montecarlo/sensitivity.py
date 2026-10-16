"""One-at-a-time sensitivity of P(avoid) to each parameter range (tornado data).

For each parameter with a non-degenerate range, pin it at its low end and at
its high end (all other parameters keep their ranges) and recompute P(avoid)
on the SAME seeded samples (common random numbers). The swing |P(hi) - P(lo)|
says which fact, if pinned down, would most change the recovery case. The top
non-reported parameter is the fact the claims handler should go and get
(e.g. request the vehicle logs for the cut-in gap).
"""
from __future__ import annotations

from montecarlo.counterfactual import PolicyFactory, compare
from montecarlo.ranges import ScenarioRanges


def tornado(ranges: ScenarioRanges, factories: dict[str, PolicyFactory] | PolicyFactory,
            n: int = 500, seed: int = 0, params: list[str] | None = None, **kw) -> dict:
    """Returns {baseline: {driver: p}, rows: [...sorted by swing desc], go_get: name | None}.

    Each row: {param, source, lo, hi, p_at_lo: {driver: p}, p_at_hi: {...}, swing}
    where swing is the max over drivers of |p_at_hi - p_at_lo|.
    """
    if callable(factories):
        factories = {"driver": factories}
    base = compare(ranges, factories, n, seed, **kw)["drivers"]
    rows = []
    for name, r in ranges.params().items():
        if params is not None and name not in params:
            continue
        if r.width == 0 or name in ("av_brake_start", "av_decel"):
            continue
        at = {}
        for end, val in (("lo", r.lo), ("hi", r.hi)):
            res = compare(ranges.with_param(name, r.pinned(val)), factories, n, seed, **kw)["drivers"]
            at[end] = {d: x["p"] for d, x in res.items()}
        swing = max(abs(at["hi"][d] - at["lo"][d]) for d in factories)
        rows.append({"param": name, "source": r.source, "lo": r.lo, "hi": r.hi,
                     "p_at_lo": at["lo"], "p_at_hi": at["hi"], "swing": swing})
    rows.sort(key=lambda x: -x["swing"])
    go_get = next((x["param"] for x in rows if x["source"] != "reported" and x["swing"] > 0), None)
    return {"baseline": {d: x["p"] for d, x in base.items()}, "n": n, "seed": seed,
            "rows": rows, "go_get": go_get}
