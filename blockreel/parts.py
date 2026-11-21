"""Part templates: faces, hair, headwear, torsos, legs, accessories and set pieces.

Every part is a small JSON file in parts/<folder>/<id>.json (plus an optional PNG or OBJ next to it).
Parts never hold final colours: they name palette slots ("hair", "primary", "pants"...), and the avatar
file says what colour each slot is. So one hair template works in every colour, and one torso template
works for every shirt colour. See parts/SCHEMA.md for the full format.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .errors import SceneError
from .mathutil import mat_mul, parse_color, rot_x, rot_y, rot_z, scale_m, translate

ROOT = Path(__file__).resolve().parent.parent

FOLDERS = {"faces": "face", "hair": "hair", "headwear": "headwear", "torsos": "torso", "legs": "legs",
           "accessories": "accessory", "sets": "set"}
SLOTS = ("skin", "hand", "hair", "primary", "secondary", "accent", "pants", "shoes", "metal", "dark", "light")
DEFAULT_PALETTE = {"skin": "#ffd23f", "hair": "#3b261b", "primary": "#2f6fe4", "secondary": "#ffffff",
                   "accent": "#ff5e4d", "pants": "#252b45", "shoes": "#2b2b30", "metal": "#b8bcc4",
                   "dark": "#23262e", "light": "#f4f4f4"}
SHAPES = ("box", "cylinder", "sphere", "obj", "ldraw")
PIECE_KEYS = {"shape", "size", "pos", "rot", "color", "bevel", "top", "bottom", "file", "scale", "spec", "subdiv", "casts", "part"}
ATTACH = ("head", "torso", "back", "hips", "hand_r", "hand_l")
TOP_KEYS = {"kind", "name", "note", "tags", "image", "pieces", "replaces_hair", "attach", "base", "arm", "bands",
            "hips", "keep_stud", "back_image", "ldraw", "title", "source", "flip"}


def find_part(folder, pid, base_dir=None):
    """Look for parts/<folder>/<pid>.json next to the scene first, then in the project."""
    if folder not in FOLDERS:
        raise SceneError(f"unknown part folder '{folder}'. Options: {', '.join(FOLDERS)}")
    dirs = []
    if base_dir:
        dirs += [Path(base_dir) / "parts" / folder, Path(base_dir).parent / "parts" / folder]
    dirs.append(ROOT / "parts" / folder)
    tried = []
    for d in dirs:
        p = d / f"{pid}.json"
        if p in tried:
            continue
        tried.append(p)
        if p.exists():
            return p
    raise SceneError(f"{FOLDERS[folder]} part '{pid}' not found. Looked in: {', '.join(str(p.parent) for p in tried)}")


class Part:
    def __init__(self, folder, pid, path, data):
        self.folder, self.id, self.path, self.data = folder, pid, path, data
        self.dir = path.parent

    def files(self):
        out = []
        for key in ("image", "back_image"):
            if self.data.get(key):
                out.append(self.dir / self.data[key])
        for pc in self.data.get("pieces", []):
            if pc.get("file"):
                out.append(self.dir / pc["file"])
        return out

    def digest(self):
        h = hashlib.sha256(json.dumps(self.data, sort_keys=True).encode("utf-8"))
        for f in self.files():
            if f.exists():
                h.update(f.read_bytes())
        return h.hexdigest()


def _num_list(v, n, ctx):
    if not isinstance(v, (list, tuple)) or len(v) != n or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        raise SceneError(f"{ctx}: expected {n} numbers, got {v!r}")
    return [float(x) for x in v]


def validate_part(folder, data, path):
    """Raise SceneError with the file and field named when a part is malformed."""
    ctx = str(path)
    if not isinstance(data, dict):
        raise SceneError(f"{ctx}: a part is a JSON object")
    unknown = set(data) - TOP_KEYS
    if unknown:
        raise SceneError(f"{ctx}: unknown keys {', '.join(sorted(unknown))}")
    kind = FOLDERS[folder]
    if data.get("kind") != kind:
        raise SceneError(f"{ctx}: \"kind\" must be \"{kind}\" for a file in parts/{folder}/ (found {data.get('kind')!r})")
    if not data.get("name"):
        raise SceneError(f"{ctx}: needs a \"name\" (a short human label)")
    ld = data.get("ldraw")
    if ld is not None:
        _check_ldraw(kind, ld, ctx)
    if kind == "face":
        if not data.get("image") and not data.get("pieces") and not ld:
            raise SceneError(f"{ctx}: a face needs an \"image\" (PNG, transparent background), \"pieces\" or an \"ldraw\" head")
    if kind == "accessory" and data.get("attach") not in ATTACH:
        raise SceneError(f"{ctx}: \"attach\" must be one of {', '.join(ATTACH)}")
    if kind in ("hair", "headwear", "accessory", "set") and not data.get("pieces"):
        raise SceneError(f"{ctx}: needs a non-empty \"pieces\" list")
    if kind == "legs" and ld:
        pass
    elif kind == "legs":
        bands = data.get("bands")
        if not bands:
            raise SceneError(f"{ctx}: legs need \"bands\": [{{\"from\": 0, \"to\": 1, \"color\": \"pants\"}}]")
        for i, b in enumerate(bands):
            if not (0 <= b.get("from", -1) < b.get("to", -1) <= 1):
                raise SceneError(f"{ctx}.bands[{i}]: needs 0 <= from < to <= 1 (fractions of leg height, top to bottom)")
            _check_color(b.get("color"), f"{ctx}.bands[{i}].color")
    for key in ("image", "back_image"):
        if data.get(key):
            f = path.parent / data[key]
            if not f.exists():
                raise SceneError(f"{ctx}: {key} file not found: {f}")
            if f.suffix.lower() != ".png":
                raise SceneError(f"{ctx}: {key} must be a .png")
            _check_png(f, ctx)
    for key in ("base", "arm", "hips"):
        if data.get(key):
            _check_color(data[key], f"{ctx}.{key}")
    for i, pc in enumerate(data.get("pieces", [])):
        _check_piece(pc, f"{ctx}.pieces[{i}]", path.parent)


def _check_ldraw(kind, ld, ctx):
    from .ldraw import load_mesh
    need = {"face": None, "torso": ("torso", "arm_r", "arm_l", "hand"), "legs": ("hips", "leg_r", "leg_l")}
    if kind not in need:
        raise SceneError(f"{ctx}: \"ldraw\" is only for faces (a head), torsos and legs")
    names = [ld] if kind == "face" else None
    if kind != "face":
        if not isinstance(ld, dict) or set(ld) != set(need[kind]):
            raise SceneError(f"{ctx}.ldraw: a {kind} needs exactly these keys: {', '.join(need[kind])}")
        names = list(ld.values())
    elif not isinstance(ld, str):
        raise SceneError(f"{ctx}.ldraw: a face's ldraw value is one head part number such as \"3626bp01\"")
    for n in names:
        try:
            load_mesh(n, 1.0)
        except ValueError as e:
            raise SceneError(f"{ctx}.ldraw: {e}")


def _check_png(f, ctx):
    from PIL import Image
    try:
        im = Image.open(f)
        im.load()
    except Exception as e:
        raise SceneError(f"{ctx}: cannot read {f.name}: {e}")
    if im.width > 2048 or im.height > 2048:
        raise SceneError(f"{ctx}: {f.name} is {im.width}x{im.height}; keep decals at 2048 pixels or less")
    if "A" not in im.convert("RGBA").getbands() or im.mode not in ("RGBA", "LA", "P"):
        raise SceneError(f"{ctx}: {f.name} has no transparency (mode {im.mode}). Save it as RGBA so the head or torso colour shows through")


def _check_color(c, ctx):
    if not isinstance(c, str):
        raise SceneError(f"{ctx}: a colour is a palette slot name or a hex string, got {c!r}")
    if c.startswith("#"):
        parse_color(c, ctx)
    elif c not in SLOTS:
        raise SceneError(f"{ctx}: '{c}' is not a palette slot. Slots: {', '.join(SLOTS)} (or use a #hex colour)")


def _check_piece(pc, ctx, base):
    if not isinstance(pc, dict):
        raise SceneError(f"{ctx}: a piece is a JSON object")
    unknown = set(pc) - PIECE_KEYS
    if unknown:
        raise SceneError(f"{ctx}: unknown keys {', '.join(sorted(unknown))}")
    shape = pc.get("shape")
    if shape not in SHAPES:
        raise SceneError(f"{ctx}: \"shape\" must be one of {', '.join(SHAPES)} (found {shape!r})")
    if shape == "ldraw":
        if not pc.get("part"):
            raise SceneError(f"{ctx}: an ldraw piece needs \"part\" (an LDraw part number such as 3901)")
        try:
            from .ldraw import load_mesh
            load_mesh(pc["part"], 1.0)
        except ValueError as e:
            raise SceneError(f"{ctx}: {e}")
    elif shape == "obj":
        if not pc.get("file"):
            raise SceneError(f"{ctx}: an obj piece needs \"file\"")
        f = base / pc["file"]
        if not f.exists():
            raise SceneError(f"{ctx}: obj file not found: {f}")
        try:
            from .meshes import obj_mesh
            obj_mesh(f, 1.0)
        except ValueError as e:
            raise SceneError(f"{ctx}: {e}")
    else:
        size = _num_list(pc.get("size"), 3, f"{ctx}.size")
        if any(x <= 0 or x > 60 for x in size):
            raise SceneError(f"{ctx}.size: each value must be above 0 and at most 60")
    _num_list(pc.get("pos", [0, 0, 0]), 3, f"{ctx}.pos")
    _num_list(pc.get("rot", [0, 0, 0]), 3, f"{ctx}.rot")
    for k in ("top", "bottom"):
        if k in pc:
            _num_list(pc[k], 2, f"{ctx}.{k}")
    _check_color(pc.get("color", "primary"), f"{ctx}.color")


_CACHE = {}


def load_part(folder, pid, base_dir=None, check=True):
    path = find_part(folder, pid, base_dir)
    key = (str(path), path.stat().st_mtime)
    if key in _CACHE:
        return _CACHE[key]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SceneError(f"{path}: not valid JSON: {e.msg} (line {e.lineno})")
    if check:
        validate_part(folder, data, path)
    _CACHE[key] = Part(folder, pid, path, data)
    return _CACHE[key]


def all_part_ids(folder):
    d = ROOT / "parts" / folder
    return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []


def resolve_color(c, palette):
    if c.startswith("#"):
        return parse_color(c)
    if c == "hand":
        c = "hand" if "hand" in palette else "skin"
    return tuple(parse_color(palette[c])) if c in palette else tuple(parse_color(DEFAULT_PALETTE[c]))


LD_SCALE = 0.0582          # studs per LDraw unit: a 92 LDU minifigure body becomes 5.35 studs


def pieces_to_items(pieces, frame, palette, part_dir, Item, glossy=True):
    """Turn a part's pieces into render Items. `frame` is the 4x4 matrix of the part's attach frame.
    Pieces with shape "ldraw" use LDraw units for pos (y up, front +z) and are scaled by LD_SCALE."""
    out = []
    for pc in pieces:
        pos = pc.get("pos", [0, 0, 0])
        rx, ry, rz = pc.get("rot", [0, 0, 0])
        if pc["shape"] == "ldraw":
            sc = LD_SCALE * float(pc.get("scale", 1.0))
            model = mat_mul(frame, translate(pos[0] * LD_SCALE, pos[1] * LD_SCALE, pos[2] * LD_SCALE),
                            rot_y(ry), rot_x(rx), rot_z(rz), scale_m(sc))
            col = resolve_color(pc.get("color", "primary"), palette)
            out.append(Item(model, (1.0, 1.0, 1.0), col, "ldraw", 0, bool(pc.get("casts", True)),
                            {"spec": 1.0 if pc.get("spec", glossy) else 0.0, "file": pc["part"]}))
            continue
        model = mat_mul(frame, translate(*pos), rot_y(ry), rot_x(rx), rot_z(rz))
        col = resolve_color(pc.get("color", "primary"), palette)
        extra = {"spec": 1.0 if (pc.get("spec", glossy)) else 0.0}
        if "top" in pc:
            extra["top"] = tuple(pc["top"])
        if "bottom" in pc:
            extra["bottom"] = tuple(pc["bottom"])
        size = pc.get("size", [1, 1, 1])
        if pc["shape"] == "obj":
            extra["file"] = str(part_dir / pc["file"])
            extra["scale"] = float(pc.get("scale", 1.0))
        else:
            extra["subdiv"] = int(pc.get("subdiv", 1 if min(size) >= 0.45 else 0))
        out.append(Item(model, tuple(float(x) for x in size), col, pc["shape"],
                        pc.get("bevel", 0.05), bool(pc.get("casts", pc["shape"] != "obj")), extra))
    return out
