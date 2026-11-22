"""Burned-in word-by-word captions for r6reel.

Public API
    CaptionTrack / Captions   timed words: Captions.from_text(...), Captions.from_words(...)
    render_caption(...)       RGBA overlay (H, W, 4) uint8 for one time, or None
    composite(frame, rgba)    alpha-composite an overlay over an RGB frame
    pop_scale(dt)             word pop-in scale, dt seconds after the word starts

Styles
    storytime   1-3 words on screen (rolling window within a phrase), current word pops
    yellow_pop  current word yellow, earlier words of the line white, later words hidden
    two_line    the phrase (up to two lines) with the current word highlighted

Everything is sized relative to the frame width, so 360x640 and 1080x1920 look alike.
Word sprites (fill, outline and shadow baked in) are cached per (word, size, role, scale),
so a frame costs a handful of alpha pastes.
"""
from __future__ import annotations

import bisect
import math
import os
import re
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

__all__ = ["CaptionTrack", "Captions", "render_caption", "composite", "pop_scale", "STYLES"]

STYLES = ("storytime", "yellow_pop", "two_line")
DEFAULT_Y = 0.62
DEFAULT_FONT_FRAC = 0.09          # font size as a fraction of frame width
SIDE_MARGIN = 0.08                # fraction of width kept clear on each side
FPS = 30
# pop-in: (frame index after the word starts, scale). 0.8 -> 1.08 -> 1.0 over 4 frames.
POP_KEYS = ((0.0, 0.80), (2.0, 1.08), (4.0, 1.00))
WHITE = (255, 255, 255)
YELLOW = (255, 214, 0)
SHADOW_OPACITY = 0.55
MIN_WORD_CHARS = 3                # timing floor: short words still take a beat
_FIT_SCALES = (1.0, 0.92, 0.85, 0.78, 0.70, 0.62, 0.55)
_TRAIL_CLOSERS = "\"'”’)]»"

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_SYSTEM_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
)
_DOWNLOAD_NAME = "Fredoka-VariableFont.ttf"
_DOWNLOAD_URLS = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/fredoka/Fredoka%5Bwdth%2Cwght%5D.ttf",
)
_NOTDEF_PROBE = "￿"         # noncharacter: never in a font, so it draws the .notdef box


# --------------------------------------------------------------------------- timing

_NON_WORD = re.compile(r"[^\w]")


def _pause_after(token: str) -> float:
    """Extra hold, in seconds, after a word that ends a clause or sentence."""
    core = token.rstrip(_TRAIL_CLOSERS)
    if core.endswith(("...", "…", ".", "!", "?")):
        return 0.30
    if core.endswith((";", ":")):
        return 0.18
    if core.endswith((",", "—", "–")):
        return 0.12
    return 0.0


def _ends_phrase(token: str) -> bool:
    return _pause_after(token) > 0.0


def pop_scale(dt: float) -> float:
    """Scale of the current word dt seconds after it starts (0.8 -> 1.08 -> 1.0 at 30 fps)."""
    f = dt * FPS
    (f0, s0), (f1, s1), (f2, s2) = POP_KEYS
    if f <= f0:
        return s0
    if f < f1:
        return s0 + (s1 - s0) * (f - f0) / (f1 - f0)
    if f < f2:
        return s1 + (s2 - s1) * (f - f1) / (f2 - f1)
    return s2


