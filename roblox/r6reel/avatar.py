"""Avatar: colors, classic-template clothing, face decal, hair/accessories -> DrawItems."""
from __future__ import annotations
import math, os, itertools
from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageDraw
from . import rig
from .rig import PARTS, TEMPLATE_W, TEMPLATE_H, TEMPLATE_RECTS
from .mesh import Mesh

_UID = itertools.count(1)
NOOB = {"Head": "#f5cd30", "Torso": "#0d69ac", "Left Arm": "#f5cd30", "Right Arm": "#f5cd30",
        "Left Leg": "#a4bd47", "Right Leg": "#a4bd47"}


def _color(c, default=(1, 1, 1)):
    """-> float RGB tuple 0..1 from '#rrggbb', 0..1 floats or 0..255 ints."""
    if c is None:
        return default
    if isinstance(c, str):
        s = c.lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    t = tuple(float(v) for v in c)[:3]
    return tuple(v / 255.0 for v in t) if max(t) > 1.0 else t


def _u8(c):
    return tuple(int(round(max(0, min(1, v)) * 255)) for v in _color(c))


def _make_drawitem():
    try:
        from r6reel.renderer import DrawItem
        return DrawItem
    except Exception:
        from dataclasses import field
        from typing import Any

        @dataclass
        class DrawItem:  # local fallback, same fields as SPEC.md
            mesh: Any
            model: Any
            color: tuple = (1, 1, 1)
            texture: Any = None
            material: str = "plastic"
            transparency: float = 0.0
            cast_shadow: bool = True
            receive_shadow: bool = True
            uv_scale: tuple = (1, 1)
            emissive: float = 0.0
            key: Any = None
        return DrawItem


# ------------------------------------------------------------------ faces
def _draw_face(name: str, S: int = 256) -> Image.Image:
    k = 4
    N = S * k
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    blk = (20, 20, 20, 255)
    w = lambda f: max(1, int(f * N))

    def box(cx, cy, rx, ry):
        return [(cx - rx) * N, (cy - ry) * N, (cx + rx) * N, (cy + ry) * N]

    def eyes(ry=0.075, rx=0.04, dy=0.0):
        for cx in (0.34, 0.66):
            d.ellipse(box(cx, 0.42 + dy, rx, ry), fill=blk)

    def arc(bb, a0, a1, wd=0.03):
        d.arc([bb[0] * N, bb[1] * N, bb[2] * N, bb[3] * N], a0, a1, fill=blk, width=w(wd))

    def line(p, q, wd=0.03):
        d.line([p[0] * N, p[1] * N, q[0] * N, q[1] * N], fill=blk, width=w(wd))

    n = name.lower()
    if n in ("smile", "default", "neutral_smile", ""):
        eyes(); arc((0.28, 0.40, 0.72, 0.74), 25, 155)
    elif n == "happy":
        for cx in (0.34, 0.66):
            arc((cx - 0.07, 0.36, cx + 0.07, 0.50), 200, 340, 0.035)
        d.pieslice(box(0.5, 0.6, 0.2, 0.15), 0, 180, fill=blk)
    elif n == "laugh":
        for cx, a in ((0.34, 1), (0.66, -1)):
            line((cx - 0.07 * a, 0.36), (cx + 0.05 * a, 0.42), 0.035)
            line((cx - 0.07 * a, 0.48), (cx + 0.05 * a, 0.42), 0.035)
        d.pieslice(box(0.5, 0.58, 0.24, 0.2), 0, 180, fill=blk)
        d.pieslice(box(0.5, 0.7, 0.13, 0.06), 0, 180, fill=(220, 90, 100, 255))
    elif n in ("shock", "scared", "shocked", "surprised"):
        for cx in (0.34, 0.66):
            d.ellipse(box(cx, 0.4, 0.075, 0.09), fill=(255, 255, 255, 255), outline=blk, width=w(0.012))
            d.ellipse(box(cx, 0.4, 0.025, 0.035), fill=blk)
        d.ellipse(box(0.5, 0.68, 0.06, 0.09), fill=blk)
    elif n == "angry":
        eyes(0.05, 0.035, 0.03)
        line((0.22, 0.28), (0.42, 0.36), 0.045); line((0.78, 0.28), (0.58, 0.36), 0.045)
        arc((0.34, 0.62, 0.66, 0.84), 200, 340, 0.035)
    elif n in ("sad", "cry", "worried"):
        eyes(0.06, 0.035, 0.03)
        line((0.22, 0.34), (0.42, 0.27), 0.03); line((0.78, 0.34), (0.58, 0.27), 0.03)
        arc((0.36, 0.62, 0.64, 0.82), 200, 340, 0.03)
        if n == "cry":
            for cx in (0.30, 0.70):
                d.rounded_rectangle([(cx - 0.025) * N, 0.5 * N, (cx + 0.025) * N, 0.82 * N], w(0.02),
                                    fill=(90, 170, 255, 230))
    elif n == "wink":
        arc((0.27, 0.38, 0.41, 0.50), 200, 340, 0.035)
        d.ellipse(box(0.66, 0.42, 0.04, 0.075), fill=blk)
        arc((0.28, 0.40, 0.72, 0.74), 25, 155)
    elif n == "smirk":
        eyes(); arc((0.36, 0.5, 0.74, 0.74), 20, 140, 0.03)
    elif n == "sleep":
        for cx in (0.34, 0.66):
            arc((cx - 0.07, 0.36, cx + 0.07, 0.48), 20, 160, 0.03)
        d.ellipse(box(0.5, 0.68, 0.035, 0.04), fill=blk)
    else:  # neutral
        eyes(); line((0.38, 0.66), (0.62, 0.66))
    return im.resize((S, S), Image.LANCZOS)


