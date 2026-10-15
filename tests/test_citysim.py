"""Tests for sim/data/citysim.py on a tiny synthetic CitySim-format fixture.

Everything here is synthetic test data (NOT CitySim data, NOT R157 values):
lane width, speeds, gaps and the wheelbase are fixture choices.
"""
import math

import numpy as np
import pandas as pd
import pytest

from sim.data import citysim as cs
from sim.policies.av_replay import AVReplayPolicy
from sim.scenario import LateralManoeuvre
from sim.world import run

FPS = 30.0
DURATION = 10.0
LANE_W = 3.6            # fixture lane width (m)
L, W = 4.5, 1.8         # fixture vehicle size (m)
ROAD_ANGLE = math.radians(30.0)  # road axis in the fixture's global frame
LANE_CENTRES = {1: 0.0, 2: LANE_W, 3: -LANE_W}
TH = cs.EventThresholds()  # defaults, as a caller would start


def _speed_profile(v0: float, segments: list[tuple[float, float]], t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exact s(t), v(t) for piecewise-constant accel [(t_start, a)], v clamped at 0."""
    dt = 1e-3
    tt = np.arange(0.0, t[-1] + dt, dt)
    a = np.zeros_like(tt)
    for t0, acc in segments:
        a[tt >= t0] = acc
    v = np.maximum(v0 + np.concatenate([[0], np.cumsum(a[:-1] * dt)]), 0.0)
    s = np.concatenate([[0], np.cumsum((v[:-1] + v[1:]) / 2 * dt)])
    return np.interp(t, tt, s), np.interp(t, tt, v)


def _vehicle(vid, s0, n_of_t, v0, segments, t, direction=1, lane_override=None):
    s, v = _speed_profile(v0, segments, t)
    s = s0 + direction * s
    n = n_of_t(t)
    dn = np.gradient(n, t)
    hdg = np.arctan2(dn, np.maximum(v, 1e-3)) + (0 if direction == 1 else math.pi)
    return dict(id=vid, s=s, n=n, v=v, hdg=hdg, lane_override=lane_override)


def _lane_of(n):
    keys = np.array(list(LANE_CENTRES))
    cents = np.array(list(LANE_CENTRES.values()))
    return keys[np.argmin(np.abs(n[:, None] - cents[None, :]), axis=1)]


def _to_rows(veh, t, with_lane=True):
    ux, uy = math.cos(ROAD_ANGLE), math.sin(ROAD_ANGLE)
    nx, ny = -uy, ux

    def g(s, n):  # road (s, n) metres -> global feet
        return (s * ux + n * nx) / cs.FT_TO_M, (s * uy + n * ny) / cs.FT_TO_M

    road_h = veh["hdg"]
    cx, cy = veh["s"], veh["n"]
    fx, fy = np.cos(road_h), np.sin(road_h)    # forward, road frame
    lx, ly = -fy, fx                            # left
    rows = {"frameNum": np.round(t * FPS).astype(int), "carId": veh["id"]}
    for name, (a, b) in {"carCenter": (0, 0), "head": (L / 2, 0), "tail": (-L / 2, 0),
                         "boundingBox1": (L / 2, -W / 2), "boundingBox2": (-L / 2, -W / 2),
                         "boundingBox3": (-L / 2, W / 2), "boundingBox4": (L / 2, W / 2)}.items():
        X, Y = g(cx + a * fx + b * lx, cy + a * fy + b * ly)
        rows[f"{name}Xft"], rows[f"{name}Yft"] = X, Y
    rows["speed"] = veh["v"] / cs.MPH_TO_MPS
    if with_lane:
        rows["laneId"] = veh["lane_override"] if veh["lane_override"] is not None else _lane_of(veh["n"])
    return pd.DataFrame(rows)


CUT = LateralManoeuvre(t_start=2.0, duration=2.0, y_from=LANE_W, y_to=0.0)


def _fixture(with_lane=True):
    t = np.arange(0, DURATION + 1e-9, 1 / FPS)
    vehicles = [
        # Cut-in: cutter from lane 2 into lane 1 ahead of follower 1, which then brakes.
        _vehicle(1, 0.0, lambda t: np.zeros_like(t), 24.0, [(3.5, -3.0), (3.5 + 4 / 3, 0.0)], t),
        _vehicle(2, 30.0, np.vectorize(CUT.y), 20.0, [], t),
        # Lead braking in lane 3.
        _vehicle(3, 0.0, lambda t: np.full_like(t, -LANE_W), 20.0, [(5.0, -6.0)], t),
        _vehicle(4, 25.0, lambda t: np.full_like(t, -LANE_W), 20.0, [(4.0, -5.0)], t),
        # Opposite carriageway traffic.
        _vehicle(5, 400.0, lambda t: np.full_like(t, 12.0), 25.0, [], t, direction=-1, lane_override=7),
    ]
    return pd.concat([_to_rows(v, t, with_lane) for v in vehicles], ignore_index=True), vehicles, t


@pytest.fixture(scope="module")
def rec():
    raw, _, _ = _fixture()
    return cs.recording_from_frame(raw, "synthetic", frame_rate=FPS)


def _brute_min_ttc(f, l, t, t_from, t_to):
    m = (t >= t_from - 1e-9) & (t <= t_to + 1e-9)
    gap = l["s"][m] - f["s"][m] - L
    closing = f["v"][m] - l["v"][m]
    ttc = np.where(closing > 0, np.maximum(gap, 0) / np.where(closing > 0, closing, 1), np.inf)
    return ttc.min()


def test_units_and_geometry(rec):
    raw, vehicles, _ = _fixture()
    row = rec.df[(rec.df["id"] == 1)].iloc[0]
    assert row["X"] == pytest.approx(raw[raw["carId"] == 1]["carCenterXft"].iloc[0] * 0.3048)
    assert row["v"] == pytest.approx(24.0)
    assert row["length"] == pytest.approx(L)
    assert row["width"] == pytest.approx(W)


def test_road_axis_recovered(rec):
    ang = cs.estimate_road_axis(rec, min_track_displacement_m=TH.min_track_displacement_m)
    assert ang == pytest.approx(ROAD_ANGLE, abs=1e-3)


def test_cut_in_found_in_road_frame(rec):
    _, vehicles, t = _fixture()
    evs = cs.find_events(rec, "cut_in", TH)
    assert len(evs) == 1
    ev = evs[0]
    assert (ev.ego.id, ev.other.id) == (1, 2)
    assert ev.meta["from_lane"] == 2 and ev.meta["to_lane"] == 1
    # Ego lane centre is y = 0, ego starts at x = 0; cutter starts one lane to the LEFT.
    assert ev.ego.samples[0][1] == pytest.approx(0.0)
    assert max(abs(s[2]) for s in ev.ego.samples) < 1e-6
    assert ev.other.samples[0][2] == pytest.approx(LANE_W, abs=1e-6)
    k0 = ev.meta["frame_start"]
    assert ev.other.samples[0][1] == pytest.approx(vehicles[1]["s"][k0] - vehicles[0]["s"][k0], abs=1e-6)
    t_change = ev.t_key  # laneId flips when the cutter crosses mid-lane (t = 3.0 s)
    assert t_change == pytest.approx(3.0, abs=1 / FPS + 1e-9)
    expected = _brute_min_ttc(vehicles[0], vehicles[1], t, t_change, t_change + TH.post_s)
    assert ev.min_ttc_s == pytest.approx(expected, rel=1e-3)
    assert ev.min_ttc_s <= TH.ttc_max_s


def test_lead_brake_found():
    raw, vehicles, t = _fixture()
    r = cs.recording_from_frame(raw, "synthetic", frame_rate=FPS)
    th = cs.EventThresholds(ttc_max_s=5.0)
    evs = cs.find_events(r, "lead_brake", th)
    assert [(e.ego.id, e.other.id) for e in evs] == [(3, 4)]
    ev = evs[0]
    assert ev.meta["min_lead_accel_mps2"] <= -th.min_lead_decel_mps2
    assert ev.min_ttc_s == pytest.approx(_brute_min_ttc(vehicles[2], vehicles[3], t, 0, DURATION), rel=1e-3)


def test_thresholds_filter(rec):
    assert cs.find_events(rec, "cut_in", cs.EventThresholds(ttc_max_s=1.0)) == []
    assert cs.find_events(rec, "cut_in", cs.EventThresholds(max_gap_at_cut_in_m=5.0)) == []


def test_without_lane_id_uses_lateral_bins():
    raw, _, _ = _fixture(with_lane=False)
    r = cs.recording_from_frame(raw, "synthetic", frame_rate=FPS)
    with pytest.raises(ValueError):
        cs.find_events(r, "cut_in", TH)
    evs = cs.find_events(r, "cut_in", cs.EventThresholds(lane_width_m=LANE_W))
    assert [(e.ego.id, e.other.id) for e in evs] == [(1, 2)]


def test_lateral_fit_recovers_cosine():
    t = np.arange(0, 7, 1 / FPS)
    samples = [(float(x), 0.0, CUT.y(x), 0.0, 20.0) for x in t]
    m = cs.lateral_manoeuvre(samples, settle_s=0.5, min_shift_m=1.0, fractions=(0.1, 0.9))
    assert m.y_from == pytest.approx(LANE_W) and m.y_to == pytest.approx(0.0)
    assert m.t_start == pytest.approx(CUT.t_start, abs=0.05)
    assert m.duration == pytest.approx(CUT.duration, abs=0.05)


def test_accel_profile_hits_segment_speeds():
    t = np.arange(0, 4 + 1e-9, 1 / FPS)
    v = np.where(t < 1.0, 20.0, 20.0 - 3.0 * (t - 1.0))
    prof = cs.accel_profile([(float(a), 0, 0, 0, float(b)) for a, b in zip(t, v)], segment_s=0.5)
    assert prof[0] == (0.0, pytest.approx(0.0))
    assert prof[-1][1] == pytest.approx(-3.0)


def test_sim_reproduces_measured_cut_in(rec):
    ev = cs.find_events(rec, "cut_in", TH)[0]
    case = cs.to_sim_scenario(ev, wheelbase_m=2.7, accel_segment_s=0.5,
                              lateral_settle_s=0.5, min_lateral_shift_m=1.0)
    res = run(case.scenario, AVReplayPolicy(case.ego_accel_profile))
    assert not res.collided
    err = cs.trajectory_error(ev, res.trace, case.actor_name)
    for k, val in err.items():
        if k.endswith("rmse_m"):
            assert val < 0.3, (k, val)


def test_resolve_path_and_serialise(rec, tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("CITYSIM_ROOT", str(tmp_path))
    assert cs.resolve_path("x.csv") == tmp_path / "x.csv"
    raw, _, _ = _fixture()
    raw.to_csv(tmp_path / "x.csv", index=False)
    r = cs.load_recording("x.csv", "synthetic", frame_rate=FPS)
    ev = cs.find_events(r, "cut_in", TH)[0]
    assert json.loads(json.dumps(cs.event_to_dict(ev)))["ego"]["id"] == 1
