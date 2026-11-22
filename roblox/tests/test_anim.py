import numpy as np
import pytest
from r6reel import clips, rig, anim
from r6reel.anim import Animator, Clip, blend, layer, poses_equal, ease
from r6reel.avatar import Avatar

REQUIRED = """idle idle_bored breathe walk run sprint_panic jog jump fall land sit sit_slouch sit_desk stand_up wave point
point_up cheer shrug facepalm laugh cry shock scared angry talk nod shake_head lean_in cross_arms hands_on_hips tie_shoes
faint ragdoll_fall sleep_hug push throw catch hug dance_1 dance_2 dance_3 kick swim climb salute bow flex""".split()


def test_required_clips_exist():
    assert set(REQUIRED) <= set(clips.names())
    with pytest.raises(KeyError):
        clips.get("nope")


@pytest.mark.parametrize("name", clips.names())
def test_clip_sampling_finite_and_continuous(name):
    c = clips.get(name)
    ts = np.linspace(0, c.duration, 120)
    prev = None
    for t in ts:
        p = c.sample(t)
        arr = np.concatenate([np.array(p[k], float).ravel() for k in ("Neck", "Right Shoulder", "Left Shoulder", "Right Hip", "Left Hip")])
        assert np.isfinite(arr).all()
        if prev is not None and not c.keyframes[0][2] == "constant":
            # no teleports: <= 70 deg per sample step (1/120 of clip) except extreme snaps
            assert np.abs(arr - prev).max() < 120, (name, t)
        prev = arr


@pytest.mark.parametrize("name", [n for n in clips.names() if clips.get(n).loop])
def test_loops_seamless(name):
    c = clips.get(name)
    assert poses_equal(c.sample(0), c.keyframes[-1][1])
    a, b = c.sample(c.duration - 1e-4, loop=False), c.sample(0)
    assert poses_equal(a, b, tol=0.05)


def test_standing_clips_ground():
    for n in ("idle", "walk", "wave", "bow", "talk"):
        c = clips.get(n)
        for t in np.linspace(0, c.duration, 9):
            assert rig.lowest_y(c.sample(t)) > -0.6   # animator clamp handles the rest


def test_easing_endpoints():
    for n in anim.EASINGS:
        assert abs(ease(n, 0.0)) < 1e-9 and abs(ease(n, 1.0) - 1) < 1e-9
    assert ease("back_out", 0.6) > 1.0 - 1e-9 or ease("back_out", 0.8) > 1.0


def test_blend_layer():
    a = {"Neck": (0, 0, 0)}; b = {"Neck": (0, 90, 0), "Right Shoulder": (90, 0, 0)}
    assert np.allclose(blend(a, b, 0.5)["Neck"], (0, 45, 0), atol=1e-6)
    assert poses_equal(blend(a, b, 1.0), b) and poses_equal(blend(a, b, 0.0), a)
    out = layer(a, b, mask={"Right Shoulder"})
    assert np.allclose(out["Neck"], 0) and np.allclose(out["Right Shoulder"], (90, 0, 0))
    # shortest path: 170 -> -170 goes through 180
    mid = blend({"Neck": (0, 170, 0)}, {"Neck": (0, -170, 0)}, 0.5)["Neck"]
    assert np.allclose(rig.euler_to_matrix(*mid), rig.euler_to_matrix(0, 180, 0), atol=1e-6)


def test_animator_deterministic_and_moves():
    def build():
        an = Animator(Avatar(name="A"), position=(0, 0, 0))
        an.move_to((0, 0, -12), 1.0, 3.0)
        an.play("wave", at=4.0, mask="arms")
        an.look_at((5, 4.5, -10), 0.5, 2.0)
        an.face("shock", 2.5)
        return an
    a1, a2 = build(), build()
    for t in (0.0, 0.7, 1.5, 2.2, 3.5, 4.4):
        p1, c1 = a1.pose_at(t); p2, c2 = a2.pose_at(t)
        assert p1 == p2 and np.array_equal(c1, c2)
        assert a1.pose_at(t)[0] == p1
    assert np.allclose(a1.position_at(0.5), (0, 0, 0)) and np.allclose(a1.position_at(3.5), (0, 0, -12))
    assert abs(a1.facing_at(3.5)) < 1e-6                       # faces -Z = 0 deg
    assert a1.face_at(2.0) == "smile" and a1.face_at(3.0) == "shock"
    assert all(rig.lowest_y(a1.pose_at(t)[0]) >= -1e-6 for t in np.linspace(0, 5, 40))
    assert len(a1.draw_items(1.5)) >= 6


def test_move_faces_direction_and_gait():
    an = Animator(Avatar(name="B"))
    an.move_to((10, 0, 0), 0.0, 2.0, gait="auto")            # +X travel -> yaw -90
    assert abs(an.facing_at(2.0) - (-90)) < 1e-6
    assert any(L.clip.name in ("walk", "jog", "run") for L in an._layers)


def test_look_at_turns_head():
    an = Animator(Avatar(name="C"), noise=0)
    an.look_at((-5, 4.5, 0), 0, 5)     # character's left (-X)
    p, _ = an.pose_at(2.0)
    assert p["Neck"][1] > 30
