"""Export side-by-side replay data for viz/web/index.html.

    export_comparison(scenario, av_policy, policy_a, policy_b, path, p_avoid=None)

runs sim.world.run once per policy on the SAME SimScenario and writes:

    {"scenario": {...meta...},
     "runs": {"av": trace, "careful_a": trace, "careful_b": trace},
     "p_avoid": {"careful_a": {"p": .., "ci90": [lo, hi]}, ...}   # only if given
    }

where each trace is {"t": [...], "ego": [[x, y, heading, v], ...], "<actor>": [...],
"result": {collided, t_collision, impact_type, other_actor, ego_speed_at_impact,
relative_speed_at_impact}}. A collided trace ends at the collision step.

Pass p_avoid only from real Monte Carlo output (montecarlo/); never fill it by hand.

`python -m viz.export` regenerates viz/web/sample.json from the test-only cut-in
fixture with TEST_DRIVER params (NOT R157) for both careful panels.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sim.scenario import SimScenario
from sim.world import Policy, SimResult, run


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)


def trace_json(res: SimResult) -> dict[str, Any]:
    out: dict[str, Any] = {"t": [_r(t) for t in res.trace["t"]]}
    for name, rows in res.trace.items():
        if name == "t":
            continue
        out[name] = [[_r(v) for v in row] for row in rows]
    out["result"] = {
        "collided": res.collided,
        "t_collision": _r(res.t_collision),
        "impact_type": res.impact_type,
        "other_actor": res.other_actor,
        "ego_speed_at_impact": _r(res.ego_speed_at_impact),
        "relative_speed_at_impact": _r(res.relative_speed_at_impact),
    }
    return out


def scenario_meta(scenario: SimScenario) -> dict[str, Any]:
    g = scenario.ego_geometry
    return {
        "duration": scenario.duration,
        "dt": scenario.dt,
        "ego_geometry": {"length": g.length, "width": g.width},
        "actors": [{"name": a.name, "length": a.geometry.length, "width": a.geometry.width}
                   for a in scenario.actors],
    }


def export_comparison(scenario: SimScenario, av_policy: Policy, policy_a: Policy, policy_b: Policy,
                      path: str | Path, p_avoid: dict[str, Any] | None = None,
                      meta: dict[str, Any] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "scenario": {**scenario_meta(scenario), **(meta or {})},
        "runs": {
            "av": trace_json(run(scenario, av_policy)),
            "careful_a": trace_json(run(scenario, policy_a)),
            "careful_b": trace_json(run(scenario, policy_b)),
        },
    }
    if p_avoid:
        data["p_avoid"] = p_avoid
    Path(path).write_text(json.dumps(data, separators=(",", ":")))
    return data


def _write_sample() -> None:
    # Hand-built cut-in (tests/test_sim.py geometry); careful panels use the UN R157 Annex 3
    # models (sim/policies/R157_ANNEX3.md). AV profile is illustrative, not from a real report.
    from sim.policies import careful_a, careful_b
    from sim.policies.av_replay import AVReplayPolicy
    from tests.test_sim import cut_in

    gap = 25.0
    av_profile = [(2.4, -4.0)]  # illustrative late, soft braking; not from a real report
    out = Path(__file__).parent / "web" / "sample.json"
    export_comparison(
        cut_in(gap_m=gap),
        AVReplayPolicy(av_profile),
        careful_a.make_policy(),
        careful_b.make_policy(),
        out,
        meta={
            "id": "sample-cut-in",
            "title": f"Cut-in, {gap:.0f} m gap, ego 72 km/h, cutter 43 km/h",
            "label": "illustrative scenario · careful drivers: UN R157 Annex 3",
            "notes": ("Hand-built scenario (tests/test_sim.py cut_in). Careful panels: UN R157 Annex 3 "
                      "Performance models 1 and 2 (sim/policies/R157_ANNEX3.md). AV braking profile "
                      f"{av_profile} is illustrative, not from an SGO report. No P(avoid) shown: "
                      "no Monte Carlo run behind this sample."),
            "crash_type": "cut_in",
        },
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    _write_sample()
