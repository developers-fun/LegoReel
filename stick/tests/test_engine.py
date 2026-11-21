"""Engine tests for stickreel: tracks, scene validation, hit events, grounding, turnaround, walk distance,
phone video, and one full frame render. Run from /home/user/LegoReel/stick:

    python3 -m unittest discover tests
"""
import os
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

from stickreel.scene import Scene
from stickreel.track import Track, SceneError, parse_color
from stickreel.poses import LOOPS
from stickreel import items
from stickreel.render import render_frame

CANVAS = dict(w=200, h=300, fps=30, duration=3.0, scale=1.0, blur=1)


def make_scene(**parts):
    data = dict(canvas=dict(CANVAS))
    data.update(parts)
    return Scene(data, base_dir=tempfile.gettempdir())


def actor_scene(keys, **static):
    spec = dict(static)
    spec["keys"] = keys
    return make_scene(actors=dict(a=spec))


def img_bytes(im):
    return np.asarray(im.convert("RGBA"), dtype=np.int16)


class TrackTests(unittest.TestCase):
    def test_values_hold_from_previous_key(self):
        tr = Track({}, [dict(t=0, x=1.0, y=5.0, ease="linear"), dict(t=1, x=2.0, ease="linear")])
        self.assertAlmostEqual(tr.get("x", 0.5), 1.5)
        self.assertAlmostEqual(tr.get("y", 0.5), 5.0)   # y not set again: holds
        self.assertAlmostEqual(tr.get("y", 3.0), 5.0)

    def test_ease_applies_to_segment_ending_at_key(self):
        # 'in' on the key at t=1 shapes the 0 -> 1 segment: 100 * 0.5**3
        tr = Track({}, [dict(t=0, x=0.0), dict(t=1, x=100.0, ease="in")])
        self.assertAlmostEqual(tr.get("x", 0.5), 12.5, places=6)
        # 'in' on the key at t=0 has no segment ending there, so the 0 -> 1 segment keeps its own ease ('inout')
        tr2 = Track({}, [dict(t=0, x=0.0, ease="in"), dict(t=1, x=100.0)])
        self.assertAlmostEqual(tr2.get("x", 0.5), 50.0, places=6)

    def test_colours_blend(self):
        tr = Track({}, [dict(t=0, fill="#000000"), dict(t=1, fill="#ffffff", ease="linear")])
        c = parse_color(tr.get("fill", 0.5))
        for ch in c[:3]:
            self.assertLessEqual(abs(ch - 127.5), 1.0)
        self.assertEqual(parse_color(tr.get("fill", 0.0))[:3], (0, 0, 0))
        self.assertEqual(parse_color(tr.get("fill", 1.0))[:3], (255, 255, 255))

    def test_strings_step_at_key_time(self):
        tr = Track({}, [dict(t=0, text="a"), dict(t=1, text="b")])
        self.assertEqual(tr.get("text", 0.5), "a")
        self.assertEqual(tr.get("text", 0.999), "a")
        self.assertEqual(tr.get("text", 1.0), "b")
        self.assertEqual(tr.get("text", 2.0), "b")


class SceneErrorTests(unittest.TestCase):
    def assertSceneError(self, fn, *needles):
        with self.assertRaises(SceneError) as cm:
            fn()
        for n in needles:
            self.assertIn(n, str(cm.exception))
        return str(cm.exception)

    def test_misspelled_actor_property_suggests_fix(self):
        msg = self.assertSceneError(lambda: make_scene(actors=dict(a=dict(leen=1.0))), "Did you mean")
        self.assertIn("lean", msg)

    def test_misspelled_key_property_suggests_fix(self):
        self.assertSceneError(lambda: actor_scene([dict(t=0, leen=1.0)]), "Did you mean")

    def test_unknown_pose(self):
        self.assertSceneError(lambda: actor_scene([dict(t=0, pose="stnad")]), "unknown pose")

    def test_unknown_anim(self):
        self.assertSceneError(lambda: actor_scene([dict(t=0, anim="chpo")]), "unknown anim")

    def test_unknown_object_kind(self):
        self.assertSceneError(lambda: make_scene(objects=dict(o=dict(kind="blob"))), "unknown kind")

    def test_unknown_expr_on_keyed_expression(self):
        self.assertSceneError(lambda: actor_scene([dict(t=0, expr="happyy")]), "unknown expr")


class HitTests(unittest.TestCase):
    def setUp(self):
        self.scene = actor_scene([dict(t=0, anim="chop", hits=[0.5, 1.2, 1.9])])
        self.actor = self.scene.actors["a"]
        self.loop = self.scene.loops["chop"]
        self.seg = self.actor.segs[0]

    def test_hit_times(self):
        self.assertEqual(self.actor.hit_times(), [0.5, 1.2, 1.9])

    def test_hit_phase_at_hits(self):
        want = 4 / 22
        for t in (0.5, 1.2):
            self.assertAlmostEqual(self.actor.phase(self.loop, self.seg, t, 1.0), want, delta=1e-6)


