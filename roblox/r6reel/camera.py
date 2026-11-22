"""r6reel.camera - keyframed, deterministic, composable virtual camera.

Conventions (match docs/SPEC.md)
--------------------------------
* Y-up, right-handed, studs.  Roblox forward is -Z: an avatar at ``facing_deg=0``
  looks toward -Z; its right hand is +X.
* ``facing_deg`` rotates about +Y with the right-hand rule (counter-clockwise seen
  from above), so +90 turns the avatar from -Z toward -X (to its left).
  ``forward(f) = (-sin f, 0, -cos f)``, ``right(f) = (cos f, 0, -sin f)``.
* ``azimuth_deg`` (shot presets) is measured from the avatar's FRONT:
  0 = in front of the face, +90 = avatar's left side, 180 = behind, -90 = right side.
* ``yaw`` for whip pans / cam offsets: positive = camera turns RIGHT; ``pitch``
  positive = camera tilts UP.  ``orbit`` degrees: positive = camera travels
  counter-clockwise seen from above.
* ``roll`` degrees: positive rotates the camera's up vector clockwise on screen
  (the world appears to rotate counter-clockwise), i.e. Rodrigues rotation of
  ``up`` about the view direction by +roll.

Design
------
A ``Camera`` has four keyframed *base tracks* (position, target, fov, roll) and an
ordered list of *effects* (push_in, orbit, drift, shake, follow, ...).  ``state(t)``
evaluates the tracks and then applies every active effect in insertion order.
Everything is a pure function of ``t``: no per-frame state.  Damped follow is
computed by deterministic fixed-step integration from its own start time (memoised
in a table, which never changes results).

``snap_to`` is a hard cut: it writes constant-eased keys and, because effects stop
at the next cut (unless ``across_cuts=True``), moves from the previous shot do not
leak into the next one.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence, Union

import numpy as np

Vec = Union[Sequence[float], np.ndarray]
Target = Union[str, Vec, Callable[[float], Vec]]

# --------------------------------------------------------------------------- #
# CameraState (lazy import from renderer, local fallback with identical fields)
# --------------------------------------------------------------------------- #


@dataclass
class LocalCameraState:
    eye: tuple
    target: tuple
    up: tuple = (0.0, 1.0, 0.0)
    fov_y: float = 70.0
    roll: float = 0.0
    near: float = 0.1
    far: float = 2000.0


_CS_CLS = None


def camera_state_cls():
    """Return renderer.CameraState if importable, else the local fallback."""
    global _CS_CLS
    if _CS_CLS is None:
        try:
            from r6reel.renderer import CameraState  # type: ignore
            _CS_CLS = CameraState
        except Exception:
            _CS_CLS = LocalCameraState
    return _CS_CLS


# --------------------------------------------------------------------------- #
# Easing
# --------------------------------------------------------------------------- #


def _linear(u): return u
def _cubic_in(u): return u ** 3
def _cubic_out(u): return 1.0 - (1.0 - u) ** 3
def _cubic_inout(u): return 4.0 * u ** 3 if u < 0.5 else 1.0 - (-2.0 * u + 2.0) ** 3 / 2.0
def _sine_inout(u): return -(math.cos(math.pi * u) - 1.0) / 2.0
def _constant(u): return 0.0 if u < 1.0 else 1.0


def _back_out(u):
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (u - 1.0) ** 3 + c1 * (u - 1.0) ** 2


def _elastic_out(u):
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    return 2.0 ** (-10.0 * u) * math.sin((u * 10.0 - 0.75) * (2.0 * math.pi / 3.0)) + 1.0


def _bounce_out(u):
    n1, d1 = 7.5625, 2.75
    if u < 1 / d1:
        return n1 * u * u
    if u < 2 / d1:
        u -= 1.5 / d1
        return n1 * u * u + 0.75
    if u < 2.5 / d1:
        u -= 2.25 / d1
        return n1 * u * u + 0.9375
    u -= 2.625 / d1
    return n1 * u * u + 0.984375


EASINGS: dict[str, Callable[[float], float]] = {
    "linear": _linear, "constant": _constant,
    "cubic_in": _cubic_in, "cubic_out": _cubic_out, "cubic_inout": _cubic_inout,
    "back_out": _back_out, "elastic_out": _elastic_out, "bounce_out": _bounce_out,
    "sine_inout": _sine_inout,
}


def ease(name: Union[str, Callable[[float], float]], u: float) -> float:
    """Apply easing ``name`` (or a callable) to u; u is clamped to [0, 1]."""
    u = 0.0 if u < 0.0 else 1.0 if u > 1.0 else float(u)
    fn = name if callable(name) else EASINGS[name]
    return fn(u)


def _progress(t, t0, t1, easing="cubic_inout") -> float:
    if t1 <= t0:
        return 1.0 if t >= t0 else 0.0
    return ease(easing, (t - t0) / (t1 - t0))


def _smooth_env(t, t0, t1, fade_in, fade_out) -> float:
    """0 -> 1 over fade_in after t0, 1 -> 0 over fade_out before t1 (t1 None = never)."""
    w = 1.0
    if fade_in > 0:
        w *= ease("sine_inout", (t - t0) / fade_in)
    elif t < t0:
        w = 0.0
    if t1 is not None:
        if fade_out > 0:
            w *= ease("sine_inout", (t1 - t) / fade_out)
        elif t >= t1:
            w = 0.0
    return w


# --------------------------------------------------------------------------- #
# Small vector helpers
# --------------------------------------------------------------------------- #

Y = np.array([0.0, 1.0, 0.0])


def _v(x) -> np.ndarray:
    return np.array(x, dtype=float).reshape(3)


def _unit(v, fallback=(0.0, 0.0, -1.0)):
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else np.array(fallback, float)


def forward_vec(facing_deg: float) -> np.ndarray:
    """Unit forward vector of an avatar facing ``facing_deg`` (0 -> -Z)."""
    a = math.radians(facing_deg)
    return np.array([-math.sin(a), 0.0, -math.cos(a)])


def right_vec(facing_deg: float) -> np.ndarray:
    a = math.radians(facing_deg)
    return np.array([math.cos(a), 0.0, -math.sin(a)])


def rot_y(v, deg: float) -> np.ndarray:
    """Rotate v about +Y by deg (right-hand rule, CCW seen from above)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = v
    return np.array([x * c + z * s, y, -x * s + z * c])


