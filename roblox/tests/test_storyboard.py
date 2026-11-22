import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image
from r6reel.scene import Scene
from r6reel.storyboard import Storyboard, _Proj
from r6reel.renderer import CameraState


def make():
    s = Scene(180, 320, world="street")
    s.add_character("Milo", position=(0, 0.1, 7.5), hair="spiky:#5a3a22", shirt_color="#c4281c")
    s.add_character("Ava", position=(4, 0.1, 7.5), facing=90)
    s.play("Milo", "wave", 0.3)
    s.face("Milo", "shock", 1.0)
    s.move_to("Ava", (-8, 0.1, 7.5), 0.5, 2.5)
    s.add_shot(0, 1, "wide", subject="Milo", moves=[{"type": "push_in", "rate": 0.06}])
    s.add_shot(1, 2, "extreme_closeup", subject="Milo", transition={"type": "zoom_punch"})
    s.add_shot(2, 3, "medium", subject="Ava", follow=True, transition={"type": "whip"})
    s.add_caption("Hello there my friend", 0.1, 2.8)
    return s


def test_panels_sorted_unique_cover_shots():
    sc = make()
    sb = Storyboard(sc, max_panels=8, tile_h=160)
    ps = sb.panels()
    ts = [p.t for p in ps]
    assert ts == sorted(ts) and len(set(ts)) == len(ts)
    assert all(b - a >= 0.4 - 1e-6 for a, b in zip(ts, ts[1:]))
    assert {p.shot_index for p in ps} == {0, 1, 2}
    assert [p.index for p in ps] == list(range(1, len(ps) + 1))
    assert all(p.reasons for p in ps)


def test_sheet_and_save(tmp_path):
    sb = Storyboard(make(), max_panels=6, cols=3, tile_h=160)
    img = sb.sheet()
    assert isinstance(img, Image.Image) and img.width >= 3 * 90 and img.height > 160
    out = tmp_path / "sb" / "storyboard.png"
    paths = sb.save(out)
    assert os.path.exists(paths[0])
    assert (tmp_path / "sb" / "storyboard.md").read_text().count("##") == len(sb.panels())
    assert (tmp_path / "sb" / "storyboard.json").exists()


def test_explicit_times():
    sb = Storyboard(make(), tile_h=160, times=[0.5, 1.5])
    assert [p.t for p in sb.panels()] == [0.5, 1.5]


def test_backward_walk_warns():
    s = Scene(180, 320, world="street")
    s.add_character("Milo", position=(0, 0.1, 7.5))             # faces -Z
    s.move_to("Milo", (0, 0.1, 17.5), 0.0, 3.0, face=0.0, gait="walk")   # travels +Z, never turns first
    s.add_shot(0, 3, "wide", subject="Milo")
    sb = Storyboard(s, tile_h=160, times=[1.5])
    assert any("backward" in w for w in sb.panels()[0].warnings)


def test_offscreen_warns():
    s = Scene(180, 320, world="street")
    s.add_character("Milo", position=(0, 0.1, 7.5))
    s.add_shot(0, 2, "medium", subject="Milo", camera={"position": (0, 5, 0), "target": (0, 5, -30), "fov": 60})
    sb = Storyboard(s, tile_h=160, times=[1.0])
    assert any("off-screen" in w for w in sb.panels()[0].warnings)


def test_projection_maps_known_point():
    cs = CameraState(eye=(0, 0, 10), target=(0, 0, 0), fov_y=90.0)
    P = _Proj(cs, 100, 200)
    (x, y), z = P.pt((0, 0, 0))
    assert abs(x - 50) < 1e-6 and abs(y - 100) < 1e-6 and z < 0
    (x, y), _ = P.pt((1, 0, 0))                 # aspect 0.5: ndc x = 1 / (10 * 0.5) = 0.2
    assert abs(x - 60) < 1e-6
    (x, y), _ = P.pt((0, 1, 0))                 # ndc y = 0.1 -> up = smaller pixel y
    assert abs(y - 90) < 1e-6
    assert P.runs([(0, 0, 0), (0, 0, 20)]) == [[(50.0, 100.0)]] or len(P.runs([(0, 0, 0), (0, 0, 20)])) == 1
