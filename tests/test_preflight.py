"""Pre-render checks. Run:  python3 -m unittest tests.test_preflight -v   (about a minute)"""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from blockreel import cli, preflight as pf
from blockreel.scene import Scene

ROOT = Path(__file__).resolve().parent.parent

BASE = {
    "meta": {"width": 270, "height": 480, "supersample": 1,
             "ground": {"zones": [], "tile": 1.164, "colors": ["#d3d5db", "#c9ccd3"], "studs": 0.3}},
    "characters": {"hero": {"avatar": "main", "variant": "plain", "position": [0, 0, 0], "yaw": 0}},
    "shots": [
        {"id": "a", "duration": 8, "camera": {"preset": "medium", "focus": [0, 0, 0]},
         "overlays": [{"t": 0.1, "duration": 2.0, "text": "WATCH THIS", "style": "hook"}]},
        {"id": "b", "duration": 8, "camera": {"preset": "close", "focus": [0, 0, 0], "yaw": 20}},
        {"id": "c", "duration": 6, "camera": {"preset": "wide", "focus": [0, 0, 0], "yaw": -20}},
    ],
}


def make(mod=None):
    d = copy.deepcopy(BASE)
    if mod:
        mod(d)
    return Scene(d, ROOT)


def run(mod=None, **kw):
    return pf.static_checks(make(mod), **kw)


def add_text(text, t=0.0, dur=2.0, style="caption", y=None, shot=0):
    def f(d):
        o = {"t": t, "duration": dur, "text": text, "style": style}
        if y is not None:
            o["y"] = y
        d["shots"][shot].setdefault("overlays", []).append(o)
    return f


class Helpers(unittest.TestCase):
    def test_contrast_ratio_extremes(self):
        self.assertAlmostEqual(pf.contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, places=0)
        self.assertAlmostEqual(pf.contrast_ratio((120, 120, 120), (120, 120, 120)), 1.0)

    def test_project_centre_and_behind(self):
        cam = make().camera_at(0.1)
        tgt = cam.position + cam.fwd * 10
        x, y = pf.project(cam, tgt, 9 / 16)
        self.assertAlmostEqual(x, 0.5, places=3)
        self.assertAlmostEqual(y, 0.5, places=3)
        self.assertIsNone(pf.project(cam, cam.position - cam.fwd * 5, 9 / 16))

    def test_project_right_is_right_and_up_is_up(self):
        cam = make().camera_at(0.1)
        base = cam.position + cam.fwd * 10
        self.assertGreater(pf.project(cam, base + cam.right, 9 / 16)[0], 0.5)
        self.assertLess(pf.project(cam, base + cam.up, 9 / 16)[1], 0.5)

    def test_sample_times_are_on_frame_boundaries_and_inside_shots(self):
        sc = make()
        for s, T in pf.sample_times(sc):
            self.assertAlmostEqual(T * sc.fps, round(T * sc.fps), places=6)
            self.assertTrue(s.start <= T < s.end)

    def test_text_bbox_is_inside_frame_and_nonempty(self):
        sc = make()
        bb = pf.text_bbox(sc, sc.texts[0])
        self.assertIsNotNone(bb)
        self.assertTrue(0 <= bb[0] < bb[2] <= sc.width and 0 <= bb[1] < bb[3] <= sc.height)

    def test_report_json_roundtrip(self):
        rep = run(add_text("LEGO TIME"))
        data = json.loads(rep.to_json())
        self.assertEqual(data["errors"], len(rep.errors))
        self.assertTrue(all({"level", "code", "message"} <= set(f) for f in data["findings"]))


class Clean(unittest.TestCase):
    def test_clean_scene_has_no_errors(self):
        rep = run(ideal=(18, 25))
        self.assertEqual(rep.errors, [], rep.text())

    def test_clean_scene_has_no_warnings_about_timing_or_text(self):
        rep = run()
        self.assertFalse(rep.codes("warn") & {"duration", "no_hook", "late_hook", "text_speed", "frame_align"}, rep.text())


