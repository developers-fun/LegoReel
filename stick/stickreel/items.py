"""Phone items for stickreel: decoded video/still frames for the phone screen, and draw_phone().

Working units follow engine.py: world/reference units through a Cam, canvas pixels = units * cam.z * S.
Run the self-test from /home/user/LegoReel/stick with: python3 -m stickreel.items
"""
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from . import engine as E
from .track import parse_color

MAX_FRAMES = 600
SCREEN_W, SCREEN_H = 120, 240
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
_VIDEO_CACHE = {}


def load_video_frames(path, w, h, fps):
    """Decode a video (or load a still image) to a list of RGB PIL images of size w x h, cropped to fill.

    Video is decoded once per (path, w, h, fps) with ffmpeg and cached. Missing or None paths give [].
    At most MAX_FRAMES frames are kept.
    """
    if not path or not os.path.isfile(path):
        return []
    key = (path, w, h, fps)
    if key in _VIDEO_CACHE:
        return _VIDEO_CACHE[key]
    frames = []
    try:
        if path.lower().endswith(_IMAGE_EXT):
            with Image.open(path) as im:
                frames = [ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS)]
        else:
            vf = f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
            cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-frames:v", str(MAX_FRAMES),
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            res = subprocess.run(cmd, capture_output=True, check=False)
            if res.returncode != 0:
                print(f"items: ffmpeg failed on {path}: {res.stderr.decode(errors='replace').strip()}", file=sys.stderr)
            else:
                fsize = w * h * 3
                n = len(res.stdout) // fsize
                if n:
                    buf = np.frombuffer(res.stdout, dtype=np.uint8, count=n * fsize).reshape(n, h, w, 3)
                    frames = [Image.fromarray(buf[i].copy(), "RGB") for i in range(n)]
    except (OSError, ValueError) as exc:
        print(f"items: could not load {path}: {exc}", file=sys.stderr)
        frames = []
    _VIDEO_CACHE[key] = frames
    return frames


def _resolve(path, scene):
    if not path:
        return None
    return path if os.path.isabs(path) else os.path.join(getattr(scene, "base_dir", "."), path)


def screen_image(p, t, scene):
    """RGBA image (SCREEN_W x SCREEN_H) of the phone screen at scene time t.

    p keys: video, video_start (s), video_speed (1), loop (True), screen_color (shown with no video or before it starts).
    """
    W, H = SCREEN_W, SCREEN_H
    fill = Image.new("RGBA", (W, H), parse_color(p.get("screen_color") or "#101820"))
    fps = scene.fps
    frames = load_video_frames(_resolve(p.get("video"), scene), W, H, fps)
    if not frames:
        return fill
    since = (t - float(p.get("video_start") or 0.0))
    if since < 0:
        return fill
    speed = float(p.get("video_speed") or 1.0)
    idx = int(since * speed * fps)
    n = len(frames)
    if p.get("loop", True):
        idx %= n
    else:
        idx = min(idx, n - 1)
    return frames[idx].convert("RGBA")


def _mix(c, target, u):
    return tuple(int(round(a + (b - a) * u)) for a, b in zip(c, target))


def _upright(k, w, h, g, color, screen, L):
    """phone standing upright on an L x L transparent layer, grip point at the layer centre.
    k = pixels per world unit. g = grip position along the length from the bottom (0..1)."""
    layer = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = L / 2.0
    W, H = w * k, h * k
    left, right = c - W / 2, c + W / 2
    top, bot = c - (1 - g) * H, c + g * H

    edge = _mix(color, (255, 255, 255), 0.35)
    d.rounded_rectangle([left, top, right, bot], radius=3.2 * k, fill=color + (255,),
                        outline=edge + (255,), width=max(1, int(round(0.6 * k))))

    bs, bt, bb = 1.2 * k, 2.4 * k, 2.4 * k           # side, top and bottom bezels
    sx0, sy0, sx1, sy1 = left + bs, top + bt, right - bs, bot - bb
    sw, sh = max(1, int(round(sx1 - sx0))), max(1, int(round(sy1 - sy0)))
    d.rounded_rectangle([sx0, sy0, sx1, sy1], radius=2.0 * k, fill=(8, 8, 10, 255))
    scr = ImageOps.fit(screen, (sw, sh), Image.BICUBIC)
    mask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, sw - 1, sh - 1], radius=2.0 * k, fill=255)
    layer.paste(scr, (int(round(sx0)), int(round(sy0))), mask)

    nw, nh = 5.0 * k, 1.3 * k                          # front camera notch in the top bezel
    ncy = top + bt / 2
    d.rounded_rectangle([c - nw / 2, ncy - nh / 2, c + nw / 2, ncy + nh / 2], radius=nh / 2, fill=(4, 4, 6, 255))
    return layer