def _basis(pos, tgt, up, roll_deg=0.0):
    """(right, up, forward) orthonormal view basis with roll applied."""
    f = _unit(np.asarray(tgt, float) - np.asarray(pos, float))
    up = _unit(up, (0, 1, 0))
    r = np.cross(f, up)
    if np.linalg.norm(r) < 1e-6:           # looking along up: pick any perpendicular
        r = np.cross(f, np.array([0.0, 0.0, -1.0]))
        if np.linalg.norm(r) < 1e-6:
            r = np.cross(f, np.array([1.0, 0.0, 0.0]))
    r = _unit(r)
    u = np.cross(r, f)
    if roll_deg:
        a = math.radians(roll_deg)
        c, s = math.cos(a), math.sin(a)
        r, u = r * c - u * s, u * c + r * s
    return r, u, f


def _yaw_pitch(v, yaw_right_deg, pitch_up_deg, up=Y):
    """Rotate direction v: yaw right (about -up), then pitch up (about local right)."""
    v = np.asarray(v, float)
    if yaw_right_deg:
        v = rot_y(v, -yaw_right_deg)
    if pitch_up_deg:
        r = np.cross(_unit(v), Y)
        if np.linalg.norm(r) < 1e-6:
            return v
        r = _unit(r)
        a = math.radians(pitch_up_deg)
        v = v * math.cos(a) + np.cross(r, v) * math.sin(a) + r * np.dot(r, v) * (1 - math.cos(a))
    return v


class _Noise:
    """Deterministic smooth noise: sum of three sines per axis, values in about [-1, 1]."""
    MULT = (1.0, 1.93, 3.37)
    AMP = (1.0, 0.5, 0.25)

    def __init__(self, seed: int = 0, axes: int = 3):
        rng = np.random.default_rng(int(seed) + 12345)
        self.phase = rng.uniform(0, 2 * math.pi, size=(axes, 3))
        self.fscale = rng.uniform(0.85, 1.15, size=(axes, 3))
        self.norm = sum(self.AMP)

    def __call__(self, t: float, freq: float = 1.0) -> np.ndarray:
        out = np.zeros(self.phase.shape[0])
        for a in range(self.phase.shape[0]):
            acc = 0.0
            for k in range(3):
                acc += self.AMP[k] * math.sin(
                    2 * math.pi * freq * self.MULT[k] * self.fscale[a, k] * t + self.phase[a, k])
            out[a] = acc / self.norm
        return out


# --------------------------------------------------------------------------- #
# Keyframe track
# --------------------------------------------------------------------------- #


class Track:
    """Keyframed scalar/vector track.  A key's easing shapes the segment ARRIVING at it
    ("constant" holds the previous value until the key's time, then jumps)."""

    def __init__(self, initial, t0: float = 0.0):
        self.keys: list[tuple[float, np.ndarray, Any]] = [(t0, np.array(initial, float), "linear")]

    def add(self, t: float, value, easing="cubic_inout") -> "Track":
        value = np.array(value, float)
        self.keys = [k for k in self.keys if abs(k[0] - t) > 1e-9]
        self.keys.append((float(t), value, easing))
        self.keys.sort(key=lambda k: k[0])
        return self

    def eval(self, t: float) -> np.ndarray:
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1].copy()
        times = [k[0] for k in ks]
        i = bisect.bisect_right(times, t)
        if i >= len(ks):
            return ks[-1][1].copy()
        (ta, va, _), (tb, vb, eb) = ks[i - 1], ks[i]
        u = (t - ta) / (tb - ta)
        return va + (vb - va) * ease(eb, u)


# --------------------------------------------------------------------------- #
# Evaluation scratch
# --------------------------------------------------------------------------- #


class _S:
    __slots__ = ("pos", "tgt", "fov", "roll")

    def __init__(self, pos, tgt, fov, roll):
        self.pos, self.tgt, self.fov, self.roll = pos, tgt, float(fov), float(roll)


