import argparse
import json
import sys

from PIL import Image, ImageDraw

from .scene import Scene, KINDS, COMMON, CANVAS_DEFAULT
from .skeleton import DEFAULTS
from .poses import POSES, LOOPS
from .track import SceneError
from .ease import EASES

DOCS = """\
STICKREEL: 2D stick-figure animation from a JSON scene. Everything is in seconds and pixels of the canvas
(default 576 x 1024, y points DOWN). You write keyframes; the engine does IK, grounding, easing, loops, effects.

SCENE = {"canvas":{...}, "poses":{}, "loops":{}, "camera":{...}, "actors":{...}, "objects":{...}, "plugins":[]}

KEYFRAMES (same for actors, objects and the camera)
  "keys": [ {"t":0, "x":100}, {"t":1.5, "x":400, "ease":"out"} ]
  A key sets values that ARRIVE at time t. Anything a key does not mention keeps its last value. "ease" shapes the
  segment that ENDS at that key. Eases: {eases}.
  Numbers, [x,y] lists and "#rrggbb" colours blend; text/bool/null switch when the key time is reached.

ACTOR (the stick figure, a small 3D rig). Angles in degrees:
  yaw: 0 = profile facing right, 90 = facing the camera, 180 = profile facing left, 270/-90 = back to camera.
       yaw tweens: 0 -> 180 turns through the FRONT, 0 -> -180 through the BACK. "face":"left"/"right" = yaw 180/0
       (add "ease":"step" to flip instantly).
  limb angle 0 = hanging down, 90 = pointing forward, 180 = straight up, -90 = backward.
  x (hip x), ground (floor y; the hip height is solved so the lowest foot touches it), lift (jump height)
  lean (torso, + forward), head (extra tilt), rot (whole body pitch about the hip), shadow (true/false)
  arm_r/arm_l = [swing, elbow_bend, out], leg_r/leg_l = [swing, knee_bend, out]  (r = the figure's right, near at yaw 0)
  "pose": "{poses}"  -> sets all limb angles at once; list any param next to it to override.
  FACE: "expr": "{faces}" (doodled, wraps around the head, hidden from behind); "talk": true flaps the mouth.
        Add your own: top-level "faces": {{"name": {{"parts":[["dot",u,v,rx,ry],["line",[[u,v],..],w],...], "mouth":[...]}}}}
        (head units: u -1..1 across, v down, radius 1; see stickreel/faces.py).
  Reach (IK, screen space, works from any yaw): hand_r_at / hand_l_at / foot_r_at / foot_l_at = [x,y] | "@name" | "@actor.anchor";
  ..._rel = [dx,dy] from the hip (dx forward); null releases. grip_rel = [dx,dy] puts BOTH hands on one point (tool grip).
  anchors: head neck hip shoulder_r/l hand_r hand_l grip foot_r foot_l elbow_* knee_* tip (item tip)
  ITEMS: any object can be held. "prop": "objname", "prop_hand": "auto"|"r"|"l"|"grip", "prop_angle" (0 = forward,
  -90 = up, in facing space; the item's top/tip points that way). "prop_l"/"prop_l_angle" = a second item in the left hand.
  Item kinds made for this: "pick", "phone" (video: path, video_start: scene time it starts, video_speed, loop,
  screen_color; key "video" to swap what plays), plus rect, circle, sprite (PNG), text. Held objects are not drawn on their own.
  "anim": a loop name. Built in: {loops}. Loops play on top of (add) or instead of (replace) the keys, blend in over
  anim_blend seconds, and anim:null stops them. walk/run are distance-locked: feet do not slide whatever the x speed.
  "hits": [t,t,...] next to "anim":"chop" times each tool contact exactly; the loop is retimed to land on them.
  Hit times become events "actor.hit" that effects can subscribe to.
  tint: [r,g,b] multipliers or "#rrggbb" colours the figure (e.g. gold).

OBJECTS  {{"kind": ..., props..., "keys": [...]}}   kinds and defaults:
{kinds}
  common: {common}
  follow:"actor.anchor" + offset:[dx,dy] pins an object to a point (labels over heads).
  space:"screen" ignores the camera (HUD, text, fades). blend:"add" for light. show:[t0,t1] visible window.
  grow: {{"prop":"w","times":"you.hit","by":6,"dur":0.1}} makes a prop step up on every hit.
  burst/pulse take "times": [..] or "actor.hit" and "at": [x,y] or "actor.tip" (position is read at each event time).
  held objects (named in an actor "prop") are drawn in the hand, not on their own.
CAMERA {{"zoom":1,"cx":288,"cy":512, "keys":[...]}}: zoom about the world point (cx,cy), which sits at screen centre.
CANVAS defaults {canvas}; blur=4 gives motion blur (4 sub-frames) for fast action.
PLUGINS: "plugins":["module"] imports python that registers artwork with @render.art("name"); use {{"kind":"art","name":...}}.

SOUND: scene "audio": {"master":0.9,"music":{"file":..,"gain":.25,"fade_out":1},"cues":[{"sfx":"thunk","times":"you.hit","gain":.8,"pitch_jitter":.06},
  {"sfx":"boom","t":8.0},{"sfx":"tick","times":{"from":9.4,"to":9.8,"every":0.034},"gain":.3},{"file":"clap.mp3","t":3}]}. Built-in sounds are synthesised
  (thunk whoosh dirt clink coins ding sparkle riser boom shimmer tick pop step thump), no files or licences. times: [s..] | "actor.hit" | "actor.step"
  (footfalls of walk/run) | {from,to,every}. `render` muxes the mix in automatically (--no-audio to skip).

COMMANDS
  python -m stickreel validate scene.json        errors come with did-you-mean hints
  python -m stickreel sheet scene.json --times 0,0.5,1 [--out sheet.png]      LOOK at frames before rendering video
  python -m stickreel compare scene.json --ref REFDIR --frames 1,60,120 [--crop x0,y0,x1,y1] [--zoom .5]   reference | mine | blend
  python -m stickreel poses [--out poses.png]    all named poses, then a turnaround and a face sheet next to it
  python -m stickreel sfx [name] [--pitch 1.2] [--out x.wav]    list or write the built-in synthesised sounds
  python -m stickreel audio scene.json --out mix.wav            mix just the sound (no video)
  python -m stickreel render scene.json --out out.mp4 [--start 0 --end 3] [--workers 4] [--png dir]
WORKFLOW: write the scene with generous gaps, `sheet` it, fix what looks wrong, then render. Author a hit loop once and time
it with "hits"; do not key every frame.
"""


