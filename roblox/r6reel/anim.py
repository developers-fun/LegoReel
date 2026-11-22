"""Clips, easing, pose blending and the per-character Animator timeline (deterministic)."""
from __future__ import annotations
import math, zlib, bisect
import numpy as np
from . import rig

JKEYS = ["root", "Neck", "Right Shoulder", "Left Shoulder", "Right Hip", "Left Hip"]
_JIDX = {k: i for i, k in enumerate(JKEYS)}

MASKS = {
    "arms": {"Right Shoulder", "Left Shoulder"}, "right_arm": {"Right Shoulder"}, "left_arm": {"Left Shoulder"},
    "head": {"Neck"}, "legs": {"Right Hip", "Left Hip"}, "upper": {"Neck", "Right Shoulder", "Left Shoulder"},
    "root": {"root"}, "lower": {"root", "Right Hip", "Left Hip"},
}


# ------------------------------------------------------------------ easing
def _bounce_out(t):
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1: return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1; return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1; return n1 * t * t + 0.9375
    t -= 2.625 / d1; return n1 * t * t + 0.984375


def _elastic_out(t):
    if t <= 0: return 0.0
    if t >= 1: return 1.0
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1


def _back_out(t, c1=1.70158):
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


EASINGS = {
    "linear": lambda t: t,
    "constant": lambda t: 1.0 if t >= 1 else 0.0,
    "cubic_in": lambda t: t ** 3,
    "cubic_out": lambda t: 1 - (1 - t) ** 3,
    "cubic_inout": lambda t: 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2,
    "elastic_out": _elastic_out,
    "bounce_out": _bounce_out,
    "back_out": _back_out,
    "back_in": lambda t: 2.70158 * t ** 3 - 1.70158 * t ** 2,
    "quad_out": lambda t: 1 - (1 - t) ** 2,
    "quad_in": lambda t: t * t,
    "sine_inout": lambda t: -(math.cos(math.pi * t) - 1) / 2,
    "smooth": lambda t: t * t * (3 - 2 * t),
}
# short aliases
for _a, _b in (("lin", "linear"), ("out", "cubic_out"), ("in", "cubic_in"), ("io", "cubic_inout"),
               ("back", "back_out"), ("bounce", "bounce_out"), ("elastic", "elastic_out"), ("step", "constant")):
    EASINGS[_a] = EASINGS[_b]


def ease(name, t):
    f = name if callable(name) else EASINGS[name]
    return f(min(1.0, max(0.0, t)))


linear = EASINGS["linear"]; constant = EASINGS["constant"]; cubic_in = EASINGS["cubic_in"]
cubic_out = EASINGS["cubic_out"]; cubic_inout = EASINGS["cubic_inout"]; elastic_out = _elastic_out
bounce_out = _bounce_out; back_out = _back_out


# ------------------------------------------------------------------ pose <-> arrays
def pose_to_arr(pose):
    rot = np.zeros((6, 3)); pos = np.zeros(3)
    r = pose.get("root") or {}
    if r.get("rot") is not None: rot[0] = r["rot"]
    if r.get("pos") is not None: pos[:] = r["pos"]
    for k in JKEYS[1:]:
        v = pose.get(k)
        if v is not None: rot[_JIDX[k]] = v
    return rot, pos


def arr_to_pose(rot, pos):
    p = {"root": {"pos": tuple(float(x) for x in pos), "rot": tuple(float(x) for x in rot[0])}}
    for k in JKEYS[1:]:
        p[k] = tuple(float(x) for x in rot[_JIDX[k]])
    return p


def neutral_pose():
    return arr_to_pose(np.zeros((6, 3)), np.zeros(3))


# ------------------------------------------------------------------ quaternions
def e2q(e):
    a, b, c = (math.radians(x) / 2 for x in e)
    qx = np.array([math.cos(a), math.sin(a), 0, 0]); qy = np.array([math.cos(b), 0, math.sin(b), 0])
    qz = np.array([math.cos(c), 0, 0, math.sin(c)])
    return qmul(qmul(qx, qy), qz)


def qmul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2,
                     w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])