@dataclass
class CaptionTrack:
    """Timed words. words = [(text, t0, t1), ...], contiguous or with gaps, never overlapping."""
    words: list = field(default_factory=list)
    style: str = "storytime"

    def __post_init__(self):
        if self.style not in STYLES:
            raise ValueError(f"unknown caption style {self.style!r}; use one of {STYLES}")

    @classmethod
    def from_words(cls, items, style: str = "storytime") -> "CaptionTrack":
        """items: [(text, t0, t1), ...] in time order. A text may hold several words."""
        words = []
        prev_end = None
        for text, a, b in items:
            a, b = float(a), float(b)
            if b <= a:
                raise ValueError(f"caption {text!r}: t1 ({b}) must be after t0 ({a})")
            if prev_end is not None and a < prev_end - 1e-9:
                raise ValueError(f"caption {text!r} starts at {a} before the previous one ends at {prev_end}")
            words.append((str(text), a, b))
            prev_end = b
        return cls(words, style)

    @classmethod
    def from_text(cls, text: str, t0: float, t1: float | None = None, wpm: float | None = None,
                  words_per_sec: float = 3.0, style: str = "storytime") -> "CaptionTrack":
        """Split text into timed words.

        Each word gets a share of the speech time proportional to its length (with a floor
        of MIN_WORD_CHARS). Punctuation holds the word a little longer. With t1 given the
        words fill [t0, t1]; without it the length follows from wpm (or words_per_sec).
        """
        tokens = text.split()
        t0 = float(t0)
        if not tokens:
            return cls([], style)
        if t1 is None:
            rate = (wpm / 60.0) if wpm is not None else float(words_per_sec)
            if rate <= 0:
                raise ValueError("words per second must be positive")
        else:
            t1 = float(t1)
            if t1 <= t0:
                raise ValueError(f"t1 ({t1}) must be after t0 ({t0})")

        weights = [max(len(_NON_WORD.sub("", tok)), MIN_WORD_CHARS) + 1 for tok in tokens]
        pauses = [_pause_after(tok) for tok in tokens]
        if t1 is None:
            speech = len(tokens) / rate
            t1 = t0 + speech + sum(pauses)
        else:
            total = t1 - t0
            pause_total = sum(pauses)
            if pause_total > 0:
                scale = min(1.0, 0.25 * total / pause_total)   # pauses never eat more than a quarter
                pauses = [p * scale for p in pauses]
            speech = total - sum(pauses)

        wsum = float(sum(weights))
        words = []
        cursor = t0
        for tok, w, p in zip(tokens, weights, pauses):
            start = cursor
            end = start + speech * w / wsum + p
            words.append((tok, start, end))
            cursor = end
        last_text, last_start, _ = words[-1]
        words[-1] = (last_text, last_start, t1)
        return cls(words, style)

    @property
    def t_start(self) -> float:
        return self.words[0][1] if self.words else 0.0

    @property
    def t_end(self) -> float:
        return self.words[-1][2] if self.words else 0.0

    def active_index(self, t: float) -> int | None:
        """Index of the word on screen at time t, or None (before, after, or in a gap)."""
        if not self.words:
            return None
        starts = [w[1] for w in self.words]
        i = bisect.bisect_right(starts, t) - 1
        if i < 0:
            return None
        return i if t < self.words[i][2] else None

    def render(self, t, width, height, style=None, y=DEFAULT_Y, font_scale=1.0):
        return render_caption(self, t, width, height, style=style, y=y, font_scale=font_scale)


Captions = CaptionTrack


def _as_track(captions) -> CaptionTrack:
    if isinstance(captions, CaptionTrack):
        return captions
    return CaptionTrack.from_words(captions)


# --------------------------------------------------------------------------- fonts

def _download_font() -> str | None:
    """Last resort: fetch a Google font TTF into assets/fonts. Never raises."""
    target = FONT_DIR / _DOWNLOAD_NAME
    for url in _DOWNLOAD_URLS:
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = resp.read()
            if data[:4] not in (b"\x00\x01\x00\x00", b"true"):
                continue
            FONT_DIR.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return str(target)
        except Exception:
            continue
    return None


@lru_cache(maxsize=1)
def _font_path() -> str | None:
    """assets/fonts/*.ttf, then system DejaVu Sans Bold, then a download. None = PIL default."""
    if FONT_DIR.is_dir():
        found = list(FONT_DIR.glob("*.ttf"))
        if found:
            def rank(p: Path):
                preferred = any(k in p.name.lower() for k in ("fredoka", "baloo", "montserrat"))
                return (0 if preferred else 1, p.name)
            return str(sorted(found, key=rank)[0])
    for p in _SYSTEM_FONTS:
        if os.path.isfile(p):
            return p
    return _download_font()