class _Smoother:
    """Exponential smoothing of a resolved target, integrated deterministically from t0."""
    DT = 1.0 / 240.0

    def __init__(self, cam: "Camera", target: Target, t0: float, tau: float):
        self.cam, self.target, self.t0, self.tau = cam, target, float(t0), float(tau)
        self.table: list[np.ndarray] = []

    def reset(self):
        self.table = []

    def raw(self, t):
        return self.cam._resolve(self.target, t)

    def __call__(self, t: float) -> np.ndarray:
        if self.tau <= 1e-9:
            return self.raw(t)
        if t <= self.t0:
            return self.raw(self.t0)
        if not self.table:
            self.table.append(self.raw(self.t0))
        n = int((t - self.t0) / self.DT + 1e-9)
        a = 1.0 - math.exp(-self.DT / self.tau)
        while len(self.table) <= n:
            k = len(self.table)
            s = self.table[-1]
            x = self.raw(self.t0 + k * self.DT)
            self.table.append(s + (x - s) * a)
        s = self.table[n]
        rem = t - (self.t0 + n * self.DT)
        if rem > 1e-12:
            s = s + (self.raw(t) - s) * (1.0 - math.exp(-rem / self.tau))
        return s


# --------------------------------------------------------------------------- #
# Effects
# --------------------------------------------------------------------------- #


class _Effect:
    t0 = 0.0
    across_cuts = False

    def reset(self):
        pass

    def apply(self, cam: "Camera", t: float, S: _S):
        raise NotImplementedError


class _PushIn(_Effect):
    def __init__(self, t0, t1, amount, rate, easing, across):
        self.t0, self.t1, self.amount, self.rate, self.easing, self.across_cuts = t0, t1, amount, rate, easing, across

    def apply(self, cam, t, S):
        if self.rate is not None:                       # continuous fractional approach per second
            dur = max(0.0, (self.t1 - self.t0) if self.t1 is not None else (t - self.t0))
            scale = (1.0 - self.rate) ** min(t - self.t0, dur) if self.rate < 1 else 0.01
        else:
            scale = 1.0 - self.amount * _progress(t, self.t0, self.t1, self.easing)
        S.pos = S.tgt + (S.pos - S.tgt) * scale


class _Orbit(_Effect):
    def __init__(self, t0, t1, degrees, around, offset, easing, across):
        self.t0, self.t1, self.degrees, self.around, self.offset, self.easing = t0, t1, degrees, around, _v(offset), easing
        self.across_cuts = across

    def apply(self, cam, t, S):
        ang = self.degrees * _progress(t, self.t0, self.t1, self.easing)
        pivot = (S.tgt if self.around is None else cam._resolve(self.around, t)) + self.offset
        S.pos = pivot + rot_y(S.pos - pivot, ang)
        S.tgt = pivot + rot_y(S.tgt - pivot, ang)


class _WhipPan(_Effect):
    def __init__(self, t0, t1, degrees, pitch, easing, across):
        self.t0, self.t1, self.degrees, self.pitch, self.easing, self.across_cuts = t0, t1, degrees, pitch, easing, across

    def apply(self, cam, t, S):
        p = _progress(t, self.t0, self.t1, self.easing)
        v = S.tgt - S.pos
        v = _yaw_pitch(v, self.degrees * p, self.pitch * p)
        S.tgt = S.pos + v


class _Drift(_Effect):
    def __init__(self, t0, t1, amount, freq, seed, fade, across):
        self.t0, self.t1, self.amount, self.freq, self.fade = t0, t1, amount, freq, fade
        self.noise = _Noise(seed, 3)
        self.across_cuts = across

    def apply(self, cam, t, S):
        w = _smooth_env(t, self.t0, self.t1, self.fade, self.fade)
        if w <= 0:
            return
        n = self.noise(t, self.freq) * (self.amount * w)
        r, u, f = _basis(S.pos, S.tgt, cam.up, 0.0)
        S.pos = S.pos + r * n[0] + u * n[1] + f * (n[2] * 0.5)
        S.tgt = S.tgt + (r * n[1] + u * n[2]) * 0.4
        S.roll += n[0] * 0.8


class _Shake(_Effect):
    def __init__(self, t0, t1, amp, freq, decay, seed, roll_amp, across):
        self.t0, self.t1, self.amp, self.freq, self.decay = t0, t1, amp, freq, decay
        self.noise = _Noise(seed, 3)
        self.roll_amp = amp * 3.0 if roll_amp is None else roll_amp
        self.across_cuts = across

    def apply(self, cam, t, S):
        if t >= self.t1:
            return
        loc = t - self.t0
        env = min(1.0, loc / 0.03)
        tail = (self.t1 - t) / max(0.05, 0.25 * (self.t1 - self.t0))
        env *= min(1.0, tail)
        if self.decay > 0:
            env *= math.exp(-self.decay * loc)
        n = self.noise(t, self.freq)
        r, u, f = _basis(S.pos, S.tgt, cam.up, 0.0)
        off = (r * n[0] + u * n[1]) * (self.amp * env)
        S.pos = S.pos + off
        S.tgt = S.tgt + off * 0.5
        S.roll += n[2] * self.roll_amp * env


