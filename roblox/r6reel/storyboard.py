"""Storyboard sheet: key frames of a Scene with motion annotations, descriptions and sanity checks.

>>> sb = Storyboard(scene, max_panels=12, cols=4, tile_h=480)
>>> sb.panels()            # list[Panel] (time, text, warnings)
>>> sb.save("out/storyboard.png")   # + storyboard.md + storyboard.json

Overlays are drawn with PIL over ``Scene.render_frame`` using the same view/projection as the renderer.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, asdict
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import clips as CL
from . import rig
from .anim import Animator, ease as _ease
from .util import look_at, perspective

PALETTE = [(30, 136, 229), (251, 140, 0), (46, 160, 67), (216, 27, 96), (142, 36, 170), (0, 172, 193)]
WHITE, RED, DARK = (255, 255, 255), (222, 40, 40), (24, 26, 32)
GAIT_CLIPS = ("walk", "jog", "run", "sprint_panic", "sneak")
STEP_GAITS = GAIT_CLIPS
IDLE_CLIPS = ("idle", "idle_bored", "breathe")
AIR_CLIPS = ("jump", "fall", "ragdoll_fall", "faint", "land", "climb", "swim", "stand_up", "spin")
EMPHASIS = ("shock", "jump", "fall", "ragdoll_fall", "faint", "scared", "kick", "throw", "spin", "push", "hug",
            "angry", "cry", "laugh", "cheer", "facepalm", "flex", "catch")
VERBS = {
    "wave": "waves", "shock": "recoils in shock", "laugh": "laughs", "cry": "cries", "angry": "gets angry",
    "point": "points", "point_up": "points up", "jump": "jumps", "fall": "falls", "ragdoll_fall": "ragdolls down",
    "faint": "faints", "talk": "talks", "cheer": "cheers", "clap": "claps", "bow": "bows", "nod": "nods",
    "shake_head": "shakes head", "shrug": "shrugs", "think": "thinks", "scared": "cowers in fear",
    "facepalm": "facepalms", "throw": "throws", "kick": "kicks", "push": "pushes", "hug": "hugs", "catch": "catches",
    "crouch": "crouches", "sit": "sits down", "sit_desk": "sits at a desk", "sit_slouch": "slouches in a seat",
    "stand_up": "stands up", "spin": "spins", "dance_1": "dances", "dance_2": "dances", "dance_3": "dances",
    "salute": "salutes", "flex": "flexes", "cross_arms": "crosses arms", "hands_on_hips": "hands on hips",
    "lean_in": "leans in", "look_around": "looks around", "land": "lands", "climb": "climbs", "swim": "swims",
    "sleep_hug": "sleeps", "tie_shoes": "ties shoes", "kick_ball": "kicks",
}
GAIT_VERB = {"walk": ("walks", "walked"), "jog": ("jogs", "jogged"), "run": ("runs", "ran"),
             "sprint_panic": ("sprints in panic", "sprinted"), "sneak": ("sneaks", "sneaked")}
LEGEND = (("arrow", "movement"), ("feet", "walking"), ("dashed", "gesture"), ("bang", "check this"))
# right foot outline in (lateral, forward) studs; wider toe, narrow heel and arch
_SHOE = [(-0.11, -0.5), (0.11, -0.5), (0.18, -0.38), (0.2, -0.1), (0.23, 0.15), (0.27, 0.35), (0.2, 0.47),
         (0.0, 0.51), (-0.18, 0.47), (-0.27, 0.33), (-0.2, 0.12), (-0.14, -0.1), (-0.15, -0.38)]
_CHEVRON = [(0, 1.8), (0.85, 0.95), (0.85, 0.45), (0, 1.3), (-0.85, 0.45), (-0.85, 0.95)]


# ------------------------------------------------------------------------------------------ data
@dataclass
class Panel:
    index: int
    t: float
    shot_index: int
    kind: str
    title: str
    lines: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    subject: str = ""


@dataclass
class _Seg:
    """One move_to segment, resolved against the animator."""
    who: str
    t0: float
    t1: float
    a: np.ndarray
    b: np.ndarray
    gait: str | None
    explicit: bool
    ease: str

    @property
    def dist(self) -> float:
        return float(np.hypot(*(self.b - self.a)[[0, 2]]))

    @property
    def speed(self) -> float:
        return self.dist / max(self.t1 - self.t0, 1e-6)

    @property
    def heading(self) -> float:
        d = self.b - self.a
        return math.degrees(math.atan2(-d[0], -d[2]))

    def at(self, u: float) -> np.ndarray:
        return self.a + (self.b - self.a) * u


class _Proj:
    """World -> pixel projection using the renderer's own look_at / perspective."""

    NEAR = 0.1

    def __init__(self, cs, w: int, h: int):
        self.w, self.h = w, h
        self.V = look_at(cs.eye, cs.target, cs.up, cs.roll)
        self.VP = perspective(cs.fov_y, w / h, 0.1, 2000.0) @ self.V

    def project(self, pts):
        """-> (N,2) pixels, (N,) view z (negative = in front of the camera)."""
        p = np.atleast_2d(np.asarray(pts, float))
        ph = np.hstack([p[:, :3], np.ones((len(p), 1))])
        vz = (self.V @ ph.T)[2]
        c = (self.VP @ ph.T).T
        with np.errstate(all="ignore"):
            ndc = c[:, :2] / c[:, 3:4]
        px = np.stack([(ndc[:, 0] * 0.5 + 0.5) * self.w, (1 - (ndc[:, 1] * 0.5 + 0.5)) * self.h], 1)
        return px, vz

    def pt(self, p):
        px, vz = self.project(p)
        return (float(px[0, 0]), float(px[0, 1])), float(vz[0])

    def runs(self, pts) -> list:
        """Visible runs of a world polyline (points behind the near plane are dropped)."""
        px, vz = self.project(pts)
        out, cur = [], []
        for (x, y), z in zip(px, vz):
            if z < -self.NEAR - 1e-6 and np.isfinite(x) and np.isfinite(y):
                cur.append((float(np.clip(x, -2e4, 2e4)), float(np.clip(y, -2e4, 2e4))))
            elif cur:
                out.append(cur)
                cur = []
        if cur:
            out.append(cur)
        return out

    def inside(self, p, margin=0.0) -> bool:
        (x, y), z = self.pt(p)
        return z < -self.NEAR and -margin <= x <= self.w + margin and -margin <= y <= self.h + margin

    def ground_dirs(self):
        """Camera (right, forward) unit vectors flattened to the ground plane (x, z)."""
        r, f = self.V[0, :3][[0, 2]], -self.V[2, :3][[0, 2]]
        nr, nf = np.linalg.norm(r), np.linalg.norm(f)
        return (r / nr if nr > 1e-6 else r), (f / nf if nf > 1e-6 else f)


class _Ctx:
    """Everything about one panel needed for text, checks and drawing."""

    def __init__(self):
        self.__dict__.update(t=0.0, win=0.0, i=0, shot=None, cs=None, proj=None, vis=[], segs={}, body={},
                            onscreen=set(), subject=None)


