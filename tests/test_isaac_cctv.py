"""Pure parts of the synthetic CCTV clip: camera maths, calibration round-trip, trace sanity.

Nothing here starts Isaac Sim. SYNTHETIC sample, not R157 and not a real crash.
"""
import json
import pathlib

import numpy as np
import pytest

from sim.video.calibrate import calibrate_from_request
from viz.isaac import cctv_sample as S
from viz.isaac.assets import CCTV, CctvCamera, cctv_timestamp_texts

SAMPLES = pathlib.Path(S.__file__).parent / "samples"


@pytest.fixture(scope="module")
def built():
    return S.build()


def test_usd_matrix_matches_projection():
    M = np.array(CCTV.usd_matrix())          # camera -> world, row-vector convention
    W2C = np.linalg.inv(M)
    for p in [(90.0, 0.0, 0.0), (70.0, 3.5, 1.2), (100.0, -3.5, 0.5)]:
        x, y, z, _ = np.array([*p, 1.0]) @ W2C   # USD camera looks down -Z, +Y up
        u = CCTV.width / 2 + CCTV.fx * x / -z
        v = CCTV.height / 2 - CCTV.fx * y / -z
        pu, pv, depth = CCTV.project(p)
        assert depth == pytest.approx(-z)
        assert (u, v) == pytest.approx((pu, pv), abs=1e-6)
    right, up, fwd = CCTV.axes()
    assert np.dot(right, fwd) == pytest.approx(0, abs=1e-12) and np.dot(up, fwd) == pytest.approx(0, abs=1e-12)
    assert up[2] > 0 and fwd[2] < 0           # tilted down, image upright


def test_camera_pose_is_cctv_like():
    assert 8.0 <= CCTV.z <= 10.0
    assert 25.0 <= CCTV.pitch_deg <= 35.0
    assert abs(CCTV.y) > S.LANE_W * 1.5 + 1.0          # beside the road, not over a lane
    assert (CCTV.width, CCTV.height) == (1920, 1080)


def _in_frame(cam, p, margin=10):
    u, v, d = cam.project(p)
    return d > 0 and margin <= u <= cam.width - margin and margin <= v <= cam.height - margin


def test_trace_sanity(built):
    doc, truth = built
    t = doc["t"]
    ego, cut = doc["actors"]["ego"]["states"], doc["actors"]["cutter"]["states"]
    m, tr = doc["meta"], truth["truth"]
    assert m["collided"] and m["other_actor"] == "cutter" and m["impact_type"] == "rear_end"
    assert 5.0 <= m["t_collision"] <= 6.0
    assert 8.0 <= t[-1] <= 10.0 and len(t) == len(ego) == len(cut)
    assert 50 <= ego[0][3] * 3.6 <= 60 and 30 <= cut[0][3] * 3.6 <= 35
    assert 10.0 <= tr["gap_at_cut_in_start_m"] <= 14.0 + 1e-6
    assert tr["av_brake_start_s"] > tr["cut_in_start_s"]           # late
    assert tr["av_decel_mps2"] < 4.0                                # soft
    assert ego[-1][3] == 0.0 and cut[-1][3] == 0.0                  # both stop
    i_imp = int(round(m["t_collision"] / doc["dt"]))
    for e, c in zip(ego[i_imp + 1:], cut[i_imp + 1:]):              # separate after impact, same lane
        assert c[0] - e[0] >= cut[i_imp][0] - ego[i_imp][0] - 1e-6 and abs(c[1]) < 1e-9
    for k in range(1, len(t)):                                      # 50 Hz, monotone forward motion
        assert t[k] - t[k - 1] == pytest.approx(doc["dt"], abs=1e-6)
        assert ego[k][0] >= ego[k - 1][0] - 1e-9
    assert "NOT simulated" in m["post_impact"] and doc["meta"]["synthetic"]


def test_key_moments_in_frame(built):
    doc, truth = built
    cam = CctvCamera(**doc["cctv_camera"])
    ego, cut = doc["actors"]["ego"]["states"], doc["actors"]["cutter"]["states"]
    for i in range(0, len(ego), 25):                                 # every 0.5 s, whole clip
        assert _in_frame(cam, (ego[i][0], ego[i][1], 0.0)), f"ego out of frame at step {i}"
        assert _in_frame(cam, (cut[i][0], cut[i][1], 0.0)), f"cutter out of frame at step {i}"
    for p in S.calibration_world():
        assert _in_frame(cam, p)


def test_calibration_round_trip_recovers_true_speeds(built):
    doc, truth = built
    cam = CctvCamera(**doc["cctv_camera"])
    c = truth["calibration"]
    calib = calibrate_from_request({"mode": "rectangle", "img_pts": c["img_pts"],
                                    "length_m": c["length_m"], "width_m": c["width_m"]})
    # rectangle frame: A=(0,0) B=(L,0) C=(L,W) D=(0,W); sim frame: A=(96,-1.75) etc.
    world = calib.project(c["img_pts"])
    np.testing.assert_allclose(world, [[0, 0], [24, 0], [24, 3.5], [0, 3.5]], atol=0.02)
    ego, cut = doc["actors"]["ego"]["states"], doc["actors"]["cutter"]["states"]

    def road(st):
        u, v, _ = cam.project((st[0], st[1], 0.0))
        return calib.project([[u, v]])[0]

    i0, i1 = 0, int(round(S.CUT_START / doc["dt"]))                 # constant-speed phase
    T = (i1 - i0) * doc["dt"]
    v_ego = np.linalg.norm(road(ego[i1]) - road(ego[i0])) / T
    v_cut = np.linalg.norm(road(cut[i1]) - road(cut[i0])) / T
    assert v_ego == pytest.approx(truth["truth"]["ego_speed_mps"], rel=0.005)
    assert v_cut == pytest.approx(truth["truth"]["other_speed_mps"], rel=0.005)
    # gap at cut-in (centre-to-centre along the road minus one car length)
    d = road(cut[i1]) - road(ego[i1])
    assert abs(d[0]) - S.CAR.length == pytest.approx(truth["truth"]["gap_at_cut_in_start_m"], abs=0.02)
    assert abs(d[1]) == pytest.approx(S.LANE_W, abs=0.02)


def test_720p_clicks_are_scaled(built):
    _, truth = built
    c = truth["calibration"]
    fields = {k: v for k, v in truth["camera"].items() if k in CctvCamera.__dataclass_fields__}
    cam720 = CctvCamera(**{**fields, "width": 1280, "height": 720})
    np.testing.assert_allclose(S.calibration_clicks(cam720), c["img_pts_1280x720"], atol=0.02)


def test_samples_on_disk_are_current(built):
    doc, truth = built
    on_disk = json.loads((SAMPLES / "cctv_cut_in_trace.json").read_text())
    assert on_disk["meta"] == json.loads(json.dumps(doc["meta"]))
    assert on_disk["cctv_camera"] == doc["cctv_camera"]
    t_disk = json.loads((SAMPLES / "cctv_cut_in_truth.json").read_text())
    assert t_disk["calibration"]["img_pts"] == truth["calibration"]["img_pts"]
    assert t_disk["truth"] == json.loads(json.dumps(truth["truth"]))


def test_timestamp_texts():
    ts = cctv_timestamp_texts(9.64)
    assert len(ts) == 11
    assert ts[0] == "CAM 04 · 2026-10-15 14:22:31"
    assert ts[-1].endswith("14:22:41")
    assert cctv_timestamp_texts(1, start_hms=(23, 59, 59))[1].endswith("00:00:00")