class _Crane(_Effect):
    def __init__(self, t0, t1, dy, easing, tilt, across):
        self.t0, self.t1, self.dy, self.easing, self.tilt, self.across_cuts = t0, t1, dy, easing, tilt, across

    def apply(self, cam, t, S):
        d = self.dy * _progress(t, self.t0, self.t1, self.easing)
        S.pos = S.pos + Y * d
        if not self.tilt:
            S.tgt = S.tgt + Y * d


class _LowAngle(_Effect):
    def __init__(self, t0, t1, height, easing, across):
        self.t0, self.t1, self.height, self.easing, self.across_cuts = t0, t1, height, easing, across

    def apply(self, cam, t, S):
        p = _progress(t, self.t0, self.t1, self.easing)
        S.pos = S.pos.copy()
        S.pos[1] = S.pos[1] + (self.height - S.pos[1]) * p


class _Dutch(_Effect):
    def __init__(self, t0, t1, degrees, easing, across):
        self.t0, self.t1, self.degrees, self.easing, self.across_cuts = t0, t1, degrees, easing, across

    def apply(self, cam, t, S):
        S.roll += self.degrees * _progress(t, self.t0, self.t1, self.easing)


class _DollyZoom(_Effect):
    def __init__(self, t0, t1, fov_to, easing, across):
        self.t0, self.t1, self.fov_to, self.easing, self.across_cuts = t0, t1, fov_to, easing, across

    def apply(self, cam, t, S):
        p = _progress(t, self.t0, self.t1, self.easing)
        f0 = S.fov
        f1 = f0 + (self.fov_to - f0) * p
        d = S.pos - S.tgt
        k = math.tan(math.radians(f0) / 2) / math.tan(math.radians(f1) / 2)
        S.pos = S.tgt + d * k          # keeps distance * tan(fov/2) constant (subject size fixed)
        S.fov = f1


class _LookAt(_Effect):
    def __init__(self, cam, target, t0, t1, offset, blend, damping, across):
        self.t0, self.t1, self.offset, self.blend = t0, t1, _v(offset), blend
        self.smooth = _Smoother(cam, target, t0, damping)
        self.across_cuts = across

    def reset(self):
        self.smooth.reset()

    def apply(self, cam, t, S):
        w = _smooth_env(t, self.t0, self.t1, self.blend, self.blend)
        if w <= 0:
            return
        S.tgt = S.tgt + (self.smooth(t) + self.offset - S.tgt) * w


class _Follow(_Effect):
    def __init__(self, cam, target, t0, t1, offset, damping, look_offset, blend, across):
        self.t0, self.t1 = t0, t1
        self.offset = None if offset is None else _v(offset)
        self.look_offset, self.blend = _v(look_offset), blend
        self.smooth = _Smoother(cam, target, t0, damping)
        self.across_cuts = across

    def reset(self):
        self.smooth.reset()

    def apply(self, cam, t, S):
        te = t if self.t1 is None else min(t, self.t1)
        s = self.smooth(te)
        if self.offset is None:                          # delta mode: keep composition, translate rig
            delta = s - self.smooth.raw(self.t0)
            S.pos = S.pos + delta
            S.tgt = S.tgt + delta
        else:                                            # absolute: ride at s + offset, aim at s + look_offset
            w = 1.0 if self.blend <= 0 else ease("sine_inout", (t - self.t0) / self.blend)
            S.pos = S.pos + (s + self.offset - S.pos) * w
            S.tgt = S.tgt + (s + self.look_offset - S.tgt) * w


# --------------------------------------------------------------------------- #
# Camera
# --------------------------------------------------------------------------- #