def _set_bold(font) -> None:
    """For variable fonts, pick weight 700 (bold) and leave other axes at default."""
    try:
        axes = font.get_variation_axes()
    except (OSError, AttributeError, ValueError):
        return
    values = []
    for axis in axes:
        name = axis.get("name", b"")
        name = name.decode("latin-1") if isinstance(name, bytes) else str(name)
        if name.lower() == "weight":
            values.append(min(max(700, axis["minimum"]), axis["maximum"]))
        else:
            values.append(axis["default"])
    try:
        font.set_variation_by_axes(values)
    except (OSError, ValueError):
        pass


@lru_cache(maxsize=128)
def _font(size: int):
    path = _font_path()
    if path is not None:
        try:
            font = ImageFont.truetype(path, size)
            _set_bold(font)
            return font
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _raster(font, ch: str) -> bytes:
    im = Image.new("L", (200, 200), 0)
    ImageDraw.Draw(im).text((20, 150), ch, font=font, fill=255, anchor="ls")
    return im.tobytes()


@lru_cache(maxsize=8192)
def _has_glyph(ch: str) -> bool:
    """True when the font draws ch as a real glyph: not the .notdef box, not blank."""
    font = _font(64)
    raster = _raster(font, ch)
    return any(raster) and raster != _raster(font, _NOTDEF_PROBE)


@lru_cache(maxsize=8192)
def _display_text(token: str) -> str:
    """Drop characters the font cannot draw (emoji, most non-Latin) instead of printing tofu."""
    return "".join(ch for ch in token if _has_glyph(ch))


def _stroke(size: int) -> int:
    return max(1, int(round(size * 0.075)))


# --------------------------------------------------------------------------- sprites

class _Sprite(NamedTuple):
    img: Image.Image   # RGBA, shadow + black outline + fill baked in
    pvx: float         # pivot (glyph centre) in img coordinates
    pvy: float


@lru_cache(maxsize=512)
def _sprite(text: str, size: int, role: str, pct: int = 100) -> _Sprite:
    """Word image. role 'plain' = white fill, 'hi' = yellow fill. pct scales the sprite."""
    if pct != 100:
        base = _sprite(text, size, role, 100)
        w, h = base.img.size
        nw, nh = max(1, round(w * pct / 100)), max(1, round(h * pct / 100))
        img = base.img.resize((nw, nh), Image.Resampling.BICUBIC)
        return _Sprite(img, base.pvx * nw / w, base.pvy * nh / h)

    font = _font(size)
    asc, desc = font.getmetrics()
    sw = _stroke(size)
    blur = max(1.0, size * 0.05)
    dy = max(1, int(round(size * 0.06)))
    adv = font.getlength(text)
    pad = sw + dy + int(math.ceil(3 * blur)) + 2
    w = int(math.ceil(adv)) + 2 * pad
    h = asc + desc + 2 * pad
    base_y = pad + asc

    outline = Image.new("L", (w, h), 0)
    ImageDraw.Draw(outline).text((pad, base_y), text, font=font, fill=255,
                                 stroke_width=sw, stroke_fill=255, anchor="ls")

    shadow_mask = Image.new("L", (w, h), 0)
    shadow_mask.paste(outline, (0, dy))
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(blur))
    shadow_mask = shadow_mask.point(lambda v: int(v * SHADOW_OPACITY))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(shadow_mask)

    outline_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    outline_layer.putalpha(outline)

    fill_mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(fill_mask).text((pad, base_y), text, font=font, fill=255, anchor="ls")
    colour = YELLOW if role == "hi" else WHITE
    fill_layer = Image.new("RGBA", (w, h), colour + (0,))
    fill_layer.putalpha(fill_mask)

    img = Image.alpha_composite(shadow, outline_layer)
    img = Image.alpha_composite(img, fill_layer)
    return _Sprite(img, pad + adv / 2.0, pad + asc / 2.0)


