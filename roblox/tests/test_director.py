import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from r6reel.director import Director, Beat, parse_script
from r6reel.scene import Scene

SCRIPT = """
@cafeteria
Milo (shocked, drop): He dropped his lunch tray.
Ava (laughing, to=Milo): Nice one!
Then Milo ran down the hallway.
"""


def test_script_parses():
    b = parse_script(SCRIPT)
    assert len(b) == 3 and b[0].emotion == "shocked" and b[1].target == "Milo" and b[0].location == "cafeteria"


def test_director_valid_and_deterministic():
    a = Director(SCRIPT, seed=3, size=(180, 320)).build()
    b = Director(SCRIPT, seed=3, size=(180, 320)).build()
    assert a.to_dict() == b.to_dict()
    assert a.shots and a.captions and a.duration > 3
    sh = sorted(a.shots, key=lambda s: s.t0)
    for x, y in zip(sh, sh[1:]):
        assert abs(x.t1 - y.t0) < 1e-6
    assert all(0.4 < s.t1 - s.t0 < 4.5 for s in sh)
    a.frame(1.0)
    Scene.from_dict(a.to_dict())


def test_beats_and_overrides():
    sc = Director([Beat("Wow.", character="Zed", emotion="happy", shot="closeup", location="park")], seed=1,
                  size=(180, 320)).build()
    assert sc.shots[0].kind == "closeup"
    assert any(a["type"] == "face" for a in sc.actions)