class Camera:
    """Keyframed deterministic camera.  All builders return ``self`` for chaining.

    ``resolver(name, t) -> (x, y, z)`` (see :meth:`bind`) gives the world point of a
    named character at time t; use whatever point you want the camera to treat as the
    subject (e.g. torso/head).  Strings passed to follow/look_at/orbit are resolved
    with it; points and ``callable(t)`` are accepted as well.
    """

    def __init__(self, position=(0, 5, -10), target=(0, 3, 0), fov=70.0, roll=0.0,
                 up=(0, 1, 0), near=0.1, far=2000.0, resolver=None):
        self._pos = Track(position)
        self._tgt = Track(target)
        self._fov = Track([fov])
        self._roll = Track([roll])
        self.up = _v(up)
        self.near, self.far = near, far
        self.resolver = resolver
        self._effects: list[_Effect] = []
        self._cuts: list[float] = []
        self.info: dict = {}

    # -- plumbing ---------------------------------------------------------- #
    def bind(self, resolver: Optional[Callable[[str, float], Vec]]) -> "Camera":
        """Set ``resolver(name, t) -> (x, y, z)`` used by follow / look_at / orbit(around=name)."""
        self.resolver = resolver
        for e in self._effects:
            e.reset()
        return self

    def _resolve(self, spec: Target, t: float) -> np.ndarray:
        if isinstance(spec, str):
            if self.resolver is None:
                raise RuntimeError(f"Camera has no resolver bound; cannot resolve {spec!r} (use Camera.bind)")
            return _v(self.resolver(spec, t))
        if callable(spec):
            return _v(spec(t))
        return _v(spec)

    def _add(self, eff: _Effect, t0: float) -> "Camera":
        eff.t0 = float(t0)
        self._effects.append(eff)
        return self

    # -- base tracks ------------------------------------------------------- #
    def key(self, t, position=None, target=None, fov=None, roll=None, ease="cubic_inout") -> "Camera":
        """Add keyframes to the base tracks (easing shapes the segment arriving at t)."""
        if position is not None: self._pos.add(t, position, ease)
        if target is not None: self._tgt.add(t, target, ease)
        if fov is not None: self._fov.add(t, [fov], ease)
        if roll is not None: self._roll.add(t, [roll], ease)
        return self

    def move_to(self, t0, t1, position=None, target=None, fov=None, roll=None, ease="cubic_inout") -> "Camera":
        """Tween base tracks from their current value at t0 to the given values at t1."""
        for trk, val in ((self._pos, position), (self._tgt, target),
                         (self._fov, None if fov is None else [fov]),
                         (self._roll, None if roll is None else [roll])):
            if val is not None:
                v0 = trk.eval(t0)
                trk.add(t0, v0, "linear")
                trk.add(t1, val, ease)
        return self

    def snap_to(self, t, position, target, fov=None, roll=None) -> "Camera":
        """Hard cut at t: base tracks jump; running moves from earlier shots end here."""
        self._pos.add(t, position, "constant")
        self._tgt.add(t, target, "constant")
        if fov is not None: self._fov.add(t, [fov], "constant")
        if roll is not None: self._roll.add(t, [roll], "constant")
        if t not in self._cuts:
            self._cuts.append(float(t))
            self._cuts.sort()
        return self

    @property
    def cut_times(self) -> list[float]:
        return list(self._cuts)

    # -- moves (additive effects) ------------------------------------------ #
    def push_in(self, t0, t1=None, amount=0.1, rate=None, ease="cubic_inout", across_cuts=False):
        """Dolly toward the target: closes ``amount`` (fraction) of the distance over t0..t1,
        holding afterwards.  ``rate`` (e.g. 0.06 = 6 %/s) instead gives a continuous slow
        push from t0 (to t1 or the end of the shot)."""
        if t1 is None and rate is None:
            raise ValueError("push_in needs t1 or rate")
        return self._add(_PushIn(t0, t1, amount, rate, ease, across_cuts), t0)

    def pull_out(self, t0, t1=None, amount=0.1, rate=None, ease="cubic_inout", across_cuts=False):
        """Dolly away: opens the distance by ``amount`` (fraction), or 'rate' per second."""
        if rate is not None:
            return self.push_in(t0, t1, rate=-abs(rate), across_cuts=across_cuts)
        return self.push_in(t0, t1, amount=-abs(amount), ease=ease, across_cuts=across_cuts)

    def orbit(self, t0, t1, degrees=90.0, around: Optional[Target] = None, offset=(0, 0, 0),
              ease="cubic_inout", across_cuts=False):
        """Rotate the rig about +Y around ``around`` (name/point; default the current target).
        Positive degrees = counter-clockwise seen from above."""
        return self._add(_Orbit(t0, t1, degrees, around, offset, ease, across_cuts), t0)

    def whip_pan(self, t0, t1, degrees=90.0, pitch=0.0, ease="cubic_inout", across_cuts=False):
        """Fast yaw (+right) / pitch (+up) sweep of the view direction, holding afterwards.
        Pair with transitions.whip() for the blur and a snap_to() at the midpoint."""
        return self._add(_WhipPan(t0, t1, degrees, pitch, ease, across_cuts), t0)

    def drift(self, t0=0.0, t1=None, amount=0.25, freq=0.25, seed=1, fade=0.6, across_cuts=False):
        """Slow handheld-ish float (studs).  Smooth noise on position, a gentler echo on aim."""
        return self._add(_Drift(t0, t1, amount, freq, seed, fade, across_cuts), t0)

    def shake(self, t0, t1, amp=0.2, freq=9.0, decay=0.0, seed=2, roll_amp=None, across_cuts=False):
        """High-frequency shake (amp in studs; roll defaults to amp*3 degrees).  ``decay`` is
        an exponential falloff rate per second (impact style)."""
        return self._add(_Shake(t0, t1, amp, freq, decay, seed, roll_amp, across_cuts), t0)

    def follow(self, target_name: Target, t0=0.0, t1=None, offset=None, damping=0.25,
               look_offset=(0, 0, 0), blend=0.0, across_cuts=False):
        """Track a moving subject.  ``damping`` is the lag time constant in seconds (0 = rigid;
        at constant speed v the camera trails by about v*damping studs).

        * ``offset=None`` (default, delta mode): keep the current framing and translate the whole
          rig by the subject's (smoothed) displacement since t0.  Works on top of any shot preset.
        * ``offset=(x,y,z)`` (absolute mode): ride at ``subject + offset`` and aim at
          ``subject + look_offset``, blending in over ``blend`` seconds.
        After t1 the camera holds where it was at t1."""
        return self._add(_Follow(self, target_name, t0, t1, offset, damping, look_offset, blend, across_cuts), t0)

    def look_at(self, target: Target, t0=0.0, t1=None, offset=(0, 0, 0), blend=0.25, damping=0.0,
                across_cuts=False):
        """Aim at a name/point (eased in/out over ``blend`` s); optional aim damping."""
        return self._add(_LookAt(self, target, t0, t1, offset, blend, damping, across_cuts), t0)

    def dolly_zoom(self, t0, t1, fov_to=100.0, ease="cubic_inout", across_cuts=False):
        """Vertigo effect: fov -> fov_to while the camera moves to keep the subject size constant."""
        return self._add(_DollyZoom(t0, t1, fov_to, ease, across_cuts), t0)

    def dutch(self, t0, t1, degrees=15.0, ease="cubic_inout", across_cuts=False):
        """Roll the camera by ``degrees`` (positive = clockwise), holding afterwards."""
        return self._add(_Dutch(t0, t1, degrees, ease, across_cuts), t0)

    tilt = dutch

    def crane(self, t0, t1, dy=6.0, ease="cubic_inout", tilt=True, across_cuts=False):
        """Rise (dy>0) or sink by dy studs; with tilt=True the aim point stays put (camera tilts)."""
        return self._add(_Crane(t0, t1, dy, ease, tilt, across_cuts), t0)

    def low_angle(self, t0=0.0, t1=None, height=0.8, ease="cubic_inout", across_cuts=False):
        """Sink the camera to ``height`` studs above the ground while the aim stays up (hero shot)."""
        return self._add(_LowAngle(t0, t0 + 0.4 if t1 is None else t1, height, ease, across_cuts), t0)

    # -- evaluation -------------------------------------------------------- #
    def _ended_by_cut(self, eff: _Effect, t: float) -> bool:
        if eff.across_cuts or not self._cuts:
            return False
        for c in self._cuts:
            if c > eff.t0 + 1e-9 and c <= t:
                return True
        return False

    def raw_state(self, t: float):
        """(pos, target, fov, roll) numpy values after tracks and effects."""
        S = _S(self._pos.eval(t), self._tgt.eval(t), self._fov.eval(t)[0], self._roll.eval(t)[0])
        for e in self._effects:
            if t < e.t0 or self._ended_by_cut(e, t):
                continue
            e.apply(self, t, S)
        return S.pos, S.tgt, S.fov, S.roll

    def state(self, t: float, offset: Optional[dict] = None):
        """CameraState at time t.  ``offset`` is an optional transitions cam_offset dict."""
        pos, tgt, fov, roll = self.raw_state(t)
        cs = camera_state_cls()(
            eye=tuple(float(x) for x in pos), target=tuple(float(x) for x in tgt),
            up=tuple(float(x) for x in self.up), fov_y=float(fov), roll=float(roll),
            near=self.near, far=self.far)
        return apply_cam_offset(cs, offset, t) if offset else cs

    def states(self, times) -> list:
        return [self.state(t) for t in times]