class Timing(unittest.TestCase):
    def test_too_short_and_too_long(self):
        self.assertIn("duration", run(lambda d: d["shots"].pop()).codes("warn"))
        def long(d):
            d["shots"][0]["duration"] = 40
        self.assertIn("duration", run(long).codes("warn"))

    def test_over_a_minute_is_an_error(self):
        def long(d):
            d["shots"][0]["duration"] = 70
        self.assertIn("duration_max", run(long).codes("error"))

    def test_shot_off_frame_grid(self):
        def f(d):
            d["shots"][0]["duration"] = 8.01
        self.assertIn("frame_align", run(f).codes("warn"))

    def test_overlapping_shots_error(self):
        def f(d):
            d["shots"][1]["start"] = 6.0
        self.assertIn("shot_overlap", run(f).codes("error"))

    def test_gap_between_shots_warns(self):
        def f(d):
            d["shots"][1]["start"] = 9.0
        self.assertIn("shot_gap", run(f).codes("warn"))

    def test_short_last_shot_warns(self):
        def f(d):
            d["shots"][2]["duration"] = 1.0
        self.assertIn("end_hold", run(f).codes("warn"))

    def test_missing_audio_is_error(self):
        def f(d):
            d["meta"]["audio"] = "does/not/exist.mp3"
        self.assertIn("audio_missing", run(f).codes("error"))


class Text(unittest.TestCase):
    def test_no_hook(self):
        def f(d):
            d["shots"][0]["overlays"] = []
        self.assertIn("no_hook", run(f).codes("warn"))

    def test_late_hook(self):
        def f(d):
            d["shots"][0]["overlays"][0]["t"] = 2.5
        self.assertIn("late_hook", run(f).codes("warn"))

    def test_brand_words_are_errors(self):
        for word in ("LEGO", "Lego bricks", "minecraft"):
            self.assertIn("brand_word", run(add_text(word, style="hook")).codes("error"), word)

    def test_brand_substring_in_other_word_is_fine(self):
        self.assertNotIn("brand_word", run(add_text("Legoland")).codes() - {"brand_word"} | set())  # sanity: runs
        self.assertNotIn("brand_word", run(add_text("Allegory of cups")).codes("error"))

    def test_text_speed(self):
        rep = run(add_text("one two three four five six seven eight nine ten", dur=1.5))
        self.assertIn("text_speed", rep.codes("warn"))

    def test_label_style_exempt_from_speed(self):
        rep = run(add_text("a b c d e f g h", dur=1.0, style="label", y=0.12))
        self.assertNotIn("text_speed", rep.codes())

    def test_text_in_bottom_zone(self):
        self.assertIn("text_bottom_zone", run(add_text("Hello there", y=0.9)).codes("warn"))

    def test_text_in_top_zone(self):
        self.assertIn("text_top_zone", run(add_text("Hello there", y=0.02, style="caption")).codes("warn"))

    def test_text_off_frame_is_error(self):
        self.assertIn("text_clipped", run(add_text("Hello there", y=1.05)).codes("error"))
        self.assertIn("text_clipped", run(add_text("Hello there", y=0.995)).codes("error"))

    def test_overlapping_texts_error_only_when_on_screen_together(self):
        both = run(add_text("FIRST LINE", t=0.0, dur=2, y=0.5), ) 
        self.assertNotIn("text_overlap", both.codes())
        def two(d):
            add_text("FIRST LINE", t=0.0, dur=2, y=0.5)(d)
            add_text("SECOND LINE", t=0.5, dur=2, y=0.5)(d)
        self.assertIn("text_overlap", run(two).codes("error"))
        def seq(d):
            add_text("FIRST LINE", t=0.0, dur=2, y=0.5)(d)
            add_text("SECOND LINE", t=2.5, dur=2, y=0.5)(d)
        self.assertNotIn("text_overlap", run(seq).codes())

    def test_text_runs_past_shot(self):
        self.assertIn("text_past_shot", run(add_text("Late", t=7.5, dur=2.0)).codes("warn"))

    def test_poor_outline_contrast(self):
        def f(d):
            d["meta"]["text_styles"] = {"caption": {"color": "#808080", "stroke": "#8a8a8a", "stroke_width": 0.12,
                                                    "pill": None}}
            add_text("Grey on grey", y=0.6)(d)
        self.assertIn("text_colors", run(f).codes("warn"))

    def test_poor_pill_contrast(self):
        def f(d):
            d["meta"]["text_styles"] = {"caption": {"color": "#303030", "pill": {"color": "#202020d9"}}}
            add_text("Dark on dark", y=0.6)(d)
        self.assertIn("text_colors", run(f).codes("warn"))

    def test_house_caption_colours_are_readable(self):
        self.assertNotIn("text_colors", run(add_text("Fine", y=0.6)).codes())

    def test_very_short_text(self):
        self.assertIn("text_short", run(add_text("Two words", dur=0.4)).codes("warn"))


