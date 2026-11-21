import unittest

import numpy as np

from stickreel import audio as A
from stickreel.render import frame_rgb
from stickreel.scene import Scene
from stickreel.track import SceneError

BASE = {"canvas": {"w": 120, "h": 200, "scale": 1, "duration": 3, "fps": 30},
        "actors": {"a": {"x": 20, "ground": 150, "keys": [{"t": 0, "anim": "walk"}, {"t": 2, "x": 420, "ease": "linear"}]}}}


def scene(audio, **extra):
    d = dict(BASE, audio=audio)
    d.update(extra)
    return Scene(d)


class AudioTests(unittest.TestCase):
    def test_unknown_sfx_suggests(self):
        with self.assertRaises(SceneError) as c:
            scene({"cues": [{"sfx": "thnk", "t": 0.5}]})
        self.assertIn("thunk", str(c.exception))

    def test_cue_needs_t_or_times(self):
        with self.assertRaises(SceneError):
            scene({"cues": [{"sfx": "pop"}]})

    def test_mix_places_sound_and_limits_peak(self):
        s = scene({"cues": [{"sfx": "boom", "t": 1.0, "gain": 3.0}]})
        m = A.mix(s)
        self.assertEqual(m.shape, (int(3 * 44100), 2))
        self.assertLessEqual(float(np.abs(m).max()), 0.98 + 1e-6)
        self.assertLess(float(np.abs(m[:int(0.95 * 44100)]).max()), 1e-6)       # silent before the cue
        self.assertGreater(float(np.abs(m[int(1.0 * 44100):int(1.2 * 44100)]).max()), 0.1)

    def test_range_times_and_footsteps(self):
        s = scene({"cues": [{"sfx": "tick", "times": {"from": 0.5, "to": 0.6, "every": 0.05}}, {"sfx": "step", "times": "a.step"}]})
        self.assertEqual(len(s.times({"from": 0.5, "to": 0.6, "every": 0.05})), 3)
        steps = s.times("a.step")
        self.assertGreaterEqual(len(steps), 3)
        self.assertTrue(all(b > a for a, b in zip(steps, steps[1:])))
        A.mix(s)

    def test_partial_mix_window(self):
        s = scene({"cues": [{"sfx": "ding", "t": 2.0}]})
        m = A.mix(s, 1.5, 2.5)
        self.assertEqual(len(m), 44100)
        self.assertGreater(float(np.abs(m[int(0.5 * 44100):]).max()), 0.1)


class PolishTests(unittest.TestCase):
    def test_out_size_and_post(self):
        s = Scene(dict(BASE, canvas=dict(BASE["canvas"], out=[240, 400], post={"vignette": 0.2, "grain": 0.01})))
        self.assertEqual(frame_rgb(s, 3).size, (240, 400))

    def test_null_expr_is_allowed_and_blink_runs(self):
        Scene(dict(BASE, actors={"a": {"keys": [{"t": 0, "expr": None}]}}))
        s = Scene(dict(BASE, actors={"a": {"x": 60, "ground": 150, "keys": [{"t": 0, "expr": "happy", "yaw": 90}]}}))
        frame_rgb(s, 0)

    def test_camera_shake_moves_camera_only_near_events(self):
        s = Scene(dict(BASE, camera={"shake": {"times": [1.0], "amp": 4, "dur": 0.2}}))
        self.assertEqual(s.cam_at(0.5)["cx"], 288.0)
        self.assertNotEqual(s.cam_at(1.05)["cx"], 288.0)


if __name__ == "__main__":
    unittest.main()
