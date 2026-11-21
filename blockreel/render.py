"""Frame rendering and the render pipeline (workers, PNG output, ffmpeg encode)."""
from __future__ import annotations

import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import math

import numpy as np
from PIL import Image, ImageFilter

from . import raster
from .character import Item, build_items
from .figure import build_brick_items
from .mathutil import mat_mul, scale_m, translate
from .parts import DEFAULT_PALETTE, pieces_to_items
from .errors import SceneError
from .overlay import draw_text
from .scene import Scene

try:
    _BOX = Image.Resampling.BOX
except AttributeError:  # Pillow < 9.1
    _BOX = Image.BOX


_VIGNETTE = {}


def _post(img, look):
    """Final colour pass at output size: gentle contrast, saturation and vignette."""
    contrast, sat, vig = look["contrast"], look["saturation"], look["vignette"]
    bloom = float(look.get("bloom", 0.0))
    tint = look.get("tint", [1.0, 1.0, 1.0])
    if (abs(contrast - 1.0) < 1e-6 and abs(sat - 1.0) < 1e-6 and vig <= 0 and bloom <= 0
            and all(abs(t - 1.0) < 1e-6 for t in tint)):
        return img
    a = np.asarray(img, dtype=np.float32) / 255.0
    if bloom > 0:
        a = _bloom(a, bloom)
    if any(abs(t - 1.0) > 1e-6 for t in tint):
        a = a * np.array(tint, np.float32)[None, None, :]
    if abs(contrast - 1.0) > 1e-6:
        a = (a - 0.5) * contrast + 0.5
    if abs(sat - 1.0) > 1e-6:
        lum = (a @ np.array([0.2126, 0.7152, 0.0722], np.float32))[:, :, None]
        a = lum + (a - lum) * sat
    if vig > 0:
        key = (img.width, img.height, vig)
        m = _VIGNETTE.get(key)
        if m is None:
            ys = np.linspace(-1.0, 1.0, img.height, dtype=np.float32)[:, None]
            xs = np.linspace(-1.0, 1.0, img.width, dtype=np.float32)[None, :]
            r2 = (xs * xs * 0.6 + ys * ys * 0.9) / 1.5
            m = (1.0 - vig * np.clip(r2, 0.0, 1.0) ** 1.5)[:, :, None]
            _VIGNETTE[key] = m
        a = a * m
    return Image.fromarray((np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8))


def _stud_items(model, p, ex):
    """Round studs on the top face of a box prop, on a grid of about one stud per unit (at most 6 per side)."""
    sx, sy, sz = p.size
    nx, nz = max(1, min(6, int(round(sx)))), max(1, min(6, int(round(sz))))
    px, pz = sx / nx, sz / nz
    d = min(px, pz) * 0.6
    out = []
    for i in range(nx):
        for j in range(nz):
            x = -sx / 2 + px * (i + 0.5)
            z = -sz / 2 + pz * (j + 0.5)
            out.append(Item(mat_mul(model, translate(x, sy / 2 + d * 0.15, z)), (d, d * 0.35, d), p.color, "stud",
                            0.03, False, dict(ex)))
    return out