# --------------------------------------------------------------------------- layout

def _wrap(texts: tuple, size: int, max_w: float, max_lines: int):
    """Greedy word wrap. Returns (lines, ok); lines are tuples of indices into texts."""
    font = _font(size)
    gap = font.getlength(" ")
    sw = _stroke(size)
    widths = [font.getlength(t) + 2 * sw for t in texts]
    lines = []
    cur: list[int] = []
    cw = 0.0
    for i, w in enumerate(widths):
        if cur and cw + gap + w > max_w:
            lines.append(tuple(cur))
            cur, cw = [i], w
        else:
            cw = cw + gap + w if cur else w
            cur.append(i)
    if cur:
        lines.append(tuple(cur))
    ok = len(lines) <= max_lines and all(len(l) > 1 or widths[l[0]] <= max_w for l in lines)
    return tuple(lines), ok


@lru_cache(maxsize=4096)
def _fit(texts: tuple, base: int, max_w: float, max_lines: int):
    """Largest size (from base down) at which texts fit. Returns (size, lines, ok)."""
    size, lines = base, ()
    for s in _FIT_SCALES:
        size = max(6, int(round(base * s)))
        lines, ok = _wrap(texts, size, max_w, max_lines)
        if ok:
            return size, lines, True
    return size, lines, False


def _style_window(style: str, j: int, n: int) -> tuple[int, int]:
    """Indices [a, b) of the phrase words shown while word j of an n-word phrase is active."""
    if style == "storytime":
        return max(0, j - 2), j + 1
    if style == "yellow_pop":
        return max(0, j - 3), j + 1
    return max(0, j - 4), min(n, j + 5)          # two_line


def _phrase_bounds(raw: list, idx: int) -> tuple[int, int]:
    """[lo, hi) of the phrase (run of words ended by punctuation) holding word idx."""
    lo = idx
    while lo > 0 and not _ends_phrase(raw[lo - 1]):
        lo -= 1
    hi = idx
    while hi < len(raw) - 1 and not _ends_phrase(raw[hi]):
        hi += 1
    return lo, hi + 1


@lru_cache(maxsize=1024)
def _phrase_size(phrase: tuple, style: str, base: int, max_w: float, max_lines: int) -> int:
    """One font size for a whole phrase, so the caption does not change size word to word."""
    n = len(phrase)
    best = None
    for j in range(n):
        if not phrase[j]:
            continue
        a, b = _style_window(style, j, n)
        win = tuple(t for t in phrase[a:b] if t)
        size, _, _ = _fit(win, base, max_w, max_lines)
        best = size if best is None else min(best, size)
    return best if best is not None else base


def _paste(canvas: Image.Image, img: Image.Image, x: int, y: int) -> None:
    W, H = canvas.size
    w, h = img.size
    x0, y0 = max(0, -x), max(0, -y)
    x1, y1 = min(w, W - x), min(h, H - y)
    if x1 <= x0 or y1 <= y0:
        return
    piece = img.crop((x0, y0, x1, y1))
    box = (x + x0, y + y0, x + x1, y + y1)
    region = canvas.crop(box)
    canvas.paste(Image.alpha_composite(region, piece), box[:2])


# --------------------------------------------------------------------------- render

