"""Contact sheet of every clip (3 time samples) with a tiny numpy/PIL painter's-algorithm rasterizer.
Usage: python examples/rig_demo.py [--view 3q|side|front] [--only name,name] [--out out/rig_clips.png]"""
import sys, os, math, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from PIL import Image, ImageDraw
from r6reel import rig, clips
from r6reel.avatar import Avatar
from r6reel.anim import Animator

CELL_W, CELL_H, SS = 110, 150, 2


def view_matrix(view):
    yaw, pitch = {"3q": (-35, 14), "side": (-90, 8), "front": (0, 8)}[view]
    return rig.euler_to_matrix(0, -yaw, 0)[:3, :3].T, pitch


def render_cell(items_fn, view="3q", cx=0.0, scale=17.0, cy=2.6):
    W, H = CELL_W * SS, CELL_H * SS
    im = Image.new("RGB", (W, H), (200, 225, 250))
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(H * 0.86), W, H], fill=(120, 170, 100))
    yaw, pitch = {"3q": (145, 14), "side": (90, 8), "front": (180, 8)}[view]
    R = (rig.euler_to_matrix(pitch, 0, 0) @ rig.euler_to_matrix(0, yaw, 0))[:3, :3]
    light = np.array([0.4, 0.8, 0.5]); light /= np.linalg.norm(light)
    tris = []
    for it in items_fn:
        m = it.mesh
        P = (np.c_[m.positions, np.ones(len(m.positions))] @ it.model.T)[:, :3]
        N = m.normals @ np.linalg.inv(it.model[:3, :3])
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        col = np.array(it.color, float)
        if it.texture is not None:
            tex = np.asarray(it.texture.convert("RGB"), float) / 255
            uv = m.uvs
            tx = np.clip((uv[:, 0] * (tex.shape[1] - 1)).astype(int), 0, tex.shape[1] - 1)
            ty = np.clip(((1 - uv[:, 1]) * (tex.shape[0] - 1)).astype(int), 0, tex.shape[0] - 1)
            vcol = tex[ty, tx] * col
        else:
            vcol = np.tile(col, (len(P), 1))
        V = P @ R.T
        for tri in m.indices:
            a, b, c = V[tri]
            nz = np.cross(b - a, c - a)[2]
            if nz >= 0:   # camera looks down -Z in view space; visible tris face +Z... use sign test
                pass
            tris.append((tri, V, N, vcol, it.transparency))
    out = []
    for tri, V, N, vcol, tr in tris:
        p = V[tri]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if n[2] <= 0:        # back-facing (camera at +Z looking toward -Z in view space)
            continue
        depth = p[:, 2].mean()
        sh = 0.45 + 0.55 * max(0.0, float(np.dot((N[tri].mean(0) @ R.T), light)))
        c = vcol[tri].mean(0) * sh
        out.append((depth, p, c, tr))
    out.sort(key=lambda o: o[0])
    for _, p, c, tr in out:
        pts = [(W / 2 + (q[0] - cx) * scale * SS, H * 0.86 - (q[1] - 0) * scale * SS) for q in p]
        d.polygon(pts, fill=tuple(int(max(0, min(1, v)) * 255) for v in c))
    return im.resize((CELL_W, CELL_H), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", default="3q"); ap.add_argument("--only", default="")
    ap.add_argument("--out", default="out/rig_clips.png"); ap.add_argument("--cols", type=int, default=3)
    a = ap.parse_args()
    names = [n for n in a.only.split(",") if n] or clips.names()
    av = Avatar.noob(name="Demo", hair="bun", shirt_color="#e8472b", pants_color="#2b3a67") if False else \
        Avatar(name="Demo", hair="spiky", shirt_color="#d9483b", pants_color="#2b3a67", accessories=["backpack:#2255aa"])
    rows = math.ceil(len(names) / a.cols)
    sheet = Image.new("RGB", (a.cols * CELL_W * 3, rows * (CELL_H + 12)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, n in enumerate(names):
        c = clips.get(n)
        an = Animator(av, base=None, noise=0.0)
        an.play(c, at=0.0, fade_in=0.0, fade_out=0.0, loop=c.loop, until=1e9)
        r, col = divmod(i, a.cols)
        x0, y0 = col * CELL_W * 3, r * (CELL_H + 12)
        d.text((x0 + 3, y0 + 1), n, fill=(0, 0, 0))
        dur = c.duration
        for k, f in enumerate((0.1, 0.45, 0.8) if c.loop or True else ()):
            t = dur * f
            items = an.draw_items(t)
            pose, cf = an.pose_at(t)
            cell = render_cell(items, a.view)
            sheet.paste(cell, (x0 + k * CELL_W, y0 + 12))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    sheet.save(a.out)
    print("saved", a.out, sheet.size)


def gl_demo(path="out/rig_gl.png"):
    """Optional: real renderer pass (skipped if r6reel.renderer / GL unavailable)."""
    try:
        from r6reel.renderer import Renderer, CameraState, Lighting
        r = Renderer(360, 480, samples=2)
    except Exception as e:
        print("GL render skipped:", e); return
    av = Avatar(name="GL", hair="spiky", shirt_color="#d9483b", pants_color="#2b3a67")
    frames = []
    for clip, t in (("wave", 0.6), ("cheer", 0.9), ("run", 0.2)):
        a = Animator(av); a.play(clip, at=0)
        frames.append(r.render(a.draw_items(t), CameraState(eye=(2.5, 4.5, -9), target=(0, 3, 0), fov_y=40), Lighting()))
    Image.fromarray(np.concatenate(frames, 1)).save(path); print("saved", path)


if __name__ == "__main__":
    main()
    gl_demo()
