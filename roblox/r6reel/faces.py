"""Searchable library of Roblox face images (transparent PNGs) for head decals.

    from r6reel import faces
    faces.search("#happy #laughing")            # AND match, list[Face]
    faces.search(["sad", "crying"], any_=True)  # OR match
    faces.get("Smile (default)")                # absolute PNG path (name, id, path or tag)
    faces.tags()                                # {tag: count}
    faces.random("#silly", seed=3)              # deterministic pick

CLI:
    python -m r6reel.faces search "#happy #laughing" [--any] [--limit N]
    python -m r6reel.faces tags
    python -m r6reel.faces get "#sad"

The library is read from assets/faces/index.json (built by tools/download_faces.py).
Faces are Roblox catalog assets; see docs/FACES.md for usage notes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import random as _random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Union

FACES_DIR = Path(__file__).resolve().parent.parent / "assets" / "faces"
INDEX_PATH = FACES_DIR / "index.json"

TagSpec = Union[str, Iterable[str], None]


@dataclass(frozen=True)
class Face:
    id: str
    name: str
    file: str            # absolute path to the PNG
    tags: tuple
    kind: str            # "decal" (flat face texture) or "thumbnail" (3D render, 420x420)
    asset_id: Optional[int] = None
    source: str = "roblox catalog"
    creator: str = ""

    def __str__(self) -> str:
        return f"{self.id}  {self.name}  [{' '.join('#' + t for t in self.tags)}]  {self.kind}"


def normalize_tags(tags: TagSpec) -> list[str]:
    """'#happy #laughing', 'happy, laughing', ['happy', '#laughing'] -> ['happy', 'laughing']."""
    if tags is None:
        return []
    if isinstance(tags, str):
        parts = re.split(r"[\s,;]+", tags)
    else:
        parts = []
        for t in tags:
            parts.extend(re.split(r"[\s,;]+", str(t)))
    out = []
    for p in parts:
        p = p.strip().lstrip("#").strip().lower()
        if p and p not in out:
            out.append(p)
    return out


@lru_cache(maxsize=1)
def _load() -> tuple[Face, ...]:
    raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    faces = []
    for e in raw:
        faces.append(Face(
            id=str(e["id"]),
            name=e.get("name", ""),
            file=str((FACES_DIR / e["file"]).resolve()),
            tags=tuple(sorted(set(t.lower() for t in e.get("tags", [])))),
            kind=e.get("kind", "thumbnail"),
            asset_id=e.get("asset_id"),
            source=e.get("source", "roblox catalog"),
            creator=e.get("creator", ""),
        ))
    return tuple(faces)


def reload() -> None:
    """Drop the cached index (call after editing assets/faces/index.json)."""
    _load.cache_clear()


def all_faces() -> list[Face]:
    return list(_load())


def search(tags: TagSpec = None, any_: bool = False, limit: Optional[int] = 20) -> list[Face]:
    """Faces matching all tags (default) or any of them. No tags returns every face.

    Results keep index order (ascending asset id). limit=None returns everything.
    """
    wanted = normalize_tags(tags)
    hits = []
    for f in _load():
        if not wanted:
            hits.append(f)
        elif any_ and any(t in f.tags for t in wanted):
            hits.append(f)
        elif not any_ and all(t in f.tags for t in wanted):
            hits.append(f)
    return hits if limit is None else hits[:limit]


def get(name_or_id: Union[str, int]) -> str:
    """Absolute path to a face PNG.

    Resolution order: an existing file path, then exact id or asset id, then exact name
    (case-insensitive), then the first face that has the tag(s) given.
    Raises KeyError when nothing matches.
    """
    key = str(name_or_id).strip()
    if key and Path(key).is_file():
        return str(Path(key).resolve())
    for f in _load():
        if key == f.id or (f.asset_id is not None and key == str(f.asset_id)):
            return f.file
    lowered = key.lower()
    for f in _load():
        if f.name.lower() == lowered:
            return f.file
    hits = search(key, limit=1)
    if hits:
        return hits[0].file
    raise KeyError(f"no face matches {name_or_id!r}")


def tags() -> dict:
    """{tag: number of faces with it}, sorted by tag name."""
    counts: dict[str, int] = {}
    for f in _load():
        for t in f.tags:
            counts[t] = counts.get(t, 0) + 1
    return dict(sorted(counts.items()))


def random(tags: TagSpec = None, seed: int = 0) -> Face:
    """Deterministic pick among faces matching tags (AND). Same seed, same face."""
    pool = search(tags, limit=None)
    if not pool:
        raise LookupError(f"no face has tags {normalize_tags(tags)}")
    return pool[_random.Random(seed).randrange(len(pool))]


def _main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m r6reel.faces", description="Search the face library.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="list faces matching tags")
    s.add_argument("tags", nargs="*", help='e.g. "#happy #laughing" or happy,laughing')
    s.add_argument("--any", action="store_true", help="match any tag instead of all")
    s.add_argument("--limit", type=int, default=20)
    sub.add_parser("tags", help="list tags with counts")
    g = sub.add_parser("get", help="print the PNG path for a name, id or tag")
    g.add_argument("name", nargs="+")
    args = ap.parse_args(argv)

    if args.cmd == "search":
        hits = search(args.tags, any_=args.any, limit=args.limit)
        for f in hits:
            print(f)
        print(f"{len(hits)} face(s)", file=sys.stderr)
    elif args.cmd == "tags":
        for t, n in sorted(tags().items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"{n:5d}  {t}")
    elif args.cmd == "get":
        try:
            print(get(" ".join(args.name)))
        except KeyError as exc:
            print(exc, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