def _ground_studs(scene, cam):
    """Raised studs on the ground lattice, only where the camera can see them (and not too far away to read)."""
    g = scene.ground
    pitch, radius = g["tile"], g["studs"] * g["tile"]
    if radius <= 0:
        return []
    H = radius * 0.62                                   # real studs are about 1/3 as tall as they are wide
    reach = 34.0
    cx, cz = cam.position[0], cam.position[2]
    i0, i1 = int(math.floor((cx - reach) / pitch)), int(math.ceil((cx + reach) / pitch))
    j0, j1 = int(math.floor((cz - reach) / pitch)), int(math.ceil((cz + reach) / pitch))
    ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
    x = (ii.ravel() + 0.5) * pitch
    z = (jj.ravel() + 0.5) * pitch
    v = np.stack([x - cam.position[0], np.full_like(x, g["y"] + H * 0.5 - cam.position[1]), z - cam.position[2]], 1)
    zc, xc, yc = v @ cam.fwd, v @ cam.right, v @ cam.up
    th = math.tan(math.radians(cam.fov) / 2.0)
    asp = scene.width / scene.height
    ok = (zc > 0.4) & (zc < reach) & (np.abs(xc) < zc * th * asp * 1.1 + pitch) & (np.abs(yc) < zc * th * 1.1 + pitch)
    sel = np.nonzero(ok)[0]
    if len(sel) > 2600:
        sel = sel[np.argsort(zc[sel])[:2600]]
    gloss = float(scene.look.get("gloss", 0.0))
    out = []
    for k in sel:
        px, pz = float(x[k]), float(z[k])
        cols = g["colors"]
        for zn in g["zones"]:
            x0, z0, x1, z1 = zn["rect"]
            if x0 <= px < x1 and z0 <= pz < z1:
                cols = zn["colors"]
                break
        col = cols[(int(ii.ravel()[k]) + int(jj.ravel()[k])) & 1]
        out.append(Item(translate(px, g["y"] + H * 0.5 - 0.01, pz), (radius * 2, H, radius * 2), tuple(col), "stud",
                        0.03, False, {"spec": gloss}))
    return out


def _blur(img, radius):
    return img.filter(ImageFilter.GaussianBlur(radius))


