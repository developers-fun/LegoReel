"""Renderer demo: writes out/renderer_demo.png and a 2 s orbiting out/renderer_demo.mp4.

Uses only a tiny local box/sphere generator (primitives module belongs to another agent).
"""
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from r6reel.mesh import Mesh
from r6reel.renderer import Renderer, DrawItem, CameraState, Lighting, PostFx
from r6reel.video import VideoWriter
from r6reel.util import compose, translate, scale as mscale


def box(size=(1, 1, 1)):
    sx, sy, sz = (s / 2 for s in size)
    faces = [((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
             ((1, 0, 0), (0, 0, -1), (0, 1, 0)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
             ((0, 1, 0), (1, 0, 0), (0, 0, -1)), ((0, -1, 0), (1, 0, 0), (0, 0, 1))]
    P, N, U, I = [], [], [], []
    for n, u, v in faces:
        n, u, v = map(np.array, (n, u, v))
        o = len(P)
        for a, b, uv in ((-1, -1, (0, 0)), (1, -1, (1, 0)), (1, 1, (1, 1)), (-1, 1, (0, 1))):
            P.append((n + u * a + v * b) * (sx, sy, sz)); N.append(n); U.append(uv)
        I += [(o, o + 1, o + 2), (o, o + 2, o + 3)]
    return Mesh(np.array(P), np.array(N), np.array(U), np.array(I))


def sphere(r=0.5, seg=32):
    P, N, U, I = [], [], [], []
    for i in range(seg + 1):
        th = math.pi * i / seg
        for j in range(seg + 1):
            ph = 2 * math.pi * j / seg
            n = (math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph))
            P.append(np.array(n) * r); N.append(n); U.append((j / seg, 1 - i / seg))
    for i in range(seg):
        for j in range(seg):
            a = i * (seg + 1) + j; b = a + seg + 1
            I += [(a, a + 1, b), (a + 1, b + 1, b)]
    return Mesh(np.array(P), np.array(N), np.array(U), np.array(I))


def build_scene():
    B, S = box(), sphere()
    items = [DrawItem(B, compose((0, -0.5, 0), (0, 0, 0), (120, 1, 120)), (0.35, 0.72, 0.25), material="grass", key="ground")]
    # path
    items.append(DrawItem(B, compose((0, 0.02, 0), (0, 0, 0), (6, 0.1, 60)), (0.75, 0.72, 0.68), material="concrete"))
    cols = [(0.95, 0.25, 0.2), (0.2, 0.5, 0.95), (1.0, 0.8, 0.1), (0.3, 0.8, 0.4), (0.7, 0.3, 0.9)]
    rng = np.random.default_rng(3)
    for i in range(5):
        h = 2 + i * 0.8
        items.append(DrawItem(B, compose((-6 + i * 3.0, h / 2, -2 + (i % 2) * 3), (0, 15 * i, 0), (2.4, h, 2.4)), cols[i]))
    items.append(DrawItem(B, compose((0, 3, -9), (0, 20, 0), (8, 6, 1)), (0.7, 0.25, 0.2), material="brick"))
    items.append(DrawItem(S, compose((4.5, 1.5, -5.5), (0, 0, 0), (3, 3, 3)), (0.95, 0.35, 0.65), material="smooth"))
    items.append(DrawItem(S, compose((-3, 1.2, 3), (0, 0, 0), (2.4, 2.4, 2.4)), (0.9, 0.9, 1.0), material="metal"))
    items.append(DrawItem(B, compose((0, 1.5, 3.5), (0, 30, 0), (3, 3, 0.2)), (0.6, 0.85, 1.0), material="glass"))
    items.append(DrawItem(S, compose((6, 1.0, 4), (0, 0, 0), (1.5, 1.5, 1.5)), (0.2, 1.0, 0.6), material="neon"))
    for k in range(40):  # filler
        x, z = rng.uniform(-30, 30, 2)
        if abs(x) < 8 and abs(z) < 8: continue
        items.append(DrawItem(B, compose((x, 1, z), (0, rng.uniform(0, 90), 0), (2, 2, 2)), tuple(rng.uniform(0.3, 1, 3))))
    return items


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
    os.makedirs(out, exist_ok=True)
    quick = "--preview" in sys.argv
    W, H = (360, 640) if quick else (1080, 1920)
    r = Renderer(W, H, samples=2 if quick else 4, quality="preview" if quick else "final")
    items = build_scene()
    light = Lighting(sun_dir=(-0.5, -0.8, -0.35), shadow_extent=30)
    fx = PostFx()

    def cam_at(a, d=20, h=8):
        return CameraState(eye=(math.sin(a) * d, h, math.cos(a) * d), target=(0, 1.5, 0), fov_y=60)

    t0 = time.time()
    img = r.render(items, cam_at(math.radians(25)), light, fx)
    print(f"first frame {time.time()-t0:.2f}s, {W}x{H}, {len(items)} items")
    from PIL import Image
    Image.fromarray(img).save(os.path.join(out, "renderer_demo.png"))
    t0 = time.time()
    frames = 60
    with VideoWriter(os.path.join(out, "renderer_demo.mp4"), W, H, fps=30) as vw:
        for f in range(frames):
            a = math.radians(25) + f / frames * math.radians(90)
            vw.write(r.render(items, cam_at(a), light, fx))
    print(f"video {frames} frames in {time.time()-t0:.1f}s ({(time.time()-t0)/frames:.2f}s/frame)")
    r.close()


if __name__ == "__main__":
    main()
