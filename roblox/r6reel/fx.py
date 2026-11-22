"""Deterministic particle FX rendered as DrawItems.

Every system is a pure function of time and a seed: ``system.items(t, cam=None) -> list[DrawItem]``.
Systems are described by small dicts (so they live in Scene JSON) and built with :func:`make_fx`.

Types (spec["type"]):
  dust         {t, pos, size=1, count=7, dur=0.7, seed}            cartoon grey-white puff burst
  footsteps    {t0, t1, character | pos+to, interval, size}        dust at the feet of a moving character
  dust_cover   {t, duration=0.4, size=1}                           camera-space puffs that fill the frame
  snow         {t0, t1, density=1, speed=5, wind=1.5}              camera-anchored snowfall
  leaves       {t0, t1, density=1, colors}                         falling leaves / debris
  coins        {t, pos, count=24, dur=2.4, spread=5}               coin shower with bounce
  papers       {t, pos, count=14, dur=3.0, spread=5}               flying papers
  sparkles     {t, pos, count=14, dur=0.9, color, radius}          star sparkles
  sweep        {t, duration=0.25, color, direction}                object sweeping through the lens
Optional on any spec: ``set`` (restrict to a set name) and ``t0``/``t1`` active window.
"""
from __future__ import annotations

import math
import zlib

import numpy as np

from .mesh import Mesh

# ------------------------------------------------------------------------------------------ meshes
_MESHES: dict = {}


def _mesh(name):
    if name not in _MESHES:
        from . import primitives as P
        _MESHES[name] = {
            "puff": lambda: P.sphere(0.5, segments=16),
            "dot": lambda: P.sphere(0.5, segments=6),
            "box": lambda: P.box((1, 1, 1)),
            "coin": lambda: P.cylinder(0.5, 0.14, segments=14, axis="z"),
        }[name]()
    return _MESHES[name]


def _DrawItem():
    from .renderer import DrawItem
    return DrawItem


def _rng(seed, salt=""):
    return np.random.default_rng(zlib.crc32(f"{seed}:{salt}".encode()) & 0x7FFFFFFF)


def _ease_out(u):
    u = min(1.0, max(0.0, u))
    return 1.0 - (1.0 - u) ** 3


def _bounce(u):
    u = min(1.0, max(0.0, u))
    if u < 1 / 2.75:
        return 7.5625 * u * u
    if u < 2 / 2.75:
        u -= 1.5 / 2.75
        return 7.5625 * u * u + 0.75
    if u < 2.5 / 2.75:
        u -= 2.25 / 2.75
        return 7.5625 * u * u + 0.9375
    u -= 2.625 / 2.75
    return 7.5625 * u * u + 0.984375


def _m(pos, scale, rot=(0, 0, 0)):
    """T @ R(euler deg XYZ, CFrame order) @ S for scale tuple/number."""
    from .util import compose
    s = (scale, scale, scale) if np.isscalar(scale) else scale
    return compose(pos, rot, s)


# ------------------------------------------------------------------------------------------ base
class FxSystem:
    """Base: active on [t0, t1] (None = always)."""
    set = None
    t0 = None
    t1 = None

    def active(self, t):
        return (self.t0 is None or t >= self.t0 - 1e-9) and (self.t1 is None or t <= self.t1 + 1e-9)

    def items(self, t, cam=None):
        return []

    def meta(self):
        return {}


class Puffs(FxSystem):
    """Burst of cartoon dust spheres expanding from `pos` (also used for footsteps)."""

    def __init__(self, t, pos, size=1.0, count=7, dur=0.7, seed=0, lift=0.6, spread=1.0, color=(0.93, 0.91, 0.88)):
        self.t, self.pos, self.size, self.count, self.dur = float(t), np.asarray(pos, float), float(size), int(count), float(dur)
        self.t0, self.t1 = self.t, self.t + self.dur
        r = _rng(seed, f"puff{t:.3f}")
        ang = r.uniform(0, 2 * math.pi, count)
        self.dirs = np.stack([np.cos(ang), np.zeros(count), np.sin(ang)], 1)
        self.r0 = r.uniform(0.35, 0.65, count) * size
        self.r1 = r.uniform(1.0, 1.7, count) * size
        self.dist = r.uniform(0.8, 2.0, count) * size * spread
        self.up = r.uniform(0.3, 1.0, count) * lift * size
        self.color = color

    def items(self, t, cam=None):
        u = (t - self.t) / self.dur
        if u < 0 or u > 1:
            return []
        DI = _DrawItem()
        out = []
        e = _ease_out(u)
        alpha_t = 1.0 - max(0.0, (u - 0.35) / 0.65) ** 1.4
        for i in range(self.count):
            r = self.r0[i] + (self.r1[i] - self.r0[i]) * e
            p = self.pos + self.dirs[i] * self.dist[i] * e + np.array([0, r * 0.55 + self.up[i] * e, 0])
            out.append(DI(mesh=_mesh("puff"), model=_m(p, r * 2.0), color=self.color,
                          transparency=1.0 - 0.92 * alpha_t, cast_shadow=False, receive_shadow=False,
                          emissive=0.35))
        return out