def _composite(img, layer, x0, y0):
    """alpha-composite layer onto img with its top-left at (x0, y0), clipping at the edges."""
    W, H = img.size
    lw, lh = layer.size
    sx, sy = max(0, -x0), max(0, -y0)
    dx, dy = max(0, x0), max(0, y0)
    cw, ch = min(lw - sx, W - dx), min(lh - sy, H - dy)
    if cw <= 0 or ch <= 0:
        return
    crop = layer.crop((sx, sy, sx + cw, sy + ch))
    if img.mode == "RGBA":
        img.alpha_composite(crop, (dx, dy))
    else:
        img.paste(crop, (dx, dy), crop)


def draw_phone(img, p, cam, t, scene):
    """draw a smartphone onto img. The grip point (x, y) in world units lands on cam.p(x, y).

    p keys: x, y, rot (deg; direction from grip to the top edge, 0 = right, -90 = up), w (26), h (48), scale (1),
    color ('#2a2a30'), grip_at (0.35, fraction up the length from the bottom), plus the screen_image keys.
    """
    x, y = float(p["x"]), float(p["y"])
    rot = float(p.get("rot", 0.0))
    w, h = float(p.get("w", 26)), float(p.get("h", 48))
    scale = float(p.get("scale", 1.0))
    g = min(1.0, max(0.0, float(p.get("grip_at", 0.35))))
    color = parse_color(p.get("color") or "#2a2a30")[:3]

    k = 4.0 * cam.z * E.S * scale                       # px per world unit
    # square layer centred on the grip that holds the phone at any angle: half-size must cover the far end
    # of the body (the longer side of the grip) and its corners
    far = max(g, 1 - g) * h * k
    L = 2 * int(math.ceil(max(w * k / 2, far, math.hypot(w * k / 2, far)))) + 8
    screen = screen_image(p, t, scene)
    layer = _upright(k, w, h, g, color, screen, L)
    layer = layer.rotate(-(rot + 90.0), resample=Image.BILINEAR)  # PIL rotates counter-clockwise; screen angles are clockwise

    gx, gy = cam.p(x, y)
    _composite(img, layer, int(round(gx - L / 2)), int(round(gy - L / 2)))


if __name__ == "__main__":
    import time
    from types import SimpleNamespace

    from .engine import Cam

    src = "/tmp/phone_test_src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=240x480:rate=30:duration=4",
                    "-pix_fmt", "yuv420p", src], check=True)
    scene = SimpleNamespace(base_dir=".", fps=30)
    E.S = 2.0

    assert load_video_frames(None, 120, 240, 30) == []
    assert load_video_frames("/nonexistent/clip.mp4", 120, 240, 30) == []
    frames = load_video_frames(src, SCREEN_W, SCREEN_H, 30)
    assert len(frames) == 120, len(frames)
    assert load_video_frames(src, SCREEN_W, SCREEN_H, 30) is frames  # cached
    scr = screen_image(dict(video=src, video_start=0.0, screen_color="#1e90ff"), 1.0, scene)
    assert scr.size == (SCREEN_W, SCREEN_H) and scr.mode == "RGBA"
    assert screen_image(dict(video=src, video_start=2.0, screen_color="#1e90ff"), 1.0, scene).getpixel((5, 5)) == (30, 144, 255, 255)

    # 300 x 300 reference canvas at S = 2
    canvas = Image.new("RGBA", (int(300 * E.S), int(300 * E.S)), (40, 44, 52, 255))
    cam = Cam(1.0, 150.0, 150.0, 150.0, 150.0)
    p = dict(video=src, video_start=0.0, video_speed=1, loop=True, screen_color="#1e90ff", x=150, y=150, rot=-90)
    draw_phone(canvas, p, cam, 1.0, scene)
    canvas.convert("RGB").save("/tmp/phone_test.png")

    # speed check on a full-size 1152 x 2048 canvas, a few runs after warm-up
    big = Image.new("RGBA", (1152, 2048), (40, 44, 52, 255))
    bigcam = Cam()
    draw_phone(big, dict(p, x=288, y=512, rot=20), bigcam, 1.0, scene)
    t0 = time.perf_counter()
    for i in range(5):
        draw_phone(big, dict(p, x=288 + i, y=512, rot=20 + i), bigcam, 1.0 + i / 30, scene)
    ms = (time.perf_counter() - t0) / 5 * 1000
    print(f"self-test ok: 120 frames decoded, phone drawn to /tmp/phone_test.png, {ms:.1f} ms per draw at 1152x2048")
