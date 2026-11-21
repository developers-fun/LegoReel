"""Pre-render checks. Everything here is cheap next to a full render (a 22 s reel is ~40 minutes), so run it first.

    python3 -m blockreel preflight reels/x.json --stills --sheet out/x_sheet.png

Three layers:
  1. static   : timing, text (speed, safe zone, collisions, brand words, contrast), characters on screen / facing the
                camera / not inside props, camera variety, last-shot hold. No 3D rendering.
  2. stills   : a few half-resolution frames per shot (not blank, not too dark/bright, hard cuts really change the
                picture, same frame renders identically twice). Also writes a contact sheet with the safe zone drawn on.
  3. video    : check_video() verifies a finished MP4 (frame count, size, fps, no black or frozen frames).

Findings are 'error' (do not render), 'warn' (look at it), or 'info'.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .errors import SceneError
from .mathutil import parse_color

# Fractions of the frame that stay clear of platform UI (top bar, bottom caption/buttons, side buttons).
SAFE = {"top": 0.08, "bottom": 0.20, "left": 0.05, "right": 0.05}
MAX_WORDS_PER_SECOND = 3.5
MIN_TEXT_SECONDS = 0.7
IDEAL_SECONDS = (18.0, 25.0)
BANNED_WORDS = ("lego", "duplo", "minecraft", "roblox")     # brand names must not appear in on-screen text
CHAR_RADIUS = 0.55         # studs, torso core (not the arms) for intersection tests
FACE_AWAY_DOT = -0.35      # facing . (camera - char) below this means the character shows its back


@dataclass
class Finding:
    level: str            # error | warn | info
    code: str
    message: str
    t: float | None = None

    def __str__(self):
        at = f" @{self.t:.2f}s" if self.t is not None else ""
        return f"[{self.level.upper():5}] {self.code}{at}: {self.message}"


class Report:
    def __init__(self):
        self.findings: list[Finding] = []
        self.sheet: str | None = None

    def add(self, level, code, message, t=None):
        self.findings.append(Finding(level, code, message, t))

    @property
    def errors(self):
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.level == "warn"]

    def codes(self, level=None):
        return {f.code for f in self.findings if level is None or f.level == level}

    def text(self):
        if not self.findings:
            return "preflight: all checks passed"
        order = {"error": 0, "warn": 1, "info": 2}
        lines = [str(f) for f in sorted(self.findings, key=lambda f: (order[f.level], f.t or 0.0))]
        lines.append(f"preflight: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return "\n".join(lines)

    def to_json(self):
        return json.dumps({"errors": len(self.errors), "warnings": len(self.warnings), "sheet": self.sheet,
                           "findings": [asdict(f) for f in self.findings]}, indent=2)


# ---- small helpers -----------------------------------------------------------

def _luma(rgb):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(a, b):
    la, lb = _luma(a), _luma(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def project(cam, p, aspect):
    """World point -> (x, y) in 0..1 screen fractions (y down), or None when behind the camera."""
    d = np.asarray(p, dtype=np.float64) - cam.position
    z = float(d @ cam.fwd)
    if z <= 0.05:
        return None
    t = math.tan(math.radians(cam.fov) / 2.0)
    x = float(d @ cam.right) / (z * t * aspect)
    y = float(d @ cam.up) / (z * t)
    return 0.5 + x / 2.0, 0.5 - y / 2.0


def sample_times(scene, per_shot=3):
    """Times inside each shot: just after the cut, the middle, just before the next cut (all on frame boundaries)."""
    f = 1.0 / scene.fps
    out = []
    for s in scene.shots:
        last = max(s.start, s.end - 2 * f)
        picks = [s.start + 2 * f, s.start + s.duration / 2.0, last][:per_shot]
        for T in picks:
            T = round(T * scene.fps) / scene.fps
            out.append((s, min(max(T, s.start), max(s.start, s.end - f))))
    return out


def text_bbox(scene, t):
    """Pixel bbox (x0, y0, x1, y1) of a text as it will be drawn at full size, or None for empty text."""
    from .overlay import draw_text
    text = t.text
    if not text:
        return None
    if scene.show_speaker and t.speaker:
        text = f"{t.speaker}: {text}"
    layer = Image.new("RGBA", (scene.width, scene.height), (0, 0, 0, 0))
    draw_text(layer, text, scene.text_styles[t.style], scene.font_path, t.y, age=10.0)
    return layer.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()


# ---- layer 1: static ----------------------------------------------------------

def check_timing(scene, rep, ideal=IDEAL_SECONDS):
    lo, hi = ideal
    if scene.duration < lo - 1e-6 or scene.duration > hi + 1e-6:
        rep.add("warn", "duration", f"reel is {scene.duration:.1f}s; the target is {lo:.0f} to {hi:.0f}s")
    if scene.duration > 60:
        rep.add("error", "duration_max", f"reel is {scene.duration:.0f}s; short-form platforms cap well below this")
    for s in scene.shots:
        for label, v in (("start", s.start), ("duration", s.duration)):
            if abs(v * scene.fps - round(v * scene.fps)) > 1e-3:
                rep.add("warn", "frame_align",
                        f"shot '{s.id}' {label} {v:.4f}s is not on a frame boundary (1/{scene.fps} s); chunked renders "
                        f"may drop or repeat a frame at the join", s.start)
        if s.duration < 0.3:
            rep.add("warn", "short_shot", f"shot '{s.id}' lasts {s.duration:.2f}s, too short to read", s.start)
    for a, b in zip(scene.shots, scene.shots[1:]):
        if b.start < a.end - 1e-6:
            rep.add("error", "shot_overlap", f"shots '{a.id}' and '{b.id}' overlap", b.start)
        elif b.start > a.end + 1e-6:
            rep.add("warn", "shot_gap", f"gap between shots '{a.id}' and '{b.id}': the earlier last frame holds", a.end)
    if scene.shots[-1].duration < 1.5:
        rep.add("warn", "end_hold", f"final shot '{scene.shots[-1].id}' is {scene.shots[-1].duration:.1f}s; hold it "
                f"at least 1.5s so there is room for an app screen or end card")
    if scene.audio_path and not scene.audio_path.exists():
        rep.add("error", "audio_missing", f"audio file not found: {scene.audio_path}")


def check_text(scene, rep, safe=SAFE):
    W, H = scene.width, scene.height
    hooks = [t for t in scene.texts if t.style == "hook" and t.text]
    if not hooks:
        rep.add("warn", "no_hook", "no 'hook' text; the first second needs a hook on screen")
    elif min(t.t0 for t in hooks) > 1.0 + 1e-6:
        rep.add("warn", "late_hook", f"first hook text appears at {min(t.t0 for t in hooks):.2f}s; it should be in the "
                f"first second")
    boxes = []
    for t in scene.texts:
        if not t.text:
            rep.add("warn", "empty_text", "empty text overlay", t.t0)
            continue
        low = t.text.lower()
        for w in BANNED_WORDS:
            if re.search(rf"\b{w}", low):
                rep.add("error", "brand_word", f"on-screen text '{t.text}' contains '{w}'; keep brand names out of copy",
                        t.t0)
        words, dur = len(t.text.split()), t.t1 - t.t0
        if t.style != "label":
            if words / dur > MAX_WORDS_PER_SECOND:
                rep.add("warn", "text_speed", f"'{t.text}' is {words} words in {dur:.1f}s "
                        f"(over {MAX_WORDS_PER_SECOND} words/s)", t.t0)
            if dur < MIN_TEXT_SECONDS and words > 1:
                rep.add("warn", "text_short", f"'{t.text}' is up for only {dur:.2f}s", t.t0)
        sh = scene.shot_at(t.t0)
        if t.t1 > sh.end + 1e-6:
            rep.add("warn", "text_past_shot", f"'{t.text}' runs past the end of shot '{sh.id}'", t.t0)
        st = scene.text_styles[t.style]
        fill, stroke = parse_color(st["color"]), parse_color(st["stroke"])
        sw = float(st.get("stroke_width", 0.0))
        if sw >= 0.05 and contrast_ratio(fill, stroke) < 4.5:
            rep.add("warn", "text_colors", f"style '{t.style}': fill and outline contrast only "
                    f"{contrast_ratio(fill, stroke):.1f}:1", t.t0)
        pill = st.get("pill")
        if pill and contrast_ratio(fill, parse_color(pill["color"][:7])) < 4.5:
            rep.add("warn", "text_colors", f"style '{t.style}': text and pill contrast only "
                    f"{contrast_ratio(fill, parse_color(pill['color'][:7])):.1f}:1", t.t0)
        bb = text_bbox(scene, t)
        if bb is None:
            rep.add("error", "text_clipped", f"'{t.text}' is completely outside the frame", t.t0)
            continue
        x0, y0, x1, y1 = bb
        if x0 <= 0 or y0 <= 0 or x1 >= W or y1 >= H:
            rep.add("error", "text_clipped", f"'{t.text}' is cut off by the frame edge", t.t0)
        elif x0 < safe["left"] * W or x1 > (1 - safe["right"]) * W:
            rep.add("warn", "text_side_margin", f"'{t.text}' is closer to the side than {safe['left']:.0%}", t.t0)
        if y0 < safe["top"] * H and t.style != "label":
            rep.add("warn", "text_top_zone", f"'{t.text}' sits in the top {safe['top']:.0%} (platform bar)", t.t0)
        if y1 > (1 - safe["bottom"]) * H:
            rep.add("warn", "text_bottom_zone", f"'{t.text}' sits in the bottom {safe['bottom']:.0%} (platform UI)", t.t0)
        n_lines = max(1, round((y1 - y0) / max(1.0, st["size"] * W * 1.22)))
        if n_lines > 3:
            rep.add("warn", "text_lines", f"'{t.text}' wraps to about {n_lines} lines; cut it down", t.t0)
        boxes.append((t, bb))
    for i, (a, ba) in enumerate(boxes):
        for b, bb in boxes[i + 1:]:
            if min(a.t1, b.t1) - max(a.t0, b.t0) <= 1e-6:
                continue
            ox = min(ba[2], bb[2]) - max(ba[0], bb[0])
            oy = min(ba[3], bb[3]) - max(ba[1], bb[1])
            if ox > 0 and oy > 0:
                rep.add("error", "text_overlap", f"'{a.text}' and '{b.text}' are on screen together and overlap",
                        max(a.t0, b.t0))


def _facing(yaw):
    r = math.radians(yaw)
    return np.array([math.sin(r), 0.0, math.cos(r)])


def check_characters(scene, rep):
    aspect = scene.width / scene.height
    margin = 0.02
    for s, T in sample_times(scene):
        cam = scene.camera_at(T)
        seen_full = []
        for cid, tl in scene.timelines.items():
            pos = tl.pos_at(T)
            height = scene.rigs[cid].height * scene.scales[cid]
            foot = project(cam, pos, aspect)
            head = project(cam, pos + np.array([0, height, 0]), aspect)
            if foot is None or head is None:
                continue
            xs = (foot[0], head[0])
            if max(xs) < -0.1 or min(xs) > 1.1:
                continue            # not in this shot
            top, bot = head[1], foot[1]
            fully = (margin <= top and bot <= 1 - margin and margin <= min(xs) and max(xs) <= 1 - margin)
            if fully:
                seen_full.append((cid, bot - top))
                to_cam = cam.position - pos
                to_cam[1] = 0
                n = np.linalg.norm(to_cam)
                yaw = tl.yaw_at(T, scene)
                if n > 1e-6 and float(_facing(yaw) @ (to_cam / n)) < FACE_AWAY_DOT:
                    spoken = any(x.speaker == cid and x.t0 <= T < x.t1 for x in scene.texts)
                    rep.add("warn", "back_to_camera",
                            f"'{cid}' faces away from the camera in shot '{s.id}'" + (" while speaking" if spoken else
                            "; the face print will not show"), T)
            elif -0.05 < foot[0] < 1.05:
                if bot > 1 + 0.02 and top > 0:
                    pass            # cropped at the feet on purpose is common in close shots
                elif top < 0:
                    rep.add("warn", "head_cropped", f"'{cid}' has the head cut off by the top of the frame in shot "
                            f"'{s.id}'", T)
                elif min(xs) < 0 or max(xs) > 1:
                    rep.add("warn", "side_cropped", f"'{cid}' is cut off at the side in shot '{s.id}'", T)
        if not seen_full:
            heads = []
            for cid, tl in scene.timelines.items():
                p = project(cam, tl.pos_at(T) + np.array([0, scene.rigs[cid].height, 0]), aspect)
                if p and 0 <= p[0] <= 1 and 0 <= p[1] <= 1:
                    heads.append(cid)
            if not heads:
                rep.add("warn", "empty_shot", f"shot '{s.id}' shows no character", T)
        else:
            cid, frac = max(seen_full, key=lambda x: x[1])
            if frac < 0.12:
                rep.add("warn", "subject_small", f"largest character in shot '{s.id}' fills only {frac:.0%} of the "
                        f"frame height", T)


def _box_hit(scene, p, T, pos, height):
    """Does a character standing at pos (cylinder radius CHAR_RADIUS) intersect prop p at time T?"""
    if p.shape == "template":
        return False
    m = scene.prop_model(p, T)
    c = m[:3, 3]
    sx, sy, sz = p.size
    if not (c[1] - sy / 2 + 0.3 < pos[1] + height and c[1] + sy / 2 - 0.3 > pos[1]):
        return False
    # to prop-local xz (the model is translate * rot_y, so invert the rotation)
    d = np.array([pos[0] - c[0], pos[2] - c[2]])
    r = np.array([[m[0, 0], m[0, 2]], [m[2, 0], m[2, 2]]])
    lx, lz = r.T @ d
    if p.shape == "cylinder":
        return math.hypot(lx / (sx / 2 + CHAR_RADIUS * 0.8), lz / (sz / 2 + CHAR_RADIUS * 0.8)) < 1.0
    ex, ez = max(abs(lx) - sx / 2, 0.0), max(abs(lz) - sz / 2, 0.0)
    return math.hypot(ex, ez) < CHAR_RADIUS * 0.8


def check_space(scene, rep):
    ids = list(scene.timelines)
    for s, T in sample_times(scene):
        for i, a in enumerate(ids):
            pa = scene.timelines[a].pos_at(T)
            for b in ids[i + 1:]:
                pb = scene.timelines[b].pos_at(T)
                if abs(pa[1] - pb[1]) < 2 and math.hypot(pa[0] - pb[0], pa[2] - pb[2]) < 1.5:
                    rep.add("warn", "characters_overlap", f"'{a}' and '{b}' stand inside each other in shot '{s.id}'", T)
        for cid in ids:
            tl = scene.timelines[cid]
            pos = tl.pos_at(T)
            h = scene.rigs[cid].height * scene.scales[cid]
            for p in scene.props:
                if _box_hit(scene, p, T, pos, h):
                    rep.add("error", "prop_intersects_character",
                            f"prop '{p.id}' passes through '{cid}' in shot '{s.id}'", T)
        # props below the ground or floating are almost always typos
    for p in scene.props:
        if p.shape != "template":
            top = p.position[1] + p.size[1] / 2
            if top < scene.ground["y"] + 0.05 and not p.track:     # half-buried scenery (hills) is fine; fully buried is a typo
                rep.add("warn", "prop_underground", f"prop '{p.id}' is entirely below the ground and can never be seen")


def check_cameras(scene, rep):
    classes = []
    for s in scene.shots:
        cam = scene.camera_at(s.start + 1.0 / scene.fps)
        if cam.position[1] < scene.ground["y"] + 0.2:
            rep.add("error", "camera_underground", f"camera of shot '{s.id}' is at or below the ground", s.start)
        if not (15 <= cam.fov <= 85):
            rep.add("warn", "camera_fov", f"camera of shot '{s.id}' has fov {cam.fov:.0f}; extremes distort the minifig",
                    s.start)
        d = cam.focus_dist
        classes.append("close" if d < 11 else ("medium" if d < 15.5 else "wide"))
    if len(scene.shots) >= 4 and len(set(classes)) < 2:
        rep.add("warn", "shot_variety", f"all {len(scene.shots)} shots use the same shot size ({classes[0]}); mix wide, "
                f"medium and close")
    for a, b in zip(scene.shots, scene.shots[1:]):
        ca, cb = scene.camera_at(a.end - 1.0 / scene.fps), scene.camera_at(b.start + 1.0 / scene.fps)
        if np.linalg.norm(ca.position - cb.position) < 0.05 and abs(ca.fov - cb.fov) < 0.5 \
                and np.linalg.norm(ca.fwd - cb.fwd) < 0.01:
            rep.add("warn", "dead_cut", f"shots '{a.id}' and '{b.id}' use the same camera; the cut will look like a glitch",
                    b.start)


def check_avatars(scene, rep):
    raw = getattr(scene, "raw_characters", None)
    for cid, av in scene.avatars.items():
        if not getattr(av, "locked", True):
            rep.add("info", "avatar_unlocked", f"avatar '{av.label}' is not locked", None)
    if raw:
        for cid, c in raw.items():
            if "avatar" in c and "avatar_fingerprint" not in c:
                rep.add("info", "no_fingerprint", f"character '{cid}' does not pin avatar_fingerprint; a changed avatar "
                        f"file would change the reel silently")


def check_grid(scene, rep):
    """Everything should sit on the stud lattice with whole-stud sizes (see blockreel/grid.py)."""
    from . import grid as gm
    if not scene.grid["enabled"]:
        rep.add("info", "grid_off", "grid snapping is off for this scene")
        return
    pitch = scene.pitch
    for p in scene.props:
        if not p.grid:
            rep.add("info", "grid_optout", f"prop '{p.id}' opted out of the grid")
            continue
        if p.shape == "template":
            if p.snapped and p.snapped.get("clamped"):
                rep.add("warn", "grid_clamped", f"set piece '{p.id}' could not be scaled to a whole-stud footprint "
                        f"within {gm.FIT_RANGE[0]}x to {gm.FIT_RANGE[1]}x; it is only position-snapped")
            continue
        if not scene.grid["props"]:
            continue
        sx, sy, sz = p.size
        for axis, v in (("x", sx), ("z", sz)):
            n = v / pitch
            if abs(n - round(n)) > 1e-6:
                rep.add("error", "grid_size", f"prop '{p.id}' is {n:.3f} studs in {axis}, not a whole number")
        plate = gm.PLATE * pitch
        if abs(sy / plate - round(sy / plate)) > 1e-6:
            rep.add("error", "grid_height", f"prop '{p.id}' is {sy / plate:.2f} plates high, not a whole number")
        wx, wz = (sz, sx) if int(round(p.rotation_y / 90.0)) % 2 else (sx, sz)
        if abs(p.rotation_y / 90.0 - round(p.rotation_y / 90.0)) > 1e-6:
            rep.add("warn", "grid_rotation", f"prop '{p.id}' is turned {p.rotation_y:.0f} degrees; only multiples of "
                    f"90 stay on the grid")
        else:
            for axis, c, w in (("x", p.position[0], wx), ("z", p.position[2], wz)):
                n = round(w / pitch)
                if not gm.on_lattice(c - (n / 2.0) * pitch, pitch):
                    rep.add("error", "grid_position", f"prop '{p.id}' edges are off the lattice in {axis}")
    if scene.grid["characters"]:
        for cid, tl in scene.timelines.items():
            x, z = tl.pos_at(0.0)[0], tl.pos_at(0.0)[2]
            if not (gm.on_lattice(x, pitch) and gm.on_lattice(z, pitch, 0.5)):
                rep.add("warn", "grid_character", f"character '{cid}' starts off the stud lattice")


def static_checks(scene, rep=None, ideal=IDEAL_SECONDS, safe=SAFE):
    rep = rep or Report()
    check_timing(scene, rep, ideal)
    check_text(scene, rep, safe)
    check_characters(scene, rep)
    check_space(scene, rep)
    check_cameras(scene, rep)
    check_avatars(scene, rep)
    check_grid(scene, rep)
    return rep


# ---- layer 2: stills ------------------------------------------------------------

def _frame_without_text(scene, idx):
    from .render import render_frame
    saved = scene.texts
    scene.texts = []
    try:
        return render_frame(scene, idx)
    finally:
        scene.texts = saved


def check_stills(path, rep, sheet=None, width_scale=0.5, per_shot=3, safe=SAFE):
    """Render a few cheap frames per shot, run pixel checks, and optionally write a contact sheet."""
    from .overlay import draw_text
    from .scene import Scene
    sc = Scene.load(path, width_scale=width_scale, supersample=1)
    W, H = sc.width, sc.height
    tiles = []
    first_last = {}
    for s, T in sample_times(sc, per_shot):
        idx = int(round(T * sc.fps))
        base = _frame_without_text(sc, idx)
        a = np.asarray(base, dtype=np.float32)
        lum = a.mean()
        if sc.fade_at(T) < 0.999:
            pass                       # an intentional fade to black is not a blank frame
        elif a.std() < 8:
            rep.add("error", "blank_frame", f"frame at {T:.2f}s (shot '{s.id}') is nearly one flat colour", T)
        elif lum < 25:
            rep.add("warn", "too_dark", f"frame at {T:.2f}s (shot '{s.id}') is very dark (mean {lum:.0f}/255)", T)
        elif lum > 238:
            rep.add("warn", "too_bright", f"frame at {T:.2f}s (shot '{s.id}') is washed out (mean {lum:.0f}/255)", T)
        first_last.setdefault(s.id, []).append(a)
        shown = base.copy()
        for t in sc.texts_at(T):
            if not t.text:
                continue
            st = sc.text_styles[t.style]
            draw_text(shown, f"{t.speaker}: {t.text}" if sc.show_speaker and t.speaker else t.text, st, sc.font_path,
                      t.y, age=10.0)
            bb = text_bbox(sc, t)
            if bb:
                reg = a[bb[1]:bb[3], bb[0]:bb[2]]
                has_edge = float(st.get("stroke_width", 0)) >= 0.05 or st.get("pill") or st.get("bg")
                if reg.size and not has_edge:
                    ratio = contrast_ratio(parse_color(st["color"]), reg.reshape(-1, 3).mean(axis=0))
                    if ratio < 3.0:
                        rep.add("warn", "text_on_busy_bg", f"'{t.text}' has only {ratio:.1f}:1 contrast against the "
                                f"picture and no outline", T)
        tiles.append((s, T, shown))
    shots = [s.id for s in sc.shots]
    for a, b in zip(shots, shots[1:]):
        if a in first_last and b in first_last:
            d = float(np.abs(first_last[a][-1] - first_last[b][0]).mean())
            if d < 3.0:
                rep.add("warn", "cut_not_visible", f"the cut from '{a}' to '{b}' barely changes the picture "
                        f"(difference {d:.1f}/255)")
    # determinism: the same frame must come out identical (parallel workers rely on it)
    s0, T0 = sample_times(sc, 1)[0]
    i0 = int(round(T0 * sc.fps))
    if not np.array_equal(np.asarray(_frame_without_text(sc, i0)), np.asarray(_frame_without_text(sc, i0))):
        rep.add("error", "nondeterministic", f"frame {i0} renders differently on two runs; chunked renders would flicker")
    if sheet:
        rep.sheet = str(make_sheet(sc, tiles, sheet, safe))
    return tiles


def make_sheet(sc, tiles, out, safe=SAFE, cols=None):
    """One PNG of every sampled still with the safe zone outlined and the shot and time printed."""
    W, H = sc.width, sc.height
    n = len(tiles)
    cols = cols or min(6, max(1, n))
    rows = math.ceil(n / cols)
    th = 360
    tw = int(th * W / H)
    pad, lab = 6, 16
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + lab + pad) + pad), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for i, (s, T, im) in enumerate(tiles):
        cx, cy = pad + (i % cols) * (tw + pad), pad + (i // cols) * (th + lab + pad)
        t = im.resize((tw, th), Image.LANCZOS)
        dt = ImageDraw.Draw(t)
        dt.rectangle([safe["left"] * tw, safe["top"] * th, (1 - safe["right"]) * tw, (1 - safe["bottom"]) * th],
                     outline=(255, 80, 80), width=1)
        sheet.paste(t, (cx, cy + lab))
        d.text((cx, cy + 2), f"{s.id}  {T:.2f}s", fill=(230, 230, 230))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def preflight(path, stills=False, sheet=None, ideal=IDEAL_SECONDS, safe=SAFE):
    from .scene import Scene
    rep = Report()
    try:
        scene = Scene.load(path)
    except SceneError as e:
        rep.add("error", "scene_invalid", str(e))
        return rep
    static_checks(scene, rep, ideal, safe)
    if stills or sheet:
        check_stills(path, rep, sheet=sheet, safe=safe)
    return rep


# ---- layer 3: finished video ----------------------------------------------------------

def _tool(name):
    p = shutil.which(name)
    if not p:
        raise SceneError(f"{name} not found on PATH")
    return p


def probe_video(path):
    out = subprocess.run([_tool("ffprobe"), "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_read_frames,codec_name,pix_fmt:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True)
    if out.returncode != 0:
        raise SceneError(f"ffprobe failed on {path}: {out.stderr.strip()[:200]}")
    d = json.loads(out.stdout)
    st = d["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"width": int(st["width"]), "height": int(st["height"]), "fps": float(num) / float(den),
            "frames": int(st["nb_read_frames"]), "codec": st["codec_name"], "pix_fmt": st.get("pix_fmt"),
            "duration": float(d["format"]["duration"])}


def check_video(path, expect_frames=None, expect_size=(1080, 1920), expect_fps=30.0, samples=8):
    """Verify a rendered MP4. Returns a Report; errors mean the file should not be sent."""
    rep = Report()
    p = Path(path)
    if not p.exists() or p.stat().st_size < 1000:
        rep.add("error", "video_missing", f"{path} is missing or empty")
        return rep
    info = probe_video(p)
    if (info["width"], info["height"]) != tuple(expect_size):
        rep.add("error", "video_size", f"video is {info['width']}x{info['height']}, expected "
                f"{expect_size[0]}x{expect_size[1]}")
    if abs(info["fps"] - expect_fps) > 0.01:
        rep.add("error", "video_fps", f"video is {info['fps']:.2f} fps, expected {expect_fps:g}")
    if expect_frames is not None and info["frames"] != expect_frames:
        rep.add("error", "video_frames", f"video has {info['frames']} frames, expected {expect_frames}")
    if info["codec"] != "h264" or info["pix_fmt"] != "yuv420p":
        rep.add("warn", "video_codec", f"video is {info['codec']}/{info['pix_fmt']}; phones expect h264/yuv420p")
    # sample frames: not black, not frozen
    ff = _tool("ffmpeg")
    prev = None
    still = 0
    n = max(2, samples)
    for i in range(n):
        t = max(0.0, (info["frames"] - 2) / info["fps"] * i / (n - 1))   # stay off the very last frame: -ss can overshoot
        r = subprocess.run([ff, "-v", "error", "-ss", f"{t:.3f}", "-i", str(p), "-frames:v", "1", "-vf", "scale=108:192",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
        raw = np.frombuffer(r.stdout, dtype=np.uint8)
        if raw.size != 108 * 192 * 3:
            rep.add("error", "video_unreadable", f"could not decode a frame near {t:.2f}s", t)
            continue
        a = raw.astype(np.float32)
        if a.mean() < 6 and i not in (0, n - 1):
            rep.add("error", "video_black", f"frame near {t:.2f}s is black", t)
        if prev is not None and float(np.abs(a - prev).mean()) < 0.5:
            still += 1
        prev = a
    if still >= n - 2:
        rep.add("error", "video_frozen", "sampled frames are all identical; the video looks frozen")
    return rep