class Footsteps(FxSystem):
    """Small dust at the feet while a character moves fast; reads positions from a callable pos(t)->xyz."""

    def __init__(self, pos_fn, t0, t1, interval=0.23, size=0.55, min_speed=9.0, seed=0, y=0.0):
        self.pos_fn, self.t0, self.t1 = pos_fn, float(t0), float(t1)
        self.interval, self.size, self.min_speed, self.seed, self.y = float(interval), float(size), float(min_speed), seed, y

    def items(self, t, cam=None):
        out = []
        k1 = int(math.floor((t - self.t0) / self.interval))
        k0 = max(0, int(math.floor((t - 0.45 - self.t0) / self.interval)))
        for k in range(k0, k1 + 1):
            ts = self.t0 + k * self.interval
            if ts > self.t1 or ts > t:
                continue
            p0, p1 = np.asarray(self.pos_fn(ts - 0.05), float), np.asarray(self.pos_fn(ts + 0.05), float)
            v = np.linalg.norm((p1 - p0)[[0, 2]]) / 0.1
            if v < self.min_speed:
                continue
            side = 0.5 if k % 2 else -0.5
            dirv = (p1 - p0) * np.array([1, 0, 1])
            dirv = dirv / (np.linalg.norm(dirv) + 1e-9)
            perp = np.array([-dirv[2], 0, dirv[0]])
            p = np.asarray(self.pos_fn(ts), float).copy()
            p = p - dirv * 0.8 + perp * side
            p[1] = self.y
            out += Puffs(ts, p, size=self.size, count=3, dur=0.45, seed=(self.seed, k), lift=0.3,
                         spread=0.6).items(t)
        return out


class DustCover(FxSystem):
    """Camera-space cluster of cartoon puffs: grows to fill the frame at mid-time, then clears."""

    def __init__(self, t, duration=0.4, size=1.0, color=(0.72, 0.68, 0.62), seed=0):
        self.t, self.dur, self.size, self.color = float(t), float(duration), float(size), color
        self.t0, self.t1 = self.t, self.t + self.dur
        r = _rng(seed, f"cover{t:.3f}")
        n = 16
        self.o = np.stack([r.uniform(-1.3, 1.3, n), r.uniform(-1.9, 1.9, n), r.uniform(0.0, 1.0, n)], 1)
        self.rad = r.uniform(0.9, 1.5, n)
        self.shade = r.uniform(0.9, 1.05, n)

    def items(self, t, cam=None):
        if cam is None:
            return []
        u = (t - self.t) / self.dur
        if u < 0 or u > 1:
            return []
        from .util import look_at
        eye, tgt = np.asarray(cam.eye, float), np.asarray(cam.target, float)
        f = tgt - eye
        f = f / (np.linalg.norm(f) + 1e-9)
        up0 = np.asarray(cam.up, float)
        r_ = np.cross(f, up0)
        r_ = r_ / (np.linalg.norm(r_) + 1e-9)
        u_ = np.cross(r_, f)
        if cam.roll:
            a = math.radians(cam.roll)
            u_ = u_ * math.cos(a) + r_ * math.sin(a)
            r_ = np.cross(f, u_)
            r_ = r_ / (np.linalg.norm(r_) + 1e-9)
        k = math.tan(math.radians(cam.fov_y) / 2)
        env = math.sin(math.pi * u) ** 2.0            # opacity/size peak at the middle (the cut moment)
        DI = _DrawItem()
        out = []
        for i in range(len(self.o)):
            dist = 2.6 + self.o[i, 2] * 2.2
            half_h = dist * k
            p = eye + f * dist + r_ * self.o[i, 0] * half_h * 0.62 + u_ * self.o[i, 1] * half_h * 0.62
            rad = self.rad[i] * half_h * (0.45 + 0.95 * env) * self.size
            col = tuple(min(1.0, c * self.shade[i]) for c in self.color)
            out.append(DI(mesh=_mesh("puff"), model=_m(p, rad * 2.0), color=col,
                          transparency=1.0 - min(0.36, 0.42 * env), cast_shadow=False, receive_shadow=False,
                          emissive=0.12))
        return out


