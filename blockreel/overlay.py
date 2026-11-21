"""Burned-in text: captions, hook text and labels."""
from __future__ import annotations

import sys

import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .mathutil import parse_color

_FALLBACK_FONTS = [
    "arialbd.ttf", "Arial Bold.ttf", "segoeuib.ttf",                       # Windows
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",                    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
]
_cache = {}


def load_font(path, size):
    key = (path, size)
    if key in _cache:
        return _cache[key]
    font = None
    candidates = ([path] if path else []) + _FALLBACK_FONTS
    for c in candidates:
        try:
            font = ImageFont.truetype(c, size)
            break
        except (OSError, ValueError):
            continue
    if font is None:
        try:
            font = ImageFont.load_default(size)  # Pillow 10.1+ returns a scalable font
        except TypeError:
            font = ImageFont.load_default()
    _cache[key] = font
    return font


def _wrap(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        words = para.split()
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            if draw.textlength(trial, font=font) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _parse_rgba(value):
    s = value.lstrip("#")
    rgb = parse_color("#" + s[:6])
    a = int(s[6:8], 16) if len(s) >= 8 else 255
    return rgb + (a,)


def _resolve_font(style, default_path):
    f = style.get("font")
    if not f:
        return default_path
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    p = Path(f)
    return str(p if p.is_absolute() else root / p)


def draw_text(img, text, style, font_path, y_override=None, age=1.0):
    """Draw one text block, centred. Style keys beyond the basics (all optional):
    font (path, relative to the project folder), shadow {dx, dy, blur, color} (fractions of size),
    pill {color, pad_x, pad_y, dot} (rounded box behind the text, padding as fractions of size),
    highlight (colour of the last line, or of `highlight_words` words), pop (seconds of pop-in)."""
    W, H = img.size
    size = max(8, int(round(style["size"] * W)))
    font = load_font(_resolve_font(style, font_path), size)
    probe = ImageDraw.Draw(img, "RGBA")
    max_w = style["max_width"] * W
    lines = _wrap(probe, text, font, max_w)
    bbox = probe.textbbox((0, 0), "Ag", font=font)
    line_h = int((bbox[3] - bbox[1]) * float(style.get("line_height", 1.22)))
    block_h = line_h * len(lines)
    widest = max(probe.textlength(l, font=font) for l in lines)
    cy = (y_override if y_override is not None else style["y"]) * H
    stroke_w = int(round(style["stroke_width"] * size))
    fill = parse_color(style["color"])
    stroke = parse_color(style["stroke"])
    pill = style.get("pill")
    sh = style.get("shadow")

    # draw the block on its own transparent layer, then composite (lets us scale it for the pop-in)
    pad = int(size * 0.6)
    lw, lh = int(widest + 2 * pad), int(block_h + 2 * pad)
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if pill:
        px, py = pill.get("pad_x", 0.5) * size, pill.get("pad_y", 0.25) * size
        box = [pad - px, pad - py + (line_h - (bbox[3] - bbox[1])) * 0.2, pad + widest + px, pad + block_h + py * 0.6]
        d.rounded_rectangle(box, radius=(box[3] - box[1]) / 2.0, fill=_parse_rgba(pill["color"]))
        if pill.get("dot"):
            r = size * 0.16
            cx0, cy0 = box[0] + (box[3] - box[1]) * 0.5, (box[1] + box[3]) / 2.0
            d.ellipse([cx0 - r, cy0 - r, cx0 + r, cy0 + r], fill=_parse_rgba(pill["dot"]))
    elif style.get("bg"):
        d.rounded_rectangle([pad - size * 0.35, pad - size * 0.17, pad + widest + size * 0.35, pad + block_h + size * 0.17],
                            radius=size * 0.3, fill=_parse_rgba(style["bg"]))

    def put(dr, dx, dy, color, sw, sc):
        y = pad + dy
        for i, line in enumerate(lines):
            w = dr.textlength(line, font=font)
            col = color
            if style.get("highlight") and color is fill and i == len(lines) - 1 and len(lines) > 1:
                col = parse_color(style["highlight"])
            dr.text((pad + (widest - w) / 2.0 + dx, y), line, font=font, fill=col, stroke_width=sw, stroke_fill=sc)
            y += line_h

    if sh:
        sl = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
        put(ImageDraw.Draw(sl), sh.get("dx", 0.0) * size, sh.get("dy", 0.06) * size, _parse_rgba(sh["color"]), stroke_w,
            _parse_rgba(sh["color"]))
        blur = sh.get("blur", 0.0) * size
        if blur > 0:
            sl = sl.filter(ImageFilter.GaussianBlur(blur))
        layer = Image.alpha_composite(sl, layer)
        d = ImageDraw.Draw(layer)
    put(d, 0, 0, fill, stroke_w, stroke)

    pop = float(style.get("pop", 0.0))
    if pop > 0 and age < pop:
        u = age / pop
        k = 0.82 + 0.18 * (1 - (1 - u) ** 3) + 0.06 * math.sin(u * math.pi)    # ease out with a small overshoot
        nw, nh = max(1, int(lw * k)), max(1, int(lh * k))
        layer = layer.resize((nw, nh), Image.LANCZOS)
        lw, lh = nw, nh
    ox = int((W - lw) / 2)
    oy = int(cy - lh / 2)
    img.paste(layer, (ox, oy), layer)
