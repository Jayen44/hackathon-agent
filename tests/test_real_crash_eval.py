"""Real-crash eval on SYNTHETIC 100-Car-format time series (no real data needed).

Fixture (not from the dataset): ego and lead at 15 m/s, 30 m gap (THW 2 s); the lead brakes at
6 m/s^2 to a stop at t = 10 s; the "human" ego brakes at 6 m/s^2 either late (t = 12.6 s,
contact) or early (t = 11.0 s, near-crash). The radar target ID changes at t = 8 s with a
0.5 s dropout, to exercise track stitching. Units as in the 100-Car dictionary (mph, ft, ft/s, g).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from eval import real_crash_eval as rce
from sim.data import hundredcar as hc

G = hc.G


def _kin(t, v0, t_brake, decel):
    tb = np.clip(t - t_brake, 0, None)
    t_stop = v0 / decel
    tb_c = np.minimum(tb, t_stop)
    v = np.where(t < t_brake, v0, np.maximum(0.0, v0 - decel * tb))
    x = v0 * np.minimum(t, t_brake) + v0 * tb_c - 0.5 * decel * tb_c ** 2
    a = np.where((t >= t_brake) & (v > 0), -decel, 0.0)
    return x, v, a


def synth_df(human_brake_t: float, trip_id: int = 1, gap0: float = 30.0) -> pd.DataFrame:
    t = np.round(np.arange(0, 20.0, 0.1), 3)
    xe, ve, ae = _kin(t, 15.0, human_brake_t, 6.0)
    xl, vl, _ = _kin(t, 15.0, 10.0, 6.0)
    gap = np.maximum(0.05, xl + gap0 - xe)
    n = len(t)
    d = {"trip_id": trip_id, "sync": np.arange(1, n + 1), "time": t,
         "speed_vehicle_composite": ve / hc.MPH, "speed_gps_horizontal": ve / hc.MPH,
         "longitudinal_accel": ae / G + 0.02,       # +0.02 g accelerometer bias
         "brake_on_off": (ae < 0).astype(int)}
    for k in range(1, 8):
        d[f"radar_forward_ID_{k}"] = 0
        d[f"radar_forward_range_{k}"] = 0.0
        d[f"radar_forward_range_rate_{k}"] = 0.0
        d[f"radar_forward_azimuth_{k}"] = 0.0
    df = pd.DataFrame(d)
    ids = np.where(t < 7.5, 5, np.where(t >= 8.0, 6, 0))
    df["radar_forward_ID_1"] = ids
    df["radar_forward_range_1"] = np.where(ids > 0, gap / hc.FT, 0.0)
    df["radar_forward_range_rate_1"] = np.where(ids > 0, (vl - ve) / hc.FT, 0.0)
    df["radar_forward_azimuth_1"] = 0.01
    return df


def row(severity: str) -> dict:
    return {"sync_start": 101, "sync_end": 150, "severity": severity,
            "precipitating_event": "Other vehicle ahead - slowed and stopped 2 seconds or less",
            "event_nature": "Conflict with a lead vehicle", "incident_type": "Rear-end, striking"}


def test_selection_rule():
    assert hc.is_lead_rear_end(row("Crash"))
    r = dict(row("Crash"), precipitating_event="Other vehicle lane change - left in front of subject")
    assert not hc.is_lead_rear_end(r)


def test_extract_units_and_stitching():
    ev, why = hc.extract_lead_event(synth_df(12.6), row("Crash"), 1)
    assert ev is not None, why
    assert ev.meta["stitched_tracks"] == 1
    assert ev.meta["pre_s"] == pytest.approx(5.0)
    assert ev.ego_v[0] == pytest.approx(15.0, abs=0.05)
    assert ev.lead_v[0] == pytest.approx(15.0, abs=0.05)
    assert ev.gap[0] == pytest.approx(30.0, abs=0.1)
    assert abs(ev.meta["accel_bias_mps2"] - 0.02 * G) < 0.1      # bias removed
    lp = hc.lead_accel_profile(ev)
    assert min(a for _, a in lp) == pytest.approx(-6.0, abs=0.8)
    assert lp[-1][1] == 0.0                                    # holds speed after the track ends


def test_human_throttle_drops_human_braking():
    ev, _ = hc.extract_lead_event(synth_df(12.6), row("Crash"), 1)
    prof = rce.human_throttle_profile(ev)
    assert all(abs(a) < 0.5 for _, a in prof)                 # human only braked; throttle ~0


def test_reproduction_and_counterfactual():
    crash, _ = hc.extract_lead_event(synth_df(12.6, trip_id=1), row("Crash"), 1)
    near, _ = hc.extract_lead_event(synth_df(11.0, trip_id=2), row("Near-Crash"), 2)
    res = rce.evaluate_events([crash, near], n=8, seed=0, variants=("human_throttle",))
    by = {e["event_id"]: e for e in res["events"]}
    assert by[1]["reproduction"]["reproduced"] and by[2]["reproduction"]["reproduced"]
    assert by[1]["reproduction"]["gap_rmse_m"] < 1.5
    # THW 2 s and a 6 m/s^2 lead stop: R157 3.3.4.3 says PM1 avoids up to 1 g here; PM2 too.
    for d in ("careful_a", "careful_b"):
        assert by[1]["counterfactual"]["human_throttle"][d]["p_avoid"] >= 0.5
        assert by[2]["counterfactual"]["human_throttle"][d]["p_avoid"] >= 0.5
    s = res["summary"]["crash"]
    assert s["n_events"] == 1 and s["reproduction"]["within_5_attempts"] == 1
    sh = s["avoidance_all"]["human_throttle"]["careful_b"]
    assert sh["avoided"] == 1 and 0 < sh["ci90"][0] < 1 and sh["ci90"][1] == 1.0
