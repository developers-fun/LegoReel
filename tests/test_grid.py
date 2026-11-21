"""Stud-grid snapping. Run:  python3 -m unittest tests.test_grid -v"""
import copy
import math
import unittest
from pathlib import Path

import numpy as np

from blockreel import grid, preflight as pf
from blockreel.scene import Scene

ROOT = Path(__file__).resolve().parent.parent
P = 1.164


def make(props=None, chars=None, grid_cfg=None, shots=None, zones=None):
    d = {
        "meta": {"width": 270, "height": 480, "supersample": 1,
                 "ground": {"zones": zones or [], "tile": P, "colors": ["#d3d5db", "#c9ccd3"], "studs": 0.3}},
        "characters": chars or {"hero": {"avatar": "main", "variant": "plain", "position": [0, 0, 0]}},
        "props": props or [],
        "shots": shots or [{"id": "a", "duration": 2, "camera": {"preset": "medium", "focus": [0, 0, 0]}}],
    }
    if grid_cfg is not None:
        d["meta"]["grid"] = grid_cfg
    return Scene(d, ROOT)


class Functions(unittest.TestCase):
    def test_studs_rounds_and_never_zero(self):
        self.assertEqual(grid.studs(4 * P + 0.1, P), 4)
        self.assertEqual(grid.studs(0.01, P), 1)
        self.assertEqual(grid.studs(5.5 * P, P), 6)

    def test_even_and_odd_footprints_put_edges_on_lines(self):
        for n in range(1, 9):
            for raw in (-7.3, -0.2, 0.0, 0.41, 3.77, 12.9):
                c = grid.snap_edge_centre(raw, n, P)
                self.assertTrue(grid.on_lattice(c - n / 2 * P, P), (n, raw))
                self.assertLessEqual(abs(c - raw), P / 2 + 1e-9)

    def test_snapping_is_idempotent(self):
        for n in (1, 2, 3, 6):
            c = grid.snap_edge_centre(2.345, n, P)
            self.assertAlmostEqual(grid.snap_edge_centre(c, n, P), c)

    def test_rotation_snaps_to_quarter_turns(self):
        for raw, want in ((0, 0), (44, 0), (46, 90), (-100, -90), (179, 180), (-179, 180), (200, 180), (-46, -90)):
            self.assertEqual(grid.snap_rotation(raw), want, raw)

    def test_character_snaps_x_to_line_and_z_to_stud_centre(self):
        for x, z in ((0, 0), (3.1, -2.2), (-11.7, 40.3)):
            sx, sz = grid.snap_character_xz(x, z, P)
            self.assertTrue(grid.on_lattice(sx, P))
            self.assertTrue(grid.on_lattice(sz, P, 0.5))

    def test_height_is_whole_plates_with_bottom_on_plate_line(self):
        plates, h, b = grid.snap_height(0.37, 1.5, P)
        self.assertAlmostEqual(h, plates * 0.4 * P)
        self.assertAlmostEqual(b / (0.4 * P), round(b / (0.4 * P)))
        self.assertEqual(grid.snap_height(0.0, 0.01, P)[0], 1)

    def test_snap_box_footprint_4x6(self):
        pos, size, rot, info = grid.snap_box([1.0, 0.7, 2.0], [4.4, 1.2, 6.2 * P], 0, P)
        self.assertEqual(info["studs"], (4, 6))
        self.assertAlmostEqual(size[0], 4 * P)
        self.assertAlmostEqual(size[2], 6 * P)

    def test_swapped_footprint_for_quarter_turn(self):
        pos, size, rot, info = grid.snap_box([0, 1, 0], [4 * P, 1, 2 * P], 90, P)
        self.assertEqual(info["studs"], (4, 2))
        self.assertEqual(info["world_studs"], (2, 4))
        self.assertTrue(grid.on_lattice(pos[0] - 1 * P, P))      # 2 studs wide in world x
        self.assertTrue(grid.on_lattice(pos[2] - 2 * P, P))      # 4 studs deep in world z

    def test_zone_rect_on_lines_and_never_empty(self):
        r = grid.snap_zone_rect([-35, -14, -5, 14], P)
        self.assertTrue(all(grid.on_lattice(v, P) for v in r))
        r = grid.snap_zone_rect([1.0, 1.0, 1.1, 1.1], P)
        self.assertGreater(r[2], r[0])
        self.assertGreater(r[3], r[1])

    def test_extent_of_known_and_unknown_pieces(self):
        e = grid.piece_extent([{"size": [2, 1, 4], "pos": [1, 0.5, 0]}])
        self.assertEqual(e, (0.0, 2.0, -2.0, 2.0, 0.0))
        self.assertIsNone(grid.piece_extent([{"shape": "ldraw"}]))
        self.assertIsNone(grid.piece_extent([]))

    def test_template_scale_makes_larger_side_whole_studs(self):
        ext = grid.piece_extent([{"size": [5.0, 3, 3.0], "pos": [0, 1.5, 0]}])
        pos, rot, s, info = grid.snap_template([0.3, 0, 0.2], 0, 1.0, ext, P)
        self.assertAlmostEqual(5.0 * s / P, round(5.0 * s / P), places=6)
        self.assertEqual(info["studs"][0], 4)

    def test_template_scale_is_clamped(self):
        ext = grid.piece_extent([{"size": [0.2, 3, 0.2], "pos": [0, 1.5, 0]}])
        _, _, s, info = grid.snap_template([0, 0, 0], 0, 1.0, ext, P)
        self.assertTrue(info["clamped"])
        self.assertLessEqual(s, grid.FIT_RANGE[1] + 1e-9)

    def test_template_edges_land_on_lattice_even_when_rotated(self):
        ext = grid.piece_extent([{"size": [4.2, 2, 2.6], "pos": [0.7, 1, -0.4]}])
        for rot in (0, 90, 180, -90):
            pos, r, s, info = grid.snap_template([5.3, 0, -2.1], rot, 1.0, ext, P)
            a = math.radians(r)
            x0, x1, z0, z1, _ = ext
            lcx, lcz = (x0 + x1) / 2 * s, (z0 + z1) / 2 * s
            fcx = pos[0] + lcx * math.cos(a) + lcz * math.sin(a)
            fcz = pos[2] - lcx * math.sin(a) + lcz * math.cos(a)
            nx, nz = info["studs"]
            self.assertTrue(grid.on_lattice(fcx - nx / 2 * P, P), rot)
            self.assertTrue(grid.on_lattice(fcz - nz / 2 * P, P), rot)


