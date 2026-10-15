"""Demo claims: synthetic but internally consistent bundles (insurance schema 0.1).

The insurance team's examples share one template impact speed, so none reproduces in
the sim and none can reach "pursue". These demo claims derive the reported outcome
(impact speed, crash time) from the AV replay of the stated control inputs, so the
evidence is self-consistent. Every bundle is labelled synthetic. Monetary figures
(paid amount, contributory negligence) are illustrative claim-file inputs, not data.

    python -m fleet.demo_claims        # writes fleet/data/demo_claims.json
"""
from __future__ import annotations

import copy
import json
import pathlib

import numpy as np

from montecarlo.evidence import ranges_from_bundle
from montecarlo.ranges import PARAM_NAMES, av_replay_policy, build_scenario, values_from_u
from sim.world import run

HERE = pathlib.Path(__file__).parent
OUT = HERE / "data" / "demo_claims.json"
T0 = 100.0  # conflict t_start on the bundle clock

VEHICLE = {
    "software_version": "2.4.1", "approved_software": ["2.4.1"], "software_verified": True,
    "occupant": "user_in_charge",
    "mode_events": [{"t": 0.0, "mode": "manual"}, {"t": 40.0, "mode": "automated"}],
    "handover": {"demand_t": None, "human_response_t": None},
    "driver_monitoring": [{"t": 95.0, "eyes_on_road": True, "hands_on_wheel": False}],
    "faults": [], "odd_inside": True,
}
BASE = {
    "schema_version": "0.1", "synthetic": True, "jurisdiction": "UK",
    "perception": {"sensors": ["camera", "lidar", "radar"], "decision_log_present": True,
                   "objects": [{"id": "hazard1", "cls": "vehicle", "first_detected_t": T0, "confidence": 0.95}]},
    "external": {"cctv": ["street_cam_demo"], "witnesses": 1, "police_report": True, "medical_records": True,
                 "weather": "dry", "lighting": "daylight"},
    "integrity": {"hashes_present": True, "chain_of_custody": True,
                  "clock_offsets_s": {"vehicle_log": 0.0, "camera": 0.02, "cctv": 0.1}, "log_gaps": [], "tamper_flag": False},
}

# (case_id, conflict, AV brake input (seconds after t_start, brake 0..1), injury, paid GBP, CN range, story)
SPECS = [
    ("DEMO-1_queue_late_brake",
     {"kind": "constant_hazard", "crash_type": "lead_vehicle_decel", "ego_speed_mps": 17.9, "gap_m": 55.0,
      "hazard_speed_mps": 0.0, "friction_mu": 0.8},
     (2.6, 0.45), "Serious", 62000, [0.0, 0.05],
     "AV approaches a stationary queue visible from 55 m at 40 mph and brakes late and softly."),
    ("DEMO-2_lead_brake_late_response",
     {"kind": "lead_braking", "crash_type": "lead_vehicle_decel", "ego_speed_mps": 22.0, "gap_m": 30.0,
      "hazard_speed_mps": 22.0, "hazard_decel_mps2": 5.5, "friction_mu": 0.8},
     (2.2, 0.5), "Serious", 54000, [0.0, 0.1],
     "Vehicle ahead brakes firmly at 50 mph; AV responds 2.2 s later with partial braking."),
    ("DEMO-3_cut_in_ample_gap",
     {"kind": "cut_in", "crash_type": "cut_in", "ego_speed_mps": 20.0, "gap_m": 32.0,
      "hazard_speed_mps": 12.0, "t_in_path_s": 2.0, "friction_mu": 0.8},
     (3.2, 0.4), "Serious", 72000, [0.0, 0.1],
     "Slower car merges 32 m ahead; AV keeps speed until it is in lane and brakes too gently."),
]


def make(case_id, conflict, brake, injury, paid, cn, story) -> dict:
    t_b, level = brake
    b = copy.deepcopy(BASE)
    b["case_id"] = case_id
    b["_fleet_source"] = "demo"
    b["_fleet_label"] = "synthetic demo claim (self-consistent; values illustrative)"
    b["narrative"] = story + " Synthetic demo claim."
    b["vehicle"] = copy.deepcopy(VEHICLE)
    b["vehicle"]["control_inputs"] = [{"t": T0 + t_b, "source": "system", "brake": level, "throttle": 0.0, "steer": 0.0}]
    b["conflict"] = {"hazard_id": "hazard1", "t_start": T0, **conflict}
    b["t_crash"] = T0 + 10.0
    b["outcome"] = {"collided": True, "impact_speed_mps": 0.0}
    # Reported outcome = AV replay of the stated inputs at the median of every range.
    ranges, _ = ranges_from_bundle(b, tier=2)
    v = values_from_u(ranges, np.full(len(PARAM_NAMES), 0.5))
    r = run(build_scenario(ranges, v), av_replay_policy(ranges, v), record_trace=False)
    if not r.collided:
        raise ValueError(f"{case_id}: AV replay does not collide; adjust the spec")
    b["t_crash"] = round(T0 + r.t_collision, 2)
    b["outcome"] = {"collided": True, "impact_speed_mps": round(r.ego_speed_at_impact, 2),
                    "injury_severity": injury, "paid_claim_gbp": paid, "third_party_share": cn}
    return b


def build() -> list[dict]:
    return [make(*s) for s in SPECS]


if __name__ == "__main__":
    bs = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bs, indent=1) + "\n")
    for b in bs:
        print(b["case_id"], "impact", b["outcome"]["impact_speed_mps"], "m/s at t+", round(b["t_crash"] - T0, 2), "s")