class Sweep(FxSystem):
    """A big flat-coloured block flying through the lens (object-sweep cut hider)."""

    def __init__(self, t, duration=0.25, color=(0.15, 0.15, 0.2), direction=1.0):
        self.t, self.dur, self.color, self.dir = float(t), float(duration), color, float(direction)
        self.t0, self.t1 = self.t, self.t + self.dur

    def items(self, t, cam=None):
        if cam is None:
            return []
        u = (t - self.t) / self.dur
        if u < 0 or u > 1:
            return []
        eye, tgt = np.asarray(cam.eye, float), np.asarray(cam.target, float)
        f = tgt - eye
        f = f / (np.linalg.norm(f) + 1e-9)
        r_ = np.cross(f, np.asarray(cam.up, float))
        r_ = r_ / (np.linalg.norm(r_) + 1e-9)
        u_ = np.cross(r_, f)
        k = math.tan(math.radians(cam.fov_y) / 2)
        dist = 1.6
        half_h = dist * k
        x = (-2.2 + 4.4 * u) * self.dir * half_h * 0.56
        p = eye + f * dist + r_ * x
        # basis matrix: x along r_, y along u_, z along f
        m = np.eye(4)
        m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = r_ * half_h * 1.2, u_ * half_h * 3.4, f * 0.4, p
        return [_DrawItem()(mesh=_mesh("box"), model=m, color=self.color, cast_shadow=False,
                            receive_shadow=False, emissive=0.1)]


class Falling(FxSystem):
    """Camera-anchored wrap-around falling particles (snow, leaves, debris)."""

    def __init__(self, t0, t1, count=140, speed=5.0, wind=1.5, size=0.2, colors=((1, 1, 1),), sway=0.6,
                 box=(46.0, 22.0, 46.0), seed=0, mesh="dot", spin=0.0, emissive=0.6, flat=False):
        self.t0, self.t1 = t0, t1
        self.count, self.speed, self.wind, self.size, self.sway = int(count), speed, wind, size, sway
        self.box, self.mesh, self.spin, self.emissive, self.flat = np.asarray(box, float), mesh, spin, emissive, flat
        r = _rng(seed, "fall")
        self.p0 = r.uniform(0, 1, (count, 3))
        self.ph = r.uniform(0, 6.28, (count, 2))
        self.sz = r.uniform(0.6, 1.4, count) * size
        self.vel = r.uniform(0.7, 1.3, count)
        self.col = [tuple(colors[i % len(colors)]) for i in range(count)]
        self.rot0 = r.uniform(0, 360, (count, 3))

    def items(self, t, cam=None):
        if cam is None:
            return []
        tgt = np.asarray(cam.target, float)
        eye = np.asarray(cam.eye, float)
        center = 0.5 * (tgt + eye)
        center = np.array([center[0], 0.0, center[2]])
        ts = t - (self.t0 or 0.0)
        fade = 1.0
        if self.t0 is not None:
            fade = min(1.0, max(0.0, (t - self.t0) / 0.6))
        DI = _DrawItem()
        out = []
        W = self.box
        for i in range(self.count):
            wy = (self.p0[i, 1] * W[1] - ts * self.speed * self.vel[i]) % W[1]
            wx = (self.p0[i, 0] * W[0] + ts * self.wind * self.vel[i] + math.sin(ts * 1.3 + self.ph[i, 0]) * self.sway) % W[0]
            wz = (self.p0[i, 2] * W[2] + math.sin(ts * 1.1 + self.ph[i, 1]) * self.sway) % W[2]
            # wrap relative to the camera centre so the field follows the camera
            px = center[0] + ((wx - center[0] + W[0] / 2) % W[0]) - W[0] / 2
            pz = center[2] + ((wz - center[2] + W[2] / 2) % W[2]) - W[2] / 2
            p = (px, wy, pz)
            if np.linalg.norm(np.array(p) - eye) < 0.8:
                continue
            s = self.sz[i] * fade
            if self.flat:
                rot = (self.rot0[i, 0] + ts * self.spin * 90, self.rot0[i, 1] + ts * self.spin * 40, self.rot0[i, 2])
                m = _m(p, (s * 1.6, s * 0.12, s * 1.1), rot)
                mesh = _mesh("box")
            else:
                m = _m(p, s * 2.0)
                mesh = _mesh(self.mesh)
            out.append(DI(mesh=mesh, model=m, color=self.col[i], cast_shadow=False, receive_shadow=False,
                          emissive=self.emissive))
        return out