class InScene(unittest.TestCase):
    def test_props_become_whole_stud_boxes_on_the_lattice(self):
        sc = make(props=[{"id": "slab", "position": [3.3, 0.5, -2.2], "size": [4.6, 0.5, 6.9], "rotation_y": 12}])
        p = sc.props[0]
        self.assertAlmostEqual(p.size[0] / P, 4, places=6)
        self.assertAlmostEqual(p.size[2] / P, 6, places=6)
        self.assertEqual(p.rotation_y, 0)
        self.assertTrue(grid.on_lattice(p.position[0] - p.size[0] / 2, P))
        self.assertTrue(grid.on_lattice(p.position[2] - p.size[2] / 2, P))
        self.assertAlmostEqual(p.size[1] / (0.4 * P), round(p.size[1] / (0.4 * P)))

    def test_prop_sitting_on_the_ground_stays_on_the_ground(self):
        sc = make(props=[{"id": "b", "position": [0, 1.0, 0], "size": [2, 2, 2]}])
        p = sc.props[0]
        self.assertAlmostEqual(p.position[1] - p.size[1] / 2, 0.0, places=6)

    def test_opt_out_keeps_exact_numbers(self):
        sc = make(props=[{"id": "free", "position": [3.3, 1, 2.2], "size": [4.6, 2, 6.9], "rotation_y": 12, "grid": False}])
        p = sc.props[0]
        self.assertEqual(tuple(p.size), (4.6, 2.0, 6.9))
        self.assertEqual(p.rotation_y, 12)

    def test_grid_can_be_turned_off(self):
        sc = make(props=[{"id": "b", "position": [3.3, 1, 2.2], "size": [4.6, 2, 6.9]}], grid_cfg={"enabled": False})
        self.assertEqual(tuple(sc.props[0].size), (4.6, 2.0, 6.9))
        self.assertIn("grid: off", sc.report())

    def test_characters_snap_start_move_and_teleport(self):
        sc = make(chars={"a": {"avatar": "main", "variant": "plain", "position": [2.2, 0, 3.3]}},
                  shots=[{"id": "s", "duration": 4, "camera": {"preset": "medium", "focus": [0, 0, 0]},
                          "actions": [{"t": 0, "character": "a", "move_to": [7.7, -4.4], "duration": 2},
                                      {"t": 2.5, "character": "a", "teleport": [-9.9, 0, 6.6]}]}])
        tl = sc.timelines["a"]
        end = tl.pos_at(2.2)
        self.assertTrue(grid.on_lattice(end[0], P) and grid.on_lattice(end[2], P, 0.5))
        tp = tl.pos_at(3.9)
        self.assertTrue(grid.on_lattice(tp[0], P) and grid.on_lattice(tp[2], P, 0.5))
        start = tl.pos_at(0.0)
        self.assertTrue(grid.on_lattice(start[0], P) and grid.on_lattice(start[2], P, 0.5))

    def test_character_y_is_preserved(self):
        sc = make(chars={"a": {"avatar": "main", "variant": "plain", "position": [0, 1.6, 0]}})
        self.assertAlmostEqual(sc.timelines["a"].pos_at(0)[1], 1.6)

    def test_zones_snap(self):
        sc = make(zones=[{"rect": [-35, -14, -5, 14], "colors": ["#d3d5db", "#c9ccd3"], "tile": P}])
        self.assertTrue(all(grid.on_lattice(v, P) for v in sc.ground["zones"][0]["rect"]))

    def test_set_piece_gets_a_whole_stud_footprint(self):
        sc = make(props=[{"id": "tree", "template": "nature_01", "position": [6.1, 0, -3.3], "rotation_y": 33, "scale": 1.1}])
        p = sc.props[0]
        self.assertEqual(p.rotation_y % 90, 0)
        self.assertTrue(p.snapped["studs"][0] >= 1)
        ext = grid.piece_extent(p.template.data["pieces"])
        big = max(ext[1] - ext[0], ext[3] - ext[2]) * p.scale / P
        self.assertAlmostEqual(big, round(big), places=5)

    def test_track_moves_with_the_snap(self):
        sc = make(props=[{"id": "ball", "position": [8.1, 1, 0.3], "size": [1, 1, 1],
                          "track": {"keys": [{"t": 0, "position": [8.1, 1, 0.3]}, {"t": 1, "position": [2.1, 1, 0.3]}]}}])
        p = sc.props[0]
        self.assertTrue(np.allclose(p.track[0][1], p.position))
        self.assertAlmostEqual(p.track[0][1][0] - p.track[1][1][0], 6.0, places=6)

    def test_report_lists_snapped_items(self):
        sc = make(props=[{"id": "slab", "position": [3.3, 0.5, -2.2], "size": [4.6, 0.5, 6.9]}])
        rep = sc.report()
        self.assertIn("grid: on", rep)
        self.assertIn("prop 'slab' ->", rep)

    def test_already_on_grid_scene_logs_nothing_for_props(self):
        sc = make(props=[{"id": "b", "position": [0, 0.5 * 0.4 * P * 3, 0], "size": [2 * P, 3 * 0.4 * P, 2 * P]}])
        self.assertFalse([g for g in sc.grid_log if g.startswith("prop")])


