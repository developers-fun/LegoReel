"""Run:  python -m unittest discover -s tests -v   (from the project folder)"""
import copy
import json
import unittest

from blockreel.avatar import load_avatar
from blockreel.errors import SceneError
from blockreel.rig import load_rig
from blockreel.scene import Scene
from blockreel.verify import check_rig

BASE = {
    "characters": {"hero": {"avatar": "main", "position": [0, 0, 0]}},
    "shots": [{"id": "a", "duration": 1, "camera": {"preset": "medium", "focus": [0, 0, 0]}}],
}


def scene(mod=None):
    d = copy.deepcopy(BASE)
    if mod:
        mod(d)
    return Scene(d, ".")


class RigTests(unittest.TestCase):
    def test_r6_numbers(self):
        r = load_rig("r6")
        self.assertEqual(r.part_size["torso"], (2.0, 2.0, 1.0))
        self.assertEqual(r.part_size["right_arm"], (1.0, 2.0, 1.0))
        self.assertEqual(r.head_visible, (1.25, 1.25, 1.25))
        self.assertAlmostEqual(r.height, 5.125)
        # right arm sits at -x in blockreel axes: pivot -1, centre -1.5
        j = r.joint["right_shoulder"]
        self.assertAlmostEqual(j["pivot"][0], -1.0)
        self.assertAlmostEqual(j["pivot"][1], 0.5)
        self.assertAlmostEqual(j["pivot"][0] + j["offset"][0], -1.5)
        # hip pivot is on the torso edge, the leg centre is at +-0.5
        h = r.joint["right_hip"]
        self.assertAlmostEqual(h["pivot"][0], -1.0)
        self.assertAlmostEqual(h["pivot"][0] + h["offset"][0], -0.5)

    def test_built_figure_matches_rig(self):
        self.assertIn("matches the rig", check_rig(load_rig("r6")))


class AvatarTests(unittest.TestCase):
    def test_fingerprint_is_stable_and_variants_differ(self):
        a1, a2 = load_avatar("main", None, None), load_avatar("main", None, None)
        self.assertEqual(a1.fingerprint, a2.fingerprint)
        self.assertNotEqual(a1.fingerprint, load_avatar("main", "jacket", None).fingerprint)

    def test_unknown_variant(self):
        with self.assertRaises(SceneError):
            load_avatar("main", "nope", None)

    def test_pinned_fingerprint_mismatch(self):
        with self.assertRaises(SceneError):
            scene(lambda d: d["characters"]["hero"].update({"avatar_fingerprint": "0000000000"}))

    def test_scale_must_be_one(self):
        with self.assertRaises(SceneError):
            scene(lambda d: d["characters"]["hero"].update({"scale": 1.2}))

    def test_inline_appearance_refused_under_house_style(self):
        with self.assertRaises(SceneError):
            scene(lambda d: d["characters"].update({"x": {"appearance": {"skin": "#fff"}}}))

    def test_avatar_plus_inline_refused(self):
        with self.assertRaises(SceneError):
            scene(lambda d: d["characters"]["hero"].update({"appearance": {"skin": "#fff"}}))


class CameraRuleTests(unittest.TestCase):
    def test_fixed_camera_ok(self):
        scene()

    def test_two_keyframes_refused(self):
        def mod(d):
            d["shots"][0]["camera"] = [{"t": 0, "preset": "medium"}, {"t": 1, "preset": "close"}]
        with self.assertRaises(SceneError):
            scene(mod)

    def test_follow_refused(self):
        def mod(d):
            d["shots"][0]["camera"] = {"position": [0, 3, 9], "target": "hero"}
        with self.assertRaises(SceneError):
            scene(mod)

    def test_shake_refused(self):
        with self.assertRaises(SceneError):
            scene(lambda d: d["shots"][0].update({"shake": 0.05}))

    def test_no_style_allows_motion(self):
        def mod(d):
            d["meta"] = {"style": None}
            d["characters"]["hero"] = {"appearance": {}}
            d["shots"][0]["camera"] = [{"t": 0, "position": [0, 3, 9], "look_at": [0, 3, 0]},
                                       {"t": 1, "position": [0, 3, 7], "look_at": [0, 3, 0]}]
            d["shots"][0]["shake"] = 0.02
        scene(mod)

    def test_frame_is_the_same_every_time_for_a_fixed_camera(self):
        s = scene()
        a, b = s.camera_at(0.1), s.camera_at(0.9)
        self.assertTrue((a.position == b.position).all() and (a.fwd == b.fwd).all())


if __name__ == "__main__":
    unittest.main()