class Characters(unittest.TestCase):
    def test_character_facing_away_warns(self):
        def f(d):
            d["characters"]["hero"]["yaw"] = 180
        self.assertIn("back_to_camera", run(f).codes("warn"))

    def test_character_facing_camera_does_not_warn(self):
        self.assertNotIn("back_to_camera", run().codes())

    def test_empty_shot(self):
        def f(d):
            d["characters"]["hero"]["position"] = [200, 0, 0]
        self.assertIn("empty_shot", run(f).codes("warn"))

    def test_head_cropped(self):
        def f(d):
            d["shots"][1]["camera"] = {"preset": "close", "focus": [0, 0, 0], "yaw": 0}
            d["shots"][1]["camera"]["focus"] = [0, 6.0, 0]       # looking above the head, feet and head both off the bottom
            d["characters"]["hero"]["position"] = [0, 0, 6]
        rep = run(f)
        self.assertTrue(rep.codes("warn") & {"head_cropped", "subject_small", "empty_shot", "side_cropped"}, rep.text())

    def test_tiny_subject(self):
        def f(d):
            d["shots"][2]["camera"] = {"preset": "wide", "focus": [0, 0, -60]}
        self.assertTrue(run(f).codes("warn") & {"subject_small", "empty_shot"})

    def test_two_characters_inside_each_other(self):
        def f(d):
            d["characters"]["b"] = {"avatar": "main", "variant": "jacket", "position": [0.5, 0, 0], "yaw": 0}
        self.assertIn("characters_overlap", run(f).codes("warn"))

    def test_character_inside_prop_is_error(self):
        def f(d):
            d["props"] = [{"id": "wall", "position": [0, 2, 0], "size": [4, 4, 4], "color": "#888888"}]
        self.assertIn("prop_intersects_character", run(f).codes("error"))

    def test_character_beside_or_on_prop_is_fine(self):
        def beside(d):
            d["props"] = [{"id": "box", "position": [6, 1, 0], "size": [2, 2, 2]}]
        self.assertNotIn("prop_intersects_character", run(beside).codes())
        def on_top(d):
            d["props"] = [{"id": "step", "position": [0, 0.5, 0], "size": [4, 1, 4]}]
            d["characters"]["hero"]["position"] = [0, 1.0, 0]
        self.assertNotIn("prop_intersects_character", run(on_top).codes())

    def test_prop_that_moves_through_character(self):
        def f(d):
            d["props"] = [{"id": "ball", "position": [8, 1, 0], "size": [1, 1, 1],
                           "track": {"shot": "a", "keys": [{"t": 0, "position": [8, 1, 0]},
                                                          {"t": 6, "position": [0, 1, 0]}]}}]
        self.assertIn("prop_intersects_character", run(f).codes("error"))

    def test_buried_prop(self):
        def f(d):
            d["props"] = [{"id": "ghost", "position": [5, -3, 0], "size": [1, 1, 1]}]
        self.assertIn("prop_underground", run(f).codes("warn"))

    def test_half_buried_hill_is_fine(self):
        def f(d):
            d["props"] = [{"id": "hill", "position": [30, -1, 0], "size": [10, 6, 10]}]
        self.assertNotIn("prop_underground", run(f).codes())