class Preflight(unittest.TestCase):
    def test_snapped_scene_passes_grid_checks(self):
        sc = make(props=[{"id": "slab", "position": [3.3, 0.5, -2.2], "size": [4.6, 0.5, 6.9]},
                         {"id": "tree", "template": "nature_01", "position": [6.1, 0, -3.3]}])
        rep = pf.Report()
        pf.check_grid(sc, rep)
        self.assertEqual(rep.errors, [], rep.text())

    def test_off_grid_prop_is_an_error(self):
        sc = make(props=[{"id": "slab", "position": [3.3, 0.5, -2.2], "size": [4.6, 0.5, 6.9]}])
        sc.props[0].size = (4.6, 0.5, 6.9)          # simulate something bypassing the snap
        rep = pf.Report()
        pf.check_grid(sc, rep)
        self.assertIn("grid_size", rep.codes("error"))

    def test_opt_out_is_reported_as_info(self):
        sc = make(props=[{"id": "free", "position": [3.3, 1, 2.2], "size": [4.6, 2, 6.9], "grid": False}])
        rep = pf.Report()
        pf.check_grid(sc, rep)
        self.assertIn("grid_optout", rep.codes("info"))

    def test_character_moved_off_lattice_warns(self):
        sc = make()
        sc.timelines["hero"].start_pos = np.array([0.3, 0.0, 0.1])
        rep = pf.Report()
        pf.check_grid(sc, rep)
        self.assertIn("grid_character", rep.codes("warn"))

    def test_prop_snapped_into_a_character_is_caught(self):
        # the snap grows a 2.5-unit-deep table to 3 studs; the hero stands right at its old edge
        sc = make(props=[{"id": "table", "position": [0, 0.75, 1.6], "size": [3, 1.5, 2.5]}],
                  chars={"hero": {"avatar": "main", "variant": "plain", "position": [0, 0, 0.4]}})
        rep = pf.static_checks(sc)
        self.assertIn("prop_intersects_character", rep.codes("error"), rep.text())


class Rendering(unittest.TestCase):
    def test_studs_on_snapped_prop_match_the_ground_lattice(self):
        from blockreel.render import _stud_items
        sc = make(props=[{"id": "slab", "position": [3.3, 0.5, -2.2], "size": [4 * P, 0.5, 3 * P], "studs": True}])
        p = sc.props[0]
        model = sc.prop_model(p, 0.0)
        items = _stud_items(model, p, {"spec": 0.0}, sc.pitch)
        self.assertEqual(len(items), 12)
        for it in items:
            x, z = it.model[0, 3], it.model[2, 3]
            self.assertTrue(grid.on_lattice(x, P, 0.5), x)
            self.assertTrue(grid.on_lattice(z, P, 0.5), z)

    def test_a_grid_scene_renders_a_frame(self):
        from blockreel.render import render_frame
        sc = make(props=[{"id": "slab", "position": [3.3, 0.5, -2.2], "size": [4.6, 0.5, 6.9], "studs": True}])
        im = render_frame(sc, 0)
        self.assertEqual(im.size, (sc.width, sc.height))
        self.assertGreater(np.asarray(im, dtype=np.float32).std(), 8)


if __name__ == "__main__":
    unittest.main()