PROCEDURAL_FACES = ("smile", "happy", "laugh", "shock", "scared", "angry", "sad", "cry", "wink",
                    "smirk", "sleep", "neutral", "worried")


def resolve_face(face) -> Image.Image:
    """face: PIL image | file path | name (faces.get, then procedural) | None (default smile)."""
    if isinstance(face, Image.Image):
        return face.convert("RGBA").resize((256, 256), Image.LANCZOS)
    if face is None:
        return _draw_face("smile")
    s = str(face)
    if os.path.isfile(s):
        return Image.open(s).convert("RGBA").resize((256, 256), Image.LANCZOS)
    if s.lower() not in ("smile", "default"):
        try:
            from r6reel import faces as _faces
            p = _faces.get(s)
            if p and os.path.isfile(str(p)):
                return Image.open(str(p)).convert("RGBA").resize((256, 256), Image.LANCZOS)
        except Exception:
            pass
    return _draw_face(s)


# ------------------------------------------------------------------ clothing layers
def _load_layer(src, color_tint=None):
    """texture (PIL/path) -> RGBA template layer or None."""
    if src is None:
        return None
    im = None
    if isinstance(src, Image.Image):
        im = src
    elif isinstance(src, np.ndarray):
        im = Image.fromarray(src)
    elif isinstance(src, str) and os.path.isfile(src):
        im = Image.open(src)
    if im is None:
        return None
    im = im.convert("RGBA")
    if im.size != (TEMPLATE_W, TEMPLATE_H):
        im = im.resize((TEMPLATE_W, TEMPLATE_H), Image.LANCZOS)
    if color_tint is not None:
        a = np.asarray(im).astype(np.float32)
        a[..., :3] *= np.array(_color(color_tint), np.float32)
        im = Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGBA")
    return im