class Coins(FxSystem):
    def __init__(self, t, pos, count=24, dur=2.4, spread=5.0, seed=0, color=(1.0, 0.79, 0.24), radius=0.55):
        self.t, self.pos, self.count, self.dur, self.spread = float(t), np.asarray(pos, float), int(count), float(dur), spread
        self.t0, self.t1 = self.t, self.t + self.dur
        r = _rng(seed, f"coins{t:.3f}")
        self.off = r.uniform(-spread, spread, (count, 2))
        self.delay = r.uniform(0, 0.8, count)
        self.start_h = r.uniform(11, 16, count)
        self.spin = r.uniform(180, 540, count)
        self.color, self.radius = color, radius

    def items(self, t, cam=None):
        out = []
        DI = _DrawItem()
        for i in range(self.count):
            lt = t - self.t - self.delay[i]
            if lt < 0:
                continue
            fall = 0.9
            u = min(1.0, lt / fall)
            y = self.start_h[i] * (1 - _bounce(u)) + self.radius
            if lt > self.dur - self.delay[i] + 0.3:
                continue
            p = (self.pos[0] + self.off[i, 0], self.pos[1] + y, self.pos[2] + self.off[i, 1])
            rot = (0, lt * self.spin[i], 0) if u < 1 else (80, i * 37.0, 0)
            out.append(DI(mesh=_mesh("coin"), model=_m(p, self.radius * 2.0, rot), color=self.color,
                          material="metal", cast_shadow=True, emissive=0.25))
        return out


class Papers(FxSystem):
    def __init__(self, t, pos, count=14, dur=3.0, spread=5.0, seed=0):
        self.t, self.pos, self.count, self.dur = float(t), np.asarray(pos, float), int(count), float(dur)
        self.t0, self.t1 = self.t, self.t + self.dur
        r = _rng(seed, f"papers{t:.3f}")
        ang = r.uniform(0, 2 * math.pi, count)
        sp = r.uniform(2, spread * 1.6, count)
        self.v = np.stack([np.cos(ang) * sp, r.uniform(6, 12, count), np.sin(ang) * sp], 1)
        self.ph = r.uniform(0, 6.28, (count, 3))
        self.spin = r.uniform(120, 400, (count, 3))

    def items(self, t, cam=None):
        lt = t - self.t
        if lt < 0 or lt > self.dur:
            return []
        DI = _DrawItem()
        out = []
        for i in range(self.count):
            drag = 1.0 - math.exp(-lt * 1.6)
            x = self.pos[0] + self.v[i, 0] * drag * 0.7 + math.sin(lt * 4 + self.ph[i, 0]) * 0.6
            z = self.pos[2] + self.v[i, 2] * drag * 0.7 + math.sin(lt * 3.5 + self.ph[i, 1]) * 0.6
            y = max(0.05, self.pos[1] + 2 + self.v[i, 1] * lt * 0.5 - 3.2 * lt * lt * (0.35 + 0.1 * math.sin(self.ph[i, 2])))
            ground = y <= 0.06
            rot = (self.spin[i, 0] * lt * (0.0 if ground else 1.0), self.spin[i, 1] * lt, 0) if not ground else (0, self.ph[i, 0] * 50, 0)
            op = 1.0 - max(0.0, (lt - self.dur * 0.8) / (self.dur * 0.2))
            out.append(DI(mesh=_mesh("box"), model=_m((x, y, z), (1.0, 0.04, 1.3), rot), color=(0.97, 0.97, 0.95),
                          transparency=1 - op, cast_shadow=False, emissive=0.15))
        return out