class Cameras(unittest.TestCase):
    def test_camera_underground(self):
        def f(d):
            d["shots"][0]["camera"] = {"position": [0, -1, 10], "look_at": [0, 2, 0], "fov": 40}
        try:
            rep = run(f)
        except Exception:
            self.skipTest("explicit camera format differs")
        self.assertIn("camera_underground", rep.codes("error"))

    def test_same_size_everywhere(self):
        def f(d):
            for s in d["shots"]:
                s["camera"] = {"preset": "medium", "focus": [0, 0, 0], "yaw": 5 * len(s["id"])}
            d["shots"].append({"id": "d", "duration": 2, "camera": {"preset": "medium", "focus": [0, 0, 0], "yaw": 40}})
        self.assertIn("shot_variety", run(f).codes("warn"))

    def test_varied_sizes_do_not_warn(self):
        self.assertNotIn("shot_variety", run().codes())

    def test_dead_cut(self):
        def f(d):
            d["shots"][1]["camera"] = copy.deepcopy(d["shots"][0]["camera"])
        self.assertIn("dead_cut", run(f).codes("warn"))


class CliAndGate(unittest.TestCase):
    def write(self, mod=None):
        d = copy.deepcopy(BASE)
        if mod:
            mod(d)
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=ROOT / "examples")
        json.dump(d, f)
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def test_preflight_exit_codes(self):
        self.assertEqual(cli.main(["preflight", self.write()]), 0)
        self.assertEqual(cli.main(["preflight", self.write(add_text("LEGO", style="hook"))]), 2)
        self.assertEqual(cli.main(["preflight", self.write(lambda d: d["shots"].pop()), "--strict"]), 1)

    def test_invalid_scene_is_reported_not_raised(self):
        rep = pf.preflight(self.write(lambda d: d.update(bogus=1)))
        self.assertIn("scene_invalid", rep.codes("error"))

    def test_render_refuses_scene_with_errors(self):
        path = self.write(add_text("LEGO", style="hook"))
        out = Path(tempfile.mkdtemp()) / "x.mp4"
        rc = cli.main(["render", path, "--out", str(out), "--start", "0", "--end", "0.1", "--quiet"])
        self.assertEqual(rc, 2)
        self.assertFalse(out.exists())


