"""Frame rendering and video export."""
import math
import os
import random
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageChops

from . import engine as E
from .engine import Cam
from .figure import draw_pick
from .scene import Scene
from .track import is_color, parse_color

ART = {}


def art(name):
    """register static artwork: fn(img, cam, props, t)."""
    def deco(fn):
        ART[name] = fn
        return fn
    return deco


def col(v, alpha=1.0):
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        c = tuple(int(x) for x in v) + (255,) * (4 - len(v))
    else:
        c = parse_color(v)
    return c[:3] + (int(c[3] * min(max(alpha, 0.0), 1.0)),)


def _layered(img, fn, alpha, blend):
    if alpha >= 0.999 and blend == "normal":
        fn(img)
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    fn(layer)
    if alpha < 0.999:
        a = layer.getchannel("A").point(lambda v: int(v * max(alpha, 0.0)))
        layer.putalpha(a)
    if blend == "add":
        rgb = ImageChops.add(img.convert("RGB"), Image.composite(layer.convert("RGB"), Image.new("RGB", img.size), layer.getchannel("A")))
        img.paste(rgb.convert("RGBA"))
    else:
        img.alpha_composite(layer)


_SPRITES = {}


def _sprite(path):
    if path not in _SPRITES:
        _SPRITES[path] = Image.open(path).convert("RGBA")
    return _SPRITES[path]


def _rot_pts(pts, c, deg, scale=1.0):
    r = math.radians(deg)
    cs, sn = math.cos(r), math.sin(r)
    return [(c[0] + (x * cs - y * sn) * scale, c[1] + (x * sn + y * cs) * scale) for x, y in pts]


def draw_kind(img, kind, p, cam, t, scene, override=None):
    """draw one object of `kind` with evaluated props p."""
    if override:
        p = dict(p, **override)
    a = p["alpha"]
    ow = p.get("ow", 2)
    if kind == "rect":
        w, h = p["w"], p["h"]
        if p["anchor"] == "topleft":
            cx, cy = p["x"] + w / 2, p["y"] + h / 2
        else:
            cx, cy = p["x"], p["y"]
        pts = _rot_pts([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)], (cx, cy), p["rot"])
        E.poly(img, pts, cam, fill=col(p["fill"]), outline=col(p["outline"]), width=ow)
    elif kind == "circle":
        E.circle(img, (p["x"], p["y"]), p["r"], cam, fill=col(p["fill"]), outline=col(p["outline"]), width=ow)
    elif kind == "ellipse":
        E.ellipse(img, (p["x"], p["y"]), p["rx"], p["ry"], cam, fill=col(p["fill"]), outline=col(p["outline"]), width=ow, rot=math.radians(p["rot"]))
    elif kind == "line":
        E.line(img, (p["x"], p["y"]), (p["x2"], p["y2"]), cam, col(p["color"]), p["width"])
    elif kind == "poly":
        pts = _rot_pts(p["points"], (p["x"], p["y"]), p["rot"], p["scale"])
        E.poly(img, pts, cam, fill=col(p["fill"]), outline=col(p["outline"]), width=ow)
    elif kind == "text":
        g = p["grad"]
        s_ = str(p["text"])
        if p.get("reveal") is not None:
            s_ = s_[:max(0, int(p["reveal"]))]
        if not s_:
            return
        E.text(img, s_, (p["x"], p["y"]), p["size"], cam, fill=col(p["fill"]), outline=col(p["outline"]), ow=ow,
               track=p["track"], weight=p["weight"], align=p["align"], grad=tuple(g) if g else None, shadow=col(p["shadow"]), width=p["width"], alpha=a)
    elif kind == "glow":
        E.glow(img, (p["x"], p["y"]), p["r"], cam, col(p["color"])[:3], p["strength"] * a, p["power"])
    elif kind == "ring":
        x, y = cam.p(p["x"], p["y"])
        R = cam.k(p["r"])
        ImageDraw.Draw(img, "RGBA").ellipse([x - R, y - R, x + R, y + R], outline=col(p["color"]), width=max(1, int(round(cam.k(p["w"])))))
    elif kind == "rays":
        for i in range(int(p["n"])):
            ang = math.radians(p["rot"] + 360.0 * i / p["n"])
            d = (math.cos(ang), math.sin(ang))
            E.line(img, (p["x"] + d[0] * p["r0"], p["y"] + d[1] * p["r0"]), (p["x"] + d[0] * p["r1"], p["y"] + d[1] * p["r1"]),
                   cam, col(p["color"]), p["w"])
    elif kind == "star":
        E.star(img, (p["x"], p["y"]), p["r"], cam, col(p["color"]), p["thin"])
    elif kind == "sprite":
        path = p["file"] if os.path.isabs(p["file"]) else os.path.join(scene.base_dir, p["file"])
        im = _sprite(path)
        k = cam.z * E.S * p["scale"]
        im2 = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
        if p["rot"]:
            im2 = im2.rotate(-p["rot"], expand=True, resample=Image.BICUBIC)
        cx, cy = cam.p(p["x"], p["y"])
        img.alpha_composite(im2, (int(cx - im2.width / 2), int(cy - im2.height / 2))) if cx - im2.width / 2 >= 0 and cy - im2.height / 2 >= 0 else img.paste(im2, (int(cx - im2.width / 2), int(cy - im2.height / 2)), im2)
    elif kind == "pick":
        draw_pick(img, (p["x"], p["y"]), p["angle"], p["len"], cam)
    elif kind == "phone":
        from .items import draw_phone
        draw_phone(img, p, cam, t, scene)
    elif kind == "burst":
        _burst(img, p, cam, t, scene)
    elif kind == "pulse":
        _pulse(img, p, cam, t, scene)
    elif kind == "art":
        fn = ART.get(p["name"])
        if fn is None:
            raise KeyError(f"unknown art '{p['name']}'. Registered: {', '.join(ART)}")
        fn(img, cam, p, t)


