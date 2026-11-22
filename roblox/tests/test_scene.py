import json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from r6reel.scene import Scene


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


def test_json_round_trip():
    s = make()
    d = s.to_dict()
    s2 = Scene.from_json(json.dumps(d))
    assert s2.to_dict() == d


def test_frame_deterministic():
    s = make()
    a = s.frame(1.37)
    b = s.frame(1.37)
    assert a[1] == b[1] and a[3] == b[3] and len(a[0]) == len(b[0])
    for x, y in zip(a[0], b[0]):
        assert np.allclose(x.model, y.model)


def test_validate_flags_problems():
    s = make()
    s.play("Milo", "no_such_clip", 0.1)
    assert any("unknown clip" in w for w in s.validate())
