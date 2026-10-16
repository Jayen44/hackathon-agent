"""Pure helpers of the Blender CCTV render (viz/render/keys.py). No bpy, no Modal."""
import json
import math
import pathlib

import pytest

from viz.isaac import assets as A
from viz.render import keys as K

SAMPLES = pathlib.Path(__file__).resolve().parent.parent / "viz/isaac/samples"


@pytest.fixture(scope="module")
def trace():
    return json.loads((SAMPLES / "cctv_cut_in_trace.json").read_text())


@pytest.fixture(scope="module")
def truth():
    return json.loads((SAMPLES / "cctv_cut_in_truth.json").read_text())


def test_frame_keys_resample_trace_at_25fps(trace):
    fr = K.frame_keys(trace, 25)
    assert len(fr) == K.n_frames(trace, 25) == 241
    assert set(fr[0]) == set(trace["actors"])
    for k in (0, 50, 137, 240):
        i = 2 * k                                   # trace dt 0.02 s, video 0.04 s
        for name, a in trace["actors"].items():
            x, y, h, v, _ = fr[k][name]
            sx, sy, sh, sv = a["states"][i]
            assert (x, y, h, v) == pytest.approx((sx, sy, sh, sv), abs=1e-9)


def test_frame_keys_interpolate_between_samples():
    tr = {"t": [0.0, 1.0], "actors": {"a": {"states": [[0.0, 0.0, 0.0, 10.0], [10.0, 0.0, 0.0, 10.0]]}}}
    fr = K.frame_keys(tr, 4)
    assert len(fr) == 5
    assert fr[2]["a"][0] == pytest.approx(5.0)
    assert fr[2]["a"][4] == pytest.approx(5.0 / K.WHEEL_RADIUS)   # rolling without slip


def test_wheel_angle_monotonic(trace):
    fr = K.frame_keys(trace, 25)
    w = [f["ego"][4] for f in fr]
    assert all(b >= a for a, b in zip(w, w[1:]))
    assert w[-1] > 0


def test_camera_matches_isaac_camera_and_truth_clicks(trace, truth):
    cam = trace["cctv_camera"]
    ref = A.CctvCamera(**cam)
    assert [c for v in K.camera_axes(cam) for c in v] == pytest.approx([c for v in ref.axes() for c in v])
    cal = truth["calibration"]
    for (wx, wy), (u, v) in zip(cal["world_pts_sim_frame"], cal["img_pts"]):
        bu, bv = K.project_blender(cam, (wx, wy, 0.0))
        ru, rv, _ = ref.project((wx, wy, 0.0))
        assert (bu, bv) == pytest.approx((ru, rv), abs=1e-6)
        assert (bu, bv) == pytest.approx((u, v), abs=0.01)


def test_blender_matrix_is_rigid(trace):
    M = K.blender_camera_matrix(trace["cctv_camera"])
    R = [[M[i][j] for j in range(3)] for i in range(3)]
    for a in range(3):
        for b in range(3):
            dot = sum(R[i][a] * R[i][b] for i in range(3))
            assert dot == pytest.approx(1.0 if a == b else 0.0, abs=1e-12)
    assert M[3] == [0.0, 0.0, 0.0, 1.0]


def test_timestamps_tick_each_second():
    ts = K.timestamp_texts(9.64)
    assert len(ts) == 11
    assert ts[0] == "CAM 04 · 2026-10-15 14:22:31"
    assert ts[1].endswith("14:22:32") and ts[-1].endswith("14:22:41")
    assert K.timestamp_texts(1.0, start_hms=(23, 59, 59))[1].endswith("00:00:00")
    assert ts == A.cctv_timestamp_texts(9.64)


def test_cctv_filtergraph_keeps_geometry_and_label():
    vf = K.cctv_filtergraph(["/t/0.txt", "/t/1.txt"], "/t/label.txt", "/f.ttf")
    assert "scale=1280:720" in vf and vf.count("scale=1920:1080") == 1
    for bad in ("lenscorrection", "crop", "pad=", "rotate", "perspective"):
        assert bad not in vf                         # calibration clicks must stay exact
    assert vf.count("textfile=/t/") == 3 and "textfile=/t/label.txt" in vf
    assert "enable='gte(t,1)*lt(t,2)'" in vf
    assert "expansion=none" in vf
    assert "SYNTHETIC RENDER" in K.CCTV_LABEL


def test_x264_args_low_bitrate():
    a = K.x264_args(1800)
    assert a[a.index("-b:v") + 1] == "1800k" and "yuv420p" in a


def test_chunks_cover_all_frames():
    c = K.chunks(241, 8)
    assert c[0] == (0, 7) and c[-1] == (240, 240)
    assert sum(e - s + 1 for s, e in c) == 241


def test_projected_box_and_detection_rate(trace):
    cam = trace["cctv_camera"]
    b = K.projected_box(cam, 84.5, 0.0, 0.0)
    assert b[0] < b[2] and b[1] < b[3]
    u, v, _ = A.CctvCamera(**cam).project((84.5, 0.0, 0.0))
    assert b[0] < u < b[2] and b[1] < v < b[3]
    off = (-50, -50, -10, -10)
    dets = [[{"label": "car", "score": 0.9, "box": list(b)}], [{"label": "truck", "score": 0.9, "box": list(b)}], []]
    r = K.detection_rate(dets, [{"ego": b, "x": off}] * 3)
    assert r["ego"]["visible"] == 3 and r["ego"]["car"] == 1 and r["ego"]["other_label"] == 1
    assert r["ego"]["car_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert r["x"]["visible"] == 0 and r["x"]["car_rate"] is None
    assert K.iou((0, 0, 2, 2), (1, 1, 3, 3)) == pytest.approx(1 / 7)
    assert math.isclose(K.iou((0, 0, 1, 1), (2, 2, 3, 3)), 0.0)