def q2m(q):
    w, x, y, z = q / np.linalg.norm(q)
    m = np.eye(4)
    m[:3, :3] = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                 [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                 [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    return m


def q2e(q):
    return np.array(rig.matrix_to_euler(q2m(q)))


def slerp(a, b, w):
    d = float(np.dot(a, b))
    if d < 0: b = -b; d = -d
    if d > 0.9995:
        q = a + (b - a) * w
    else:
        th = math.acos(min(1.0, d)); s = math.sin(th)
        q = (math.sin((1 - w) * th) * a + math.sin(w * th) * b) / s
    return q / np.linalg.norm(q)


def _blend_rot(ea, eb, w):
    if w <= 0 or np.allclose(ea, eb): return np.array(ea, float)
    if w >= 1: return np.array(eb, float)
    return q2e(slerp(e2q(ea), e2q(eb), w))


def _blend_arr(ra, pa, rb, pb, w, joints=None):
    """Blend arrays; joints = set of indices (None -> all). Returns new (rot,pos)."""
    rot = ra.copy(); pos = pa.copy()
    for i in (range(6) if joints is None else joints):
        rot[i] = _blend_rot(ra[i], rb[i], w)
        if i == 0: pos = pa + (pb - pa) * w
    return rot, pos


def blend(a, b, w):
    """Blend two pose dicts: quaternion slerp for rotations, lerp for root pos."""
    ra, pa = pose_to_arr(a); rb, pb = pose_to_arr(b)
    return arr_to_pose(*_blend_arr(ra, pa, rb, pb, float(w)))


def _mask_idx(mask):
    if mask is None: return None
    if isinstance(mask, str): mask = MASKS[mask]
    return sorted(_JIDX[m] for m in mask)


def layer(base, overlay, mask=None, weight=1.0):
    """Overlay `overlay` onto `base` for the masked joints (names or MASKS key; None = all)."""
    ra, pa = pose_to_arr(base); rb, pb = pose_to_arr(overlay)
    return arr_to_pose(*_blend_arr(ra, pa, rb, pb, weight, _mask_idx(mask)))


def poses_equal(a, b, tol=1e-3):
    """Rotation-equivalent comparison (handles 0 vs 360)."""
    ra, pa = pose_to_arr(a); rb, pb = pose_to_arr(b)
    if np.abs(pa - pb).max() > tol: return False
    for i in range(6):
        if np.abs(rig.euler_to_matrix(*ra[i]) - rig.euler_to_matrix(*rb[i])).max() > tol: return False
    return True


def add_noise(pose, t, amount=1.0, seed=0):
    """Deterministic low-frequency life: small rotation wobble on neck/shoulders/root (degrees*amount)."""
    rng = np.random.RandomState(zlib.crc32(str(seed).encode()) & 0x7fffffff)
    rot, pos = pose_to_arr(pose)
    scale = {0: 0.6, 1: 1.4, 2: 1.0, 3: 1.0}
    for j, s in scale.items():
        for ax in range(3):
            f = rng.uniform(0.25, 0.9, 3); ph = rng.uniform(0, 6.28, 3)
            rot[j, ax] += amount * s * sum(math.sin(2 * math.pi * f[k] * t + ph[k]) for k in range(3)) / 3
    return arr_to_pose(rot, pos)


# ------------------------------------------------------------------ Clip
class Clip:
    """Keyframed pose animation. keyframes=[(t, pose_dict, easing)]; the easing of key i shapes the
    segment from key i-1 into key i (Roblox semantic). Interpolation is plain euler lerp so
    multi-turn spins work. loop clips wrap time; hold clips keep their last pose until overridden."""

    def __init__(self, name, duration, keyframes, loop=False, hold=False, ref_speed=None, face=None):
        self.name, self.duration, self.loop, self.hold = name, float(duration), bool(loop), bool(hold)
        self.ref_speed, self.face = ref_speed, face
        kf = sorted(((float(t), p, e) for t, p, e in keyframes), key=lambda k: k[0])
        if self.loop and self.duration > 0:  # guarantee a closing key == first key
            if kf[-1][0] < self.duration - 1e-9:
                kf.append((self.duration, kf[0][1], "linear"))
            else:
                kf[-1] = (self.duration, kf[0][1], kf[-1][2])
        self.keyframes = kf
        self._t = np.array([k[0] for k in kf])
        arrs = [pose_to_arr(k[1]) for k in kf]
        self._rot = np.array([a[0] for a in arrs]); self._pos = np.array([a[1] for a in arrs])
        self._ease = [k[2] for k in kf]

    def sample_arr(self, t, loop=None):
        lp = self.loop if loop is None else loop
        if lp and self.duration > 0: t = t % self.duration
        i = bisect.bisect_right(self._t, t)
        if i <= 0: return self._rot[0], self._pos[0]
        if i >= len(self._t): return self._rot[-1], self._pos[-1]
        t0, t1 = self._t[i - 1], self._t[i]
        a = (t - t0) / max(t1 - t0, 1e-9)
        e = ease(self._ease[i], a)
        return (self._rot[i - 1] + (self._rot[i] - self._rot[i - 1]) * e,
                self._pos[i - 1] + (self._pos[i] - self._pos[i - 1]) * e)

    def sample(self, t, loop=None) -> dict:
        return arr_to_pose(*self.sample_arr(t, loop))

    def __repr__(self):
        return f"Clip({self.name!r}, {self.duration:.2f}s, loop={self.loop}, keys={len(self.keyframes)})"


# ------------------------------------------------------------------ Animator
def _ramp(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class _Layer:
    __slots__ = ("clip", "at", "speed", "fade_in", "fade_out", "weight", "mask", "loop", "end", "prio", "seq", "face")

    def weight_at(self, t):
        if t < self.at or t >= self.end: return 0.0
        w = self.weight
        if self.fade_in > 0: w *= _ramp((t - self.at) / self.fade_in)
        if self.fade_out > 0 and self.end < 1e17: w *= _ramp((self.end - t) / self.fade_out)
        return w


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class Animator:
    """Per-character timeline. pose_at(t) is a pure function of t and the registered events."""

    GAITS = (("walk", 0.5, 9.0), ("jog", 9.0, 14.0), ("run", 14.0, 20.0), ("sprint_panic", 20.0, 1e9))

    def __init__(self, avatar, position=(0, 0, 0), facing_deg=0.0, base="idle", noise=0.5,
                 seed=None, ground_clamp=True):
        self.avatar = avatar
        self.start_pos = np.array(position, float)
        self.start_facing = float(facing_deg)
        self.base = base
        self.noise = float(noise)
        self.seed = avatar.name if seed is None else seed
        self.ground_clamp = ground_clamp
        self.resolver = None            # callable(name)->point | Animator
        self._layers: list[_Layer] = []
        self._moves = []                # (t0,t1,to,ease)
        self._turns = []                # (t, yaw_target, dur)
        self._looks = []                # (t0,t1,target,fade_in,fade_out)
        self._faces = []                # (t, name)
        self._seq = 0

    # ---- authoring
    def play(self, clip, at=0.0, speed=1.0, fade_in=0.1, fade_out=0.1, weight=1.0, mask=None, loop=None,
             until=None, face=None, _prio=1):
        if isinstance(clip, str):
            from . import clips as _c
            clip = _c.get(clip)
        lp = clip.loop if loop is None else bool(loop)
        L = _Layer()
        L.clip, L.at, L.speed, L.fade_in, L.fade_out = clip, float(at), float(speed), float(fade_in), float(fade_out)
        L.weight, L.mask, L.loop, L.prio = float(weight), _mask_idx(mask), lp, _prio
        if until is not None: L.end = float(until)
        elif lp or clip.hold: L.end = 1e18
        else: L.end = at + clip.duration / max(speed, 1e-6)
        L.seq = self._seq; self._seq += 1
        L.face = clip.face if face is True else (face if isinstance(face, str) else None)
        self._layers.append(L)
        if L.face: self.face(L.face, at)
        return self

    def stop(self, t, fade=0.1):
        """End every still-open layer at time t."""
        for L in self._layers:
            if L.end > t and L.at < t: L.end = t + fade; L.fade_out = max(L.fade_out, fade)
        return self

    def move_to(self, pos, t0, t1, ease="cubic_inout", face=True, gait="auto"):
        pos = np.array(pos, float)
        cur = self.position_at(t0)
        self._moves.append((float(t0), float(t1), pos, ease))
        d = pos - cur; d[1] = 0
        dist = float(np.hypot(d[0], d[2]))
        if face is True and dist > 0.05:
            self._turns.append((float(t0), math.degrees(math.atan2(-d[0], -d[2])), min(0.3, 0.5 * (t1 - t0))))
        elif isinstance(face, (int, float)) and not isinstance(face, bool):
            self._turns.append((float(t1), float(face), 0.25))
        if gait and dist > 0.05 and t1 > t0:
            v = dist / (t1 - t0)
            name = gait
            if gait == "auto":
                name = next((n for n, lo, hi in self.GAITS if lo <= v < hi), None)
            if name:
                from . import clips as _c
                c = _c.get(name)
                sp = min(1.7, max(0.6, v / c.ref_speed)) if c.ref_speed else 1.0
                self.play(c, at=t0, speed=sp, fade_in=0.12, fade_out=0.15, until=t1, _prio=0)
        return self

    def face_dir(self, deg, t, dur=0.25):
        self._turns.append((float(t), float(deg), float(dur))); return self

    def look_at(self, target, t0, t1, fade_in=0.12, fade_out=0.2):
        self._looks.append((float(t0), float(t1), target, fade_in, fade_out)); return self

    def face(self, name, t):
        self._faces.append((float(t), name)); self._faces.sort(key=lambda f: f[0]); return self

    # ---- queries
    def position_at(self, t):
        cur = self.start_pos.copy()
        for t0, t1, to, e in sorted(self._moves, key=lambda m: m[0]):
            if t <= t0: break
            if t >= t1: cur = to.copy()
            else: cur = cur + (to - cur) * ease(e, (t - t0) / (t1 - t0)); break
        return cur

    def facing_at(self, t):
        cur = self.start_facing
        for tt, tgt, dur in sorted(self._turns, key=lambda m: m[0]):
            if t <= tt: break
            delta = _wrap180(tgt - cur)
            if dur <= 0 or t >= tt + dur: cur = cur + delta
            else: cur = cur + delta * ease("cubic_out", (t - tt) / dur)
        return cur

    def face_at(self, t):
        name = self.avatar.face_name
        for ft, fn in self._faces:
            if ft <= t: name = fn
            else: break
        return name

    def _frame(self, t):
        m = rig.yaw_matrix(self.facing_at(t)); m[:3, 3] = self.position_at(t); return m

    def _target_point(self, tgt, t):
        if callable(tgt) and not isinstance(tgt, Animator): tgt = tgt(t)
        if isinstance(tgt, str):
            if self.resolver is None: return None
            tgt = self.resolver(tgt)
        if isinstance(tgt, Animator): return tgt.position_at(t) + np.array([0, 4.5, 0])
        return None if tgt is None else np.asarray(tgt, float)

    def _look_quat(self, tgt, t):
        p = self._target_point(tgt, t)
        if p is None: return None
        fr = self._frame(t)
        local = np.linalg.inv(fr) @ np.array([p[0], p[1], p[2], 1.0])
        d = local[:3] - np.array([0, 4.5, 0]); n = np.linalg.norm(d)
        if n < 1e-6: return None
        a, b, c = d / n
        psi = math.degrees(math.asin(max(-1.0, min(1.0, -a))))
        phi = math.degrees(math.atan2(b, -c))
        if phi > 90: phi = 180 - phi
        if phi < -90: phi = -180 - phi
        psi = max(-75.0, min(75.0, psi)); phi = max(-35.0, min(45.0, phi))
        return e2q((phi, psi, 0))

    def pose_at(self, t):
        """-> (pose_dict, root_cf). Pure in t."""
        rot = np.zeros((6, 3)); pos = np.zeros(3)
        if self.base:
            from . import clips as _c
            rot, pos = [x.copy() for x in _c.get(self.base).sample_arr(t, True)]
        for L in sorted(self._layers, key=lambda L: (L.prio, L.at, L.seq)):
            w = L.weight_at(t)
            if w <= 0: continue
            r2, p2 = L.clip.sample_arr((t - L.at) * L.speed, L.loop)
            rot, pos = _blend_arr(rot, pos, r2, p2, min(1.0, w), L.mask)
        for t0, t1, tgt, fi, fo in self._looks:
            if t < t0 - 1e-9 or t > t1 + fo: continue
            w = _ramp((t - t0) / fi) if fi > 0 else 1.0
            if t > t1: w *= _ramp(1 - (t - t1) / fo) if fo > 0 else 0.0
            q = self._look_quat(tgt, t)
            if q is None or w <= 0: continue
            ql = slerp(np.array([1.0, 0, 0, 0]), q, w)
            rot[1] = q2e(qmul(ql, e2q(rot[1])))
        pose = arr_to_pose(rot, pos)
        if self.noise > 0: pose = add_noise(pose, t, self.noise, self.seed)
        if self.ground_clamp:
            lift = rig.ground_lift(pose)
            if lift > 1e-6: pose = rig.with_root_offset(pose, lift)
        return pose, self._frame(t)

    def draw_items(self, t):
        pose, cf = self.pose_at(t)
        return self.avatar.draw_items(pose, cf, face=self.face_at(t))