# --------------------------------------------------------------------------- #
# Transition camera offsets
# --------------------------------------------------------------------------- #

_SHAKE_NOISE = _Noise(777, 3)


def apply_cam_offset(cs, offset: Optional[dict], t: float = 0.0):
    """Apply a transitions ``cam_offset`` dict (fov_scale, yaw, pitch, roll, shake) to a
    CameraState and return a NEW state of the same class.  yaw + is right, pitch + is up,
    shake is an amplitude in studs (deterministic noise of t)."""
    if not offset:
        return cs
    eye, tgt = _v(cs.eye), _v(cs.target)
    fov = cs.fov_y * float(offset.get("fov_scale", 1.0))
    roll = cs.roll + float(offset.get("roll", 0.0))
    yaw, pitch = float(offset.get("yaw", 0.0)), float(offset.get("pitch", 0.0))
    if yaw or pitch:
        tgt = eye + _yaw_pitch(tgt - eye, yaw, pitch)
    amp = float(offset.get("shake", 0.0))
    if amp:
        n = _SHAKE_NOISE(t, 11.0)
        r, u, f = _basis(eye, tgt, cs.up, 0.0)
        off = (r * n[0] + u * n[1]) * amp
        eye, tgt = eye + off, tgt + off * 0.5
        roll += n[2] * amp * 3.0
    cls = type(cs)
    return cls(eye=tuple(float(x) for x in eye), target=tuple(float(x) for x in tgt),
               up=tuple(cs.up), fov_y=float(fov), roll=float(roll), near=cs.near, far=cs.far)


def project_points(cs, points, width: int, height: int):
    """Perspective-project world points. Returns (N,3) array of (px, py, depth), pixel origin
    top-left; depth <= near means behind the camera.  Honors roll."""
    pts = np.asarray(points, float).reshape(-1, 3)
    r, u, f = _basis(_v(cs.eye), _v(cs.target), _v(cs.up), cs.roll)
    rel = pts - _v(cs.eye)
    depth = rel @ f
    th = math.tan(math.radians(cs.fov_y) / 2)
    safe = np.where(np.abs(depth) < 1e-9, 1e-9, depth)
    nx = (rel @ r) / (safe * th * (width / height))
    ny = (rel @ u) / (safe * th)
    return np.stack([(nx * 0.5 + 0.5) * width, (0.5 - ny * 0.5) * height, depth], axis=1)