class Sparkles(FxSystem):
    def __init__(self, t, pos, count=14, dur=0.9, color=(1.0, 0.9, 0.4), radius=2.5, seed=0):
        self.t, self.pos, self.count, self.dur, self.color, self.radius = float(t), np.asarray(pos, float), int(count), float(dur), color, radius
        self.t0, self.t1 = self.t, self.t + self.dur
        r = _rng(seed, f"spark{t:.3f}")
        self.off = r.normal(0, 1, (count, 3)) * radius * 0.5
        self.delay = r.uniform(0, 0.5, count) * dur
        self.life = r.uniform(0.35, 0.6, count) * dur + 0.15
        self.size = r.uniform(0.25, 0.55, count)

    def items(self, t, cam=None):
        DI = _DrawItem()
        out = []
        for i in range(self.count):
            u = (t - self.t - self.delay[i]) / self.life[i]
            if u < 0 or u > 1:
                continue
            s = self.size[i] * math.sin(math.pi * u)
            p = self.pos + self.off[i] + np.array([0, u * 0.8, 0])
            for sc in ((s * 1.8, s * 0.35, s * 0.35), (s * 0.35, s * 1.8, s * 0.35)):   # 4-point star = two crossed bars
                out.append(DI(mesh=_mesh("box"), model=_m(p, sc), color=self.color, cast_shadow=False,
                              receive_shadow=False, emissive=1.0, material="neon"))
        return out


# ------------------------------------------------------------------------------------------ factory
FX_TYPES = ("dust", "footsteps", "dust_cover", "snow", "leaves", "coins", "papers", "sparkles", "sweep")


def make_fx(spec: dict, resolver=None, seed=0) -> FxSystem:
    """Build an FxSystem from a spec dict. `resolver(name, t)` gives a character's feet position (footsteps)."""
    ty = spec.get("type")
    sd = spec.get("seed", seed)
    if ty == "dust":
        s = Puffs(spec["t"], spec.get("pos", (0, 0, 0)), spec.get("size", 1.0), spec.get("count", 7),
                  spec.get("dur", 0.7), sd)
    elif ty == "footsteps":
        ch = spec.get("character")
        if ch is None or resolver is None:
            raise ValueError("footsteps needs 'character' (and a resolver)")
        s = Footsteps(lambda tt, ch=ch: resolver(ch, tt), spec["t0"], spec["t1"], spec.get("interval", 0.23),
                      spec.get("size", 0.55), spec.get("min_speed", 9.0), sd, spec.get("y", 0.0))
    elif ty == "dust_cover":
        s = DustCover(spec["t"], spec.get("duration", 0.4), spec.get("size", 1.0),
                      tuple(spec.get("color", (0.72, 0.68, 0.62))), sd)
    elif ty == "sweep":
        s = Sweep(spec["t"], spec.get("duration", 0.25), tuple(spec.get("color", (0.15, 0.15, 0.2))),
                  spec.get("direction", 1.0))
    elif ty == "snow":
        s = Falling(spec.get("t0"), spec.get("t1"), count=int(150 * spec.get("density", 1.0)),
                    speed=spec.get("speed", 5.0), wind=spec.get("wind", 1.5), size=spec.get("size", 0.16),
                    colors=((1, 1, 1),), seed=sd)
    elif ty == "leaves":
        cols = [tuple(c) for c in spec.get("colors", [(0.9, 0.5, 0.1), (0.8, 0.25, 0.1), (0.95, 0.75, 0.2)])]
        s = Falling(spec.get("t0"), spec.get("t1"), count=int(60 * spec.get("density", 1.0)),
                    speed=spec.get("speed", 2.4), wind=spec.get("wind", 2.0), size=spec.get("size", 0.28),
                    colors=cols, sway=1.2, seed=sd, spin=3.0, emissive=0.15, flat=True, box=(36, 18, 36))
    elif ty == "coins":
        s = Coins(spec["t"], spec.get("pos", (0, 0, 0)), spec.get("count", 24), spec.get("dur", 2.4),
                  spec.get("spread", 5.0), sd)
    elif ty == "papers":
        s = Papers(spec["t"], spec.get("pos", (0, 0, 0)), spec.get("count", 14), spec.get("dur", 3.0),
                   spec.get("spread", 5.0), sd)
    elif ty == "sparkles":
        s = Sparkles(spec["t"], spec.get("pos", (0, 3, 0)), spec.get("count", 14), spec.get("dur", 0.9),
                     tuple(spec.get("color", (1.0, 0.9, 0.4))), spec.get("radius", 2.5), sd)
    else:
        raise ValueError(f"unknown fx type {ty!r}; known: {FX_TYPES}")
    s.set = spec.get("set")
    if spec.get("t0") is not None and ty not in ("snow", "leaves", "footsteps"):
        s.t0 = spec["t0"]
    return s
