"""Turn a sim/ SimResult trace into the JSON viz/isaac/render_trace.py takes.

Format:
    {
      "name": str, "dt": float, "t": [...],
      "lane_width": 3.5, "lane_centres": [0.0, 3.5],
      "actors": {"ego": {"length", "width", "height", "states": [[x, y, heading, v], ...]}, ...},
      "meta": {"collided", "t_collision", "impact_type", "other_actor",
               "ego_speed_at_impact", "relative_speed_at_impact", "policy", "label"}
    }

    python -m viz.isaac.export_trace          # regenerates viz/isaac/samples/*.json
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import asdict

from sim.scenario import SimScenario
from sim.world import SimResult


def export(result: SimResult, scenario: SimScenario, name: str, *, policy: str = "",
           label: str = "", lane_width: float = 3.5,
           lane_centres: list[float] | None = None) -> dict:
    tr = result.trace
    geoms = {"ego": scenario.ego_geometry, **{a.name: a.geometry for a in scenario.actors}}
    actors = {}
    for key, states in tr.items():
        if key == "t":
            continue
        g = geoms.get(key)
        actors[key] = {
            "length": g.length if g else 4.5,
            "width": g.width if g else 1.8,
            "height": 1.5,
            "states": [[round(float(v), 4) for v in s] for s in states],
        }
    meta = {k: v for k, v in asdict(result).items() if k != "trace"}
    meta.update(policy=policy, label=label)
    if lane_centres is None:
        ys = [s[1] for a in actors.values() for s in a["states"]]
        lane_centres = sorted({round(y / lane_width) * lane_width for y in ys} | {0.0})
    return {
        "name": name,
        "dt": scenario.dt,
        "t": [round(float(x), 4) for x in tr["t"]],
        "lane_width": lane_width,
        "lane_centres": lane_centres,
        "actors": actors,
        "meta": meta,
    }


def write(doc: dict, path: str | pathlib.Path) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, separators=(",", ":")))
    return p


def _samples() -> None:
    """Sample traces for the render pipeline. ILLUSTRATIVE ONLY.

    Uses the test-only driver fixture from tests/test_sim.py (NOT R157 values)
    and a hand-built cut-in, not a real SGO crash. Do not quote these numbers.
    """
    from sim.policies.av_replay import AVReplayPolicy
    from sim.policies.careful_base import DriverParams, ReactiveBrakingDriver
    from sim.scenario import LateralManoeuvre, ScriptedActor
    from sim.vehicle import Geometry, VehicleState
    from sim.world import run

    car = Geometry(length=4.5, width=1.8, wheelbase=2.7)
    # Same values as tests/test_sim.py TEST_DRIVER. Test fixture, not R157.
    test_driver = DriverParams(reaction_time=0.75, max_decel=7.0, jerk=20.0,
                               ttc_threshold=3.0, lateral_margin=0.3, lead_decel_threshold=2.0)
    gap = 25.0
    cutter = ScriptedActor("cutter", car, VehicleState(gap + car.length, 3.5, 0.0, 12.0),
                           lateral=LateralManoeuvre(t_start=0.5, duration=2.0, y_from=3.5, y_to=0.0))
    scen = SimScenario(car, VehicleState(0.0, 0.0, 0.0, 20.0), [cutter], duration=8.0)

    out = pathlib.Path(__file__).parent / "samples"
    label = "SAMPLE: hand-built cut-in, test-fixture driver params (not R157, not a real crash)"
    for name, policy, pol_name in [
        ("cut_in_av_replay", AVReplayPolicy([(0.0, 0.0), (2.2, -3.0)]), "av_replay (late, soft braking)"),
        ("cut_in_careful_test", ReactiveBrakingDriver(test_driver), "careful (TEST fixture params)"),
    ]:
        r = run(scen, policy)
        p = write(export(r, scen, name, policy=pol_name, label=label, lane_centres=[0.0, 3.5]), out / f"{name}.json")
        print(f"{p}: collided={r.collided} t={r.t_collision} impact={r.impact_type} "
              f"steps={len(r.trace['t'])}")


if __name__ == "__main__":
    _samples()
