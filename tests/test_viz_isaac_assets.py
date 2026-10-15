import pytest

from viz.isaac import assets as A


def _fitted_extent(fit, lo, hi):
    pts = [A.apply_fit(fit, (x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    xs, ys, zs = zip(*pts)
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def test_fit_z_up_x_forward_model():
    lo, hi = (-2.0, -0.9, 0.3), (2.6, 0.9, 1.8)  # 4.6 m long, offset from origin, floating
    fit = A.fit_vehicle(lo, hi, 4.5)
    (x0, x1), (y0, y1), (z0, _) = _fitted_extent(fit, lo, hi)
    assert x1 - x0 == pytest.approx(4.5)
    assert (x0 + x1) / 2 == pytest.approx(0.0, abs=1e-9)
    assert (y0 + y1) / 2 == pytest.approx(0.0, abs=1e-9)
    assert z0 == pytest.approx(0.0, abs=1e-9)
    assert fit.yaw_deg == 0 and fit.up_fix_deg == 0


def test_fit_y_up_model_lying_along_z():
    # Y-up asset, length along its z axis, in centimetres
    lo, hi = (-90.0, 0.0, -230.0), (90.0, 150.0, 230.0)
    fit = A.fit_vehicle(lo, hi, 4.5, up_axis="Y")
    (x0, x1), (y0, y1), (z0, z1) = _fitted_extent(fit, lo, hi)
    assert x1 - x0 == pytest.approx(4.5)
    assert y1 - y0 == pytest.approx(1.8 * 4.5 / 4.6, rel=1e-6)
    assert z0 == pytest.approx(0.0, abs=1e-9) and z1 == pytest.approx(150 * 4.5 / 460)
    assert fit.up_fix_deg == 90


def test_fit_rejects_degenerate_bbox():
    with pytest.raises(ValueError):
        A.fit_vehicle((0, 0, 0), (0, 0, 0), 4.5)


def test_vehicle_candidates_ego_and_others_differ():
    ego = A.vehicle_candidates(0, None)
    other = A.vehicle_candidates(1, None, ["/vol/assets/cars/kenney_sedan.usd"])
    assert ego[0][0].endswith(A.VEHICLES[A.EGO_VEHICLE].rel_path)
    assert ego[0][0].startswith(A.DEFAULT_ASSETS_ROOT)
    assert other[0][0] != ego[0][0]
    assert other[-1][0] == "/vol/assets/cars/kenney_sedan.usd"
    assert all("police" not in u for u, _ in other)


def test_sky_falls_back_to_polyhaven():
    c = A.sky_candidates("omniverse://localhost/NVIDIA/Assets/Isaac/5.1")
    assert c[0].startswith("omniverse://localhost/") and c[-1] == A.POLYHAVEN_SKY


def test_brake_flags_follow_trace_deceleration():
    t = [i * 0.02 for i in range(6)]
    states = [(0, 0, 0, 20.0), (0, 0, 0, 20.0), (0, 0, 0, 19.9), (0, 0, 0, 19.8), (0, 0, 0, 19.8), (0, 0, 0, 19.8)]
    assert A.brake_flags(states, t) == [False, False, True, True, False, False]


def test_chase_cam_is_smooth_and_converges():
    cam = A.ChaseCam()
    eye0, _ = cam.update(0.0, 0.0, 0.0, 0.04)
    assert eye0[0] == pytest.approx(-cam.back)
    # ego jumps 10 m: camera must not teleport, must not overshoot, must converge
    xs = [cam.update(10.0, 0.0, 0.0, 0.04)[0][0] for _ in range(200)]
    assert xs[0] - eye0[0] < 2.0
    assert all(b >= a - 1e-9 for a, b in zip(xs, xs[1:]))
    assert xs[-1] == pytest.approx(10.0 - cam.back, abs=1e-3)