def render_caption(captions, t: float, width: int, height: int, style: str | None = None,
                   y: float = DEFAULT_Y, font_scale: float = 1.0):
    """RGBA overlay (height, width, 4) uint8 for time t, or None when no word is on screen.

    captions    a CaptionTrack/Captions, or a list of (text, t0, t1)
    style       one of STYLES; defaults to the track's style
    y           vertical centre of the caption block, as a fraction of frame height
    font_scale  multiplies the default size (9 % of width)
    """
    track = _as_track(captions)
    style = style or track.style
    if style not in STYLES:
        raise ValueError(f"unknown caption style {style!r}")
    W, H = int(width), int(height)
    if W <= 0 or H <= 0:
        raise ValueError("width and height must be positive")

    idx = track.active_index(float(t))
    if idx is None:
        return None

    raw = [w[0] for w in track.words]
    lo, hi = _phrase_bounds(raw, idx)
    disp = tuple(_display_text(tok) for tok in raw[lo:hi])
    j = idx - lo
    base = max(8, int(round(font_scale * DEFAULT_FONT_FRAC * W)))
    max_w = (1.0 - 2.0 * SIDE_MARGIN) * W
    max_lines = 1 if style == "storytime" else 2
    size = _phrase_size(disp, style, base, max_w, max_lines)

    # words on screen now: the window for this word, minus anything that drew nothing
    a, b = _style_window(style, j, len(disp))
    items = [(k, disp[k]) for k in range(a, b) if disp[k]]
    if not items:
        return None
    cur = next((p for p, (k, _) in enumerate(items) if k == j), None)
    lo_w, hi_w = 0, len(items)
    while True:
        texts = tuple(txt for _, txt in items[lo_w:hi_w])
        lines, ok = _wrap(texts, size, max_w, max_lines)
        if ok or hi_w - lo_w <= 1:
            break
        if cur is None:
            hi_w -= 1
        elif cur - lo_w > hi_w - 1 - cur:
            lo_w += 1
        else:
            hi_w -= 1
    texts = tuple(txt for _, txt in items[lo_w:hi_w])
    rel_cur = None if cur is None else cur - lo_w

    font = _font(size)
    asc, desc = font.getmetrics()
    gap = font.getlength(" ")
    line_h = (asc + desc) + int(round(size * 0.08))
    block_h = (len(lines) - 1) * line_h + (asc + desc)
    top = float(y) * H - block_h / 2.0

    pop = 1.0
    if rel_cur is not None:
        pop = pop_scale(float(t) - track.words[idx][1])
    pop_pct = int(round(pop * 50)) * 2          # quantised to 2 % so sprites cache well

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for li, line in enumerate(lines):
        widths = [font.getlength(texts[k]) for k in line]
        line_w = sum(widths) + gap * (len(line) - 1)
        x = (W - line_w) / 2.0
        baseline = top + li * line_h + asc
        for pos, k in enumerate(line):
            is_cur = k == rel_cur
            role = "hi" if (is_cur and style != "storytime") else "plain"
            spr = _sprite(texts[k], size, role, pop_pct if is_cur else 100)
            cx = x + widths[pos] / 2.0
            cy = baseline - asc / 2.0
            _paste(canvas, spr.img, int(round(cx - spr.pvx)), int(round(cy - spr.pvy)))
            x += widths[pos] + gap

    return np.array(canvas, dtype=np.uint8)


def composite(frame_rgb, rgba) -> np.ndarray:
    """Alpha-composite an RGBA overlay (from render_caption) over an RGB frame. Returns uint8."""
    frame = np.asarray(frame_rgb)
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame_rgb must be (H, W, 3)")
    out = np.array(frame, dtype=np.uint8, copy=True)
    if rgba is None:
        return out
    rgba = np.asarray(rgba)
    if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.shape[:2] != frame.shape[:2]:
        raise ValueError("rgba must be (H, W, 4) matching the frame")
    alpha = rgba[..., 3]
    rows = np.flatnonzero(alpha.any(axis=1))
    cols = np.flatnonzero(alpha.any(axis=0))
    if rows.size == 0:
        return out
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    a = alpha[y0:y1, x0:x1, None].astype(np.float32) / 255.0
    src = rgba[y0:y1, x0:x1, :3].astype(np.float32)
    dst = out[y0:y1, x0:x1].astype(np.float32)
    out[y0:y1, x0:x1] = np.clip(dst * (1.0 - a) + src * a + 0.5, 0, 255).astype(np.uint8)
    return out
