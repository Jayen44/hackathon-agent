"""Regenerate insurance/examples/*.json (synthetic crash bundles, one per decision path).

    python scripts/make_examples.py            # writes into insurance/examples
Edit the cases here, never the JSON by hand. `python -m insurance.gaps` lists decision paths with no example.
"""
import copy
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "insurance" / "examples")
out.mkdir(parents=True, exist_ok=True)

base = {
    "schema_version": "0.1",
    "case_id": "base",
    "synthetic": True,
    "t_crash": 100.0,
    "jurisdiction": "UK",
    "vehicle": {
        "software_version": "2.4.1",
        "approved_software": ["2.4.1"],
        "occupant": "user_in_charge",
        "mode_events": [{"t": 0.0, "mode": "manual"}, {"t": 40.0, "mode": "automated"}],
        "handover": {"demand_t": None, "human_response_t": None},
        "driver_monitoring": [{"t": 90.0, "eyes_on_road": True, "hands_on_wheel": False},
                              {"t": 98.0, "eyes_on_road": True, "hands_on_wheel": False}],
        "control_inputs": [{"t": 98.5, "source": "system", "brake": 0.4, "throttle": 0.0, "steer": 0.0},
                           {"t": 99.5, "source": "system", "brake": 0.9, "throttle": 0.0, "steer": 0.0}],
        "faults": [],
        "odd_inside": True,
        "software_verified": True,   # someone confirmed: no alteration, safety-critical updates current
    },
    "perception": {
        "sensors": ["camera", "lidar", "radar"],
        "objects": [{"id": "obstacle1", "cls": "stationary_vehicle", "first_detected_t": 97.0, "confidence": 0.9}],
        "decision_log_present": True,
    },
    "external": {"cctv": ["street_cam_12"], "witnesses": 2, "police_report": True, "medical_records": False,
                 "weather": "dry", "lighting": "daylight"},
    "integrity": {"hashes_present": True, "chain_of_custody": True,
                  "clock_offsets_s": {"vehicle_log": 0.0, "camera": 0.02, "cctv": 0.12},
                  "log_gaps": [], "tamper_flag": False},
    # Hazard visible to a human ~ 40 m ahead at ~30 mph. The system only detected it at t=97 (3 s later).
    "conflict": {"hazard_id": "obstacle1", "t_start": 94.0, "ego_speed_mps": 13.4, "gap_m": 40.0,
                 "hazard_speed_mps": 0.0, "friction_mu": 0.7},
    "outcome": {"collided": True, "impact_speed_mps": 9.0, "injury_severity": "Slight"},
}


G = 9.81


def _simulate(d):
    """Ego braking from the logged control inputs vs the hazard. Returns (t_impact, impact_speed) or None.
    Brake -> deceleration = brake * mu * g (a synthetic simplification, same spirit as the engine's own kinematics)."""
    c = d["conflict"]
    mu, kind = c.get("friction_mu", 0.7), c.get("kind", "constant_hazard")
    ins = sorted((i for i in d["vehicle"]["control_inputs"] if i.get("brake") is not None), key=lambda i: i["t"])
    t, v, gap, vh = c["t_start"], c["ego_speed_mps"], c["gap_m"], c["hazard_speed_mps"]
    a_h = c.get("hazard_decel_mps2", 0.0) if kind == "lead_braking" else 0.0
    t_in = c["t_start"] + (c.get("t_in_path_s", 0.0) if kind == "cut_in" else 0.0)
    dt = 0.001
    while t < c["t_start"] + 30:
        b = 0.0
        for i in ins:
            if i["t"] <= t:
                b = i["brake"]
        v = max(0.0, v - b * mu * G * dt)
        vh = max(0.0, vh - a_h * dt)
        gap += (vh - v) * dt
        t += dt
        if t >= t_in and gap <= 0:
            return t, v
        if v == 0.0 and t > t_in:
            return None
    return None


def settle(d, det_off=1.8):
    """Make the bundle's timeline self-consistent: the hazard is detected det_off s after t_start, braking follows,
    the simulated impact lands exactly on t_crash, and outcome.impact_speed_mps is the simulated impact speed.
    (Hand-typed values used to contradict each other: see issue #20.)"""
    if not d["outcome"].get("collided") or not d.get("conflict"):
        return
    c = d["conflict"]
    det = c["t_start"] + det_off
    for o in d["perception"]["objects"]:
        if o["id"] == c["hazard_id"]:
            o["first_detected_t"] = det
    new = []
    for i in d["vehicle"]["control_inputs"]:
        i = dict(i)
        if i["source"] == "system":
            continue
        i["t"] = c["t_start"] + 2.3 if i.get("brake", 0) else det + 0.5   # late human brake / human steer override
        new.append(i)
    if any(i["source"] == "system" for i in d["vehicle"]["control_inputs"]):
        new += [{"t": det + 0.3, "source": "system", "brake": 0.4, "throttle": 0.0, "steer": 0.0},
                {"t": det + 0.8, "source": "system", "brake": 0.9, "throttle": 0.0, "steer": 0.0}]
    d["vehicle"]["control_inputs"] = sorted(new, key=lambda i: i["t"])
    r = _simulate(d)
    if r is None:
        raise SystemExit(f"{d['case_id']}: no collision in the settled timeline; adjust the case")
    shift = d["t_crash"] - r[0]
    c["t_start"] = round(c["t_start"] + shift, 3)
    for o in d["perception"]["objects"]:
        if o["id"] == c["hazard_id"]:
            o["first_detected_t"] = round(o["first_detected_t"] + shift, 3)
    for i in d["vehicle"]["control_inputs"]:
        i["t"] = round(i["t"] + shift, 3)
    d["outcome"]["impact_speed_mps"] = round(r[1], 2)


