import math
import sys, os
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from r6reel import camera as C
from r6reel import transitions as T


def proj_height_fraction(cs, pts, aspect=9 / 16):
    """Independent pinhole projection: fraction of frame height spanned by the points."""
    eye, tgt = np.array(cs.eye), np.array(cs.target)
    f = (tgt - eye) / np.linalg.norm(tgt - eye)
    r = np.cross(f, [0, 1, 0]); r /= np.linalg.norm(r)
    u = np.cross(r, f)
    t = math.tan(math.radians(cs.fov_y) / 2)
    ys = []
    for p in pts:
        q = np.array(p) - eye
        ys.append((q @ u) / ((q @ f) * t))          # NDC y in [-1, 1]
    return (max(ys) - min(ys)) / 2.0


def subject_pts(H=5.0, pos=(0, 0, 0)):
    # fill is measured at the avatar's front surface (0.1*H in front of the root plane, facing -Z)
    x, y, z = pos
    return [(x, y, z - 0.1 * H), (x, y + H, z - 0.1 * H)]


def test_state_deterministic():
    def build():
        return (C.shot("medium", (1, 0, 2), facing_deg=30)
                .push_in(0, 2, 0.1).drift(0, None, 0.3).shake(0.5, 1.0, 0.2).dutch(0, 1, 8))
    a, b = build(), build()
    for t in (0.0, 0.37, 0.9, 1.5, 3.0):
        assert a.state(t) == b.state(t)
        assert a.state(t) == a.state(t)
    # order of evaluation must not matter (no hidden state)
    x = a.state(1.2); a.state(0.1); a.state(2.9)
    assert a.state(1.2) == x


@pytest.mark.parametrize("H", [5.0, 8.0])
@pytest.mark.parametrize("fov", [60.0, 70.0, 90.0])
def test_framing_fill(H, fov):
    cam = C.shot("wide", (3, 0, -4), subject_height=H, fill=0.5, fov=fov, elevation_deg=0)
    got = proj_height_fraction(cam.state(0), subject_pts(H, (3, 0, -4)))
    assert got == pytest.approx(0.5, abs=0.02)


def test_framing_default_wide_and_medium():
    cam = C.shot("wide", (0, 0, 0), fill=0.5)               # default 4 deg elevation
    assert proj_height_fraction(cam.state(0), subject_pts()) == pytest.approx(0.5, abs=0.04)
    cam = C.shot("medium", (0, 0, 0), fill=0.5)              # region = waist up (2.75 studs)
    pts = [(0, 5 * 0.45, -0.5), (0, 5.0, -0.5)]
    assert proj_height_fraction(cam.state(0), pts) == pytest.approx(0.5, abs=0.03)


def test_distance_formula_and_facing():
    cam = C.shot("wide", (0, 0, 0), fill=0.5, elevation_deg=0)
    d = C.framing_distance(5, 70, 0.5)
    assert cam.info["distance"] == pytest.approx(d + 0.5)
    assert cam.state(0).eye[2] == pytest.approx(-(d + 0.5))           # facing -Z => camera in front at -Z
    cam = C.shot("wide", (0, 0, 0), facing_deg=90, elevation_deg=0)
    assert cam.state(0).eye[0] < -1                           # +90 faces -X
    cam = C.shot("chase_behind", (0, 0, 0))
    assert cam.state(0).eye[2] > 1                            # behind a -Z facing avatar = +Z


def test_closeups_fill_more_and_extreme_has_wide_fov():
    s = {k: C.shot(k, (0, 0, 0)) for k in ("wide", "medium", "closeup", "extreme_closeup")}
    d = [s[k].info["distance"] for k in ("wide", "medium", "closeup", "extreme_closeup")]
    assert d == sorted(d, reverse=True)
    assert s["extreme_closeup"].state(0).fov_y >= 80
    # head (y 3.75..5) fills >= 40 % of frame height in the extreme close-up
    f = proj_height_fraction(s["extreme_closeup"].state(0), [(0, 3.75, -0.625), (0, 5, -0.625)])
    assert f > 0.4


def test_all_presets_look_at_subject():
    for kind in C.SHOT_KINDS:
        if kind == "pov":
            continue
        cam = C.shot(kind, (2, 0, 3), facing_deg=40)
        cs = cam.state(0)
        assert np.all(np.isfinite(cs.eye)) and np.all(np.isfinite(cs.target))
        # subject centre must project inside the frame
        p = C.project_points(cs, [(2, 5 * C.PRESETS[kind]['cy'], 3)], 360, 640)[0]
        assert p[2] > 0 and 0 < p[0] < 360 and 0 < p[1] < 640, kind


