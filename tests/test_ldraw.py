"""LDraw importer and real-minifigure rig: geometry loads, prints survive, the figure builds in every pose."""
import random
import unittest
from pathlib import Path

import numpy as np

from blockreel import ldraw, parts
from blockreel.avatar import load_avatar
from blockreel.figure import build_brick_items
from blockreel import poses

ROOT = Path(__file__).resolve().parent.parent


class LDrawLibrary(unittest.TestCase):
    def test_attribution_files_ship_with_the_library(self):
        for name in ("CAreadme.txt", "CAlicense.txt"):
            self.assertTrue((ROOT / "ldraw" / name).exists(), name)

    def test_plain_head_loads_as_triangles(self):
        V, N, F, C = ldraw.load_mesh("3626b")
        self.assertGreater(len(F), 100)
        self.assertEqual(V.shape[1], 3)
        self.assertTrue(np.isfinite(V).all())

    def test_printed_head_has_explicit_colours(self):
        V, N, F, C = ldraw.load_mesh("3626bp01")
        self.assertTrue((np.asarray(C) >= 0).any() if C is not None and len(C) else False)

    def test_head_is_about_the_size_of_a_real_head(self):
        V, *_ = ldraw.load_mesh("3626b")
        ext = V.max(axis=0) - V.min(axis=0)
        # a minifig head is 24 LDU wide; the importer returns LDU
        self.assertTrue(18 < ext.max() < 40, ext)

    def test_part_title_comes_from_the_library(self):
        self.assertIn("Minifig", ldraw.part_title("3626bp01"))


class Catalog(unittest.TestCase):
    def test_catalog_is_large_and_valid(self):
        total = 0
        for folder in ("faces", "torsos", "hair", "headwear", "legs", "accessories"):
            ids = [i for i in parts.all_part_ids(folder) if i.startswith("ld_")]
            total += len(ids)
            for pid in random.Random(3).sample(ids, min(25, len(ids))):
                parts.load_part(folder, pid)
        self.assertGreater(total, 1500)


class Figure(unittest.TestCase):
    def test_every_variant_builds_in_every_pose(self):
        for variant in (None, "plain", "jacket", "host", "guest"):
            av = load_avatar("main", variant, None)
            for pose_name in poses.CLIPS:
                pose = poses.evaluate(pose_name, 0.4)
                items = build_brick_items(av, (0.0, 0.0, 0.0), 0.0, pose, None)
                self.assertGreater(len(items), 8, (variant, pose_name))

    def test_expression_swaps_the_head(self):
        av = load_avatar("main", None, None)
        a = build_brick_items(av, (0, 0, 0), 0.0, poses.full({}), None)
        b = build_brick_items(av, (0, 0, 0), 0.0, poses.full({}), "surprised")
        fa = {i.extra.get("file") for i in a if i.extra}
        fb = {i.extra.get("file") for i in b if i.extra}
        self.assertNotEqual(fa, fb)

    def test_gray_and_main_share_parts_but_not_colours(self):
        m, c = load_avatar("main", None, None), load_avatar("gray", None, None)
        self.assertNotEqual(m.fingerprint, c.fingerprint)
        self.assertEqual(m.parts["face"].id, c.parts["face"].id)


if __name__ == "__main__":
    unittest.main()


class Expressions(unittest.TestCase):
    def test_main_has_several_faces_per_emotion(self):
        av = load_avatar("main", None, None)
        for emo in ("happy", "laugh", "sad", "angry", "scared", "surprised", "smirk", "cool"):
            self.assertGreaterEqual(len([k for k in av.expressions if k.startswith(emo)]), 3, emo)
        self.assertGreaterEqual(len([k for k in av.expressions if k.startswith("talk_")]), 3)

    def test_back_side_face_turns_the_head(self):
        av = load_avatar("main", None, None)
        self.assertTrue(av.expressions["sad"].data.get("flip"))
        self.assertFalse(av.expressions["happy"].data.get("flip"))

    def test_lip_flap_only_with_talk_faces(self):
        from blockreel.render import _mouth_frame
        av = load_avatar("main", None, None)
        seen = {_mouth_frame(av, t / 30.0) for t in range(60)}
        self.assertIn(None, seen)
        self.assertTrue(any(s and s.startswith("talk_") for s in seen))
        gray = load_avatar("gray", None, None)
        gray.expressions = {k: v for k, v in gray.expressions.items() if not k.startswith("talk_")}
        self.assertIsNone(_mouth_frame(gray, 0.2))