def _origin(at, te, scene):
    if isinstance(at, str):
        return scene.resolve(at, te)
    return at


def _burst(img, p, cam, t, scene):
    times = scene.times(p["times"])
    for ei, te in enumerate(times):
        age = t - te
        if age < 0 or age > p["life"]:
            continue
        ox, oy = _origin(p["at"], te, scene)
        rng = random.Random(p["seed"] * 7919 + ei)
        c = p["color"]
        for i in range(int(p["n"])):
            sp = rng.uniform(*p["speed"])
            an = math.radians(rng.uniform(*p["angle"]))
            sz = rng.uniform(*p["size"])
            life = p["life"] * rng.uniform(0.6, 1.0)
            if age > life:
                continue
            x = ox + math.cos(an) * sp * age
            y = oy + math.sin(an) * sp * age + 0.5 * p["gravity"] * age * age
            f = 1 - age / life
            E.circle(img, (x, y), sz * (0.6 + 0.4 * f), cam, fill=col(c if isinstance(c, str) else c[i % len(c)], f))


def _pulse(img, p, cam, t, scene):
    for te in scene.times(p["times"]):
        age = t - te
        if age < 0 or age > p["dur"]:
            continue
        f = 1 - age / p["dur"]
        ox, oy = _origin(p["at"], te, scene)
        for r, c, s in zip(p["r"], p["color"], p["strength"]):
            E.glow(img, (ox, oy), r, cam, col(c)[:3], s * f, 1.3)


def draw_actor(img, actor, cam, t, scene):
    pose, anch, p = actor.solve(t)
    hooks = {}
    for pname, ang_key, hand_key in (("prop", "prop_angle_world", p["prop_hand"]), ("prop_l", "prop_l_angle_world", "l")):
        obj = scene.objects.get(p[pname]) if p[pname] else None
        if obj is None:
            continue
        if hand_key == "auto":
            hand_key = "grip" if p["grip_w"] >= 0.5 else "r"
        g = anch["grip"] if hand_key == "grip" else anch["hand_" + hand_key]
        arm = "arm_r" if hand_key in ("r", "grip") else "arm_l"
        if hand_key == "grip":
            arm = "arm_r" if pose["depth"]["arm_r"] <= pose["depth"]["arm_l"] else "arm_l"
        hp = obj.props(t)
        ang = anch[ang_key]

        def draw_it(base, obj=obj, hp=hp, g=g, ang=ang):
            draw_kind(base, obj.kind, hp, cam, t, scene, override=dict(x=g[0], y=g[1], angle=ang, rot=ang))
        hooks[arm] = draw_it
    if p["shadow"]:
        sh = 1.0 - min(p["lift"] / 120.0, 0.8)
        E.ellipse(img, (p["x"], p["ground"]), 30 * sh, 5.5 * sh, cam, fill=(0, 0, 0, int(55 * sh)))
    from .figure3d import draw_figure
    pose["tint"] = _tint(p["tint"])
    from .faces import talk_amount
    talk = talk_amount(t, p["talk_seed"]) if p["talk"] else None
    draw_figure(img, pose, cam, face=p["expr"], talk_open=talk, faces=scene.faces, item_hooks=hooks)


