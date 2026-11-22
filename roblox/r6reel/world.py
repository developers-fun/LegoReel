"""Scenery scene graph (Part, Prop, World) and builders for houses, trees, furniture and small scenes.

Conventions (match primitives.py and SPEC.md)
- Y-up, right-handed, studs. A builder's geometry sits on y=0 and is centred on x=0, z=0, so a Prop's
  position is the spot where it stands. Fronts face -Z.
- Prop/Part rotation is Euler degrees, applied as R = Rx @ Ry @ Rz (CFrame.Angles order).
  (0, 90, 0) turns the front from -Z to -X; (0, -90, 0) turns it to +X.
- Scale is applied in the local frame before rotation: M = T @ R @ S.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from r6reel import primitives as P
from r6reel.mesh import Mesh

# Palette (Roblox-ish BrickColors)
WHITE = "#f2f3f3"
LIGHT_GREY = "#e5e4df"
GREY = "#a3a2a5"
DARK_GREY = "#3a3d42"
RED = "#c4281c"
BLUE = "#0d69ac"
YELLOW = "#f5cd30"
GOLD = "#ffc93c"
GREEN = "#4caf50"
DARK_GREEN = "#2e7d32"
WOOD = "#c99a63"
DARK_WOOD = "#8c5a2b"
BRICK = "#b35a3c"
GLASS_TINT = "#9fd8ff"
SIDEWALK = "#d9d6cf"
ASPHALT = "#3a3d42"
GRASS = "#5aa84a"
LAMP = "#fff3b0"
ORANGE = "#ff9d2e"

MATERIALS = {"plastic", "smooth", "grass", "brick", "wood", "concrete", "glass", "neon", "metal"}
_EMISSIVE = {"neon": 1.0, "glass": 0.1}  # glass windows glow a little; neon fully lit


def _rgb(c) -> tuple:
    """'#rrggbb' or an (r, g, b) tuple of 0..1 floats -> (r, g, b) floats."""
    if isinstance(c, str):
        s = c.lstrip("#")
        if len(s) != 6:
            raise ValueError(f"colour must be #rrggbb, got {c!r}")
        return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    vals = tuple(float(x) for x in c)
    if len(vals) != 3:
        raise ValueError(f"colour needs 3 components, got {c!r}")
    return vals


def _vec3(v) -> tuple:
    return tuple(float(x) for x in v)


def _trs(position, rotation, scale) -> np.ndarray:
    rx, ry, rz = np.radians(np.asarray(rotation, float))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    rot_x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    rot_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rot_z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    m = np.eye(4)
    m[:3, :3] = rot_x @ rot_y @ rot_z @ np.diag(np.asarray(scale, float))
    m[:3, 3] = np.asarray(position, float)
    return m


@dataclass
class _FallbackDrawItem:
    """Same fields as r6reel.renderer.DrawItem; used only while the renderer is unavailable."""
    mesh: Mesh
    model: np.ndarray = None
    color: tuple = (1.0, 1.0, 1.0)
    texture: object = None
    material: str = "plastic"
    transparency: float = 0.0
    cast_shadow: bool = True
    receive_shadow: bool = True
    uv_scale: tuple = (1.0, 1.0)
    emissive: float = 0.0
    key: str | None = None


def _draw_item_cls():
    try:
        from r6reel.renderer import DrawItem
        return DrawItem
    except Exception:  # renderer not importable (missing GL, or not built yet)
        return _FallbackDrawItem


@dataclass
class Part:
    """One drawable: a Mesh with its own colour, material and local transform inside a Prop."""
    mesh: Mesh
    color: tuple
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)
    scale: tuple = (1.0, 1.0, 1.0)
    texture: str | None = None      # path to an image, tiled by uv
    material: str = "plastic"
    transparency: float = 0.0
    cast_shadow: bool = True
    name: str = ""

    def __post_init__(self):
        if self.material not in MATERIALS:
            raise ValueError(f"unknown material {self.material!r}")
        self.color = _rgb(self.color)
        self.position = _vec3(self.position)
        self.rotation = _vec3(self.rotation)
        self.scale = _vec3(self.scale)

    def matrix(self) -> np.ndarray:
        return _trs(self.position, self.rotation, self.scale)


class Prop:
    """Named group of Parts and child Props with a transform (position, Euler rotation, scale)."""

    def __init__(self, name="prop", parts=(), children=(), position=(0, 0, 0), rotation=(0, 0, 0),
                 scale=(1, 1, 1)):
        self.name = name
        self.parts = list(parts)
        self.children = list(children)
        self.position = position
        self.rotation = rotation
        self.scale = scale

    def add(self, item):
        """Append a Part or a child Prop and return it."""
        if isinstance(item, Part):
            self.parts.append(item)
        elif isinstance(item, Prop):
            self.children.append(item)
        else:
            raise TypeError(f"cannot add {type(item).__name__} to a Prop")
        return item

    def matrix(self) -> np.ndarray:
        return _trs(self.position, self.rotation, self.scale)

    def to_draw_items(self, parent: np.ndarray | None = None) -> list:
        """Flatten this Prop tree into renderer DrawItems with world-space model matrices."""
        out = []
        self._collect(np.eye(4) if parent is None else parent, _draw_item_cls(), out)
        return out

    def _collect(self, parent, draw_item, out):
        m = parent @ self.matrix()
        for part in self.parts:
            out.append(draw_item(
                mesh=part.mesh,
                model=m @ part.matrix(),
                color=part.color,
                texture=part.texture,
                material=part.material,
                transparency=part.transparency,
                cast_shadow=part.cast_shadow,
                receive_shadow=True,
                uv_scale=(1.0, 1.0),
                emissive=_EMISSIVE.get(part.material, 0.0),
                key=f"{id(part.mesh)}|{part.texture or ''}",
            ))
        for child in self.children:
            child._collect(m, draw_item, out)


class World:
    """Named props plus sun, sky and fog settings. Passed to the renderer through lighting()."""

    def __init__(self, sky_top="#5aa9ff", sky_bottom="#cfe9ff", sun_dir=(-0.4, -1.0, -0.3),
                 sun_color=(1.0, 0.96, 0.88), sun_intensity=1.0, ambient=(0.55, 0.6, 0.7),
                 fog_color=None, fog_density=0.0):
        self.sky_top = _rgb(sky_top)
        self.sky_bottom = _rgb(sky_bottom)
        self.sun_dir = _vec3(sun_dir)           # direction the light travels
        self.sun_color = _rgb(sun_color)
        self.sun_intensity = float(sun_intensity)
        self.ambient = _rgb(ambient)
        self.fog_color = None if fog_color is None else _rgb(fog_color)
        self.fog_density = float(fog_density)
        self.props: dict[str, Prop] = {}

    def add(self, item) -> Prop:
        """Add a Prop (or a bare Part, wrapped in a Prop). Duplicate names get a numeric suffix."""
        if isinstance(item, Part):
            item = Prop(name=item.name or "part", parts=[item])
        if not isinstance(item, Prop):
            raise TypeError(f"World.add expects a Prop or Part, got {type(item).__name__}")
        base = item.name or "prop"
        name, k = base, 2
        while name in self.props:
            name = f"{base}_{k}"
            k += 1
        item.name = name
        self.props[name] = item
        return item

    def get(self, name) -> Prop:
        if name not in self.props:
            raise KeyError(f"no prop named {name!r}")
        return self.props[name]

    def draw_items(self) -> list:
        items = []
        for prop in self.props.values():
            items.extend(prop.to_draw_items())
        return items

    def lighting(self) -> dict:
        d = np.asarray(self.sun_dir, float)
        d = d / np.linalg.norm(d)
        return {
            "sun_dir": tuple(float(x) for x in d),
            "sun_color": self.sun_color,
            "sun_intensity": self.sun_intensity,
            "ambient": self.ambient,
            "sky_top": self.sky_top,
            "sky_bottom": self.sky_bottom,
            "fog_color": self.fog_color if self.fog_color is not None else self.sky_bottom,
            "fog_density": self.fog_density,
        }


# ---- helpers for builders ---------------------------------------------------------------

def _part(mesh, color, pos=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), material="plastic",
          texture=None, transparency=0.0, name="") -> Part:
    return Part(mesh=mesh, color=color, position=pos, rotation=rot, scale=scale, material=material,
                texture=texture, transparency=transparency, name=name)


def _box_part(size, pos, color, material="plastic", rot=(0, 0, 0), name="") -> Part:
    return _part(P.box(size), color, pos, rot, material=material, name=name)


def _single(name, *parts) -> Prop:
    return Prop(name=name, parts=list(parts))


def _facade(xs, ys, z, sign, win_w, win_h, shutter_color) -> list:
    """Glass windows (plus optional shutters) on a wall plane at z. sign=-1 faces -Z, +1 faces +Z."""
    out = []
    for x in xs:
        for y in ys:
            out.append(_box_part((win_w, win_h, 0.12), (x, y, z + sign * 0.04), GLASS_TINT, "glass",
                                 name="window"))
            if shutter_color:
                for side in (-1, 1):
                    out.append(_box_part((0.5, win_h * 1.1, 0.12),
                                         (x + side * (win_w / 2 + 0.35), y, z + sign * 0.04),
                                         shutter_color, "plastic", name="shutter"))
    return out


# ---- builders -----------------------------------------------------------------------

def ground(size=(200.0, 200.0), material="grass", color=GRASS, name="ground") -> Prop:
    """Thick slab whose top surface is y=0."""
    sx, sz = size
    return _single(name, _box_part((sx, 2.0, sz), (0, -1.0, 0), color, material, name="slab"))


def road(length=60.0, width=10.0, color=ASPHALT, name="road") -> Prop:
    """Asphalt strip along X, top at y=0.1, with white centre dashes."""
    parts = [_box_part((length, 0.1, width), (0, 0.05, 0), color, "concrete", name="asphalt")]
    for i in range(int(length // 6)):
        x = -length / 2 + 3 + 6 * i
        parts.append(_box_part((3.0, 0.04, 0.4), (x, 0.12, 0), WHITE, name="dash"))
    return _single(name, *parts)


def sidewalk(length=60.0, width=4.0, height=0.5, color=SIDEWALK, name="sidewalk") -> Prop:
    """Concrete kerb-high walkway along X."""
    return _single(name, _box_part((length, height, width), (0, height / 2, 0), color, "concrete",
                                   name="slab"))


def house(w=10.0, d=10.0, h=7.0, color=YELLOW, roof_color=RED, shutter_color=BLUE, name="house") -> Prop:
    """Walls with a gable roof; two windows with shutters on front and back, a door on the front."""
    rh = min(w, d) * 0.5
    parts = [_box_part((w, h, d), (0, h / 2, 0), color, "plastic", name="walls")]
    parts.append(_part(P.prism([(-(w + 1.2) / 2, h - 0.05), ((w + 1.2) / 2, h - 0.05), (0, h + rh)],
                               d + 1.2, "z"), roof_color, material="plastic", name="roof"))
    xs = [-w / 4, w / 4]
    parts += _facade(xs, [h * 0.55], -d / 2, -1, 2.0, 2.0, shutter_color)
    parts += _facade(xs, [h * 0.55], d / 2, 1, 2.0, 2.0, shutter_color)
    parts.append(_box_part((1.8, 3.2, 0.3), (0, 1.6, -d / 2 - 0.05), DARK_WOOD, "wood", name="door"))
    return _single(name, *parts)


def apartment_block(floors=5, w=14.0, d=12.0, floor_h=3.0, color=BRICK, shutter_color=BLUE,
                    name="apartment_block") -> Prop:
    """Brick block with a window grid on front and back, a roof lip and a front door."""
    h = floors * floor_h
    parts = [_box_part((w, h, d), (0, h / 2, 0), color, "brick", name="walls"),
             _box_part((w + 0.6, 0.6, d + 0.6), (0, h + 0.3, 0), LIGHT_GREY, "concrete", name="roof_lip")]
    cols = max(2, int(w // 4))
    xs = [-w / 2 + (i + 0.5) * w / cols for i in range(cols)]
    for sign, z in ((-1, -d / 2), (1, d / 2)):
        for f in range(floors):
            y = f * floor_h + floor_h * 0.55
            row = [x for x in xs if not (sign < 0 and f == 0 and abs(x) < 2.5)]  # keep the door clear
            parts += _facade(row, [y], z, sign, 1.8, 1.8, shutter_color)
    parts.append(_box_part((2.0, 2.6, 0.3), (0, 1.3, -d / 2 - 0.05), DARK_WOOD, "wood", name="door"))
    return _single(name, *parts)


def skyscraper(floors=25, w=10.0, d=10.0, floor_h=3.0, color=LIGHT_GREY, name="skyscraper") -> Prop:
    """Tall metal block with a glass band on every floor of all four faces, a roof cap and an antenna."""
    h = floors * floor_h
    parts = [_box_part((w, h, d), (0, h / 2, 0), color, "metal", name="body")]
    band = floor_h * 0.55
    for f in range(floors):
        y = f * floor_h + floor_h * 0.5
        parts.append(_box_part((w - 1.0, band, 0.12), (0, y, -d / 2 - 0.04), GLASS_TINT, "glass", name="band"))
        parts.append(_box_part((w - 1.0, band, 0.12), (0, y, d / 2 + 0.04), GLASS_TINT, "glass", name="band"))
        parts.append(_box_part((0.12, band, d - 1.0), (-w / 2 - 0.04, y, 0), GLASS_TINT, "glass", name="band"))
        parts.append(_box_part((0.12, band, d - 1.0), (w / 2 + 0.04, y, 0), GLASS_TINT, "glass", name="band"))
    parts.append(_box_part((w * 0.5, 1.0, d * 0.5), (0, h + 0.5, 0), GREY, "metal", name="roof_cap"))
    parts.append(_part(P.cylinder(0.15, 6.0), DARK_GREY, pos=(0, h + 4.0, 0), material="metal", name="antenna"))
    return _single(name, *parts)


def tree(kind="round", trunk_color=DARK_WOOD, leaf_color=None, name="tree") -> Prop:
    """Blocky tree. kind="round": trunk plus a blob of spheres. kind="pine": trunk plus three cones."""
    if kind == "round":
        leaf_color = leaf_color or GREEN
        parts = [_part(P.cylinder(0.5, 3.0), trunk_color, pos=(0, 1.5, 0), material="wood", name="trunk"),
                 _part(P.sphere(2.6), leaf_color, pos=(0, 4.8, 0), name="crown"),
                 _part(P.sphere(1.8), leaf_color, pos=(1.4, 3.9, 0.6), name="crown"),
                 _part(P.sphere(1.6), leaf_color, pos=(-1.2, 4.0, -0.9), name="crown")]
    elif kind == "pine":
        leaf_color = leaf_color or DARK_GREEN
        parts = [_part(P.cylinder(0.5, 2.5), trunk_color, pos=(0, 1.25, 0), material="wood", name="trunk")]
        for radius, height, base in ((2.8, 3.5, 2.5), (2.2, 3.2, 4.0), (1.4, 2.8, 5.8)):
            parts.append(_part(P.cone(radius, height), leaf_color, pos=(0, base + height / 2, 0), name="cone"))
    else:
        raise ValueError(f"tree kind must be 'round' or 'pine', got {kind!r}")
    return _single(name, *parts)


def bush(radius=1.2, color=GREEN, name="bush") -> Prop:
    """Two overlapping leaf spheres sitting on the ground."""
    r = float(radius)
    return _single(name,
                   _part(P.sphere(r), color, pos=(0, r * 0.9, 0), name="leaves"),
                   _part(P.sphere(r * 0.75), color, pos=(r * 0.9, r * 0.6, r * 0.4), name="leaves"))


def fence(length=12.0, height=3.0, color=WOOD, name="fence") -> Prop:
    """Posts every ~3 studs with two rails, along X."""
    n = max(2, int(length // 3) + 1)
    parts = [_box_part((0.5, height, 0.5), (x, height / 2, 0), color, "wood", name="post")
             for x in np.linspace(-length / 2, length / 2, n)]
    for y in (height * 0.3, height * 0.75):
        parts.append(_box_part((length, 0.4, 0.2), (0, y, 0), color, "wood", name="rail"))
    return _single(name, *parts)


def lamp_post(height=10.0, color=DARK_GREY, name="lamp_post") -> Prop:
    """Base block, pole and a glowing lamp head at the top."""
    pole_top = height - 0.9
    return _single(name,
                   _box_part((1.4, 0.6, 1.4), (0, 0.3, 0), color, "metal", name="base"),
                   _part(P.cylinder(0.25, pole_top - 0.6), color, pos=(0, (0.6 + pole_top) / 2, 0),
                         material="metal", name="pole"),
                   _box_part((1.4, 0.9, 1.4), (0, height - 0.45, 0), LAMP, "neon", name="lamp"))


def bench(length=6.0, color=WOOD, name="bench") -> Prop:
    """Slatted bench along X with its backrest on the +Z side."""
    return _single(name,
                   _box_part((length, 0.4, 1.6), (0, 1.6, 0), color, "wood", name="seat"),
                   _box_part((0.4, 1.4, 1.4), (-(length / 2 - 0.6), 0.7, 0), color, "wood", name="leg"),
                   _box_part((0.4, 1.4, 1.4), (length / 2 - 0.6, 0.7, 0), color, "wood", name="leg"),
                   _box_part((length, 1.4, 0.3), (0, 2.5, 0.65), color, "wood", name="backrest"))


def table(w=4.0, d=2.5, h=3.0, color=WOOD, name="table") -> Prop:
    """Flat top on four legs."""
    parts = [_box_part((w, 0.4, d), (0, h - 0.2, 0), color, "wood", name="top")]
    for sx in (-1, 1):
        for sz in (-1, 1):
            parts.append(_box_part((0.4, h - 0.4, 0.4), (sx * (w / 2 - 0.3), (h - 0.4) / 2, sz * (d / 2 - 0.3)),
                                   color, "wood", name="leg"))
    return _single(name, *parts)


def chair(color=BLUE, name="chair") -> Prop:
    """Seat, four legs and a backrest on the +Z side (a sitter faces -Z)."""
    parts = [_box_part((2.0, 0.4, 2.0), (0, 1.9, 0), color, "plastic", name="seat"),
             _box_part((2.0, 2.4, 0.3), (0, 3.3, 0.85), color, "plastic", name="backrest")]
    for sx in (-1, 1):
        for sz in (-1, 1):
            parts.append(_box_part((0.3, 1.9, 0.3), (sx * 0.85, 0.95, sz * 0.85), color, "plastic", name="leg"))
    return _single(name, *parts)


def desk(w=5.0, d=2.5, h=3.0, color=WOOD, name="desk") -> Prop:
    """Table with one drawer on the right side."""
    prop = table(w, d, h, color, name=name)
    prop.add(_box_part((1.5, 1.0, d - 0.5), (w / 2 - 1.25, h - 0.9, 0), color, "wood", name="drawer"))
    prop.add(_box_part((0.5, 0.12, 0.1), (w / 2 - 1.25, h - 0.9, -(d - 0.5) / 2 - 0.05), GREY, "metal",
                       name="handle"))
    return prop


def locker_row(count=6, color=BLUE, name="locker_row") -> Prop:
    """Lockers side by side along X, each 2 studs wide, fronts on -Z, centred on the origin."""
    parts = []
    for i in range(count):
        x = (i - (count - 1) / 2) * 2.0
        parts.append(_box_part((1.9, 7.0, 1.2), (x, 3.5, 0), color, "plastic", name="locker"))
        parts.append(_box_part((0.15, 0.8, 0.1), (x + 0.65, 3.5, -0.65), GREY, "metal", name="handle"))
    return _single(name, *parts)


def door(w=3.0, h=6.5, d=0.4, color=RED, frame_color=WHITE, name="door") -> Prop:
    """Door panel with a white frame and a metal knob, facing -Z."""
    parts = [_box_part((w, h, d), (0, h / 2, 0), color, "wood", name="panel"),
             _box_part((0.4, h + 0.4, d + 0.3), (-(w / 2 + 0.2), (h + 0.4) / 2, 0), frame_color, "plastic",
                       name="frame"),
             _box_part((0.4, h + 0.4, d + 0.3), (w / 2 + 0.2, (h + 0.4) / 2, 0), frame_color, "plastic",
                       name="frame"),
             _box_part((w + 0.8, 0.4, d + 0.3), (0, h + 0.2, 0), frame_color, "plastic", name="frame"),
             _part(P.sphere(0.25), YELLOW, pos=(w / 2 - 0.4, h * 0.5, -d / 2 - 0.15), material="metal",
                   name="knob")]
    return _single(name, *parts)


def window_wall(w=12.0, h=8.0, cols=4, rows=2, wall_color=LIGHT_GREY, frame_color=WHITE,
                name="window_wall") -> Prop:
    """Wall slab with a grid of framed glass panes on the -Z face."""
    parts = [_box_part((w, h, 0.6), (0, h / 2, 0), wall_color, "plastic", name="wall")]
    for i in range(cols):
        for j in range(rows):
            x = -w / 2 + (i + 0.5) * w / cols
            y = (j + 0.5) * h / rows
            parts.append(_box_part((w / cols - 0.2, h / rows - 0.2, 0.25), (x, y, -0.3), frame_color, "plastic",
                                   name="frame"))
            parts.append(_box_part((w / cols - 0.7, h / rows - 0.7, 0.15), (x, y, -0.45), GLASS_TINT, "glass",
                                   name="pane"))
    return _single(name, *parts)


def sign(text_texture=None, w=6.0, h=3.0, pole_h=7.0, color=WHITE, name="sign") -> Prop:
    """Post with a red-edged board. The face is a plane (white, or the given texture) facing -Z."""
    parts = [_part(P.cylinder(0.25, pole_h), DARK_GREY, pos=(0, pole_h / 2, 0), material="metal", name="post"),
             _box_part((w, h, 0.3), (0, pole_h, 0), RED, "plastic", name="board"),
             _part(P.plane((w * 0.92, h * 0.92)), color, pos=(0, pole_h, -0.2), rot=(-90, 0, 0),
                   texture=text_texture, name="face")]
    return _single(name, *parts)


def car(color=RED, name="car") -> Prop:
    """Blocky car, nose toward -Z, wheels on the ground at y=0 (plus any Prop offset)."""
    parts = [_box_part((4.2, 1.6, 8.0), (0, 1.3, 0), color, "plastic", name="body"),
             _box_part((3.4, 1.5, 3.6), (0, 2.85, -0.3), GLASS_TINT, "glass", name="cabin"),
             _box_part((3.4, 0.25, 3.6), (0, 3.73, -0.3), color, "plastic", name="roof"),
             _box_part((4.3, 0.4, 0.3), (0, 0.7, -4.1), DARK_GREY, "plastic", name="bumper")]
    for x in (-2.05, 2.05):
        for z in (-2.6, 2.6):
            parts.append(_part(P.cylinder(0.8, 0.7, axis="x"), "#1d1d1d", pos=(x, 0.8, z), name="wheel"))
    for x in (-1.4, 1.4):
        parts.append(_box_part((0.8, 0.4, 0.12), (x, 1.4, -4.06), LAMP, "neon", name="headlight"))
    return _single(name, *parts)


def umbrella(color=YELLOW, pole_h=7.0, canopy_radius=4.0, name="umbrella") -> Prop:
    """Pole with a cone canopy (apex up)."""
    return _single(name,
                   _part(P.cylinder(0.15, pole_h), DARK_GREY, pos=(0, pole_h / 2, 0), material="metal",
                         name="pole"),
                   _part(P.cone(canopy_radius, 1.5), color, pos=(0, pole_h + 0.75, 0), name="canopy"))


def cloud(puffs=6, seed=0, color=WHITE, name="cloud") -> Prop:
    """Low-poly cloud: a row of squashed spheres. Place it in the sky with the Prop position."""
    rng = np.random.default_rng(seed)
    parts = []
    for i in range(puffs):
        r = float(rng.uniform(1.5, 3.0))
        x = (i - (puffs - 1) / 2) * 2.2 + float(rng.uniform(-0.5, 0.5))
        y = float(rng.uniform(-0.4, 0.4))
        z = float(rng.uniform(-1.0, 1.0))
        parts.append(_part(P.sphere(r), color, pos=(x, y, z), scale=(1.0, 0.7, 1.0), name="puff"))
    return _single(name, *parts)


def brick_wall(w=10.0, h=6.0, thickness=1.0, color=BRICK, name="brick_wall") -> Prop:
    """Brick slab with a light coping on top."""
    return _single(name,
                   _box_part((w, h, thickness), (0, h / 2, 0), color, "brick", name="bricks"),
                   _box_part((w + 0.3, 0.3, thickness + 0.3), (0, h + 0.15, 0), LIGHT_GREY, "concrete",
                             name="coping"))


def stairs(steps=5, step_w=4.0, step_h=1.0, step_d=2.0, color=GREY, name="stairs") -> Prop:
    """Solid staircase that climbs toward -Z (the front), each step one block tall."""
    parts = []
    for i in range(steps):
        height = (i + 1) * step_h
        z = -(i * step_d + step_d / 2)
        parts.append(_box_part((step_w, height, step_d), (0, height / 2, z), color, "concrete", name="step"))
    return _single(name, *parts)


def crate(size=(2.0, 2.0, 2.0), color=WOOD, name="crate") -> Prop:
    """Wooden box with two dark bands."""
    sx, sy, sz = size
    parts = [_box_part((sx, sy, sz), (0, sy / 2, 0), color, "wood", name="box")]
    for f in (0.3, 0.7):
        parts.append(_box_part((sx + 0.12, 0.2, sz + 0.12), (0, sy * f, 0), DARK_WOOD, "wood", name="band"))
    return _single(name, *parts)


def ball(radius=1.0, color=YELLOW, name="ball") -> Prop:
    """Sphere resting on the ground."""
    return _single(name, _part(P.sphere(radius), color, pos=(0, radius, 0), name="ball"))


def duck_toy(color=YELLOW, name="duck_toy") -> Prop:
    """Rubber duck: squashed body, head, orange beak, two eyes. Faces -Z."""
    return _single(name,
                   _part(P.sphere(0.9), color, pos=(0, 0.72, 0), scale=(1.2, 0.8, 1.4), name="body"),
                   _part(P.sphere(0.6), color, pos=(0, 1.6, -0.6), name="head"),
                   _box_part((0.45, 0.2, 0.5), (0, 1.45, -1.1), ORANGE, "plastic", name="beak"),
                   _box_part((0.14, 0.14, 0.14), (-0.25, 1.8, -1.15), "#111111", name="eye"),
                   _box_part((0.14, 0.14, 0.14), (0.25, 1.8, -1.15), "#111111", name="eye"))


def coin(radius=0.7, color=GOLD, name="coin") -> Prop:
    """Upright gold coin (its face points along Z), bottom on the ground."""
    return _single(name, _part(P.cylinder(radius, 0.2, axis="z"), color, pos=(0, radius, 0), material="metal",
                               name="disc"))


# ---- small assembled scenes -----------------------------------------------------------

def classroom(rows=4, cols=5, name="classroom") -> Prop:
    """Room with a whiteboard on the -Z wall and a grid of desks with chairs facing the board."""
    pitch = 6.0
    width = cols * pitch + 4.0
    depth = rows * pitch + 12.0
    parts = [
        _box_part((width, 0.5, depth), (0, -0.25, 0), "#d7c59a", "wood", name="floor"),
        _box_part((width + 1, 12, 1), (0, 6, -depth / 2 - 0.5), LIGHT_GREY, name="front_wall"),
        _box_part((width + 1, 12, 1), (0, 6, depth / 2 + 0.5), LIGHT_GREY, name="back_wall"),
        _box_part((1, 12, depth), (-width / 2 - 0.5, 6, 0), "#bfe3ff", name="left_wall"),
        _box_part((1, 12, depth), (width / 2 + 0.5, 6, 0), "#bfe3ff", name="right_wall"),
        _box_part((cols * 4 + 0.6, 5, 0.2), (0, 6, -depth / 2 + 0.25), GREY, "metal", name="board_frame"),
        _box_part((cols * 4, 4.4, 0.3), (0, 6, -depth / 2 + 0.35), WHITE, "smooth", name="whiteboard"),
    ]
    prop = _single(name, *parts)
    z0 = -depth / 2 + 6.0
    for r in range(rows):
        z = z0 + r * pitch
        for c in range(cols):
            x = (c - (cols - 1) / 2) * pitch
            prop.add(_placed(desk(), (x, 0, z)))
            prop.add(_placed(chair(), (x, 0, z + 2.4)))
    return prop


def _placed(prop: Prop, pos, rot=(0, 0, 0)) -> Prop:
    prop.position = pos
    prop.rotation = rot
    return prop


def cafeteria(name="cafeteria") -> Prop:
    """Floor and walls, a serving counter at the back, three rows of long tables with benches both sides."""
    parts = [
        _box_part((40, 0.5, 40), (0, -0.25, 0), "#d7c59a", "plastic", name="floor"),
        _box_part((41, 12, 1), (0, 6, 20.5), "#f5f0d8", name="back_wall"),
        _box_part((1, 12, 41), (-20.5, 6, 0), "#f5f0d8", name="left_wall"),
        _box_part((1, 12, 41), (20.5, 6, 0), "#f5f0d8", name="right_wall"),
        _box_part((20, 4, 3), (0, 2, 17), LIGHT_GREY, name="counter"),
        _box_part((20.6, 0.4, 3.6), (0, 4.2, 17), BLUE, name="counter_top"),
    ]
    prop = _single(name, *parts)
    for z in (-8.0, 2.0, 12.0):
        for x in (-10.0, 0.0, 10.0):
            prop.add(_placed(table(w=10.0, d=3.0, h=3.0, color=WOOD), (x, 0, z)))
            prop.add(_placed(bench(length=10.0), (x, 0, z + 2.4)))
            prop.add(_placed(bench(length=10.0), (x, 0, z - 2.4), (0, 180, 0)))
    return prop


def school_hallway(length=60.0, name="school_hallway") -> Prop:
    """Hallway along Z, 12 studs wide, lockers on both walls, ceiling lights every 10 studs."""
    parts = [
        _box_part((12, 0.5, length), (0, -0.25, 0), "#d7c59a", "plastic", name="floor"),
        _box_part((12, 0.5, length), (0, 12.25, 0), WHITE, name="ceiling"),
        _box_part((1, 12, length), (-6.5, 6, 0), "#f5f0d8", name="left_wall"),
        _box_part((1, 12, length), (6.5, 6, 0), "#f5f0d8", name="right_wall"),
    ]
    for z in np.arange(-length / 2 + 5, length / 2 - 4, 10.0):
        parts.append(_box_part((4, 0.2, 1.2), (0, 11.8, float(z)), LAMP, "neon", name="light"))
    prop = _single(name, *parts)
    count = max(1, int(length // 2))
    prop.add(_placed(locker_row(count=count, color=BLUE), (-5.4, 0, 0), (0, -90, 0)))
    prop.add(_placed(locker_row(count=count, color=YELLOW), (5.4, 0, 0), (0, 90, 0)))
    return prop


def bedroom(name="bedroom") -> Prop:
    """16 x 16 room with a bed, nightstand and lamp, a desk and chair, a window, a rug and toys."""
    parts = [
        _box_part((16, 0.5, 16), (0, -0.25, 0), "#b07a45", "wood", name="floor"),
        _box_part((17, 10, 1), (0, 5, 8.5), "#bfe3ff", name="back_wall"),
        _box_part((1, 10, 17), (-8.5, 5, 0), "#bfe3ff", name="left_wall"),
        _box_part((1, 10, 17), (8.5, 5, 0), "#bfe3ff", name="right_wall"),
        _part(P.plane((8, 6)), RED, pos=(3, 0.05, -1), material="plastic", name="rug"),
    ]
    prop = _single(name, *parts)
    bed_parts = [
        _box_part((6, 1.2, 9), (0, 0.6, 0), WOOD, "wood", name="frame"),
        _box_part((5.6, 0.9, 8.6), (0, 1.65, 0), WHITE, "plastic", name="mattress"),
        _box_part((5.8, 0.4, 5.5), (0, 2.3, -1.5), BLUE, "plastic", name="blanket"),
        _box_part((3.2, 0.6, 1.8), (0, 2.4, 3.2), YELLOW, "plastic", name="pillow"),
        _box_part((6.2, 3.0, 0.5), (0, 1.5, 4.75), WOOD, "wood", name="headboard"),
    ]
    prop.add(_placed(_single("bed", *bed_parts), (-3, 0, 3.0)))
    night = [
        _box_part((2, 2.5, 2), (0, 1.25, 0), WOOD, "wood", name="table"),
        _part(P.cylinder(0.4, 1.2), WHITE, pos=(0, 3.1, 0), name="lamp_base"),
        _part(P.cone(0.9, 1.0), YELLOW, pos=(0, 3.9, 0), material="neon", name="lamp_shade"),
    ]
    prop.add(_placed(_single("nightstand", *night), (1.2, 0, 6.8)))
    prop.add(_placed(desk(), (5.5, 0, -4.0)))
    prop.add(_placed(chair(color=RED), (5.5, 0, -2.4), (0, 180, 0)))
    prop.add(_placed(window_wall(w=6.0, h=6.0, cols=2, rows=2), (-7.7, 3.5, 0), (0, -90, 0)))
    prop.add(_placed(duck_toy(), (-2, 0, -4), (0, 30, 0)))
    prop.add(_placed(ball(radius=1.0, color=RED), (4, 0, -6)))
    return prop


def _fountain(name="fountain") -> Prop:
    return _single(name,
                   _part(P.cylinder(4.5, 1.0), LIGHT_GREY, pos=(0, 0.5, 0), material="concrete", name="basin"),
                   _part(P.cylinder(3.9, 0.2), "#2ea3ff", pos=(0, 1.05, 0), material="glass", name="water"),
                   _part(P.cylinder(0.8, 3.0), LIGHT_GREY, pos=(0, 2.5, 0), material="concrete", name="pillar"),
                   _part(P.cylinder(2.0, 0.4), LIGHT_GREY, pos=(0, 4.2, 0), material="concrete", name="top"),
                   _part(P.sphere(0.9), "#2ea3ff", pos=(0, 4.8, 0), material="glass", name="spout"))


def town_square(name="town_square") -> Prop:
    """Grass block with a concrete plaza, a fountain in the middle, benches, lamps, trees, a speed sign,
    a road with a parked car and buildings around the edge. Buildings on the far side face the plaza."""
    prop = Prop(name=name)
    prop.add(ground(size=(120.0, 120.0)))
    prop.add(_box_part((40, 0.2, 40), (0, 0.1, 0), SIDEWALK, "concrete", name="plaza"))
    prop.add(_placed(_fountain(), (0, 0, 0)))
    for pos, rot in (((9, 0, 0), (0, 90, 0)), ((-9, 0, 0), (0, -90, 0)),
                     ((0, 0, 9), (0, 0, 0)), ((0, 0, -9), (0, 180, 0))):
        prop.add(_placed(bench(), pos, rot))
    for x in (-18.0, 18.0):
        for z in (-18.0, 18.0):
            prop.add(_placed(lamp_post(), (x, 0, z)))
    prop.add(_placed(sign(w=6.0, h=3.0, pole_h=7.0), (14, 0, 12), (0, 180, 0)))
    prop.add(_placed(tree("round"), (-24, 0, 10)))
    prop.add(_placed(tree("pine"), (24, 0, 10)))
    prop.add(_placed(tree("round", leaf_color=GREEN), (22, 0, -14)))
    prop.add(_placed(bush(), (-14, 0, 26)))
    prop.add(_placed(bush(), (14, 0, 26)))
    prop.add(_placed(apartment_block(), (-14, 0, -30), (0, 180, 0)))
    prop.add(_placed(skyscraper(floors=18, w=10, d=10), (10, 0, -34), (0, 180, 0)))
    prop.add(_placed(house(), (-30, 0, 4), (0, -90, 0)))
    prop.add(_placed(house(color=BLUE, roof_color=DARK_GREY), (30, 0, -6), (0, 90, 0)))
    prop.add(_placed(road(length=120.0, width=10.0), (0, 0, 32)))
    prop.add(_placed(sidewalk(length=120.0), (0, 0, 24)))
    prop.add(_placed(sidewalk(length=120.0), (0, 0, 40)))
    prop.add(_placed(car(), (-20, 0.1, 32), (0, 90, 0)))
    prop.add(_placed(umbrella(), (-6, 0, 16)))
    return prop


def crowd_positions(n, area=(20.0, 20.0), seed=0, min_dist=1.0) -> list:
    """n random (x, z) points inside an area centred on the origin (a scalar area is a square side).
    Points try to keep `min_dist` apart; with a tight area they give up after 50 tries and overlap."""
    if np.isscalar(area):
        w = d = float(area)
    else:
        w, d = float(area[0]), float(area[1])
    rng = np.random.default_rng(seed)
    pts: list[tuple] = []
    for _ in range(int(n)):
        for _attempt in range(50):
            p = (float(rng.uniform(-w / 2, w / 2)), float(rng.uniform(-d / 2, d / 2)))
            if all(math.dist(p, q) >= min_dist for q in pts):
                break
        pts.append(p)
    return pts
