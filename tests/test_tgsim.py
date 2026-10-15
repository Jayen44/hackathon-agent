"""Tests for sim/data/tgsim.py on a tiny synthetic TGSIM-format fixture.

Everything here is synthetic test data (NOT TGSIM data, NOT R157 values): the
curved road, lane width, speeds, gaps and the wheelbase are fixture choices.
"""
import json
import math

import numpy as np
import pandas as pd
import pytest

from sim.data import tgsim as tg
from sim.policies.av_replay import AVReplayPolicy
from sim.scenario import LateralManoeuvre
from sim.world import run

FPS = tg.TGSIM_FPS
DURATION = 12.0
LANE_W = 3.6
L, W = 4.5, 1.8
R = 800.0          # fixture road radius (m), curving left
ORIGIN = np.array([150.0, 400.0])  # image-frame offset (keeps yloc positive)
LANES = {2: 0.0, 3: -LANE_W, 4: -2 * LANE_W}           # our carriageway, inner lane 2 on the left
OPP = {-2: 14.0, -3: 14.0 + LANE_W, -4: 14.0 + 2 * LANE_W}  # opposite carriageway (left of us)
CUT = LateralManoeuvre(t_start=2.0, duration=2.0, y_from=0.0, y_to=-LANE_W)  # lane 2 -> lane 3
TH = tg.EventThresholds()


def _centre(s):
    phi = s / R
    return np.stack([R * np.sin(phi), R * (1 - np.cos(phi))], -1), phi


def _speed(v0, segments, t):
    dt = 1e-3
    tt = np.arange(0.0, t[-1] + dt, dt)
    a = np.zeros_like(tt)
    for t0, acc in segments:
        a[tt >= t0] = acc
    v = np.maximum(v0 + np.concatenate([[0], np.cumsum(a[:-1] * dt)]), 0.0)
    s = np.concatenate([[0], np.cumsum((v[:-1] + v[1:]) / 2 * dt)])
    return np.interp(t, tt, s), np.interp(t, tt, v)


def _veh(vid, s0, n_of_t, v0, segs, t, direction=1, lanes=LANES, av="no"):
    s, v = _speed(v0, segs, t)
    s = s0 + direction * s
    n = n_of_t(t)
    c, phi = _centre(s)
    P = c + n[:, None] * np.stack([-np.sin(phi), np.cos(phi)], -1)
    keys = np.array(list(lanes))
    cents = np.array(list(lanes.values()))
    lane = keys[np.argmin(np.abs(n[:, None] - cents[None, :]), 1)]
    return dict(id=vid, s=s, n=n, v=v, df=pd.DataFrame({
        "id": vid, "time": np.round(t, 1), "xloc_kf": P[:, 0] + ORIGIN[0], "yloc_kf": P[:, 1] + ORIGIN[1],
        # Path speed: s is centre-line arc length, so a lane at offset n moves (1 - n / R) as fast.
        "lane_kf": lane, "speed_kf": np.hypot(*np.gradient(P, t, axis=0).T), "acceleration_kf": np.gradient(v, t),
        "length_smoothed": L, "width_smoothed": W, "type_most_common": "small-vehicle",
        "av": av, "run_index": 1}))


def _fixture():
    t = np.arange(0, DURATION + 1e-9, 1 / FPS)
    const = lambda y: (lambda tt: np.full_like(tt, y))  # noqa: E731
    vs = [
        # Automated ego (lane 3) is cut in on by vehicle 2 from lane 2, then brakes.
        _veh(1, 100.0, const(-LANE_W), 24.0, [(3.5, -3.0), (3.5 + 4 / 3, 0.0)], t, av="yes"),
        _veh(2, 130.0, np.vectorize(CUT.y), 20.0, [], t),
        # Lead braking in lane 4.
        _veh(3, 100.0, const(-2 * LANE_W), 20.0, [(5.0, -6.0)], t),
        _veh(4, 125.0, const(-2 * LANE_W), 20.0, [(4.0, -5.0)], t),
    ]
    # Opposite carriageway background traffic (dense, lane keeping, far apart).
    k = 10
    for lane, n in OPP.items():
        for j in range(12):
            vs.append(_veh(k, 520.0 - 40.0 * j, const(n), 25.0, [], t, direction=-1, lanes=OPP))
            k += 1
    # Same-direction background in lane 2, well ahead of the events.
    for j in range(6):
        vs.append(_veh(k, 260.0 + 40.0 * j, const(0.0), 22.0, [], t))
        k += 1
    raw = pd.concat([v["df"] for v in vs], ignore_index=True)
    return raw, vs, t


def _survey():
    """Dense lane-centre points over the whole road, all six lanes equally
    (stands in for hours of real traffic, which occupy every lane everywhere)."""
    s = np.arange(-100.0, 900.0, 0.5)
    c, phi = _centre(s)
    nrm = np.stack([-np.sin(phi), np.cos(phi)], -1)
    P = np.concatenate([c + n * nrm for n in [*LANES.values(), *OPP.values()]]) + ORIGIN
    return P[:, 0], P[:, 1]  # global frame = (xloc, yloc)


@pytest.fixture(scope="module")
def data():
    raw, vs, t = _fixture()
    rec = tg.recording_from_frame(raw, "synthetic", run=1)
    df = tg.prepare(rec, TH, ref=tg.reference_line(*_survey()))
    return raw, vs, t, rec, df


