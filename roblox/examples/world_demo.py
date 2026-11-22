"""Quick isometric painter's-algorithm preview of world.town_square(). Writes out/world_town.png.

Flat shading with the sun from world.lighting(); back faces are culled using the triangle winding,
so inverted winding shows up as holes. No GL needed.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from r6reel import world  # noqa: E402

WIDTH, HEIGHT = 1000, 700
MARGIN = 30

# Camera sits at +X, +Y, +Z looking at the origin, so the -Z fronts of buildings are seen from behind.
# Buildings on the far side are rotated to face the plaza (+Z), which this camera can see.
TO_CAMERA = np.array([1.0, 0.8, 1.0])
TO_CAMERA /= np.linalg.norm(TO_CAMERA)
FORWARD = -TO_CAMERA
RIGHT = np.cross(FORWARD, [0.0, 1.0, 0.0])
RIGHT /= np.linalg.norm(RIGHT)
UP = np.cross(RIGHT, FORWARD)


def _gradient(top, bottom):
    t = np.linspace(0.0, 1.0, HEIGHT)[:, None]
    col = (1 - t) * np.array(top) + t * np.array(bottom)
    img = np.repeat(col[:, None, :], WIDTH, axis=1)
    return (img * 255).astype(np.uint8)


def collect(items, sun_dir):
    """Return screen polygons with colours, sorted for painter's order."""
    to_sun = -np.asarray(sun_dir, float)
    polys, keys, colors = [], [], []
    for it in items:
        m = it.model
        pos = it.mesh.positions.astype(float) @ m[:3, :3].T + m[:3, 3]
        max_y = pos[:, 1].max()
        flat = max_y < 0.6  # ground, roads, plaza and kerbs: draw first, by height
        tri = pos[it.mesh.indices]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        length = np.linalg.norm(n, axis=1)
        ok = length > 1e-9
        n = n[ok] / length[ok][:, None]
        tri = tri[ok]
        facing = n @ TO_CAMERA > 0
        n, tri = n[facing], tri[facing]
        if len(tri) == 0:
            continue
        lam = np.clip(n @ to_sun, 0.0, 1.0)
        shade = 0.45 + 0.55 * lam
        base = np.asarray(it.color, float)
        col = np.clip(base[None, :] * shade[:, None], 0, 1)
        depth = tri.mean(axis=1) @ TO_CAMERA
        sx = tri @ RIGHT
        sy = -(tri @ UP)
        polys.append(np.stack([sx, sy], axis=-1))
        keys.append(np.stack([np.full(len(tri), 0 if flat else 1),
                              np.full(len(tri), max_y) if flat else depth], axis=1))
        colors.append(col)
    polys = np.concatenate(polys)
    keys = np.concatenate(keys)
    colors = np.concatenate(colors)
    order = np.lexsort((keys[:, 1], keys[:, 0]))
    return polys[order], colors[order]


def render(town, out_path):
    items = town.to_draw_items()
    polys, colors = collect(items, world.World().sun_dir)
    lo = polys.reshape(-1, 2).min(axis=0)
    hi = polys.reshape(-1, 2).max(axis=0)
    scale = min((WIDTH - 2 * MARGIN) / (hi[0] - lo[0]), (HEIGHT - 2 * MARGIN) / (hi[1] - lo[1]))
    offset = np.array([WIDTH / 2, HEIGHT / 2]) - (lo + hi) / 2 * scale

    img = Image.fromarray(_gradient((0.35, 0.66, 1.0), (0.81, 0.91, 1.0)))
    draw = ImageDraw.Draw(img)
    for tri, col in zip(polys, colors):
        pts = [tuple(p) for p in tri * scale + offset]
        rgb = tuple(int(c * 255) for c in col)
        draw.polygon(pts, fill=rgb)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path)
    print(f"{len(items)} parts, {len(polys)} triangles drawn -> {out_path}")


if __name__ == "__main__":
    render(world.town_square(), os.path.join(ROOT, "out", "world_town.png"))