# --------------------------------------------------------------------------- #
# Shot presets
# --------------------------------------------------------------------------- #

def framing_distance(region_height: float, fov_deg: float, fill: float) -> float:
    """Distance along the view axis at which a vertical extent occupies ``fill`` of frame height."""
    return region_height / (2.0 * fill * math.tan(math.radians(fov_deg) / 2.0))


# kind -> dict(rh: framed region height / H, cy: region centre height / H, fov, fill (default),
#              az, el (degrees), rw: region width / H (must fit the frame width))
PRESETS: dict[str, dict] = {
    "wide":            dict(rh=1.00, cy=0.50, fov=70, fill=0.30, az=0,   el=4,   rw=0.50),
    "medium":          dict(rh=0.55, cy=0.725, fov=70, fill=0.55, az=0,  el=0,   rw=0.50),
    "closeup":         dict(rh=0.32, cy=0.86, fov=75, fill=0.60, az=0,   el=0,   rw=0.30),
    "extreme_closeup": dict(rh=0.25, cy=0.90, fov=85, fill=0.50, az=0,   el=0,   rw=0.25),
    "low_angle_hero":  dict(rh=1.00, cy=0.50, fov=75, fill=0.55, az=0,   el=-22, rw=0.50),
    "high_angle":      dict(rh=1.00, cy=0.50, fov=70, fill=0.35, az=0,   el=50,  rw=0.50),
    "top_down":        dict(rh=1.00, cy=0.50, fov=70, fill=0.25, az=0,   el=90,  rw=0.50),
    "chase_behind":    dict(rh=1.00, cy=0.50, fov=75, fill=0.45, az=180, el=10,  rw=0.50),
    "side_tracking":   dict(rh=1.00, cy=0.50, fov=70, fill=0.40, az=-90, el=3,   rw=0.50),
    "two_shot":        dict(rh=1.00, cy=0.50, fov=70, fill=0.38, az=0,   el=6,   rw=0.50),
    "over_shoulder":   dict(rh=0.50, cy=0.85, fov=48, fill=0.42, az=0,   el=0,   rw=0.30),
    "pov":             dict(rh=1.00, cy=0.50, fov=80, fill=0.50, az=0,   el=0,   rw=0.50),
}
SHOT_KINDS = tuple(PRESETS)
def _front_offset(kind, P, H, az, el):
    """Distance from the region's centre plane to the nearest body surface (fill is measured there):
    half the avatar depth (0.5 stud; 0.625 for the head) face-on, half the width (1 stud) side-on,
    the top of the body when looking straight down."""
    base = 0.125 * H if kind in ("closeup", "extreme_closeup") else 0.1 * H
    a = abs(((az + 180.0) % 360.0) - 180.0)
    if 60.0 <= a <= 120.0:
        base = 0.2 * H
    c = math.cos(math.radians(el))
    dz = base * c
    if abs(el) >= 75.0:
        dz += 0.5 * P["rh"] * H * math.sin(math.radians(abs(el)))
    return dz


def _footprint(P, H, el):
    # horizontal extent that adds to the apparent height when looking down: depth (0.2 H) for tilted
    # views, full body width when looking straight down
    return (P["rw"] if abs(el) >= 75 else _FOOTPRINT) * H


_FOOTPRINT = 0.2   # avatar depth/H used for the elevated-view extent (top-down: 1 stud for H=5, arms ignored)