def flat_layer(kind: str, color) -> Image.Image:
    """Synthetic template layer from a flat color. kind: 'shirt' (torso + sleeves) or 'pants'."""
    im = Image.new("RGBA", (TEMPLATE_W, TEMPLATE_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = _u8(color) + (255,)
    for part, faces in TEMPLATE_RECTS.items():
        for face, (x, y, w, h) in faces.items():
            if kind == "shirt" and part in ("Torso", "Right Arm", "Left Arm"):
                if part == "Torso":
                    d.rectangle([x, y, x + w - 1, y + h - 1], fill=c)
                elif face == "top":
                    d.rectangle([x, y, x + w - 1, y + h - 1], fill=c)
                elif face != "bottom":
                    d.rectangle([x, y, x + w - 1, y + int(h * 0.72) - 1], fill=c)
            elif kind == "pants" and part in ("Torso", "Right Leg", "Left Leg"):
                if part == "Torso":
                    if face == "bottom":
                        d.rectangle([x, y, x + w - 1, y + h - 1], fill=c)
                    elif face != "top":
                        d.rectangle([x, y + int(h * 0.76), x + w - 1, y + h - 1], fill=c)
                elif face != "top":
                    d.rectangle([x, y, x + w - 1, y + h - 1], fill=c)
    return im


# ------------------------------------------------------------------ hair & accessories (head-local space)
from .rig import box_mesh, sphere_mesh, cylinder_mesh, cone_mesh, arc_mesh  # noqa: E402

Piece = tuple  # (name, Mesh, color(None->accessory color), material, transparency)


def _tf(mesh, pos=(0, 0, 0), rot=(0, 0, 0)):
    return mesh.transformed(rig.cframe(pos, rot))


def _cap(h=0.5, grow=0.07, back=0.05):
    """Hair cap hugging the top/back of the head."""
    return box_mesh((1.25 + grow * 2, h, 1.25 + grow * 2 - 0.1), (0, 0.6 - h / 2 + 0.06, back), 0.2, 3)


def _spiky():
    ps = [("base", _cap(0.45), None, "plastic", 0.0)]
    rng = np.random.RandomState(7)
    for i, (x, z, tx, tz) in enumerate([(0, -0.3, 0, -18), (-0.35, -0.1, 22, -10), (0.35, -0.1, -22, -10),
                                        (0, 0.1, 0, 0), (-0.38, 0.3, 24, 12), (0.38, 0.3, -24, 12), (0, 0.4, 0, 22)]):
        ps.append((f"s{i}", _tf(cone_mesh(0.2, 0.62, 8), (x, 0.88, z), (tz, 0, tx)), None, "plastic", 0.0))
    return ps


def _bun():
    return [("base", _cap(0.5), None, "plastic", 0), ("bun", sphere_mesh((0.36, 0.36, 0.36), 10, (0, 0.85, 0.15)), None, "plastic", 0)]


def _bacon():
    return [("base", _cap(0.42, 0.06), None, "plastic", 0),
            ("fringe", _tf(box_mesh((1.38, 0.28, 0.5), radius=0.1), (0, 0.5, -0.38), (-14, 0, 0)), None, "plastic", 0),
            ("swoop", _tf(box_mesh((0.7, 0.2, 0.6), radius=0.08), (-0.25, 0.7, -0.2), (-10, 0, 14)), None, "plastic", 0)]


def _ponytail():
    ps = [("base", _cap(0.5), None, "plastic", 0),
          ("tie", box_mesh((0.36, 0.12, 0.36), (0, 0.25, 0.7), 0.04), (0.85, 0.15, 0.2), "plastic", 0)]
    for i, (y, z, s) in enumerate([(0.2, 0.78, 0.3), (-0.12, 0.82, 0.34), (-0.5, 0.84, 0.3)]):
        ps.append((f"t{i}", box_mesh((s, 0.42, s), (0, y, z), 0.1), None, "plastic", 0))
    return ps


def _pigtails():
    ps = [("base", _cap(0.5), None, "plastic", 0)]
    for sx in (-1, 1):
        for i, (y, s) in enumerate([(0.2, 0.3), (-0.12, 0.28), (-0.42, 0.24)]):
            ps.append((f"p{sx}{i}", box_mesh((s, 0.4, s), (sx * 0.78, y, 0.3), 0.1), None, "plastic", 0))
    return ps


def _long():
    return [("base", _cap(0.55), None, "plastic", 0),
            ("back", box_mesh((1.45, 1.15, 0.34), (0, -0.05, 0.62), 0.1), None, "plastic", 0),
            ("sideL", box_mesh((0.2, 0.9, 0.55), (-0.68, -0.05, 0.25), 0.07), None, "plastic", 0),
            ("sideR", box_mesh((0.2, 0.9, 0.55), (0.68, -0.05, 0.25), 0.07), None, "plastic", 0),
            ("fringe", _tf(box_mesh((1.3, 0.18, 0.3), radius=0.07), (0, 0.5, -0.5), (-12, 0, 0)), None, "plastic", 0)]


def _afro():
    return [("afro", sphere_mesh((0.98, 0.9, 0.86), 14, (0, 0.55, 0.3)), None, "plastic", 0)]


def _mohawk():
    ps = []
    for i, z in enumerate(np.linspace(-0.5, 0.5, 6)):
        ps.append((f"m{i}", box_mesh((0.18, 0.5 - 0.04 * i, 0.22), (0, 0.78 - 0.02 * i, z), 0.05), None, "plastic", 0))
    return ps


def _cap_hat():
    return [("dome", box_mesh((1.38, 0.5, 1.38), (0, 0.42, 0.02), 0.22, 3), None, "plastic", 0),
            ("brim", box_mesh((1.05, 0.08, 0.7), (0, 0.22, -0.88), 0.03), None, "plastic", 0),
            ("button", sphere_mesh((0.08, 0.08, 0.08), 6, (0, 0.7, 0.02)), None, "plastic", 0)]


def _beanie():
    return [("dome", box_mesh((1.38, 0.8, 1.38), (0, 0.35, 0.02), 0.3, 3), None, "plastic", 0),
            ("fold", box_mesh((1.44, 0.2, 1.44), (0, 0.12, 0.02), 0.06), (0.9, 0.9, 0.92), "plastic", 0),
            ("pom", sphere_mesh((0.2, 0.2, 0.2), 8, (0, 0.85, 0.02)), (0.95, 0.95, 0.95), "plastic", 0)]


def _tophat():
    return [("brim", cylinder_mesh(0.95, 0.08, 24, "y", (0, 0.62, 0)), None, "plastic", 0),
            ("tube", cylinder_mesh(0.56, 0.95, 24, "y", (0, 1.1, 0)), None, "plastic", 0),
            ("band", cylinder_mesh(0.575, 0.2, 24, "y", (0, 0.8, 0)), (0.75, 0.1, 0.12), "plastic", 0)]


def _crown():
    ps = [("ring", cylinder_mesh(0.62, 0.28, 20, "y", (0, 0.74, 0)), None, "metal", 0)]
    for i in range(6):
        a = i * math.pi / 3
        ps.append((f"pt{i}", cone_mesh(0.14, 0.34, 6, (0.5 * math.cos(a), 1.04, 0.5 * math.sin(a))), None, "metal", 0))
        ps.append((f"gem{i}", sphere_mesh((0.06, 0.06, 0.06), 5, (0.5 * math.cos(a), 1.24, 0.5 * math.sin(a))),
                   (0.9, 0.1, 0.2), "plastic", 0))
    return ps


def _glasses(dark=False):
    ps = []
    z = -0.66
    for sx in (-1, 1):
        cx = sx * 0.25
        t = 0.045
        ps += [(f"top{sx}", box_mesh((0.42, t, 0.04), (cx, 0.29, z)), None, "plastic", 0),
               (f"bot{sx}", box_mesh((0.42, t, 0.04), (cx, -0.02, z)), None, "plastic", 0),
               (f"l{sx}", box_mesh((t, 0.34, 0.04), (cx - 0.2, 0.135, z)), None, "plastic", 0),
               (f"r{sx}", box_mesh((t, 0.34, 0.04), (cx + 0.2, 0.135, z)), None, "plastic", 0),
               (f"lens{sx}", box_mesh((0.36, 0.28, 0.02), (cx, 0.135, z - 0.005)),
                (0.05, 0.05, 0.07) if dark else (0.7, 0.85, 1.0), "glass", 0.0 if dark else 0.65),
               (f"arm{sx}", box_mesh((0.04, 0.04, 0.62), (sx * 0.46, 0.27, -0.35)), None, "plastic", 0)]
    ps.append(("bridge", box_mesh((0.12, t, 0.04), (0, 0.27, z)), None, "plastic", 0))
    return ps


def _headphones():
    ps = [("band", _tf(arc_mesh(0.72, 0.1, 0.2, 0, 180, 20), (0, -0.02, 0)), None, "plastic", 0)]
    for sx in (-1, 1):
        ps.append((f"cup{sx}", cylinder_mesh(0.3, 0.24, 16, "x", (sx * 0.74, 0.0, 0.0)), (0.12, 0.12, 0.14), "plastic", 0))
        ps.append((f"pad{sx}", cylinder_mesh(0.24, 0.3, 16, "x", (sx * 0.72, 0.0, 0.0)), (0.9, 0.2, 0.3), "plastic", 0))
    return ps


def _backpack():
    ps = [("body", box_mesh((1.4, 1.65, 0.55), (0, 0.0, 0.8), 0.12), None, "plastic", 0),
          ("pocket", box_mesh((1.0, 0.6, 0.18), (0, -0.4, 1.12), 0.06), None, "plastic", 0)]
    for sx in (-1, 1):
        ps.append((f"strap{sx}", box_mesh((0.22, 1.5, 0.08), (sx * 0.55, 0.15, -0.54)), None, "plastic", 0))
        ps.append((f"strapT{sx}", box_mesh((0.22, 0.08, 1.0), (sx * 0.55, 0.96, 0.0)), None, "plastic", 0))
    return ps


# name -> (builder, attach part, default color)
ACCESSORIES = {
    "bun": (_bun, "Head", "#6b3f1d"), "bacon": (_bacon, "Head", "#8a4a1c"),
    "ponytail": (_ponytail, "Head", "#e8c15a"), "pigtails": (_pigtails, "Head", "#d4503a"),
    "spiky": (_spiky, "Head", "#1d1d22"), "buzz": (lambda: [("base", _cap(0.32, 0.03), None, "plastic", 0)], "Head", "#3a2a1c"),
    "long": (_long, "Head", "#2b1b12"), "afro": (_afro, "Head", "#1a1412"), "mohawk": (_mohawk, "Head", "#e03070"),
    "cap": (_cap_hat, "Head", "#c8242b"), "beanie": (_beanie, "Head", "#2c6fbb"),
    "tophat": (_tophat, "Head", "#17171a"), "crown": (_crown, "Head", "#f2c230"),
    "glasses": (_glasses, "Head", "#1b1b1f"), "sunglasses": (lambda: _glasses(True), "Head", "#111114"),
    "headphones": (_headphones, "Head", "#222226"), "backpack": (_backpack, "Torso", "#d8512b"),
}
HAIR_NAMES = ("bun", "bacon", "ponytail", "pigtails", "spiky", "buzz", "long", "afro", "mohawk", "cap", "beanie", "tophat", "crown")
_ACC_CACHE: dict = {}


def accessory_pieces(name, style=None):
    style = style or rig.get_edge_style()
    if (name, style) not in _ACC_CACHE:
        if name not in ACCESSORIES:
            raise KeyError(f"unknown accessory '{name}'. Known: {sorted(ACCESSORIES)}")
        old = rig._BUILD_STYLE[0]
        rig._BUILD_STYLE[0] = style
        try:
            _ACC_CACHE[(name, style)] = ACCESSORIES[name][0]()
        finally:
            rig._BUILD_STYLE[0] = old
    return _ACC_CACHE[(name, style)]


def _norm_part(k):
    s = str(k).replace("_", "").replace(" ", "").lower()
    for p in PARTS:
        if p.replace(" ", "").lower() == s:
            return p
    raise KeyError(k)


class Avatar:
    """R6 avatar. See SPEC.md. Textures: PIL images composed once and cached."""

    def __init__(self, name="Noob", skin="#f5cd30", shirt=None, pants=None, face="smile", hair=None,
                 accessories=(), body_colors=None, scale=1.0, shirt_color=None, pants_color=None,
                 hair_color=None, edge_style=None):
        self.name = name
        self.edge_style = edge_style   # None -> follow rig.get_edge_style() at draw time
        self.uid = f"{name}#{next(_UID)}"
        self.scale = float(scale)
        sk = _color(skin)
        self.body_colors = {p: sk for p in PARTS}
        if body_colors:
            for k, v in body_colors.items():
                self.body_colors[_norm_part(k)] = _color(v)
        self._shirt = self._make_layer("shirt", shirt, shirt_color)
        self._pants = self._make_layer("pants", pants, pants_color)
        self._face_cache: dict = {}
        self.face_name = "smile"
        self._face_src = {}
        self.set_face(face)
        self._tex_cache: dict = {}
        self._acc_specs = []
        accs = []
        if hair:
            accs.append((hair, hair_color))
        for a in accessories or ():
            if isinstance(a, (tuple, list)):
                accs.append((a[0], a[1] if len(a) > 1 else None))
            elif isinstance(a, str) and ":" in a:
                n, c = a.split(":", 1)
                accs.append((n, c))
            else:
                accs.append((a, None))
        self.accessory_names = [a[0] for a in accs]
        for nm, col in accs:
            _, attach, dcol = ACCESSORIES[nm] if nm in ACCESSORIES else (None, None, None)
            if attach is None:
                raise KeyError(f"unknown hair/accessory '{nm}'. Known: {sorted(ACCESSORIES)}")
            base = _color(col if col is not None else dcol)
            self._acc_specs.append((nm, attach, base))

    @classmethod
    def noob(cls, **kw):
        return cls(body_colors=NOOB, **kw)

    # ---- clothing
    @staticmethod
    def _make_layer(kind, tex, color):
        if tex is not None and not (isinstance(tex, str) and tex.startswith("#") and not os.path.isfile(tex)):
            if isinstance(tex, (tuple, list)) and not isinstance(tex, Image.Image) and len(tex) in (3, 4) \
                    and all(isinstance(v, (int, float)) for v in tex):
                return flat_layer(kind, tex)
            lay = _load_layer(tex, color)
            if lay is not None:
                return lay
        if isinstance(tex, str) and tex.startswith("#"):
            return flat_layer(kind, tex)
        if color is not None:
            return flat_layer(kind, color)
        return None

    # ---- face
    def set_face(self, face):
        key = face if isinstance(face, str) or face is None else f"img{id(face)}"
        key = "smile" if key is None else str(key)
        if key not in self._face_src:
            self._face_src[key] = resolve_face(face)
        self.face_name = key
        return self

    def _head_texture(self, face_key):
        if face_key not in self._face_cache:
            if face_key not in self._face_src:
                self._face_src[face_key] = resolve_face(face_key)
            skin = _u8(self.body_colors["Head"]) + (255,)
            atlas = Image.new("RGBA", (512, 256), skin)
            atlas.alpha_composite(self._face_src[face_key], (0, 0))
            self._face_cache[face_key] = atlas.convert("RGB")
        return self._face_cache[face_key]

    def part_texture(self, part):
        """Composed per-part texture (template layout) or None when the part is plain color."""
        if part == "Head":
            return None
        layers = []
        if part in ("Torso", "Right Leg", "Left Leg") and self._pants is not None:
            layers.append(self._pants)
        if part in ("Torso", "Right Arm", "Left Arm") and self._shirt is not None:
            layers.append(self._shirt)
        if not layers:
            return None
        if part not in self._tex_cache:
            im = Image.new("RGBA", (TEMPLATE_W, TEMPLATE_H), _u8(self.body_colors[part]) + (255,))
            for lay in layers:
                im.alpha_composite(lay)
            self._tex_cache[part] = im.convert("RGB")
        return self._tex_cache[part]

    # ---- drawing
    def draw_items(self, pose: dict, root_cf=None, face=None) -> list:
        DrawItem = _make_drawitem()
        root_cf = np.eye(4) if root_cf is None else np.asarray(root_cf, float)
        S = np.diag([self.scale] * 3 + [1.0])
        models = rig.part_models(pose, root_cf @ S)
        out = []
        fk = self.face_name if face is None else str(face)
        st = self.edge_style or rig.get_edge_style()
        for p in PARTS:
            if p == "Head":
                tex, col, key = self._head_texture(fk), (1, 1, 1), f"{self.uid}:Head:{fk}"
            else:
                tex = self.part_texture(p)
                col = (1, 1, 1) if tex is not None else self.body_colors[p]
                key = f"{self.uid}:{p}:tex" if tex is not None else f"r6mesh:{st}:{p}"
            out.append(DrawItem(mesh=rig.part_mesh(p, st), model=models[p], color=col, texture=tex, key=key))
        for nm, attach, base in self._acc_specs:
            for pn, mesh, pc, mat, tr in accessory_pieces(nm, st):
                col = _color(pc) if pc is not None else base
                out.append(DrawItem(mesh=mesh, model=models[attach], color=col, material=mat, transparency=tr,
                                    cast_shadow=tr < 0.5, key=f"r6acc:{st}:{nm}:{pn}"))
        return out