class GroundingTests(unittest.TestCase):
    GROUND = 250.0

    def test_lowest_foot_touches_ground(self):
        for pose in ("stand", "crouch", "sit", "hands_up"):
            for yaw in (0, 90, 180, 270):
                with self.subTest(pose=pose, yaw=yaw):
                    sc = actor_scene([dict(t=0, pose=pose, yaw=float(yaw))], x=100.0, ground=self.GROUND, lift=0.0)
                    pose_d, _, _ = sc.actors["a"].solve(0.0)
                    lowest = max(f[1] for f in pose_d["feet"])
                    self.assertAlmostEqual(lowest, self.GROUND, delta=0.01)


class TurnaroundTests(unittest.TestCase):
    def render_at_yaw(self, yaw):
        sc = actor_scene([dict(t=0, pose="stand", yaw=float(yaw))], x=100.0, ground=250.0)
        return render_frame(sc, 0.0)

    @staticmethod
    def bbox(im):
        a = np.asarray(im.convert("RGBA"))[..., :3].sum(axis=2)
        ys, xs = np.nonzero(a)
        return xs.min(), ys.min(), xs.max(), ys.max()

    def test_front_and_back_differ(self):
        a = img_bytes(self.render_at_yaw(0))
        b = img_bytes(self.render_at_yaw(270))
        self.assertFalse(np.array_equal(a, b))

    def test_side_views_differ_and_silhouette_close(self):
        a = self.render_at_yaw(90)
        b = self.render_at_yaw(270)
        self.assertFalse(np.array_equal(img_bytes(a), img_bytes(b)))
        ba, bb = self.bbox(a), self.bbox(b)
        for u, v in zip(ba, bb):
            self.assertLessEqual(abs(int(u) - int(v)), 3)


class WalkDistanceTests(unittest.TestCase):
    def test_phase_advances_by_distance_over_stride(self):
        # linear x from 100 to 400 over 1 s: 300 px per second, stride 150 px -> phase 2 per second
        sc = actor_scene([dict(t=0, anim="walk", x=100.0, ease="linear"), dict(t=1, x=400.0, ease="linear")])
        a = sc.actors["a"]
        loop, seg = LOOPS["walk"], a.segs[0]
        t1, t2 = 0.2, 0.6
        dx = a.track.get("x", t2, 0) - a.track.get("x", t1, 0)
        self.assertAlmostEqual(dx, 120.0, places=6)
        p1 = a.phase(loop, seg, t1, 1.0)
        p2 = a.phase(loop, seg, t2, 1.0)
        advance = (p2 - p1) % 1.0
        self.assertAlmostEqual(advance, (dx / loop["stride"]) % 1.0, delta=1e-3)


class PhoneVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="stick_phone_")
        cls.video = os.path.join(cls.tmp, "clip.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc=size=240x480:rate=30:duration=2", "-pix_fmt", "yuv420p", cls.video],
                       check=True, timeout=60)
        cls.scene = Scene(dict(canvas=dict(CANVAS)), base_dir=cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_video_frames_change_over_time(self):
        p = dict(video="clip.mp4", video_start=0.0, loop=False, screen_color="#102030")
        a = np.asarray(items.screen_image(p, 0.1, self.scene), dtype=np.int16)
        b = np.asarray(items.screen_image(p, 1.5, self.scene), dtype=np.int16)
        self.assertEqual(a.shape, (items.SCREEN_H, items.SCREEN_W, 4))
        self.assertFalse(np.array_equal(a, b))

    def test_missing_video_falls_back_to_screen_colour(self):
        p = dict(video=os.path.join(self.tmp, "nope.mp4"), screen_color="#102030")
        im = items.screen_image(p, 0.5, self.scene)
        self.assertEqual(im.size, (items.SCREEN_W, items.SCREEN_H))
        self.assertEqual(im.getpixel((3, 3)), (16, 32, 48, 255))


class FullFrameTests(unittest.TestCase):
    def test_render_frame_with_pick_burst_and_pulse(self):
        sc = make_scene(
            objects=dict(
                pk=dict(kind="pick", x=0, y=0, angle=-45, len=40),
                burst=dict(kind="burst", times="a.hit", at=[100, 150], n=8, seed=3, life=0.5),
                pulse=dict(kind="pulse", times="a.hit", at=[100, 150], r=[30, 12], dur=0.2),
            ),
            actors=dict(a=dict(
                x=100.0, ground=250.0, prop="pk", prop_hand="r", expr="happy",
                keys=[dict(t=0, anim="chop", hits=[0.5, 1.2, 1.9])],
            )),
        )
        im = render_frame(sc, 0.6)
        self.assertEqual(im.size, (CANVAS["w"], CANVAS["h"]))


if __name__ == "__main__":
    unittest.main()