def test_moves_additive_compose():
    base = C.shot("medium", (0, 0, 0))
    s0 = base.state(1.0)
    cam = C.shot("medium", (0, 0, 0)).push_in(0, 2, 0.2).drift(0, None, 0.3).shake(0.5, 1.5, 0.3)
    s = cam.state(1.0)
    # push_in moves closer; drift/shake only perturb
    d0 = np.linalg.norm(np.array(s0.eye) - np.array(s0.target))
    d1 = np.linalg.norm(np.array(s.eye) - np.array(s.target))
    assert d1 < d0
    assert s != cam.state(1.001)


def test_continuity_of_moves():
    cam = (C.shot("closeup", (0, 0, 0)).push_in(0, 3, 0.2).orbit(0.5, 2.5, 60)
           .drift(0, None, 0.3).shake(1, 2, 0.15).dutch(0.2, 1.0, 10).crane(0, 2, 2)
           .whip_pan(2.5, 2.8, 40).dolly_zoom(0, 3, 100).low_angle(0, 1, 1.0))
    ts = np.arange(0, 3.5, 1 / 120)
    prev = cam.state(ts[0])
    for t in ts[1:]:
        cur = cam.state(t)
        step = np.linalg.norm(np.array(cur.eye) - np.array(prev.eye))
        assert step < 0.25, (t, step)
        assert abs(cur.fov_y - prev.fov_y) < 1.0
        assert abs(cur.roll - prev.roll) < 1.5
        a, b = np.array(prev.target) - np.array(prev.eye), np.array(cur.target) - np.array(cur.eye)
        ang = math.degrees(math.acos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1)))
        assert ang < 4.0, (t, ang)
        prev = cur


def test_effects_hold_after_end_and_stop_at_cut():
    cam = C.Camera((0, 3, -10), (0, 3, 0)).push_in(0, 1, 0.5)
    assert cam.state(5).eye[2] == pytest.approx(-5.0)
    cam.snap_to(6, (10, 3, -10), (10, 3, 0), fov=50)
    assert cam.state(6).eye == pytest.approx((10, 3, -10))     # push_in does not leak into next shot
    assert cam.state(6).fov_y == 50 and cam.state(5.99).fov_y == 70


def test_follow_lags_moving_target():
    v, tau = 4.0, 0.3
    res = lambda name, t: (v * t, 3.0, 0.0) if name == "Bob" else (0, 0, 0)
    cam = C.Camera((0, 4, -10), (0, 3, 0)).bind(res).follow("Bob", damping=tau)
    e0 = cam.state(0).eye[0]
    for t in (2.0, 3.0):
        lag = v * t - (cam.state(t).eye[0] - e0)
        assert lag == pytest.approx(v * tau, rel=0.08)         # steady-state lag = v * tau
        tl = cam.state(t).target[0]
        assert tl < v * t                                      # trails the target
    # rigid follow has no lag; deterministic and order independent
    rigid = C.Camera((0, 4, -10), (0, 3, 0)).bind(res).follow("Bob", damping=0)
    assert rigid.state(2).eye[0] == pytest.approx(v * 2)
    assert cam.state(2.0) == cam.state(2.0)


def test_follow_absolute_offset_and_look_at():
    res = lambda name, t: (0.0, 3.0, -2.0 * t)
    cam = C.Camera().bind(res).follow("Bob", offset=(0, 2, 8), damping=0.0, look_offset=(0, 0, 0))
    s = cam.state(2.0)
    assert s.eye == pytest.approx((0, 5, 4))
    assert s.target == pytest.approx((0, 3, -4))
    cam2 = C.Camera((0, 3, 10), (0, 3, 0)).bind(res).look_at("Bob", 0, None, blend=0.0)
    assert cam2.state(3.0).target == pytest.approx((0, 3, -6))
    with pytest.raises(RuntimeError):
        C.Camera().look_at("Nobody").state(1)


def test_orbit_keeps_distance():
    cam = C.Camera((0, 3, -10), (0, 3, 0)).orbit(0, 2, 180)
    s = cam.state(2)
    assert s.eye == pytest.approx((0, 3, 10), abs=1e-6)
    s1 = cam.state(1)
    assert np.linalg.norm(np.array(s1.eye) - np.array(s1.target)) == pytest.approx(10)


def test_dolly_zoom_keeps_subject_size():
    cam = C.Camera((0, 3, -10), (0, 3, 0)).dolly_zoom(0, 2, 110)
    pts = [(0, 1, 0), (0, 5, 0)]
    f0 = proj_height_fraction(cam.state(0), pts)
    f1 = proj_height_fraction(cam.state(1.3), pts)
    assert f0 == pytest.approx(f1, rel=0.01)
    assert cam.state(2).fov_y == pytest.approx(110)