CASES = {}
DET_OFF = {"17_cut_in_avoidable": 3.8, "21_pursue_cut_in": 3.8, "05_unavoidable_close_cutin": 0.2, "16_lead_braking_unavoidable": 0.1, "18_cut_in_unavoidable": 0.2}


def case(name):
    def deco(fn):
        CASES[name] = fn
        return fn
    return deco


@case("01_av_late_detection")
def _(b): pass


@case("02_human_driving_manual")
def _(b):
    b["vehicle"]["mode_events"] = [{"t": 0.0, "mode": "manual"}]
    b["vehicle"]["control_inputs"] = [{"t": 99.0, "source": "human", "brake": 1.0}]


@case("03_handover_ignored_by_human")
def _(b):
    b["vehicle"]["handover"] = {"demand_t": 80.0, "human_response_t": None}
    b["vehicle"]["driver_monitoring"] = [{"t": 82.0, "eyes_on_road": False, "hands_on_wheel": False},
                                         {"t": 95.0, "eyes_on_road": False, "hands_on_wheel": False}]


@case("04_handover_too_short")
def _(b):
    b["vehicle"]["handover"] = {"demand_t": 97.0, "human_response_t": None}


@case("05_unavoidable_close_cutin")
def _(b):
    b["conflict"].update(gap_m=10.0, crash_type="cut_in", t_start=99.2)
    b["outcome"]["impact_speed_mps"] = 12.0


@case("06_borderline_needs_review")
def _(b):
    b["conflict"]["gap_m"] = 28.0


@case("07_outside_odd")
def _(b):
    b["vehicle"]["odd_inside"] = False


@case("08_integrity_failure")
def _(b):
    b["integrity"]["tamper_flag"] = True
    b["integrity"]["clock_offsets_s"]["cctv"] = 1.8


@case("09_human_override")
def _(b):
    b["vehicle"]["control_inputs"].append({"t": 99.0, "source": "human", "brake": 0.0, "throttle": 0.0, "steer": 0.4})


@case("10_critical_fault")
def _(b):
    b["vehicle"]["faults"] = [{"t": 96.0, "code": "LIDAR_FRONT_DEGRADED", "severity": "critical"}]


@case("11_no_collision")
def _(b):
    b["outcome"] = {"collided": False}


@case("12_missing_conflict")
def _(b):
    b["conflict"] = None


@case("13_unapproved_software")
def _(b):
    b["vehicle"]["software_version"] = "9.9.9-dev"


@case("14_human_took_control_in_time")
def _(b):
    b["vehicle"]["handover"] = {"demand_t": 90.0, "human_response_t": 95.0}


@case("15_lead_braking_avoidable")
def _(b):
    b["conflict"] = {"hazard_id": "lead1", "kind": "lead_braking", "t_start": 94.0, "ego_speed_mps": 20.0,
                     "gap_m": 30.0, "hazard_speed_mps": 20.0, "hazard_decel_mps2": 6.0, "friction_mu": 0.7}
    b["perception"]["objects"] = [{"id": "lead1", "cls": "car", "first_detected_t": 96.5, "confidence": 0.95}]


@case("16_lead_braking_unavoidable")
def _(b):
    b["conflict"] = {"hazard_id": "lead1", "kind": "lead_braking", "t_start": 99.0, "ego_speed_mps": 20.0,
                     "gap_m": 15.0, "hazard_speed_mps": 20.0, "hazard_decel_mps2": 8.0, "friction_mu": 0.7}
    b["perception"]["objects"] = [{"id": "lead1", "cls": "car", "first_detected_t": 99.1, "confidence": 0.95}]


@case("17_cut_in_avoidable")
def _(b):
    b["conflict"] = {"hazard_id": "cutter1", "kind": "cut_in", "t_start": 94.0, "ego_speed_mps": 20.0,
                     "gap_m": 40.0, "hazard_speed_mps": 12.0, "t_in_path_s": 1.0, "friction_mu": 0.7}
    b["perception"]["objects"] = [{"id": "cutter1", "cls": "car", "first_detected_t": 97.0, "confidence": 0.9}]


@case("18_cut_in_unavoidable")
def _(b):
    b["conflict"] = {"hazard_id": "cutter1", "kind": "cut_in", "t_start": 99.3, "ego_speed_mps": 20.0,
                     "gap_m": 12.0, "hazard_speed_mps": 10.0, "t_in_path_s": 0.3, "friction_mu": 0.7}
    b["perception"]["objects"] = [{"id": "cutter1", "cls": "car", "first_detected_t": 99.5, "confidence": 0.9}]


@case("21_pursue_cut_in")
def _(b):
    """Clean demo 'Pursue': AV-at-fault cut-in, reproducible timeline, paid amount known, injured party's share assessed."""
    CASES["17_cut_in_avoidable"](b)
    b["outcome"].update(injury_severity="Serious", paid_claim_gbp=60000, third_party_share=[0.0, 0.1])


@case("22_pursue_lead_braking")
def _(b):
    CASES["15_lead_braking_avoidable"](b)
    b["outcome"].update(injury_severity="Serious", paid_claim_gbp=80000, third_party_share=[0.0, 0.1])


@case("19_s4_unauthorised_software_change")
def _(b):
    b["vehicle"]["unauthorised_software_change"] = True


@case("20_s3_2_engaged_when_inappropriate")
def _(b):
    b["vehicle"]["engaged_when_inappropriate"] = True   # verdict still follows the evidence; exclusion is flagged


if __name__ == "__main__":
    for name, mutate in CASES.items():
        d = copy.deepcopy(base)
        d["case_id"] = name
        mutate(d)
        settle(d, DET_OFF.get(name, 1.8))
        (out / f"{name}.json").write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(CASES)} bundles to {out}")