def test_reference_line_is_band_centre():
    X, Y = _survey()
    ref = tg.reference_line(X, Y)
    s, d = tg.frenet(ref, X, Y)
    # Band runs from n = -7.2 (our outer lane) to n = 21.2 (their outer lane): centre n = 7.
    n_all = np.repeat([*LANES.values(), *OPP.values()], len(X) // 6)
    mid = (min(n_all) + max(n_all)) / 2
    inner = (s > s.min() + 100) & (s < s.max() - 100)  # away from the data ends
    off = np.abs(d) - np.abs(n_all - mid)
    assert np.max(np.abs(off[inner])) < 0.2


def test_columns_units_and_flags(data):
    raw, _, _, rec, _ = data
    d = rec.df
    r = d[d["id"] == 1].iloc[0]
    assert r["X"] == pytest.approx(raw[raw["id"] == 1]["xloc_kf"].iloc[0])
    assert r["Y"] == pytest.approx(raw[raw["id"] == 1]["yloc_kf"].iloc[0])  # not mirrored (checked on real data)
    assert r["v"] == pytest.approx(raw[raw["id"] == 1]["speed_kf"].iloc[0])
    assert (r["length"], r["width"]) == (L, W)
    assert bool(r["automated"]) and not bool(d[d["id"] == 2]["automated"].iloc[0])
    assert d["frame"].diff().dropna().isin([1]).mean() > 0.9  # 0.1 s grid


def test_frenet_follows_curved_road(data):
    _, vs, _, _, df = data
    # Arc length along the reference line tracks centre-line arc length (up to a constant),
    # lateral offset tracks n (up to a constant) on a road that turns ~40 deg.
    for v in (vs[0], vs[2]):
        g = df[df["id"] == v["id"]].sort_values("frame")
        # Frenet arc length runs (R - offset) / R as fast as lane arc length: fit that scale.
        slope, icpt = np.polyfit(v["s"], g["x"].to_numpy(), 1)
        assert abs(abs(slope) - 1) < 0.03
        assert np.max(np.abs(g["x"].to_numpy() - (slope * v["s"] + icpt))) < 0.05
        dn = g["y"].to_numpy() - v["n"]
        assert np.ptp(dn) < 0.05
    # Reference-line orientation is arbitrary; the two carriageways must get opposite directions.
    ours = set(df.loc[df["lane"] > 0, "direction"])
    theirs = set(df.loc[df["lane"] < 0, "direction"])
    assert len(ours) == 1 and len(theirs) == 1 and ours != theirs


def test_lane_order_inner_left(data):
    _, _, _, _, df = data
    lo = tg.lane_lateral_order(df)
    d_ours = int(df.loc[df["id"] == 1, "direction"].iloc[0])
    ours = lo[lo["direction"] == d_ours].set_index("lane")["median_y_m"]
    assert ours[2] > ours[3] > ours[4]


def test_cut_in_found(data):
    _, vs, t, rec, df = data
    evs = tg.find_events(rec, "cut_in", TH, df=df)
    assert [(e.ego.id, e.other.id) for e in evs] == [(1, 2)]
    ev = evs[0]
    assert (ev.meta["from_lane"], ev.meta["to_lane"]) == (2, 3)
    assert ev.meta["ego_automated"] and not ev.meta["other_automated"]
    assert ev.meta["run"] == 1
    assert ev.meta["bbox_overlap"] is False
    assert ev.other.samples[0][2] == pytest.approx(LANE_W, abs=0.2)  # cutter starts one lane left
    assert max(abs(s[2]) for s in ev.ego.samples) < 0.2
    assert ev.t_key == pytest.approx(3.0, abs=1 / FPS + 1e-9)
    assert ev.min_ttc_s <= TH.ttc_max_s


def test_lead_brake_found(data):
    _, _, _, rec, df = data
    th = tg.EventThresholds(ttc_max_s=5.0)
    evs = tg.find_events(rec, "lead_brake", th, df=df)
    assert [(e.ego.id, e.other.id) for e in evs] == [(3, 4)]
    assert evs[0].meta["lane"] == 4


def test_reconstruction_and_roundtrip(data):
    _, _, _, rec, df = data
    ev = tg.find_events(rec, "cut_in", TH, df=df)[0]
    ev2 = tg.event_from_dict(json.loads(json.dumps(tg.event_to_dict(ev))))
    assert ev2.ego.samples == ev.ego.samples and ev2.meta == ev.meta
    case = tg.to_sim_scenario(ev2, wheelbase_m=2.7, accel_segment_s=0.5,
                              lateral_settle_s=0.5, min_lateral_shift_m=1.0)
    res = run(case.scenario, AVReplayPolicy(case.ego_accel_profile))
    assert not res.collided
    err = tg.trajectory_error(ev2, res.trace, case.actor_name)
    for k, val in err.items():
        if k.endswith("rmse_m"):
            assert val < 0.3, (k, val)


def test_load_recordings_splits_runs(tmp_path):
    raw, _, _ = _fixture()
    two = pd.concat([raw, raw.assign(run_index=2)], ignore_index=True)
    two.to_csv(tmp_path / "x.csv", index=False)
    recs = tg.load_recordings(tmp_path / "x.csv", "synthetic")
    assert [r.df["run"].iloc[0] for r in recs] == [1, 2]
    assert len(recs[0].df) == len(raw)