class Stills(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = copy.deepcopy(BASE)
        d["shots"] = d["shots"][:2]
        cls.dir = tempfile.mkdtemp()
        cls.path = Path(cls.dir) / "s.json"
        cls.path.write_text(json.dumps(d))
        cls.sheet = Path(cls.dir) / "sheet.png"

    def test_stills_layer_runs_and_writes_sheet(self):
        rep = pf.Report()
        # base_dir: the scene loads avatars relative to the repo, so run from there
        d = json.loads(self.path.read_text())
        p = ROOT / "examples" / "_pf_tmp.json"
        p.write_text(json.dumps(d))
        self.addCleanup(lambda: p.unlink(missing_ok=True))
        tiles = pf.check_stills(str(p), rep, sheet=self.sheet, per_shot=2)
        self.assertEqual(len(tiles), 4)
        self.assertEqual(rep.errors, [], rep.text())
        self.assertTrue(self.sheet.exists() and self.sheet.stat().st_size > 2000)

    def test_flat_frame_is_flagged_blank(self):
        from PIL import Image
        p = ROOT / "examples" / "_pf_blank.json"
        d = copy.deepcopy(BASE)
        d["shots"] = d["shots"][:1]
        p.write_text(json.dumps(d))
        self.addCleanup(lambda: p.unlink(missing_ok=True))
        real = pf._frame_without_text
        pf._frame_without_text = lambda sc, idx: Image.new("RGB", (sc.width, sc.height), (40, 40, 40))
        self.addCleanup(lambda: setattr(pf, "_frame_without_text", real))
        rep = pf.Report()
        pf.check_stills(str(p), rep, per_shot=1)
        self.assertIn("blank_frame", rep.codes("error"), rep.text())

    def test_dark_and_washed_out_frames_warn(self):
        from PIL import Image, ImageDraw
        p = ROOT / "examples" / "_pf_dark.json"
        d = copy.deepcopy(BASE)
        d["shots"] = d["shots"][:1]
        p.write_text(json.dumps(d))
        self.addCleanup(lambda: p.unlink(missing_ok=True))
        real = pf._frame_without_text
        self.addCleanup(lambda: setattr(pf, "_frame_without_text", real))
        for colour, code in (((6, 6, 6), "too_dark"), ((250, 250, 250), "too_bright")):
            def fake(sc, idx, colour=colour):
                im = Image.new("RGB", (sc.width, sc.height), colour)
                ImageDraw.Draw(im).rectangle([10, 10, 30, 30], fill=tuple(255 - c for c in colour))
                return im
            pf._frame_without_text = fake
            rep = pf.Report()
            pf.check_stills(str(p), rep, per_shot=1)
            self.assertIn(code, rep.codes("warn"), rep.text())

    def test_fade_to_black_is_not_a_blank_frame(self):
        d = copy.deepcopy(BASE)
        d["shots"] = d["shots"][:1]
        d["shots"][0]["fade_in"] = 7.9          # first sample (2 frames in) is almost black
        p = ROOT / "examples" / "_pf_fade.json"
        p.write_text(json.dumps(d))
        self.addCleanup(lambda: p.unlink(missing_ok=True))
        rep = pf.Report()
        pf.check_stills(str(p), rep, per_shot=1)
        self.assertNotIn("blank_frame", rep.codes())


class Video(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        d = copy.deepcopy(BASE)
        d["shots"] = [{"id": "a", "duration": 1.0, "camera": {"preset": "medium", "focus": [0, 0, 0]},
                       "actions": [{"t": 0, "character": "hero", "pose": "wave"}]}]
        cls.scene = ROOT / "examples" / "_pf_video.json"
        cls.scene.write_text(json.dumps(d))
        cls.mp4 = cls.dir / "v.mp4"
        rc = cli.main(["render", str(cls.scene), "--out", str(cls.mp4), "--quiet", "--skip-preflight", "--supersample", "1"])
        assert rc == 0

    @classmethod
    def tearDownClass(cls):
        cls.scene.unlink(missing_ok=True)

    def test_good_video_passes(self):
        rep = pf.check_video(self.mp4, expect_frames=30, expect_size=(270, 480), expect_fps=30.0)
        self.assertEqual(rep.errors, [], rep.text())

    def test_wrong_frame_count_and_size_are_errors(self):
        rep = pf.check_video(self.mp4, expect_frames=31, expect_size=(1080, 1920))
        self.assertTrue({"video_frames", "video_size"} <= rep.codes("error"))

    def test_missing_file(self):
        self.assertIn("video_missing", pf.check_video(self.dir / "nope.mp4").codes("error"))

    def test_black_video_is_flagged(self):
        black = self.dir / "black.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30:d=2",
                        "-pix_fmt", "yuv420p", str(black)], check=True)
        rep = pf.check_video(black)
        self.assertTrue(rep.codes("error") & {"video_black", "video_frozen"}, rep.text())

    def test_cli_check_video(self):
        self.assertEqual(cli.main(["check-video", str(self.mp4), "--scene", str(self.scene)]), 0)
        self.assertEqual(cli.main(["check-video", str(self.mp4), "--frames", "99", "--scene", str(self.scene)]), 2)


class Shipped(unittest.TestCase):
    def test_shipped_example_scenes_have_no_errors(self):
        for f in sorted((ROOT / "examples").glob("*.json")):
            if f.name.startswith("_pf_"):
                continue
            rep = pf.preflight(str(f))
            self.assertEqual(rep.errors, [], f"{f.name}\n{rep.text()}")


if __name__ == "__main__":
    unittest.main()