# ------------------------------------------------------------------------------------------ small helpers
@lru_cache(maxsize=64)
def _font(size: int, bold: bool = False):
    names = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf") if bold else ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
    for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/Library/Fonts", "C:/Windows/Fonts"):
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return ImageFont.truetype(p, size)
    try:
        from .captions import _font_path
        p = _font_path()
        if p:
            return ImageFont.truetype(p, size)
    except Exception:                                   # noqa: BLE001
        pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _fmt(d: float) -> str:
    return f"{d:.0f}" if d >= 9.5 or abs(d - round(d)) < 0.05 else f"{d:.1f}"


def _wrap(text: str, font, width: float) -> list:
    out, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if cur and font.getlength(trial) > width:
            out.append(cur)
            cur = word
        else:
            cur = trial
    return out + [cur] if cur else out or [""]


def _poly_len(pts) -> float:
    return float(sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])))


def _trim(pts, dist):
    """Polyline without its last `dist` pixels."""
    pts = list(pts)
    while len(pts) > 2 and math.hypot(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]) <= dist:
        dist -= math.hypot(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
        pts.pop()
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    n = math.hypot(x1 - x0, y1 - y0)
    if n > 1e-6 and dist < n:
        f = (n - dist) / n
        pts[-1] = (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
    return pts


def _dashes(pts, dash, gap):
    out, cur, on, left = [], [pts[0]], True, dash
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = math.hypot(x1 - x0, y1 - y0)
        pos = 0.0
        while n - pos > left:
            pos += left
            p = (x0 + (x1 - x0) * pos / n, y0 + (y1 - y0) * pos / n)
            if on:
                out.append(cur + [p])
            cur, on, left = [p], not on, (gap if on else dash)
        left -= n - pos
        if on:
            cur.append((x1, y1))
    if on and len(cur) > 1:
        out.append(cur)
    return out


def _smooth(pts, n=6):
    """Catmull-Rom through the points."""
    if len(pts) < 3:
        return list(pts)
    p = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(p) - 2):
        for s in range(n):
            u = s / n
            out.append(tuple(0.5 * (2 * p[i][c] + (-p[i - 1][c] + p[i + 1][c]) * u
                                    + (2 * p[i - 1][c] - 5 * p[i][c] + 4 * p[i + 1][c] - p[i + 2][c]) * u * u
                                    + (-p[i - 1][c] + 3 * p[i][c] - 3 * p[i + 1][c] + p[i + 2][c]) * u ** 3)
                            for c in (0, 1)))
    return out + [pts[-1]]


def _fwd(f_deg: float) -> np.ndarray:
    a = math.radians(f_deg)
    return np.array([-math.sin(a), 0.0, -math.cos(a)])


def _right(f_deg: float) -> np.ndarray:
    a = math.radians(f_deg)
    return np.array([math.cos(a), 0.0, -math.sin(a)])


def _wrap180(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


# ------------------------------------------------------------------------------------------ drawing canvas
class _Canvas:
    """2x supersampled RGBA layer with outlined strokes, pills and label placement (all coords in 1x pixels)."""
    S = 2

    def __init__(self, w: int, h: int, k: float):
        self.w, self.h, self.k = w, h, k
        self.im = Image.new("RGBA", (w * self.S, h * self.S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
        self.taken: list = []

    def P(self, pts):
        return [(x * self.S, y * self.S) for x, y in pts]

    def result(self):
        return self.im.resize((self.w, self.h), Image.LANCZOS)

    def stroke(self, pts, col, width=4.0, alpha=255, dashed=False, head=False, outline=True, caps=True):
        pts = [(float(x), float(y)) for x, y in pts if np.isfinite(x) and np.isfinite(y)]
        if len(pts) < 2 or _poly_len(pts) < 1.0:
            return
        k = self.k
        hl = max(7.0, width * 2.6) if head else 0.0
        shaft = _trim(pts, hl * 0.7) if head and _poly_len(pts) > hl else pts
        passes = ([(WHITE, width + max(2.0, 3 * k), 1.4)] if outline else []) + [(col, width, 1.0)]
        for c, wd, hs in passes:
            fill = tuple(c) + (alpha,)
            for seg in (_dashes(shaft, 8 * k, 5 * k) if dashed else [shaft]):
                if len(seg) >= 2:
                    self.d.line(self.P(seg), fill=fill, width=max(1, int(round(wd * self.S))), joint="curve")
                    if caps:
                        for x, y in (seg[0], seg[-1]):
                            r = wd / 2 * self.S
                            self.d.ellipse([x * self.S - r, y * self.S - r, x * self.S + r, y * self.S + r], fill=fill)
            if head:
                self._head(pts, hl, hs, fill)

    def _head(self, pts, hl, scale, fill):
        tip = pts[-1]
        back = tip
        for p in reversed(pts[:-1]):
            back = p
            if math.hypot(tip[0] - p[0], tip[1] - p[1]) >= hl * 0.6:
                break
        dx, dy = tip[0] - back[0], tip[1] - back[1]
        n = math.hypot(dx, dy) or 1.0
        dx, dy = dx / n, dy / n
        bx, by = tip[0] - dx * hl, tip[1] - dy * hl
        hw = hl * 0.55
        tri = [tip, (bx - dy * hw, by + dx * hw), (bx + dy * hw, by - dx * hw)]
        cx, cy = sum(p[0] for p in tri) / 3, sum(p[1] for p in tri) / 3
        tri = [(cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in tri]
        self.d.polygon(self.P(tri), fill=fill)

    def poly(self, pts, col, alpha=255, edge=None):
        self.d.polygon(self.P(pts), fill=tuple(col) + (alpha,),
                       outline=(tuple(edge) + (alpha,)) if edge else None, width=self.S if edge else 1)

    def text_size(self, text, size, bold=True):
        f = _font(int(round(size * self.S)), bold)
        b = f.getbbox(text)
        return f.getlength(text) / self.S, (b[3] - b[1]) / self.S

    def text(self, xy, text, size, fill=WHITE, bold=True, anchor="mm", stroke=None):
        f = _font(int(round(size * self.S)), bold)
        kw = dict(stroke_width=int(stroke[1] * self.S), stroke_fill=stroke[0]) if stroke else {}
        self.d.text((xy[0] * self.S, xy[1] * self.S), text, font=f, fill=tuple(fill) + (255,), anchor=anchor, **kw)

    def reserve(self, rect):
        self.taken.append(tuple(rect))

    def fit(self, w, h, cx, cy, margin=2.0):
        """Rect (x0,y0,x1,y1) of size w*h near (cx,cy) that avoids reserved rects and stays in the frame."""
        offs = [(0, 0), (0, -1), (0, 1), (1, 0), (-1, 0), (1, -1), (-1, -1), (1, 1), (-1, 1), (0, -2), (0, 2),
                (2, 0), (-2, 0), (0, -3), (0, 3)]
        best, bh = None, 0
        for ox, oy in offs:
            x = min(max(cx + ox * (w + 3) * 0.6 - w / 2, margin), self.w - w - margin)
            y = min(max(cy + oy * (h + 3) - h / 2, margin), self.h - h - margin)
            r = (x, y, x + w, y + h)
            hit = sum(1 for t in self.taken if r[0] < t[2] + 2 and r[2] > t[0] - 2 and r[1] < t[3] + 2 and r[3] > t[1] - 2)
            if hit == 0:
                best, bh = r, 0
                break
            if best is None or hit < bh:
                best, bh = r, hit
        self.taken.append(best)
        return best

    def pill(self, cx, cy, text, fill, size=11.0, fg=WHITE, alpha=255, place=True):
        k = self.k
        tw, _ = self.text_size(text, size)
        w, h = tw + 9 * k, size * 1.55
        r = self.fit(w, h, cx, cy) if place else (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        self.d.rounded_rectangle([c * self.S for c in r], radius=h / 2 * self.S, fill=tuple(fill) + (alpha,),
                                 outline=(255, 255, 255, 255), width=int(1.5 * self.S))
        self.text(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2 - 0.5), text, size, fg)
        return r

    def circle(self, cx, cy, r, fill, outline=WHITE, width=1.5):
        S = self.S
        self.d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=tuple(fill) + (255,),
                       outline=tuple(outline) + (255,), width=int(width * S))


# ------------------------------------------------------------------------------------------ camera glyphs
def _glyph(cv: _Canvas, kind: str, x: float, y: float, s: float, sign: float = 1.0):
    """Camera-move icon in a dark rounded box at (x, y) size s."""
    k = cv.k
    cv.d.rounded_rectangle([x * cv.S, y * cv.S, (x + s) * cv.S, (y + s) * cv.S], radius=6 * k * cv.S,
                           fill=(18, 20, 26, 215), outline=(255, 255, 255, 200), width=cv.S)
    u = s / 40.0
    wd = max(1.6, 2.0 * u)
    P = lambda a, b: (x + a * u, y + b * u)                                    # noqa: E731
    st = lambda pts, head=False: cv.stroke([P(*p) for p in pts], WHITE, wd, head=head, outline=False)  # noqa: E731
    if kind in ("push_in", "dolly_zoom"):
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            st([(20 + sx * 15, 20 + sy * 15), (20 + sx * 6, 20 + sy * 6)], True)
    elif kind == "pull_out":
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            st([(20 + sx * 6, 20 + sy * 6), (20 + sx * 15, 20 + sy * 15)], True)
    elif kind == "whip_pan":
        st([(6, 20), (34, 20)] if sign >= 0 else [(34, 20), (6, 20)], True)
        st([(8, 14), (20, 14)] if sign >= 0 else [(32, 14), (20, 14)])
        st([(8, 26), (20, 26)] if sign >= 0 else [(32, 26), (20, 26)])
    elif kind == "orbit":
        a = np.radians(np.linspace(200, 20, 18) if sign >= 0 else np.linspace(-20, 160, 18))
        st([(20 + 13 * math.cos(v), 22 - 11 * math.sin(v)) for v in a], True)
        cv.circle(*P(20, 22), 2 * u, WHITE, outline=WHITE, width=0.5)
    elif kind in ("crane", "low_angle"):
        st([(20, 33), (20, 7)] if sign >= 0 else [(20, 7), (20, 33)], True)
        st([(12, 33), (28, 33)])
    elif kind in ("shake", "drift"):
        amp = 4.0 if kind == "shake" else 7.0
        for yy in (12, 20, 28):
            st([(6 + i * 2.8, yy + amp * math.sin(i * 0.9 + yy)) for i in range(13)])
    elif kind == "dutch":
        ang = math.radians(15 * (1 if sign >= 0 else -1))
        c, sn = math.cos(ang), math.sin(ang)
        box = [(20 + c * px - sn * py, 20 + sn * px + c * py) for px, py in ((-11, -15), (11, -15), (11, 15), (-11, 15), (-11, -15))]
        st(box)
    elif kind in ("follow", "look_at"):
        st([(5, 12), (33, 12)], True)
        st([(11, 22), (27, 22), (27, 33), (11, 33), (11, 22)])
        st([(27, 25), (33, 22), (33, 33), (27, 30)])
    else:                                                                       # static / locked
        st([(13, 20), (13, 13), (16, 9), (24, 9), (27, 13), (27, 20)])
        st([(10, 20), (30, 20), (30, 33), (10, 33), (10, 20)])


# ------------------------------------------------------------------------------------------ Storyboard
class Storyboard:
    """Key-frame storyboard of a Scene. See module docstring."""

    def __init__(self, scene, max_panels=12, cols=4, tile_h=480, minimap=True, captions=False, times=None):
        scene._ensure_built()
        self.scene = scene
        self.max_panels, self.cols, self.tile_h = int(max_panels), max(1, int(cols)), int(tile_h)
        self.minimap, self.captions = bool(minimap), bool(captions)
        self.times = sorted(float(t) for t in times) if times else None
        self.h = self.tile_h
        self.w = int(round(self.h * scene.width / scene.height / 2)) * 2
        self.k = max(self.h / 480.0, 0.35)
        self.names = [c["name"] for c in scene.characters]
        self.colors = {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(self.names)}
        self._segs = self._build_segments()
        self._panels: list | None = None
        self._ctx: dict = {}
        self._tiles: dict = {}

    # ---------------------------------------------------------------- segments / helpers
    def _an(self, name) -> Animator:
        return self.scene._animators[name]

    def _build_segments(self) -> dict:
        out = {n: [] for n in self.names}
        for a in self.scene.actions:
            if a.get("type") != "move_to" or a["character"] not in out:
                continue
            t0, t1 = float(a["t0"]), float(a["t1"])
            if t1 - t0 < 0.01:
                continue                                                          # `place` teleports
            an = self._an(a["character"])
            seg = _Seg(a["character"], t0, t1, an.position_at(t0), np.array(a["pos"], float), None, False,
                       a.get("ease") or "cubic_inout")
            if seg.dist < 0.3:
                continue
            g = a.get("gait", "auto")
            if g in (None, False):
                seg.explicit = True
            elif g == "auto":
                seg.gait = next((n for n, lo, hi in Animator.GAITS if lo <= seg.speed < hi), None)
            else:
                seg.gait, seg.explicit = str(g), True
            out[a["character"]].append(seg)
        return out

    def _scale(self, name) -> float:
        return float(self._an(name).avatar.scale)

    def _body(self, name, t):
        an = self._an(name)
        pose, cf = an.pose_at(t)
        S = np.diag([an.avatar.scale] * 3 + [1.0])
        return an.position_at(t), rig.part_models(pose, cf @ S), pose, cf @ S

    def _subject(self, shot):
        s = shot.subject
        if s is None:
            s = self.names[0] if self.names else None
        if isinstance(s, str) and s.startswith("prop:"):
            return "prop", s[5:]
        if isinstance(s, str) and s in self._an_names():
            return "char", s
        return "point", None

    def _an_names(self):
        return self.scene._animators

    def _subject_point(self, shot, t):
        kind, nm = self._subject(shot)
        if kind == "char":
            return self.scene._resolve_point(nm, t)
        if kind == "prop":
            return np.asarray(self.scene._prop_state(nm, t)[0], float)
        s = shot.subject
        return np.asarray(s, float) if isinstance(s, (list, tuple)) and len(s) == 3 else None

    def _active_layers(self, name, t0, t1, names=None, exclude=()):
        out = []
        for L in self._an(name)._layers:
            if L.at < t1 and L.end > t0 and L.clip.name not in exclude and (names is None or L.clip.name in names):
                out.append(L)
        return out

    # ---------------------------------------------------------------- key frame selection
    def _candidates(self) -> list:
        sc, D = self.scene, self.scene.duration
        multi = len(self.names) > 1
        out: list = []

        def add(t, score, reason, must=False):
            out.append((float(min(max(t, 0.0), max(D - 0.03, 0.0))), float(score), reason, must))

        for s in sc.timeline.shots:
            d = s.t1 - s.t0
            trs = [x.get("type", "cut") if isinstance(x, dict) else str(x)
                   for x in (s.transition if isinstance(s.transition, list) else [s.transition] if s.transition else [])]
            trs = [x for x in trs if x != "cut"]
            add(min(s.t0 + 0.15, s.t1 - 0.05), 100 + (25 if trs else 0) + min(10.0, d), "shot start"
                + (f" ({'+'.join(trs)})" if trs else ""), must=d > 0.6)
        tag = lambda n: f" ({n})" if multi else ""                                  # noqa: E731
        for a in sc.actions:
            ty, who = a.get("type"), a.get("character")
            try:
                if ty == "play" and a["clip"] not in GAIT_CLIPS + IDLE_CLIPS:
                    clip = CL.get(a["clip"])
                    sp = float(a.get("speed") or 1.0)
                    dur = clip.duration / max(sp, 1e-6)
                    until = a.get("until")
                    emph = 15 if a["clip"] in EMPHASIS else 0
                    add(a["t"] + 0.12, 40 + emph, f"{a['clip']} starts{tag(who)}")
                    if not clip.loop:
                        pk = a["t"] + 0.35 * dur
                        if until is not None:
                            pk = min(pk, float(until) - 0.05)
                        add(pk, 70 + emph, f"{a['clip']} clip peaks{tag(who)}")
                elif ty == "turn" and abs(float(a["deg"])) >= 45:
                    add(a["t"] + float(a.get("dur", 0.25)) * 0.8, 50, f"turns {a['deg']:.0f} deg{tag(who)}")
            except Exception:                                                       # noqa: BLE001
                continue
        for who, segs in self._segs.items():
            for s in segs:
                g = s.gait or "move"
                add(s.t0 + 0.08, 50, f"{g} starts{tag(who)}")
                add(s.t1 - 0.03, 45, f"{g} arrives{tag(who)}")
                if s.t1 - s.t0 > 1.5:
                    add((s.t0 + s.t1) / 2, 40, f"mid-{g}{tag(who)}")
        for who in self.names:
            for ft, fn in self._an(who)._faces:
                add(ft + 0.1, 55, f"face {fn}{tag(who)}")
        for tr, _c in sc._tracks:
            if tr.words:
                add(tr.words[0][1] + 0.05, 45, 'caption starts: "' + " ".join(w[0] for w in tr.words[:4])[:28] + '"')
                for prev, w in zip(tr.words, tr.words[1:]):
                    if prev[0].rstrip()[-1:] in ".?!":
                        add(w[1] + 0.05, 30, "caption phrase")
        for p in sc.props:
            for key in p.get("keys") or []:
                add(key["t"] + 0.05, 35, f"prop {p['name']} moves")
        return out

    def _select(self) -> list:
        """-> sorted [(t, [reasons])]."""
        if self.times is not None:
            return [(t, ["requested time"]) for t in self.times]
        cands = self._candidates()
        tl = self.scene.timeline
        order = sorted(cands, key=lambda c: (-c[1], c[0]))
        chosen: list = []                                           # (t, score, reason)

        def free(t):
            return all(abs(t - c[0]) >= 0.4 for c in chosen)
        must = sorted((c for c in order if c[3]), key=lambda c: -c[1])[: self.max_panels]
        for c in must:
            if free(c[0]):
                chosen.append(c[:3])
        for c in order:
            if len(chosen) >= self.max_panels:
                break
            if not c[3] and free(c[0]):
                chosen.append(c[:3])
        chosen.sort(key=lambda c: c[0])
        res = [(c[0], [c[2]]) for c in chosen]
        for c in cands:                                               # fold near-duplicates into reasons
            for t, rs in res:
                if (t, c[2]) != (c[0], c[2]) and abs(t - c[0]) < 0.4 and c[2] not in rs and len(rs) < 4 \
                        and tl.shot_index(t) == tl.shot_index(c[0]):
                    rs.append(c[2])
                    break
        return res

    # ---------------------------------------------------------------- panels
    def panels(self) -> list:
        if self._panels is not None:
            return self._panels
        sel = self._select()
        D = self.scene.duration
        out = []
        for i, (t, reasons) in enumerate(sel):
            nxt = sel[i + 1][0] if i + 1 < len(sel) else max(D, t + 0.6)
            ctx = self._make_ctx(i, t, nxt)
            title, lines = self._describe(ctx, reasons)
            p = Panel(i + 1, round(t, 3), ctx.i, ctx.shot.kind, title, lines, [], reasons,
                      ctx.subject[1] or "" if ctx.subject else "")
            p.warnings = self._checks(ctx)
            self._ctx[i] = ctx
            out.append(p)
        self._panels = out
        return out

    def _make_ctx(self, idx, t, nxt) -> _Ctx:
        sc = self.scene
        c = _Ctx()
        c.t, c.win = t, min(nxt, t + 3.0)
        c.i = sc.timeline.shot_index(t)
        c.shot = sc.timeline.shots[c.i]
        c.cs = sc.frame(t)[1]
        c.proj = _Proj(c.cs, self.w, self.h)
        c.vis = [s["name"] for s in sc.characters if sc._char_visible(s, t, c.shot.set)]
        c.subject = self._subject(c.shot)
        for n in c.vis:
            c.segs[n] = [s for s in self._segs[n] if s.t0 < c.win and s.t1 > t - 1.5]
            try:
                c.body[n] = self._body(n, t)
                c.onscreen_pts = None
                if any(c.proj.inside(m[:3, 3]) for m in c.body[n][1].values()) or c.proj.inside(c.body[n][0]):
                    c.onscreen.add(n)
            except Exception:                                                       # noqa: BLE001
                pass
        return c

    # ---------------------------------------------------------------- text
    def _dir_word(self, ctx, heading_deg) -> str:
        r, f = ctx.proj.ground_dirs()
        h = _fwd(heading_deg)[[0, 2]]
        a, b = float(h @ f), float(h @ r)
        ang = math.degrees(math.atan2(b, a))
        side = "right" if b > 0 else "left"
        if abs(ang) <= 22:
            return "away from camera"
        if abs(ang) >= 158:
            return "toward camera"
        if 68 <= abs(ang) <= 112:
            return f"to the {side}"
        return ("away, " if abs(ang) < 90 else "toward camera, ") + side

    def _move_text(self, ctx, s: _Seg) -> str:
        verb, past = GAIT_VERB.get(s.gait, ("moves", "moved")) if s.gait else ("glides", "glided")
        d = f"{_fmt(s.dist)} studs {self._dir_word(ctx, s.heading)}"
        if ctx.t >= s.t1 - 0.1:
            return f"arrives ({past} {d})"
        return f"{verb} {d} ({s.t1 - s.t0:.1f} s)"

    def _cam_info(self, shot, t):
        """-> (text parts, [(glyph kind, sign)])."""
        parts, glyphs = [], []
        for m in shot.moves:
            ty = m.get("type")
            at = shot.t0 + float(m.get("at", 0.0))
            end = at + float(m["dur"]) if m.get("dur") is not None and ty != "dutch" else shot.t1
            if not (at - 0.02 <= t <= end + 0.02):
                continue
            sign = 1.0
            if ty in ("push_in", "pull_out"):
                txt = f"{'push in' if ty == 'push_in' else 'pull out'} " + (
                    f"{float(m['amount']) * 100:.0f}%" if m.get("amount") is not None
                    else f"{float(m.get('rate', 0.06)) * 100:.0f}%/s")
            elif ty == "whip_pan":
                sign = 1.0 if float(m.get("degrees", 60)) >= 0 else -1.0
                txt = f"whip pan {abs(float(m.get('degrees', 60))):.0f} deg"
            elif ty == "orbit":
                sign = 1.0 if float(m.get("degrees", 30)) >= 0 else -1.0
                txt = f"orbit {abs(float(m.get('degrees', 30))):.0f} deg"
            elif ty == "crane":
                sign = 1.0 if float(m.get("dy", 4)) >= 0 else -1.0
                txt = f"crane {'up' if sign > 0 else 'down'} {abs(float(m.get('dy', 4))):.0f}"
            elif ty == "dutch":
                sign = 1.0 if float(m.get("degrees", 4)) >= 0 else -1.0
                txt = f"dutch {float(m.get('degrees', 4)):+.0f} deg"
            else:
                txt = str(ty).replace("_", " ")
            parts.append(txt)
            glyphs.append((ty, sign))
        if shot.follow:
            parts.append("follows subject")
            glyphs.append(("follow", 1.0))
        if shot.camera:
            parts.append("manual camera")
        if not glyphs:
            glyphs = [("static", 1.0)]
        order = ("whip_pan", "orbit", "crane", "push_in", "pull_out", "dolly_zoom", "follow", "dutch", "shake", "drift")
        glyphs.sort(key=lambda g: order.index(g[0]) if g[0] in order else 99)
        return parts, glyphs[:2]

    def _says(self, t) -> str | None:
        best = None
        for tr, _c in self.scene._tracks:
            w = tr.words
            if not w or not (w[0][1] - 0.4 <= t <= w[-1][2] + 0.4):
                continue
            idx = min(range(len(w)), key=lambda i: 0 if w[i][1] <= t < w[i][2] else min(abs(t - w[i][1]), abs(t - w[i][2])))
            lo, hi = idx, idx
            while lo > 0 and w[lo - 1][0].rstrip()[-1:] not in ".?!":
                lo -= 1
            while hi < len(w) - 1 and w[hi][0].rstrip()[-1:] not in ".?!":
                hi += 1
            best = " ".join(x[0] for x in w[lo:hi + 1])
            break
        if best is None:
            return None
        return best if len(best) <= 70 else best[:67].rstrip() + "..."

    def _char_line(self, ctx, n) -> str | None:
        t, an = ctx.t, self._an(n)
        parts = []
        seg = next((s for s in ctx.segs.get(n, []) if s.t0 - 0.05 <= t <= s.t1 + 0.05), None)
        if seg:
            parts.append(self._move_text(ctx, seg))
        for L in self._active_layers(n, t, t + 1e-6, exclude=GAIT_CLIPS + IDLE_CLIPS):
            if L.at <= t < L.end:
                v = VERBS.get(L.clip.name, L.clip.name.replace("_", " "))
                if v not in parts:
                    parts.append(v)
        for t0, t1, tgt, _fi, _fo in an._looks:
            if t0 <= t <= t1 + 0.1:
                parts.append("look at " + (tgt if isinstance(tgt, str) else "a point"))
                break
        if an._faces:
            parts.append(f"face {an.face_at(t)}")
        if not parts or (len(parts) == 1 and parts[0].startswith("face ") and ctx.subject[1] != n):
            return f"{n}: stands" if ctx.subject[1] == n else None
        return f"{n}: " + ", ".join(parts[:3])

    def _describe(self, ctx, reasons):
        shot, t = ctx.shot, ctx.t
        kind = shot.kind.upper().replace("_", " ")
        sk, sn = ctx.subject
        who = sn if sk == "char" else (f"prop {sn}" if sk == "prop" else "a point")
        if shot.other and shot.kind in ("two_shot", "over_shoulder"):
            who += f" & {shot.other}"
        title = f"#{{n}}  {t:.2f}s  {kind} on {who}"
        parts, _g = self._cam_info(shot, t)
        lines = ["CAM: " + (", ".join(parts) if parts else "locked")]
        if t - shot.t0 < 0.6:
            trs = shot.transition if isinstance(shot.transition, list) else [shot.transition] if shot.transition else []
            names = [x.get("type", "cut") if isinstance(x, dict) else str(x) for x in trs]
            if ctx.i == 0 and not names:
                lines.append("OPENING SHOT")
            else:
                lines.append("CUT IN: " + (" + ".join(names) if names else "cut"))
        for n in ctx.vis:
            if n in ctx.onscreen or ctx.subject[1] == n:
                ln = self._char_line(ctx, n)
                if ln:
                    lines.append(ln)
        s = self._says(t)
        if s:
            lines.append(f'SAYS: "{s}"')
        return title, lines

    # ---------------------------------------------------------------- checks
    def _checks(self, ctx) -> list:
        W: list = []
        for fn in (self._chk_screen, self._chk_motion, self._chk_overlap, self._chk_camera, self._chk_float):
            try:
                W += fn(ctx)
            except Exception:                                                       # noqa: BLE001
                continue
        return W

    def _chk_screen(self, ctx):
        W, P = [], ctx.proj
        sk, sn = ctx.subject
        important = {sn} if sk == "char" else set()
        if ctx.shot.other:
            important.add(ctx.shot.other)
        for n in ctx.vis:
            if n not in important or n not in ctx.body:
                continue
            if n not in ctx.onscreen:
                W.append(f"{n} is off-screen")
                continue
            if n == sn and ctx.shot.kind != "insert":
                feet, M, _p, _cf = ctx.body[n]
                top = M["Head"][:3, 3] + np.array([0, 0.6 * self._scale(n), 0])
                (fx, fy), fz = P.pt(feet)
                (hx, hy), hz = P.pt(top)
                lim = 0.06 if ctx.shot.kind in ("top_down", "high_angle") else 0.12
                if fz < -P.NEAR and hz < -P.NEAR and abs(fy - hy) < lim * self.h:
                    W.append("subject tiny in frame")
        return W

    def _chk_motion(self, ctx):
        W, t = [], ctx.t
        for n in ctx.vis:
            an = self._an(n)
            for s in ctx.segs.get(n, []):
                if s.t1 <= t or s.t0 >= ctx.win:
                    continue
                if s.speed > 1.0:
                    ts = min(max(t, s.t0 + 0.35), s.t1 - 0.05) if s.t1 - s.t0 > 0.45 else (s.t0 + s.t1) / 2
                    if abs(_wrap180(s.heading - an.facing_at(ts))) > 100:
                        W.append(f"{n} travels backward")
                if s.explicit and s.gait and CL.get(s.gait).ref_speed:
                    m = s.speed / CL.get(s.gait).ref_speed
                    if not 0.6 <= m <= 1.7:
                        W.append(f"{n} feet slide (speed {m:.1f}x {s.gait})")
                elif s.explicit and not s.gait and s.speed > 1.0:
                    ts = (max(t, s.t0) + min(ctx.win, s.t1)) / 2
                    if not self._active_layers(n, ts, ts + 1e-6, exclude=IDLE_CLIPS + GAIT_CLIPS):
                        W.append(f"{n} glides without a gait clip")
        return list(dict.fromkeys(W))

    def _chk_overlap(self, ctx):
        W = []
        vs = [n for n in ctx.vis if n in ctx.body]
        for i, a in enumerate(vs):
            for b in vs[i + 1:]:
                d = ctx.body[a][0] - ctx.body[b][0]
                if math.hypot(d[0], d[2]) < 1.6:
                    W.append(f"{a} and {b} overlap")
        return W

    def _chk_camera(self, ctx):
        W, sc, t = [], self.scene, ctx.t
        sp = self._subject_point(ctx.shot, t)
        if sp is None:
            return W
        if float(np.linalg.norm(np.asarray(ctx.cs.eye) - sp)) < 1.5:
            W.append("camera inside subject")
        if not sc.timeline.transitions_at(t) and sc._built_sets[ctx.shot.set]["bounds"]:
            un = sc.timeline.cameras[ctx.i].state(t)
            if float(np.linalg.norm(np.asarray(un.eye) - np.asarray(ctx.cs.eye))) > 0.1:
                (x, y), z = ctx.proj.pt(sp)
                if z >= -ctx.proj.NEAR or max(abs(x - self.w / 2) / self.w, abs(y - self.h / 2) / self.h) > 0.25:
                    W.append("camera clamped by wall")
        return W

    def _chk_float(self, ctx):
        W, t = [], ctx.t
        gy = self.scene._built_sets[ctx.shot.set]["ground_y"]
        for n in ctx.vis:
            if n not in ctx.body:
                continue
            _f, _M, pose, cf = ctx.body[n]
            low = rig.lowest_y(pose, cf)
            special = any(L.clip.name in AIR_CLIPS or L.clip.name.startswith(("sit", "sleep"))
                          for L in self._active_layers(n, t - 0.3, t + 0.3))
            if low > gy + 0.6 and not special:
                W.append(f"{n} floats")
            elif low < gy - 0.3:
                W.append(f"{n} is sunk below the ground")
        return W

    # ---------------------------------------------------------------- overlay drawing
    def _draw(self, ctx, panel, frame) -> Image.Image:
        k, w, h, P, t = self.k, self.w, self.h, ctx.proj, ctx.t
        cv = _Canvas(w, h, k)
        badge, gl = 24 * k, 40 * k
        cv.reserve((3 * k, 3 * k, 3 * k + badge, 3 * k + badge * (2 if panel.warnings else 1) + 3 * k))
        cv.reserve((w - 52 * k, 3 * k, w - 3 * k, 3 * k + 18 * k))
        parts, glyphs = self._cam_info(ctx.shot, t)
        gx = [w - 4 * k - (i + 1) * (gl + 4 * k) + 4 * k for i in range(len(glyphs))]
        for x in gx:
            cv.reserve((x, h - gl - 4 * k, x + gl, h - 4 * k))
        msz = int(round(110 * max(k, 0.55)))
        if self.minimap:
            cv.reserve((4 * k, h - msz - 4 * k, 4 * k + msz, h - 4 * k))
        try:
            self._ground_layer(cv, ctx)
        except Exception:                                                           # noqa: BLE001
            pass
        for n in ctx.vis:
            try:
                self._tag(cv, ctx, n)
            except Exception:                                                       # noqa: BLE001
                pass
        try:
            self._move_labels(cv, ctx)
        except Exception:                                                           # noqa: BLE001
            pass
        if self.minimap:
            try:
                self._minimap(cv, ctx, 4 * k, h - msz - 4 * k, msz)
            except Exception:                                                       # noqa: BLE001
                pass
        for (gk, sign), x in zip(glyphs, gx):
            _glyph(cv, gk, x, h - gl - 4 * k, gl, sign)
        cv.circle(3 * k + badge / 2, 3 * k + badge / 2, badge / 2, WHITE, outline=(0, 0, 0), width=1)
        cv.text((3 * k + badge / 2, 3 * k + badge / 2 - 0.5), str(panel.index), 13 * k, (0, 0, 0))
        if panel.warnings:
            cv.circle(3 * k + badge / 2, 3 * k + badge * 1.5 + 3 * k, badge / 2, RED, outline=WHITE, width=1.5)
            cv.text((3 * k + badge / 2, 3 * k + badge * 1.5 + 3 * k - 0.5), "!", 15 * k, WHITE)
        cv.pill(w - 27 * k, 12 * k, f"{t:.2f}s", (20, 22, 28), size=10.5 * k, alpha=220, place=False)
        im = Image.fromarray(frame).convert("RGBA")
        im.alpha_composite(cv.result())
        return im.convert("RGB")

    def _tag(self, cv, ctx, n):
        P, k = ctx.proj, self.k
        if n not in ctx.body:
            return
        feet, M, _p, _cf = ctx.body[n]
        col = self.colors[n]
        head = M["Head"][:3, 3] + np.array([0, 0.9 * self._scale(n), 0])
        (x, y), z = P.pt(head)
        if n in ctx.onscreen:
            cv.pill(x, y - 11 * k, n, col, size=11 * k)
            f = _fwd(self._an(n).facing_at(ctx.t))
            s = self._scale(n)
            poly = [feet + np.array([0, 0.05, 0]) + f * a * s + _right(self._an(n).facing_at(ctx.t)) * b * s
                    for b, a in _CHEVRON]
            px, vz = P.project(np.array(poly))
            if np.all(vz < -P.NEAR):
                cv.poly([tuple(p) for p in px], col, 235, edge=WHITE)
        else:                                                                       # off-screen: edge marker
            (cx, cy), cz = P.pt(M["Torso"][:3, 3])
            dx, dy = (cx - self.w / 2) * (1 if cz < 0 else -1), (cy - self.h / 2) * (1 if cz < 0 else -1)
            sc = 0.5 * min(self.w / max(abs(dx), 1e-6), self.h / max(abs(dy), 1e-6)) * 0.85
            arrow = "<" if dx < 0 and abs(dx) > abs(dy) else ">" if dx > 0 and abs(dx) > abs(dy) else ("^" if dy < 0 else "v")
            cv.pill(self.w / 2 + dx * sc, self.h / 2 + dy * sc, f"{arrow} {n} off-screen", col, size=10 * k)

    def _ground_layer(self, cv, ctx):
        P, k, t = ctx.proj, self.k, ctx.t
        for n in ctx.vis:
            col, sc = self.colors[n], self._scale(n)
            for s in ctx.segs.get(n, []):
                if s.gait in STEP_GAITS and s.dist > 0.8:
                    self._footprints(cv, ctx, s, col, sc)
            for s in ctx.segs.get(n, []):                                           # arrows over prints
                a, b = max(s.t0, t), min(s.t1, ctx.win)
                if b <= a:
                    continue
                an = self._an(n)
                pa, pb = an.position_at(a), an.position_at(b)
                if np.hypot(*(pb - pa)[[0, 2]]) < 0.5:
                    continue
                m = max(3, int(np.hypot(*(pb - pa)[[0, 2]]) / 0.2))
                pts = np.array([an.position_at(a + (b - a) * i / m) for i in range(m + 1)]) + np.array([0, 0.06, 0])
                runs = P.runs(pts)
                if runs:
                    cv.stroke(max(runs, key=len), col, 6.5 * k, head=True)
            self._limb_arrows(cv, ctx, n, col)

    def _footprints(self, cv, ctx, s: _Seg, col, sc):
        c = CL.get(s.gait)
        step = (c.ref_speed or 6.5) * c.duration / 2
        step = max(step, s.dist / 60)
        f = s.heading
        fw, rt = _fwd(f), _right(f)
        us = np.linspace(0, 1, 65)
        es = np.array([_ease(s.ease, u) for u in us])
        i, side = 0, 1
        d = step / 2
        while d < s.dist:
            u = d / s.dist
            tp = s.t0 + (s.t1 - s.t0) * float(np.interp(u, es, us))
            pos = s.at(u) + rt * side * 0.45 * sc + np.array([0, 0.03, 0])
            pts = [pos + rt * (lat * side) * sc + fw * fo * sc for lat, fo in _SHOE]
            px, vz = ctx.proj.project(np.array(pts))
            if np.all(vz < -ctx.proj.NEAR) and np.all(np.abs(px) < 1e4):
                cv.poly([tuple(p) for p in px], col, 89 if tp <= ctx.t else 217, edge=(25, 25, 25))
            d += step
            side = -side
            i += 1

    def _limb_arrows(self, cv, ctx, n, col):
        t, k = ctx.t, self.k
        wl = min(0.6, ctx.win - t)
        if wl < 0.12:
            return
        an = self._an(n)
        ts = [t + wl * i / 7 for i in range(8)]
        moving = np.hypot(*(an.position_at(ts[-1]) - an.position_at(t))[[0, 2]]) > 0.3
        air = bool(self._active_layers(n, t, t + wl, names=AIR_CLIPS))
        if moving and not air:
            return
        feet0 = an.position_at(t)
        tracks = {"Right Hand": [], "Left Hand": [], "Head": [], "Torso": []}
        for tt in ts:
            feet, M, _p, _c = self._body(n, tt)
            off = feet0 - feet
            tracks["Right Hand"].append((M["Right Arm"] @ np.array([0, -1.0, 0, 1.0]))[:3] + off)
            tracks["Left Hand"].append((M["Left Arm"] @ np.array([0, -1.0, 0, 1.0]))[:3] + off)
            tracks["Head"].append(M["Head"][:3, 3] + off)
            tracks["Torso"].append(M["Torso"][:3, 3] + off)
        cand = []
        for name, pts in tracks.items():
            hand = "Hand" in name
            if hand and moving:
                continue
            disp = max(float(np.linalg.norm(p - pts[0])) for p in pts)
            thr = 1.2 if hand else 0.8
            if disp > thr:
                cand.append((disp / thr, pts))
        for _r, pts in sorted(cand, key=lambda c: -c[0])[:2]:
            runs = ctx.proj.runs(np.array(pts))
            if not runs:
                continue
            run = max(runs, key=len)
            sm = _smooth(run)
            if _poly_len(sm) > 8 * k:
                cv.stroke(sm, col, 3.2 * k, dashed=True, head=True)

    def _move_labels(self, cv, ctx):
        P, k, t = ctx.proj, self.k, ctx.t
        for n in ctx.vis:
            for s in ctx.segs.get(n, []):
                a, b = max(s.t0, t), min(s.t1, ctx.win)
                if b <= a:
                    continue
                an = self._an(n)
                pa, pb = an.position_at(a), an.position_at(b)
                d = float(np.hypot(*(pb - pa)[[0, 2]]))
                if d < 0.5:
                    continue
                mid = (pa + pb) / 2 + np.array([0, 0.06, 0])
                (x, y), z = P.pt(mid)
                if z < -P.NEAR:
                    cv.pill(x, y - 12 * k, f"{_fmt(d)} studs {s.gait or 'glide'}", self.colors[n], size=10 * k)

    def _minimap(self, cv, ctx, x0, y0, size):
        k, S, t = self.k, cv.S, ctx.t
        cs, d = ctx.cs, cv.d
        eye = np.asarray(cs.eye, float)
        tgt = np.asarray(cs.target, float)
        pts = [eye[[0, 2]]]
        paths = []
        for n in ctx.vis:
            if n in ctx.body:
                pts.append(ctx.body[n][0][[0, 2]])
            for s in ctx.segs.get(n, []):
                a, b = max(s.t0, t), min(s.t1, ctx.win)
                if b > a:
                    pa, pb = self._an(n).position_at(a), self._an(n).position_at(b)
                    pts += [pa[[0, 2]], pb[[0, 2]]]
                    paths.append((n, pa[[0, 2]], pb[[0, 2]]))
        fwd = (tgt - eye)[[0, 2]]
        fn = np.linalg.norm(fwd)
        fwd = fwd / fn if fn > 1e-6 else np.array([0.0, -1.0])
        lo, hi = np.min(pts, 0), np.max(pts, 0)
        ctr = (lo + hi) / 2
        ext = max(float((hi - lo).max()), 14.0) * 1.3
        M = lambda p: (x0 + size / 2 + (p[0] - ctr[0]) / ext * size, y0 + size / 2 + (p[1] - ctr[1]) / ext * size)  # noqa: E731
        d.rounded_rectangle([x0 * S, y0 * S, (x0 + size) * S, (y0 + size) * S], radius=7 * k * S,
                            fill=(16, 18, 24, 175), outline=(255, 255, 255, 140), width=S)
        # camera FOV cone + triangle
        hf = math.atan(math.tan(math.radians(cs.fov_y) / 2) * self.w / self.h)
        reach = float(np.clip(fn * 1.3, 0.2 * ext, 0.6 * ext))
        base = math.atan2(fwd[1], fwd[0])
        cone = [M(eye[[0, 2]])] + [M(eye[[0, 2]] + reach * np.array([math.cos(base + a), math.sin(base + a)]))
                                   for a in np.linspace(-hf, hf, 9)]
        d.polygon([(a * S, b * S) for a, b in cone], fill=(255, 255, 255, 55), outline=(255, 255, 255, 150))
        ex, ey = M(eye[[0, 2]])
        pr = np.array([-fwd[1], fwd[0]])
        tri = [(ex + fwd[0] * 7 * k, ey + fwd[1] * 7 * k), (ex - fwd[0] * 4 * k + pr[0] * 4.5 * k, ey - fwd[1] * 4 * k + pr[1] * 4.5 * k),
               (ex - fwd[0] * 4 * k - pr[0] * 4.5 * k, ey - fwd[1] * 4 * k - pr[1] * 4.5 * k)]
        cv.poly(tri, (240, 240, 240), 255, edge=(20, 20, 20))
        for n, pa, pb in paths:
            cv.stroke([M(pa), M(pb)], self.colors[n], 1.8 * k, head=True, outline=False)
        for n in ctx.vis:
            if n not in ctx.body:
                continue
            p = ctx.body[n][0][[0, 2]]
            f = _fwd(self._an(n).facing_at(t))[[0, 2]]
            cx, cy = M(p)
            cv.stroke([(cx, cy), (cx + f[0] * 10 * k, cy + f[1] * 10 * k)], self.colors[n], 1.8 * k, outline=False)
            cv.circle(cx, cy, 4.2 * k, self.colors[n], width=1.2)
            cv.text((cx, cy - 8 * k), n[:1].upper(), 8 * k, WHITE, stroke=((0, 0, 0), 1))

    # ---------------------------------------------------------------- tiles / sheet
    def _tile(self, i) -> Image.Image:
        if i not in self._tiles:
            p = self.panels()[i]
            frame = self.scene.render_frame(p.t, preview=True, size=(self.w, self.h), captions=self.captions,
                                            motion_blur=False)
            self._tiles[i] = self._draw(self._ctx[i], p, frame)
        return self._tiles[i]

    def _card(self, p: Panel):
        """-> [(text, bold, rgb, swatch rgb|None)] wrapped to the tile width."""
        size = 13
        width = self.w - 16
        out = []
        rows = [(p.title.replace("{n}", str(p.index)), True, (20, 20, 20), None)]
        for ln in p.lines:
            nm = ln.split(":")[0]
            if ln.startswith("CAM"):
                rows.append((ln, False, (40, 60, 110), None))
            elif ln.startswith(("CUT IN", "OPENING")):
                rows.append((ln, True, (110, 60, 20), None))
            elif nm in self.colors:
                rows.append((ln, False, (30, 30, 30), self.colors[nm]))
            else:
                rows.append((ln, False, (70, 70, 70), None))
        rows += [("! " + wn, True, RED, None) for wn in p.warnings]
        for text, bold, col, sw in rows:
            f = _font(size, bold)
            ind = 12 if sw else 0
            for j, seg in enumerate(_wrap(text, f, width - ind)):
                out.append((seg, bold, col, sw if j == 0 else None, ind))
        return out

    def _card_h(self, p) -> int:
        return 10 + int(len(self._card(p)) * 17.5) + 6

    def _draw_card(self, im, x, y, h, p):
        d = ImageDraw.Draw(im)
        d.rectangle([x, y, x + self.w, y + h], fill=(250, 250, 250))
        yy = y + 8
        for text, bold, col, sw, ind in self._card(p):
            if sw:
                d.rectangle([x + 8, yy + 3, x + 16, yy + 11], fill=sw)
            d.text((x + 8 + ind, yy), text, font=_font(13, bold), fill=col)
            yy += 17.5

    def _title_bar(self, im, n_pages, page):
        sc, d = self.scene, ImageDraw.Draw(im)
        txt = (f"{sc.name}   |   {sc.duration:.1f}s   |   {len(sc.timeline.shots)} shots   |   {len(self.panels())} panels"
               + (f"   |   page {page + 1}/{n_pages}" if n_pages > 1 else ""))
        d.text((12, 10), txt, font=_font(20, True), fill=(240, 240, 240))
        x, y = 12, 44
        for kind, label in LEGEND:
            if kind == "arrow":
                d.line([(x, y + 8), (x + 22, y + 8)], fill=PALETTE[0], width=4)
                d.polygon([(x + 28, y + 8), (x + 19, y + 2), (x + 19, y + 14)], fill=PALETTE[0])
                x += 36
            elif kind == "feet":
                for dx, dy in ((0, 9), (11, 3)):
                    d.ellipse([x + dx, y + dy, x + dx + 8, y + dy + 11], fill=PALETTE[1])
                x += 28
            elif kind == "dashed":
                for dx in (0, 11, 22):
                    d.line([(x + dx, y + 8), (x + dx + 6, y + 8)], fill=PALETTE[2], width=3)
                x += 38
            else:
                d.ellipse([x, y, x + 16, y + 16], fill=RED)
                d.text((x + 8, y + 8), "!", font=_font(12, True), fill=WHITE, anchor="mm")
                x += 22
            d.text((x, y + 8), label, font=_font(13), fill=(200, 200, 200), anchor="lm")
            x += _font(13).getlength(label) + 26

    def pages(self) -> list:
        """All sheet pages (PIL images); a page is at most 4000 px high."""
        ps = self.panels()
        if not ps:
            return [Image.new("RGB", (self.w, 80), (40, 40, 44))]
        gap, bar = 8, 76
        rows = [list(range(i, min(i + self.cols, len(ps)))) for i in range(0, len(ps), self.cols)]
        heights = [self.h + max(self._card_h(ps[j]) for j in r) for r in rows]
        groups, cur, tot = [], [], bar + gap
        for r, rh in zip(rows, heights):
            if cur and tot + rh + gap > 4000:
                groups.append(cur)
                cur, tot = [], bar + gap
            cur.append((r, rh))
            tot += rh + gap
        groups.append(cur)
        W = self.cols * self.w + (self.cols + 1) * gap
        pages = []
        for pi, grp in enumerate(groups):
            im = Image.new("RGB", (W, bar + gap + sum(rh + gap for _r, rh in grp)), (42, 44, 48))
            self._title_bar(im, len(groups), pi)
            y = bar + gap
            for r, rh in grp:
                for c, j in enumerate(r):
                    x = gap + c * (self.w + gap)
                    im.paste(self._tile(j), (x, y))
                    self._draw_card(im, x, y + self.h, rh - self.h, ps[j])
                y += rh + gap
            pages.append(im)
        return pages

    def sheet(self) -> Image.Image:
        return self.pages()[0]

    # ---------------------------------------------------------------- text outputs
    def markdown(self) -> str:
        sc = self.scene
        out = [f"# Storyboard: {sc.name}", "",
               f"{sc.duration:.1f}s, {len(sc.timeline.shots)} shots, {len(self.panels())} panels", ""]
        for p in self.panels():
            out.append(f"## {p.title.replace('{n}', str(p.index))}")
            out.append(f"- why: {', '.join(p.reasons)}")
            out += [f"- {ln}" for ln in p.lines]
            out += [f"- **WARNING: {w}**" for w in p.warnings]
            out.append("")
        return "\n".join(out)

    def to_dict(self) -> dict:
        ps = []
        for p in self.panels():
            d = asdict(p)
            d["title"] = p.title.replace("{n}", str(p.index))
            ps.append(d)
        return {"scene": self.scene.name, "duration": self.scene.duration, "shots": len(self.scene.timeline.shots),
                "panels": ps}

    def warnings(self) -> list:
        """[(panel index, time, text)] for every check that fired."""
        return [(p.index, p.t, w) for p in self.panels() for w in p.warnings]

    def save(self, path) -> list:
        """Write the sheet PNG(s) plus .md and .json next to it; returns the PNG paths."""
        path = str(path)
        base, _ext = os.path.splitext(path)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        pages = self.pages()
        paths = [path] if len(pages) == 1 else [f"{base}_{i + 1}.png" for i in range(len(pages))]
        for im, pth in zip(pages, paths):
            im.save(pth)
        with open(base + ".md", "w") as f:
            f.write(self.markdown())
        with open(base + ".json", "w") as f:
            json.dump(self.to_dict(), f, indent=1)
        return paths
