#!/usr/bin/env python3
"""Turn Roblox face thumbnails (3D head renders) into flat RGBA decals (features only).
usage: decalize_faces.py [id ...]  -> assets/faces/decal/<id>.png (256x256)"""
import json, sys, os
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
ROOT = os.path.join(os.path.dirname(__file__), "..", "assets", "faces")
OUT = os.path.join(ROOT, "decal")

def rgb2lab(a):
    a = a / 255.0
    a = np.where(a > 0.04045, ((a + 0.055) / 1.055) ** 2.4, a / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = a @ m.T / np.array([0.95047, 1, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)

def decalize(path, size=256):
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)[..., 3]
    ys, xs = np.where(a > 128)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1 - x0, y1 - y0
    s = min(w, h) * 0.86                       # central face square
    cx, cy = (x0 + x1) / 2, y0 + h * 0.54
    box = (int(cx - s / 2), int(cy - s / 2), int(cx + s / 2), int(cy + s / 2))
    crop = im.crop(box).resize((size, size), Image.LANCZOS)
    arr = np.asarray(crop).astype(np.float32)
    rgb, al = arr[..., :3], arr[..., 3] / 255
    lab = rgb2lab(rgb)
    # base skin = median Lab of opaque pixels in the outer ring of the crop (cheeks/forehead)
    yy, xx = np.mgrid[:size, :size]
    ring = ((np.abs(xx - size / 2) > size * 0.34) | (np.abs(yy - size / 2) > size * 0.34)) & (al > 0.9)
    if ring.sum() < 200: ring = al > 0.9
    base = np.median(lab[ring], axis=0)
    # smooth illumination: blur Lab of pixels close to base, normalise L only
    d = np.linalg.norm(lab - base, axis=-1)
    skin = d < 14
    Lb = gaussian_filter(np.where(skin, lab[..., 0], base[0]).astype(np.float32), 18)
    lab2 = lab.copy(); lab2[..., 0] = lab[..., 0] - (np.asarray(Lb) - base[0])
    d = np.linalg.norm(lab2 - base, axis=-1)
    alpha = np.clip((d - 9) / 12, 0, 1) * al
    # rounded-square mask to drop silhouette edges
    r = (np.maximum(np.abs(xx - size / 2), np.abs(yy - size / 2)) / (size / 2))
    alpha *= np.clip((0.96 - r) / 0.06, 0, 1)
    out = np.dstack([rgb, alpha * 255]).astype(np.uint8)
    cover = float((alpha > 0.5).mean())
    return Image.fromarray(out, "RGBA"), cover, base

if __name__ == "__main__":
    idx = json.load(open(os.path.join(ROOT, "index.json")))
    ids = set(sys.argv[1:]) or {x["id"] for x in idx}
    os.makedirs(OUT, exist_ok=True)
    cov = {}
    for x in idx:
        if x["id"] in ids and x["kind"] == "thumbnail":
            try:
                im, c, base = decalize(os.path.join(ROOT, x["file"]))
                im.save(os.path.join(OUT, x["id"] + ".png")); cov[x["id"]] = c
            except Exception as e:
                print("fail", x["id"], e)
    json.dump(cov, open(os.path.join(OUT, "_coverage.json"), "w"))
    print(len(cov), "decals")