def _dof(img, depth, focus, cfg):
    """Soft background: pixels further than `focus + start` studs are blurred, fully by `focus + end`.
    The blur only mixes background pixels with each other, so the subject keeps a clean edge."""
    W, H = img.size
    start, end = float(cfg.get("start", 4.0)), float(cfg.get("end", 24.0))
    m = np.clip((depth - (focus + start)) / max(end - start, 1e-3), 0.0, 1.0)
    m = m * m * (3.0 - 2.0 * m)
    m *= float(cfg.get("strength", 1.0))
    if m.max() < 0.01:
        return img
    r = max(1.0, float(cfg.get("radius", 7.0)) * W / 1080.0) / 2.0          # blur at half size, then enlarge
    hw, hh = max(2, W // 2), max(2, H // 2)
    small = img.resize((hw, hh), Image.BILINEAR)
    ms = Image.fromarray((m * 255).astype(np.uint8)).resize((hw, hh), Image.BILINEAR)
    marr = np.asarray(ms, dtype=np.float32) / 255.0
    num = Image.fromarray((np.asarray(small, dtype=np.float32) * marr[:, :, None]).astype(np.uint8))
    num = np.asarray(_blur(num, r), dtype=np.float32)
    den = np.asarray(_blur(ms, r), dtype=np.float32)[:, :, None] / 255.0
    blurred = np.clip(num / np.maximum(den, 0.02), 0, 255)
    big = np.asarray(Image.fromarray(blurred.astype(np.uint8)).resize((W, H), Image.BILINEAR), dtype=np.float32)
    mm = m[:, :, None]
    out = np.asarray(img, dtype=np.float32) * (1.0 - mm) + big * mm
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _bloom(a, strength):
    """Soft glow from the brightest areas. a: float image 0..1, shape (h, w, 3)."""
    h, w = a.shape[:2]
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    bright = np.clip((lum - 0.72) / 0.28, 0.0, 1.0)[:, :, None] * a
    im = Image.fromarray((bright * 255).astype(np.uint8)).resize((max(2, w // 4), max(2, h // 4)), Image.BILINEAR)
    im = _blur(im, max(2.0, w / 120.0))
    g = np.asarray(im.resize((w, h), Image.BILINEAR), dtype=np.float32) / 255.0
    return 1.0 - (1.0 - a) * (1.0 - g * strength)          # screen blend


_FLAP = (1, 0, 2, 0, 3, 1, 0, 2, 0, 3, 2, 0)     # which talk face (0 = the resting face), 8 changes a second


def _mouth_frame(app, T):
    """Name of the talk face to show at time T, or None for the resting face. Uses the avatar's expressions named
    talk_1, talk_2, ... (any number); nothing happens if the avatar defines none."""
    names = [k for k in app.expressions if k.startswith("talk_")]
    if not names:
        return None
    k = _FLAP[int(T * 8.0) % len(_FLAP)]
    return None if k == 0 else names[(k - 1) % len(names)]


def render_frame(scene, idx):
    """Return one frame as a PIL RGB image."""
    W, H, ss = scene.width, scene.height, scene.supersample
    T = idx / scene.fps
    cam = scene.camera_at(T)

    items, contact = [], []
    ck = scene.shadow_cfg["contact"]
    for cid, tl in scene.timelines.items():
        pos = tl.pos_at(T)
        yaw = tl.yaw_at(T, scene)
        pose = tl.pose_at(T, cam.position, scene, pos, yaw)
        sc = scene.scales[cid]
        app = scene.appearances[cid]
        if hasattr(app, "parts"):          # a brick avatar made of part templates
            expr = tl.expression_at(T)
            if expr is None and any(x.speaker == cid and x.t0 <= T < x.t1 for x in scene.texts):
                expr = _mouth_frame(app, T)      # lip flap while this character has a dialogue line
            items += build_brick_items(app, pos, yaw, pose, expr)
        else:
            items += build_items(app, scene.rigs[cid], pos, yaw, pose, sc)
        lift = max(0.0, pose["root_y"])
        if ck > 0:
            contact.append((float(pos[0]), float(pos[2]), 1.0 * sc, ck / (1.0 + 0.6 * lift)))
    gloss = float(scene.look.get("gloss", 0.0))
    for p in scene.props:
        model = scene.prop_model(p, T)
        if p.shape == "template":
            m = mat_mul(model, scale_m(p.scale))
            pal = dict(DEFAULT_PALETTE)
            pal.update(p.palette or {})
            for it in pieces_to_items(p.template.data["pieces"], m, pal, p.template.dir, Item, glossy=gloss > 0):
                items.append(it._replace(casts=it.casts and p.casts))
            continue
        ex = {"spec": gloss}
        if gloss > 0 and max(p.size) <= 6:
            ex["subdiv"] = 1
        items.append(Item(model, p.size, p.color, p.shape, p.bevel, p.casts, ex))
        if p.studs and p.shape == "box":
            items += _stud_items(model, p, ex)

    if scene.ground.get("geo_studs"):
        items += _ground_studs(scene, cam)

    fb = raster.Framebuffer(W * ss, H * ss)
    raster.fill_sky(fb, cam, scene.bg_top, scene.bg_bottom, scene.light_dir, scene.sun_glow, scene.clouds)
    shadow = raster.build_shadow(items, cam, scene.light_dir, scene.ground["y"], scene.shadow_cfg)
    raster.draw_ground(fb, cam, scene.ground, contact, shadow)
    fill_dir = scene.lighting.fill_dir_for(cam)
    bevel = scene.look["bevel"]
    for it in items:
        raster.draw_item(fb, cam, it, scene.lighting, fill_dir, bevel)

    img = Image.fromarray(fb.color)  # uint8 (h, w, 3) becomes an RGB image
    if ss > 1:
        img = img.resize((W, H), _BOX)
    if scene.look.get("dof"):
        img = _dof(img, fb.depth[::ss, ::ss][:H, :W], cam.focus_dist, scene.look["dof"])
    img = _post(img, scene.look)

    f = scene.fade_at(T)
    if f < 0.999:
        img = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), img, max(0.0, f))

    for t in scene.texts_at(T):
        if not t.text:
            continue
        text = t.text
        if scene.show_speaker and t.speaker:
            text = f"{t.speaker}: {text}"
        draw_text(img, text, scene.text_styles[t.style], scene.font_path, t.y, age=T - t.t0)
    return img


# ---- multiprocessing worker --------------------------------------------------

_W = {}


def _init_worker(path, width_scale, supersample):
    _W["scene"] = Scene.load(path, width_scale=width_scale, supersample=supersample)


def _work(idx):
    img = render_frame(_W["scene"], idx)
    return idx, img.tobytes()


# ---- ffmpeg ------------------------------------------------------------------

def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SceneError(
            "ffmpeg was not found on PATH. Install it (Windows: `winget install Gyan.FFmpeg`, "
            "macOS: `brew install ffmpeg`, Linux: your package manager), open a new terminal, "
            "and check `ffmpeg -version`. Or run with --frames-only to write PNG frames without it.")
    return exe


def ffmpeg_command(ffmpeg, scene, out_path, audio):
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{scene.width}x{scene.height}",
           "-r", str(scene.fps), "-i", "-"]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
            "-c:v", "libx264", "-preset", str(scene.export["preset"]), "-crf", str(scene.export["crf"]),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-movflags", "+faststart", "-r", str(scene.fps)]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += [str(out_path)]
    return cmd


# ---- pipeline ----------------------------------------------------------------

def render_scene(scene_path, out_path=None, *, preview=False, workers=None, start=None, end=None,
                 supersample=None, frames_only=False, save_frames=None, crf=None, preset=None,
                 progress=True):
    width_scale = 0.5 if preview else 1.0
    if preview and supersample is None:
        supersample = 1
    scene = Scene.load(scene_path, width_scale=width_scale, supersample=supersample)
    if crf is not None:
        scene.export["crf"] = crf
    if preset is not None:
        scene.export["preset"] = preset

    first = 0 if start is None else max(0, int(round(start * scene.fps)))
    last = scene.frame_count if end is None else min(scene.frame_count, int(round(end * scene.fps)))
    if first >= last:
        raise SceneError(f"empty frame range: start={start}s end={end}s, scene is {scene.duration:.2f}s")
    indices = list(range(first, last))

    save_dir = Path(save_frames) if save_frames else None
    if frames_only and not save_dir:
        save_dir = Path(out_path).with_suffix("") if out_path else Path("frames")
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    proc = None
    if not frames_only:
        if out_path is None:
            raise SceneError("an output path is required (use --out)")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = find_ffmpeg()
        audio = scene.audio_path if (scene.audio_path and scene.audio_path.exists()) else None
        if scene.audio_path and not audio:
            print(f"warning: audio file not found, exporting without audio: {scene.audio_path}", file=sys.stderr)
        if audio and (start is not None or end is not None):
            print("warning: audio is not trimmed to --start/--end; it will be cut at the video length", file=sys.stderr)
        proc = subprocess.Popen(ffmpeg_command(ffmpeg, scene, out_path, audio), stdin=subprocess.PIPE)

    n_workers = workers if workers else max(1, (os.cpu_count() or 2) // 2)
    n_workers = max(1, min(n_workers, len(indices)))
    t0 = time.time()
    done = 0
    W, H = scene.width, scene.height

    def sink(idx, raw):
        if save_dir:
            Image.frombytes("RGB", (W, H), raw).save(save_dir / f"frame_{idx:05d}.png")
        if proc:
            proc.stdin.write(raw)

    try:
        if n_workers == 1:
            for idx in indices:
                sink(idx, render_frame(scene, idx).tobytes())
                done += 1
                _progress(progress, done, len(indices), t0)
        else:
            ctx = mp.get_context("spawn")
            with ctx.Pool(n_workers, initializer=_init_worker,
                          initargs=(str(scene_path), width_scale, supersample)) as pool:
                for idx, raw in pool.imap(_work, indices, chunksize=2):
                    sink(idx, raw)
                    done += 1
                    _progress(progress, done, len(indices), t0)
    except BrokenPipeError:
        raise SceneError("ffmpeg closed the pipe early. Re-run without -loglevel quiet to see its error.")
    finally:
        if proc:
            try:
                proc.stdin.close()
            except Exception:
                pass
            code = proc.wait()
            if code != 0:
                raise SceneError(f"ffmpeg exited with code {code}")
    if progress:
        print()
    return out_path if proc else save_dir


def _progress(on, done, total, t0):
    if not on:
        return
    el = time.time() - t0
    rate = done / el if el > 0 else 0.0
    eta = (total - done) / rate if rate > 0 else 0.0
    sys.stdout.write(f"\rframe {done}/{total}  {rate:.2f} fps  elapsed {el:.0f}s  eta {eta:.0f}s   ")
    sys.stdout.flush()
