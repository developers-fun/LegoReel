import numpy as np
from r6reel.scene import Scene
from r6reel import audio as A


def _scene():
    sc = Scene.from_json({"version": 1, "name": "t", "width": 270, "height": 480, "fps": 30,
                          "sets": {"m": {"name": "m", "location": "town_square", "lighting": "day"}},
                          "characters": [{"name": "Jay", "avatar": {}, "position": [0, 0, 0], "sets": ["m"]}],
                          "actions": [{"character": "Jay", "type": "move_to", "t0": 0.0, "t1": 1.0, "pos": [0, 0, -4], "gait": "walk"}],
                          "shots": [{"t0": 0.0, "t1": 1.0, "kind": "wide", "set": "m", "subject": "Jay"},
                                    {"t0": 1.0, "t1": 2.0, "kind": "closeup", "set": "m", "subject": "Jay", "transition": {"type": "whip"}}],
                          "captions": [{"style": "storytime", "words": [["a", 0.1, 0.4], ["b", 0.4, 0.8]]}],
                          "audio": {"cues": [{"sfx": "whoosh", "times": "transition:whip", "delay": -0.1},
                                             {"sfx": "step", "times": "steps:Jay"}, {"sfx": "tick", "times": "words"}]}})
    sc._ensure_built()
    return sc


def test_times_resolve():
    sc = _scene()
    assert A.resolve_times(sc, "transition:whip") == [1.0]
    assert len(A.resolve_times(sc, "steps:Jay")) >= 2
    assert A.resolve_times(sc, "words") == [0.1, 0.4]
    assert A.resolve_times(sc, {"from": 0, "to": 1, "every": 0.5}) == [0.0, 0.5, 1.0]


def test_mix_is_audible_and_bounded():
    sc = _scene()
    m = A.mix(sc, sc.audio)
    assert m.shape == (int(round(sc.duration * 44100)), 2)
    assert 0.01 < np.abs(m).max() <= 0.98


def test_validate_flags_unknown_sfx():
    assert A.validate({"cues": [{"sfx": "nope", "t": 1}]})
