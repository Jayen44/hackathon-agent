from sim.policies.av_replay import AVReplayPolicy
from sim.scenario import LateralManoeuvre, ScriptedActor, SimScenario
from sim.vehicle import Geometry, VehicleState
from sim.world import run
from viz.isaac.export_trace import export

CAR = Geometry(length=4.5, width=1.8, wheelbase=2.7)


def test_export_shape_matches_renderer_contract():
    cutter = ScriptedActor("cutter", CAR, VehicleState(19.5, 3.5, 0.0, 12.0),
                           lateral=LateralManoeuvre(0.5, 2.0, 3.5, 0.0))
    scen = SimScenario(CAR, VehicleState(0.0, 0.0, 0.0, 20.0), [cutter], duration=5.0)
    r = run(scen, AVReplayPolicy([]))
    doc = export(r, scen, "t")
    assert set(doc["actors"]) == {"ego", "cutter"}
    n = len(doc["t"])
    assert all(len(a["states"]) == n and len(a["states"][0]) == 4 for a in doc["actors"].values())
    assert doc["actors"]["ego"]["length"] == 4.5
    assert doc["meta"]["collided"] and doc["meta"]["other_actor"] == "cutter"
    assert doc["lane_centres"] == [0.0, 3.5]