def shot(kind: str, subject_pos=(0, 0, 0), subject_height: float = 5.0, facing_deg: float = 0.0,
         fill: Optional[float] = None, fov: Optional[float] = None, aspect: float = 9.0 / 16.0,
         azimuth_deg: Optional[float] = None, elevation_deg: Optional[float] = None,
         other_pos=None, anchor: str = "feet", screen_y: float = 0.5, min_height: float = 0.3,
         follow: Optional[str] = None, damping: float = 0.3, resolver=None) -> Camera:
    """Build a Camera framed like ``kind`` around a subject.

    subject_pos   avatar position: feet on the ground (anchor="feet", default) or bounding-box
                  centre (anchor="center").  For an R6 rig feet=(x,0,z) and height 5.
    subject_height  studs (R6 = 5).  facing_deg  see module docstring (0 faces -Z).
    fill          fraction of FRAME HEIGHT that the preset's framed region occupies (default per
                  kind; ``fill=0.5`` on "wide" => the whole 5-stud body is 50 % of frame height).
                  fill is measured at the avatar's nearest surface (see _front_offset).
                  Region per kind: wide/low_angle_hero/high_angle/top_down/chase/side/two_shot =
                  whole body; medium = waist up (55 % of H); closeup = head+shoulders (32 %);
                  extreme_closeup = head (25 %); over_shoulder = head+chest of the speaker.
    aspect        width/height of the frame (9/16); used for the width-fit check (the camera backs
                  off if the region would be cropped horizontally) and two_shot spacing.
    other_pos     second avatar (feet): listener for over_shoulder (default 3.2 studs in front of the
                  subject), partner for two_shot (default 3.5 studs to the subject's right).
    screen_y      where the framed region's centre lands vertically (0 top .. 1 bottom, 0.5 centred);
                  use ~0.4 to leave room for captions below.
    follow        optional character name: adds ``follow(name, damping)`` in delta mode.
    Distances are computed from fov and aspect: d = extent / (2 * fill * tan(fov/2)).
    """
    if kind not in PRESETS:
        raise ValueError(f"unknown shot kind {kind!r}; choose from {SHOT_KINDS}")
    P = dict(PRESETS[kind])
    H = float(subject_height)
    feet = _v(subject_pos) - (Y * (H / 2.0) if anchor == "center" else 0.0)
    fill = P["fill"] if fill is None else float(fill)
    f_deg = P["fov"] if fov is None else float(fov)
    az = P["az"] if azimuth_deg is None else float(azimuth_deg)
    el = P["el"] if elevation_deg is None else float(elevation_deg)
    th = math.tan(math.radians(f_deg) / 2.0)
    C = feet + Y * (P["cy"] * H)
    cam_up = None
    info = dict(kind=kind, fill=fill, fov=f_deg, aspect=aspect)

    if kind == "pov":
        fwd = forward_vec(facing_deg)
        eye = feet + Y * (0.9 * H) + fwd * (0.18 * H)
        target = eye + fwd * 20.0 + Y * (-0.5)
        cam = Camera(eye, target, fov=f_deg, resolver=resolver)
        info.update(distance=0.0)
    elif kind == "over_shoulder":
        fwd = forward_vec(facing_deg)
        O = feet + fwd * 3.2 if other_pos is None else _v(other_pos)
        S2 = (O - feet) * np.array([1, 0, 1])
        dist_os = max(float(np.linalg.norm(S2)), 0.5)
        u_dir = _unit(-S2)                                   # from listener toward speaker
        d_fill = framing_distance(P["rh"] * H, f_deg, fill)
        d_w = P["rw"] * H / (0.95 * 2 * th * aspect)
        d = max(d_fill, d_w) + 0.1 * H
        d = max(d, dist_os + 0.9 * H)                         # stay behind the listener
        right = np.array([-u_dir[2], 0.0, u_dir[0]])         # right of the view direction
        eye_xz = feet - u_dir * d + right * (0.5 * H)
        eye = np.array([eye_xz[0], feet[1] + 1.0 * H, eye_xz[2]])
        target = feet + Y * (P["cy"] * H) - right * (0.05 * H)  # speaker sits a bit right of centre
        cam = Camera(eye, target, fov=f_deg, resolver=resolver)
        info.update(distance=d, other=tuple(O))
    elif kind == "two_shot":
        B = feet + right_vec(facing_deg) * 3.5 if other_pos is None else _v(other_pos)
        M = (feet + B) / 2.0
        ab = (B - feet) * np.array([1, 0, 1])
        sep = float(np.linalg.norm(ab))
        u_dir = _unit(ab, (1, 0, 0))
        perp = np.array([u_dir[2], 0.0, -u_dir[0]])
        if perp[2] < 0:                                       # prefer the side with +Z (camera looks toward -Z)
            perp = -perp
        ext = P["rh"] * H * math.cos(math.radians(el)) + _footprint(P, H, el) * abs(math.sin(math.radians(el)))
        d_h = ext / (2 * fill * th)
        d_w = (sep + P["rw"] * H) / (0.9 * 2 * th * aspect)
        d = max(d_h, d_w) + 0.1 * H
        Cm = M + Y * (P["cy"] * H)
        eye = Cm + d * (math.cos(math.radians(el)) * perp + math.sin(math.radians(el)) * Y)
        target = Cm
        cam = Camera(eye, target, fov=f_deg, resolver=resolver)
        info.update(distance=d, other=tuple(B), separation=sep)
    else:
        ext = P["rh"] * H * math.cos(math.radians(el)) + _footprint(P, H, el) * abs(math.sin(math.radians(el)))
        d_h = ext / (2 * fill * th)
        d_w = P["rw"] * H / (0.95 * 2 * th * aspect)
        d = max(d_h, d_w) + _front_offset(kind, P, H, az, el)
        front = forward_vec(facing_deg + az)
        eye = C + d * (math.cos(math.radians(el)) * front + math.sin(math.radians(el)) * Y)
        if eye[1] < min_height:
            eye[1] = min_height
        target = C
        if kind == "top_down":
            cam_up = forward_vec(facing_deg)
        cam = Camera(eye, target, fov=f_deg, up=cam_up if cam_up is not None else (0, 1, 0), resolver=resolver)
        info.update(distance=d)

    if abs(screen_y - 0.5) > 1e-9 and kind != "pov":
        # aim lower/higher so the framed region's centre lands at screen_y (0=top .. 1=bottom)
        eye = cam._pos.eval(0)
        tgt = cam._tgt.eval(0)
        _, u, _ = _basis(eye, tgt, cam.up, 0.0)
        vis_h = 2.0 * float(np.linalg.norm(tgt - eye)) * th
        cam._tgt = Track(tgt - u * ((0.5 - screen_y) * vis_h))
    cam.info = info
    if follow:
        cam.follow(follow, t0=0.0, damping=damping)
    return cam


Camera.shot = staticmethod(shot)  # type: ignore[attr-defined]