def docs_text():
    from .faces import FACES
    kinds = "\n".join(f"    {k}: " + ", ".join(f"{p}={v!r}" for p, v in d.items()) for k, d in KINDS.items())
    vals = dict(eases=", ".join(EASES), poses=" | ".join(POSES), faces=" | ".join(FACES), loops=", ".join(LOOPS),
                kinds=kinds, common=", ".join(f"{k}={v!r}" for k, v in COMMON.items()), canvas=str(CANVAS_DEFAULT))
    out = DOCS
    for k, v in vals.items():
        out = out.replace("{" + k + "}", v)
    return out.replace("{{", "{").replace("}}", "}")


def sheet(scene, times, out, cols=None):
    from .render import frame_rgb
    c = scene.canvas
    cols = cols or min(len(times), 6)
    rows = (len(times) + cols - 1) // cols
    W = 288
    H = int(W * c["h"] / c["w"])
    sh = Image.new("RGB", (W * cols, H * rows), "black")
    for i, t in enumerate(times):
        im = frame_rgb(scene, int(round(t * scene.fps))).resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 52, 14], fill="black")
        d.text((3, 2), f"{t:.2f}s", fill="yellow")
        sh.paste(im, ((i % cols) * W, (i // cols) * H))
    sh.save(out)
    print("wrote", out)


def compare(scene, ref_dir, frames, out, crop=None, zoom=0.5, scale=1.0):
    """reference frame | my render | 50% blend. ref_dir holds f001.png... (ffmpeg -i ref.mp4 f%03d.png); frames are 1-based."""
    import os
    from .render import frame_rgb
    scene.canvas["scale"] = scale
    scene.canvas["blur"] = 1
    W, H = scene.canvas["w"], scene.canvas["h"]
    box = tuple(int(v) for v in crop.split(",")) if crop else (0, 0, W, H)
    cw, ch = box[2] - box[0], box[3] - box[1]
    rows = []
    for n in frames:
        ref = Image.open(os.path.join(ref_dir, f"f{n:03d}.png")).convert("RGB").resize((W, H))
        mine = frame_rgb(scene, n - 1)
        row = Image.new("RGB", (cw * 3, ch))
        for j, im in enumerate((ref, mine, Image.blend(ref, mine, 0.5))):
            row.paste(im.crop(box), (j * cw, 0))
        row = row.resize((int(cw * 3 * zoom), int(ch * zoom)))
        d = ImageDraw.Draw(row)
        d.rectangle([0, 0, 28, 12], fill="black")
        d.text((2, 1), str(n), fill="yellow")
        rows.append(row)
    sh = Image.new("RGB", (rows[0].width, rows[0].height * len(rows)))
    for i, r in enumerate(rows):
        sh.paste(r, (0, i * r.height))
    sh.save(out)
    print("wrote", out)


def _tile_sheet(tiles, out, cols=6, W=200, H=260):
    """tiles = [(label, actor_spec)] rendered one per cell."""
    from .render import frame_rgb
    rows = (len(tiles) + cols - 1) // cols
    sh = Image.new("RGB", (W * cols, H * rows), "white")
    base = {"canvas": {"w": W, "h": H, "scale": 1.5, "bg": "#e8e2d0"}}
    for i, (label, a) in enumerate(tiles):
        im = frame_rgb(Scene(dict(base, actors={"a": a})), 0)
        ImageDraw.Draw(im).text((4, 4), label, fill="black")
        sh.paste(im, ((i % cols) * W, (i // cols) * H))
    sh.save(out)
    print("wrote", out)


def poses_sheet(out):
    """poses.png (every named pose), poses_turn.png (one pose at 8 yaw angles), poses_faces.png (every expression, front view)."""
    from .faces import FACES
    _tile_sheet([(n, {"x": 100, "ground": 200, "keys": [{"t": 0, "pose": n}]}) for n in POSES], out)
    stem = out[:-4] if out.endswith(".png") else out
    _tile_sheet([(f"yaw {y}", {"x": 100, "ground": 200, "keys": [{"t": 0, "pose": "relax", "yaw": y, "expr": "happy"}]})
                 for y in (0, 45, 90, 135, 180, 225, 270, 315)], stem + "_turn.png", cols=8)
    _tile_sheet([(n, {"x": 100, "ground": 200, "keys": [{"t": 0, "pose": "relax", "yaw": 90, "expr": n}]}) for n in FACES], stem + "_faces.png", cols=8)
    print("poses:", ", ".join(POSES))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="stickreel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("docs")
    v = sub.add_parser("validate"); v.add_argument("scene")
    s = sub.add_parser("sheet"); s.add_argument("scene"); s.add_argument("--times", required=True); s.add_argument("--out", default="sheet.png"); s.add_argument("--cols", type=int)
    p = sub.add_parser("poses"); p.add_argument("--out", default="poses.png")
    c = sub.add_parser("compare"); c.add_argument("scene"); c.add_argument("--ref", required=True); c.add_argument("--frames", required=True)
    c.add_argument("--out", default="compare.png"); c.add_argument("--crop"); c.add_argument("--zoom", type=float, default=0.5)
    au = sub.add_parser("audio"); au.add_argument("scene"); au.add_argument("--out", default="mix.wav")
    sf = sub.add_parser("sfx"); sf.add_argument("name", nargs="?"); sf.add_argument("--pitch", type=float, default=1.0); sf.add_argument("--out")
    r = sub.add_parser("render"); r.add_argument("scene"); r.add_argument("--out"); r.add_argument("--start", type=float); r.add_argument("--end", type=float)
    r.add_argument("--workers", type=int, default=2); r.add_argument("--no-audio", action="store_true"); r.add_argument("--png"); r.add_argument("--crf", type=int, default=18)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "docs":
            print(docs_text())
        elif a.cmd == "validate":
            sc = Scene.load(a.scene)
            print(f"ok: {len(sc.actors)} actors, {len(sc.objects)} objects, {sc.duration}s @ {sc.fps} fps")
            for t in (0.0, sc.duration / 2, sc.duration - 1 / sc.fps):
                for ac in sc.actors.values():
                    ac.solve(t)
        elif a.cmd == "sheet":
            sc = Scene.load(a.scene)
            sheet(sc, [float(x) for x in a.times.split(",")], a.out, a.cols)
        elif a.cmd == "audio":
            from . import audio as A
            sc = Scene.load(a.scene)
            m = A.mix(sc)
            A.write_wav(a.out, m)
            print(f"wrote {a.out}: {len(m) / 44100:.2f}s, peak {abs(m).max():.2f}, {len(sc.audio.get('cues', [])) if sc.audio else 0} cue lines")
        elif a.cmd == "sfx":
            from .sfx import SFX, describe, render_sfx, write_wav
            if not a.name:
                for k, v in describe().items():
                    print(f"  {k:9s} {v}")
            else:
                write_wav(a.out or f"{a.name}.wav", render_sfx(a.name, a.pitch))
                print("wrote", a.out or f"{a.name}.wav")
        elif a.cmd == "compare":
            compare(Scene.load(a.scene), a.ref, [int(x) for x in a.frames.split(",")], a.out, a.crop, a.zoom)
        elif a.cmd == "poses":
            poses_sheet(a.out)
        elif a.cmd == "render":
            from .render import render_video
            render_video(a.scene, a.out, a.start, a.end, a.workers, a.png, a.crf, audio=not a.no_audio)
    except SceneError as e:
        print("scene error:", e, file=sys.stderr)
        sys.exit(2)