def test_easing_and_track_constant():
    for n in C.EASINGS:
        assert C.ease(n, 0.0) == pytest.approx(0.0, abs=1e-9)
        assert C.ease(n, 1.0) == pytest.approx(1.0, abs=1e-9)
    assert C.ease("back_out", 0.8) > 1.0            # overshoot
    cam = C.Camera().key(1, fov=90, ease="constant")
    assert cam.state(0.99).fov_y == 70 and cam.state(1.0).fov_y == 90


# ------------------------------- transitions -------------------------------- #

def test_whip_peaks_midway_and_continuous():
    w = T.whip(1.0, 1.2, "right", 70)
    ts = np.linspace(1.0, 1.2, 41)
    blur = [w.at(t).post["blur_amount"] for t in ts]
    assert int(np.argmax(blur)) == 20 and blur[0] == pytest.approx(0) and blur[-1] == pytest.approx(0, abs=1e-12)
    assert w.cut_time == pytest.approx(1.1)
    assert w.at(0.9).is_neutral and w.at(1.3).is_neutral
    yaw = np.array([w.at(t).cam_offset["yaw"] for t in ts])
    speed = np.abs(np.diff(yaw))
    assert int(np.argmax(speed)) in (19, 20)               # fastest at the middle
    assert yaw[0] == 0 and yaw[-1] == pytest.approx(0)
    # yaw sweep is continuous in angular speed across the cut: same sign, no reversal
    assert np.all(np.diff(yaw[:20]) > 0) and np.all(np.diff(yaw[21:]) > 0)
    assert w.at(1.0 + 0.1 - 1e-6).cam_offset["yaw"] == pytest.approx(70, abs=0.1)
    assert w.at(1.1 + 1e-6).cam_offset["yaw"] == pytest.approx(-70, abs=0.1)
    assert T.whip(0, 1, "up").at(0.5).post["blur_dir"] == (0.0, 1.0)
    assert T.whip(0, 1, "left").at(0.25).cam_offset["yaw"] < 0


def test_zoom_punch_flash_fade_shake():
    z = T.zoom_punch(2.0, 0.15, 0.25)
    mags = [1 / z.at(2.0 + i / 120).cam_offset["fov_scale"] for i in range(31)]
    assert max(mags) == pytest.approx(1.15, abs=0.005)
    assert mags[0] == pytest.approx(1.0) and mags[-1] == pytest.approx(1.0, abs=0.005)
    assert 1 / z.at(2.0 + 4 / 30).cam_offset["fov_scale"] == pytest.approx(1.15, abs=0.005)
    f = T.flash(1.0, 0.08)
    assert f.at(1.0).post["flash"] == 1.0 and f.at(1.08).post["flash"] == pytest.approx(0, abs=1e-9)
    assert T.fade(0, 1).at(0.5).post["fade"] == pytest.approx(0.5)
    assert T.fade(0, 1, to_black=False).at(0.25).post["fade"] == pytest.approx(0.75)
    s = T.shake_hit(1.0, 0.5, 0.3)
    assert s.at(1.0).cam_offset["shake"] == pytest.approx(0.5) and s.at(1.3).cam_offset["shake"] == pytest.approx(0)
    d = T.dust_cover(3.0, 0.4)
    assert d.at(3.2).meta["duration"] == 0.4 and d.cut_time == pytest.approx(3.2)


def test_compose_and_apply_offset():
    fx = T.compose([T.whip(0, 0.2), T.flash(0.1, 0.05), T.shake_hit(0.05, 0.4, 0.3), T.zoom_punch(0.0, 0.1, 0.2)], 0.1)
    assert fx.post["flash"] == 1.0 and fx.post["blur_amount"] > 0.06
    assert fx.cam_offset["shake"] > 0 and fx.cam_offset["fov_scale"] < 1.0
    cam = C.shot("medium", (0, 0, 0))
    base = cam.state(0.1)
    off = cam.state(0.1, offset=fx.cam_offset)
    assert off.fov_y < base.fov_y and off.target != base.target
    assert cam.state(0.1, offset=T.neutral_cam()) == base
    # yaw right turns the view toward +X for a camera looking along +Z? check sign on -Z view
    c2 = C.Camera((0, 3, 0), (0, 3, -10))
    r = c2.state(0, offset={"yaw": 30})
    assert r.target[0] > 1                       # looking down -Z, right is +X


def test_speed_ramp():
    sr = T.speed_ramp(1.0, 2.0, 1.0, 0.25, hold_to=3.0, back_to=3.5)
    assert sr.source_time(1.0) == pytest.approx(1.0)
    assert sr.speed(2.5) == pytest.approx(0.25)
    assert sr.source_time(0.5) == pytest.approx(0.5)
    assert sr.source_time(3.0) < 3.0 - 0.5
    ts = np.linspace(0, 5, 200)
    src = [sr.source_time(t) for t in ts]
    assert np.all(np.diff(src) > 0)
    assert sr.speed(10) == pytest.approx(1.0)
