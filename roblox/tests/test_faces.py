"""Tests for r6reel.faces and the face index (assets/faces/index.json).

Run from the repo root:  python -m pytest tests/test_faces.py   (or python tests/test_faces.py)
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from r6reel import faces  # noqa: E402

FACES_DIR = ROOT / "assets" / "faces"
INDEX = json.loads((FACES_DIR / "index.json").read_text(encoding="utf-8"))
CORE_EMOTIONS = [
    "happy", "laughing", "sad", "crying", "angry", "shocked", "surprised", "scared", "worried",
    "nervous", "sleepy", "bored", "confused", "smirk", "cool", "silly", "love", "evil",
    "embarrassed", "serious", "neutral", "sick", "dizzy",
]


def test_normalize_tags_accepts_all_spellings():
    assert faces.normalize_tags("#happy #laughing") == ["happy", "laughing"]
    assert faces.normalize_tags("Happy, LAUGHING") == ["happy", "laughing"]
    assert faces.normalize_tags(["#Happy", "laughing", "happy"]) == ["happy", "laughing"]
    assert faces.normalize_tags(None) == []
    assert faces.normalize_tags("  ") == []


def test_index_is_large_and_well_formed():
    assert 40 <= len(INDEX) <= 60
    ids = [e["id"] for e in INDEX]
    assert len(ids) == len(set(ids)), "asset ids must be unique"
    for e in INDEX:
        assert e["tags"], f"{e['id']} has no tags"
        assert e["kind"] in ("decal", "thumbnail")  # lean library is all flat decals
        assert (FACES_DIR / e["file"]).is_file(), e["file"]


def test_every_core_emotion_has_at_least_1_face():
    counts = faces.tags()
    for tag in CORE_EMOTIONS:
        assert counts.get(tag, 0) >= 1, f"#{tag} has {counts.get(tag, 0)}"


def test_default_smile_is_present_and_tagged():
    smile = faces.search("#default #happy #smile", limit=None)
    assert any(f.id == "classic_smile" for f in smile)


def test_image_sizes_match_kind():
    for f in faces.search(None, limit=None)[:60] + faces.search("#default", limit=None):
        im = Image.open(f.file)
        assert im.mode == "RGBA"
        expected = (256, 256) if f.kind == "decal" else (420, 420)
        assert im.size == expected, f.id


def test_search_and_is_default_and_any_is_union():
    both = faces.search("#happy #laughing", limit=None)
    assert both, "expected some happy+laughing faces"
    assert all({"happy", "laughing"} <= set(f.tags) for f in both)
    either = faces.search(["happy", "laughing"], any_=True, limit=None)
    assert {f.id for f in both} <= {f.id for f in either}
    assert len(either) > len(both)


def test_search_limit_and_empty_query():
    assert len(faces.search("#happy", limit=5)) == 5
    assert len(faces.search(None, limit=3)) == 3
    assert len(faces.search(None, limit=None)) == len(INDEX)
    assert faces.search("#nosuchtag") == []


def test_get_by_id_name_path_and_tag():
    smile_path = faces.get("classic_smile")
    assert Path(smile_path).is_file() and Path(smile_path).is_absolute()
    assert faces.get("Smile") == smile_path      # case-insensitive exact name
    assert faces.get(smile_path) == smile_path            # existing file path passes through
    tagged = faces.get("#sick")
    assert "sick" in [t for f in faces.search("#sick", limit=None) if f.file == tagged for t in f.tags]


def test_get_missing_raises_keyerror():
    with pytest.raises(KeyError):
        faces.get("definitely-not-a-face-xyz")


def test_tags_counts_match_search():
    counts = faces.tags()
    assert counts == dict(sorted(counts.items()))
    assert counts["happy"] == len(faces.search("happy", limit=None))


def test_random_is_deterministic_and_in_pool():
    a = faces.random("#silly", seed=3)
    b = faces.random("#silly", seed=3)
    assert a == b
    assert "silly" in a.tags
    with pytest.raises(LookupError):
        faces.random("#nosuchtag")


def test_cli_search_and_tags():
    out = subprocess.run([sys.executable, "-m", "r6reel.faces", "search", "#happy #laughing", "--limit", "3"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    assert len([ln for ln in out.stdout.splitlines() if ln.strip()]) == 3
    out = subprocess.run([sys.executable, "-m", "r6reel.faces", "tags"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    assert "happy" in out.stdout


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
