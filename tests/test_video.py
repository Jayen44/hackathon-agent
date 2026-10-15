"""sim/video: calibration, speed and conflict extraction on SYNTHETIC data only.

A pinhole camera (10 m high, pitched down 20 deg, 1920x1080) looks along a straight road.
World trajectories are projected to pixels, 1 px Gaussian box jitter is added, and the
pipeline must recover speeds and conflict facts. No real video, no detector.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from sim.video.calibrate import (CalibrationError, calibrate, calibrate_from_request, fit_homography,
                                 project, rectangle_world_points)
from sim.video.trajectories import Track, analyse, kinematics

FPS = 25.0


def cam_H(height=10.0, pitch_deg=20.0, back=15.0, f=1400.0, y_cam=1.75):
    """World ground plane (x fwd, y left) -> image pixels for a pinhole camera."""
    p = math.radians(pitch_deg)
    right = np.array([0.0, -1.0, 0.0])
    fwd = np.array([math.cos(p), 0.0, -math.sin(p)])
    down = np.cross(fwd, right)
    R = np.vstack([right, down, fwd])
    C = np.array([-back, y_cam, height])
    K = np.array([[f, 0, 960.0], [0, f, 540.0], [0, 0, 1.0]])
    H = K @ np.c_[R[:, 0], R[:, 1], -R @ C]
    return H / H[2, 2]


H_W2I = cam_H()
H_I2W = np.linalg.inv(H_W2I)


def to_px(xy):
    return project(H_W2I, xy)


def make_track(tid, xy, noise_px=1.0, seed=0, frames=None):
    px = to_px(xy) + np.random.default_rng(seed).normal(0, noise_px, (len(xy), 2))
    w, h = 80.0, 60.0
    boxes = np.c_[px[:, 0] - w / 2, px[:, 1] - h, px[:, 0] + w / 2, px[:, 1]]
    fr = np.arange(len(xy)) if frames is None else frames
    return Track(tid, "car", fr, boxes)


# Calibration rectangle: one 3.5 m lane, 20 m of it, starting 5 m ahead of the camera foot.
RECT_W = rectangle_world_points(20.0, 3.5) + np.array([5.0, 0.0])
RECT_PX = to_px(RECT_W)


def rect_calib(click_sigma_px=1.0):
    return calibrate_from_request({"mode": "rectangle", "img_pts": RECT_PX.tolist(),
                                   "length_m": 20.0, "width_m": 3.5, "click_sigma_px": click_sigma_px})


def test_homography_recovers_known_points():
    H = fit_homography(RECT_PX, RECT_W)
    probe = np.array([[0.0, 0.0], [12.0, 1.0], [40.0, -3.5], [60.0, 7.0]])
    assert np.allclose(project(H, to_px(probe)), probe, atol=1e-6)
    np.testing.assert_allclose(H / H[2, 2], H_I2W / H_I2W[2, 2], rtol=1e-6, atol=1e-9)


def test_homography_overdetermined_reports_residual():
    world = np.array([[5, 0], [25, 0], [25, 3.5], [5, 3.5], [15, 1.75], [10, 7.0]], float)
    px = to_px(world)
    c = calibrate(px, world, click_sigma_px=0.5, world_sigma_m=0.02)
    assert c.reproj_rms_m < 1e-6 and len(c.ensemble) > 50
    px_bad = px.copy()
    px_bad[4] += [12, 0]
    assert calibrate(px_bad, world).reproj_rms_px > 2.0


def test_calibration_rejects_degenerate_input():
    with pytest.raises(CalibrationError):
        fit_homography([[0, 0], [1, 1], [2, 2], [3, 3]], [[0, 0], [1, 0], [2, 0], [3, 0]])
    with pytest.raises(CalibrationError):
        rectangle_world_points(0, 3.5)
    with pytest.raises(CalibrationError):
        calibrate_from_request({"mode": "rectangle", "img_pts": [[0, 0]] * 3, "length_m": 1, "width_m": 1})


def test_calibration_uncertainty_grows_with_click_sigma():
    far = to_px(np.array([[40.0, 0.0]]))
    s1 = rect_calib(0.5).position_sigma_m(far)
    s2 = rect_calib(4.0).position_sigma_m(far)
    assert 0 < s1 < s2


@pytest.mark.parametrize("v", [8.0, 15.0, 25.0])
def test_constant_speed_track(v):
    t = np.arange(0, 4, 1 / FPS)
    xy = np.c_[5 + v * t, np.full_like(t, 1.75)]
    k = kinematics(make_track(1, xy), rect_calib(), FPS)
    mid = slice(10, -10)
    err = k.speed[mid] - v
    assert abs(np.median(err)) < 0.03 * v + 0.2
    assert np.percentile(np.abs(err), 95) < 0.08 * v + 0.5
    # Error bar is honest: most samples within 3 sigma, and the bar is not absurdly wide.
    assert np.mean(np.abs(err) < 3 * k.speed_sd[mid] + 0.05) > 0.9
    assert np.median(k.speed_sd[mid]) < 0.1 * v + 1.0


def test_dropped_frames_ok():
    t_all = np.arange(0, 4, 1 / FPS)
    keep = np.ones(len(t_all), bool)
    keep[30:38] = False
    fr = np.nonzero(keep)[0]
    xy = np.c_[5 + 12 * t_all[keep], np.zeros(keep.sum())]
    k = kinematics(make_track(1, xy, frames=fr), rect_calib(), FPS)
    assert abs(np.median(k.speed) - 12) < 0.4


def _lead_brake_world(T=4.0):
    t = np.arange(0, T, 1 / FPS)
    ego = np.c_[5 + 15 * t, np.zeros_like(t)]
    v0, a, tb = 10.0, 6.0, 1.0
    tt = np.clip(t - tb, 0, v0 / a)
    xo = 5 + 24.6 + v0 * np.minimum(t, tb) + v0 * tt - 0.5 * a * tt ** 2
    other = np.c_[xo, np.zeros_like(t)]
    return ego, other


def test_conflict_lead_brake():
    ego, other = _lead_brake_world()
    tracks = {1: make_track(1, ego, seed=1), 2: make_track(2, other, seed=2)}
    out = analyse(tracks, rect_calib(), FPS, ego_id=1, lane_width_m=3.5, case_id="synthetic-lead", synthetic=True)
    b = out["bundle"]
    c, r = b["conflict"], b["conflict_ranges"]
    assert c["crash_type"] == "lead_vehicle_decel"
    assert out["other_id"] == 2
    assert abs(c["ego_speed_mps"] - 15) < 0.8 and abs(c["hazard_speed_mps"] - 10) < 0.8
    t0 = c["t_start"]
    assert 0.4 <= t0 < 1.0           # first settled frame (half a smoothing window in)
    gap_true = 20 - 5 * t0
    assert abs(c["gap_m"] - gap_true) < 1.0
    assert r["gap"]["lo"] <= gap_true <= r["gap"]["hi"]
    assert r["ego_speed"]["lo"] <= 15 <= r["ego_speed"]["hi"]
    assert r["other_decel"]["hi"] >= 4.5 and r["other_decel"]["lo"] <= 7.0
    assert abs((r["other_brake_time"]["lo"] + r["other_brake_time"]["hi"]) / 2 - (1.0 - t0)) < 0.3
    assert all(v["source"] == "reported" for v in r.values())
    assert b["outcome"]["collided"] is True and b["external"]["cctv"]


def test_conflict_cut_in():
    t = np.arange(0, 4, 1 / FPS)
    ego = np.c_[5 + 15 * t, np.zeros_like(t)]
    ts, dur, y0 = 1.0, 2.0, 3.5
    u = np.clip((t - ts) / dur, 0, 1)
    y = y0 * (1 + np.cos(np.pi * u)) / 2
    other = np.c_[5 + 4.6 + 15 + 9 * t, y]
    tracks = {1: make_track(1, ego, seed=3), 2: make_track(2, other, seed=4),
              3: make_track(3, np.c_[5 + 25 * t, np.full_like(t, -3.5)], seed=5)}   # passing car, not the hazard
    out = analyse(tracks, rect_calib(), FPS, ego_id=1, lane_width_m=3.5)
    c, r = out["bundle"]["conflict"], out["bundle"]["conflict_ranges"]
    assert out["other_id"] == 2
    assert c["crash_type"] == "cut_in"
    t0 = c["t_start"]
    assert abs(c["gap_m"] - (15 - 6 * t0)) < 1.0
    mid = lambda k: (r[k]["lo"] + r[k]["hi"]) / 2
    assert abs(mid("lateral_offset") - 3.5) < 0.6
    assert abs(mid("cut_in_start") - (1.0 - t0)) < 0.3
    assert abs(mid("cut_in_duration") - 2.0) < 0.4
    # Override is respected.
    out2 = analyse(tracks, rect_calib(), FPS, ego_id=1, other_id=2, lane_width_m=3.5,
                   crash_type="lead_vehicle_decel", collided=False)
    assert out2["bundle"]["conflict"]["crash_type"] == "lead_vehicle_decel"
    assert out2["bundle"]["outcome"] == {"collided": False}


def test_bundle_runs_through_estimate():
    from montecarlo.estimate import estimate
    ego, other = _lead_brake_world()
    tracks = {1: make_track(1, ego, seed=1), 2: make_track(2, other, seed=2)}
    b = analyse(tracks, rect_calib(), FPS, ego_id=1, lane_width_m=3.5)["bundle"]
    res = estimate(b, n=200, sensitivity=False, replays=True)
    assert res["evidence_tier"] == 1
    for d in ("careful_a", "careful_b"):
        assert 0 <= res["drivers"][d]["p_avoid"] <= 1
    assert set(res["replays"]) == {"av", "careful_a", "careful_b"}
    assert res["ranges"]["gap"]["source"] == "reported"


def test_pipeline_replay_json_matches_viewer_format():
    from sim.video.pipeline import run
    ego, other = _lead_brake_world()
    tracks = {1: make_track(1, ego, seed=1), 2: make_track(2, other, seed=2)}
    tj = {"fps": FPS, "tracks": {str(k): {"cls": "car", "frames": tr.frames.tolist(), "boxes": tr.boxes.tolist()}
                                 for k, tr in tracks.items()}}
    req = {"calibration": {"mode": "rectangle", "img_pts": RECT_PX.tolist(), "length_m": 20, "width_m": 3.5},
           "ego_track": 1, "lane_width_m": 3.5, "n": 200, "sensitivity": False}
    out = run(tj, req, case_id="synthetic", synthetic=True)
    rp = out["replay"]
    assert set(rp["runs"]) == {"av", "careful_a", "careful_b"}
    for r in rp["runs"].values():
        assert len(r["t"]) == len(r["ego"]) and "other" in r
    assert rp["scenario"]["measured"]["ego"]["speed_sd"]
    assert 0 <= rp["p_avoid"]["careful_a"]["p"] <= 1


def test_privacy_blur_changes_only_regions():
    cv2 = pytest.importorskip("cv2")
    from sim.video.detect import privacy_blur
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (200, 300, 3), dtype=np.uint8)
    out = privacy_blur(img, persons=[[10, 10, 60, 120]], vehicles=[[150, 50, 290, 190]], plates=True)
    assert not np.array_equal(out[20:100, 20:50], img[20:100, 20:50])        # person blurred
    assert not np.array_equal(out[160:185, 190:250], img[160:185, 190:250])   # plate zone blurred
    assert np.array_equal(out[60:90, 155:170], img[60:90, 155:170])           # car body untouched
    assert np.array_equal(out[150:199, 70:140], img[150:199, 70:140])         # background untouched


def test_fragmented_tracks_merge_and_duplicates_ignored():
    ego, other = _lead_brake_world()
    a = make_track(1, ego[:50], seed=1, frames=np.arange(50))
    b = make_track(7, ego[45:], seed=6, frames=np.arange(45, len(ego)))       # ID switch
    dup = make_track(9, ego[20:60] + [0.4, 0.0], seed=8, frames=np.arange(20, 60))   # duplicate box on the AV
    o = make_track(2, other, seed=2)
    out = analyse({1: a, 7: b, 9: dup, 2: o}, rect_calib(), FPS, ego_id=[1, 7], lane_width_m=3.5)
    assert out["other_id"] == 2 and out["ego_ids"] == [1, 7]
    assert abs(out["bundle"]["conflict"]["ego_speed_mps"] - 15) < 0.8