def _tint(v):
    if v is None:
        return None
    if isinstance(v, str):
        c = parse_color(v)
        return tuple(x / 255.0 for x in c[:3])
    return tuple(v)


def render_frame(scene, t, S=None):
    c = scene.canvas
    E.S = S or c["scale"]
    W, H = int(c["w"] * E.S), int(c["h"] * E.S)
    img = Image.new("RGBA", (W, H), col(c["bg"]))
    cv = scene.cam_at(t)
    world = Cam(cv["zoom"], cv["cx"], cv["cy"], cv["tx"], cv["ty"])
    screen = Cam(1.0, c["w"] / 2, c["h"] / 2, c["w"] / 2, c["h"] / 2)
    held = {a.params(t)["prop"] for a in scene.actors.values()}
    items = []
    for i, o in enumerate(scene.objects.values()):
        if o.name in scene.held_names or not o.visible(t):
            continue
        items.append((o.track.get("z", t, 0), i, "obj", o))
    for j, a in enumerate(scene.actors.values()):
        items.append((a.params(t)["z"], 1000 + j, "actor", a))
    items.sort(key=lambda it: (it[0], it[1]))
    for _, _, typ, thing in items:
        if typ == "actor":
            draw_actor(img, thing, world, t, scene)
            continue
        p = thing.props(t)
        cam = screen if p["space"] == "screen" else world
        a = p["alpha"] if thing.kind in ("rect", "circle", "ellipse", "line", "poly", "ring", "rays", "star", "sprite", "pick", "art", "burst") else 1.0
        if a <= 0.001 and thing.kind not in ("burst", "pulse"):
            continue
        blend = "add" if p["blend"] == "add" else "normal"
        _layered(img, lambda im, th=thing, pp=p, cm=cam: draw_kind(im, th.kind, pp, cm, t, scene), a if thing.kind != "text" else 1.0, blend)
    return img


def frame_rgb(scene, n):
    """final frame n as an RGB PIL image at canvas size, with motion blur (canvas.blur sub-frames)."""
    c = scene.canvas
    blur = int(c["blur"])
    t0 = n / scene.fps
    if blur <= 1:
        im = render_frame(scene, t0)
    else:
        acc = None
        for i in range(blur):
            ti = t0 + ((i + 0.5) / blur - 0.5) / scene.fps
            arr = np.asarray(render_frame(scene, max(ti, 0.0)).convert("RGB"), dtype=np.float32)
            acc = arr if acc is None else acc + arr
        im = Image.fromarray((acc / blur).astype(np.uint8))
    return im.convert("RGB").resize((c["w"], c["h"]), Image.LANCZOS)


_G = {}


def _init(path):
    _G["scene"] = Scene.load(path)


def _work(n):
    return n, frame_rgb(_G["scene"], n).tobytes()


def render_video(path, out, start=None, end=None, workers=2, png_dir=None, crf=18):
    scene = Scene.load(path)
    c = scene.canvas
    n0 = int(round((start or 0) * scene.fps))
    n1 = int(round((end if end is not None else scene.duration) * scene.fps))
    frames = list(range(n0, n1))
    ff = None
    if out:
        ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{c['w']}x{c['h']}",
                               "-r", str(scene.fps), "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                               "-c:v", "libx264", "-crf", str(crf), "-colorspace", "bt709", "-color_primaries", "bt709",
                               "-color_trc", "bt709", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    if png_dir:
        os.makedirs(png_dir, exist_ok=True)
    with Pool(workers, initializer=_init, initargs=(path,)) as pool:
        for k, (n, raw) in enumerate(pool.imap(_work, frames, chunksize=2)):
            if ff:
                ff.stdin.write(raw)
            if png_dir:
                Image.frombytes("RGB", (c["w"], c["h"]), raw).save(os.path.join(png_dir, f"f{n:04d}.png"))
            if k % 15 == 0:
                print(f"frame {n}/{n1}", file=sys.stderr, flush=True)
    if ff:
        ff.stdin.close()
        ff.wait()
