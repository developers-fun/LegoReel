"""Command line: python -m r6reel <command> ..."""
from __future__ import annotations

import argparse
import os
import sys
import time


def _size(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def _progress(label):
    t0 = time.time()

    def cb(i, n):
        if i % 5 == 0 or i == n:
            el = time.time() - t0
            print(f"\r{label} {i}/{n} frames  {el:.0f}s  eta {el / i * (n - i):.0f}s ", end="", file=sys.stderr, flush=True)
        if i == n:
            print(file=sys.stderr)
    return cb


def cmd_render(a):
    from .scene import Scene
    sc = Scene.from_json(a.scene)
    if a.fps:
        sc.fps = a.fps
    out = sc.render(a.out, start=a.start, end=a.end, preview=a.preview, size=_size(a.size) if a.size else None,
                    progress=_progress("render"), audio=a.audio)
    print("wrote", out)


def cmd_direct(a):
    from .director import Director
    kw = dict(seed=a.seed, pace=a.pace, style=a.style)
    if a.size:
        kw["size"] = _size(a.size)
    if a.fps:
        kw["fps"] = a.fps
    with open(a.script) as f:
        text = f.read()
    sc = Director(text, **kw).build()
    if a.save:
        sc.to_json(a.save)
        print("scene json:", a.save)
    for w in sc.validate():
        print("warn:", w)
    out = sc.render(a.out, start=a.start, end=a.end, preview=a.preview, progress=_progress("render"), audio=a.audio)
    print("wrote", out)


def cmd_validate(a):
    from .scene import Scene
    sc = Scene.from_json(a.scene)
    w = sc.validate()
    for x in w:
        print("warn:", x)
    print(f"{len(w)} warning(s); duration {sc.duration:.2f}s, {len(sc.shots)} shots")
    return 1 if w and a.strict else 0


def cmd_list(a):
    from . import presets as PR
    what = a.what
    if what == "clips":
        from . import clips
        print("\n".join(clips.names()))
    elif what == "faces":
        try:
            from . import faces
            tags = faces.tags()
            print("tags:", ", ".join(f"{k}({v})" if not isinstance(tags, list) or isinstance(k, str) is False else str(k)
                                    for k, v in (tags.items() if isinstance(tags, dict) else [(t, "") for t in tags])))
        except Exception as e:                         # noqa: BLE001
            from .avatar import PROCEDURAL_FACES
            print(f"(faces library unavailable: {e}); built-in procedural faces:")
            print("\n".join(PROCEDURAL_FACES))
    elif what == "presets":
        print("lighting:", ", ".join(PR.lighting_names()))
        print("locations:", ", ".join(PR.location_names()))
        print("caption styles: storytime, yellow_pop, two_line; variants A-D")
        print("pace: fast, normal, slow")
    elif what == "builders":
        print("\n".join(PR.builder_names()))
    elif what == "emotions":
        for k in PR.emotion_names():
            e = PR.EMOTIONS[k]
            print(f"{k:12s} clips={e['clips']} face_tags={e['face_tags']} cams={e['cams']} energy={e['energy']}")


def cmd_faces(a):
    try:
        from . import faces
    except Exception as e:                             # noqa: BLE001
        print("faces library unavailable:", e)
        return 1
    res = faces.search(a.query, limit=a.limit)
    for f in res:
        print(getattr(f, "id", None) or getattr(f, "name", None) or f, getattr(f, "tags", ""))
    print(len(res), "result(s)")


def cmd_demo(a):
    from .director import Director
    from .scene import Scene
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "..", "examples"))
    try:
        import story_demo
        sc = story_demo.build(size=_size(a.size) if a.size else (1080, 1920))
    except ImportError:
        sc = Director("@cafeteria\nMilo (shocked, drop): He dropped his tray.\nAva (laughing, to=Milo): Nice one!").build()
    out = a.out or "out/demo.mp4"
    sc.to_json(os.path.splitext(out)[0] + ".json")
    sc.render(out, preview=not a.final, progress=_progress("demo"))
    print("wrote", out)


def cmd_contact(a):
    from .scene import Scene
    sc = Scene.from_json(a.scene)
    times = None
    if a.times:
        times = [float(x) for x in a.times.split(",")]
    img = sc.contact_sheet(times, cols=a.cols, tile_h=a.tile_h, step=a.step)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    img.save(a.out)
    print("wrote", a.out, img.size)


def cmd_storyboard(a):
    from .scene import Scene
    from .storyboard import Storyboard
    if a.scene.lower().endswith(".txt"):
        from .director import Director
        with open(a.scene) as f:
            sc = Director(f.read(), seed=a.seed, pace=a.pace).build()
    else:
        sc = Scene.from_json(a.scene)
    times = [float(x) for x in a.times.split(",")] if a.times else None
    sb = Storyboard(sc, max_panels=a.max, cols=a.cols, tile_h=a.tile_h, minimap=not a.no_minimap,
                    captions=a.captions, times=times)
    paths = sb.save(a.out)
    for p in paths:
        print("wrote", p)
    ws = sb.warnings()
    print(f"{len(sb.panels())} panels, {len(ws)} warning(s)")
    for i, t, w in ws:
        print(f"  panel {i} ({t:.2f}s): {w}")
    sc.close()


def cmd_sfx(a):
    from . import sfx
    if a.test:
        return sfx._selftest()
    for k, v in sfx.describe().items():
        print(f"{k:<9} {v}")


def cmd_audio(a):
    from .scene import Scene
    from . import audio as A
    sc = Scene.from_json(a.scene)
    if not isinstance(sc.audio, dict):
        print("scene has no \"audio\" section (dict)")
        return 1
    sc._ensure_built()
    m = A.mix(sc, sc.audio)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    A.write_wav(a.out, m)
    print(f"wrote {a.out}: {len(m) / 44100:.2f}s, peak {abs(m).max():.2f}, {len(sc.audio.get('cues', []))} cue lines")


def main(argv=None):
    p = argparse.ArgumentParser(prog="r6reel", description="Roblox R6 storytime video renderer")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="render a scene.json to mp4")
    r.add_argument("scene"), r.add_argument("out")
    r.add_argument("--preview", action="store_true"), r.add_argument("--start", type=float), r.add_argument("--end", type=float)
    r.add_argument("--fps", type=float), r.add_argument("--size"), r.add_argument("--audio")
    r.set_defaults(fn=cmd_render)
    d = sub.add_parser("direct", help="auto-direct a script (.txt or .json) into a video")
    d.add_argument("script"), d.add_argument("out")
    d.add_argument("--seed", type=int, default=0), d.add_argument("--pace", default="normal")
    d.add_argument("--style", default="storytime"), d.add_argument("--preview", action="store_true")
    d.add_argument("--start", type=float), d.add_argument("--end", type=float), d.add_argument("--size")
    d.add_argument("--fps", type=float), d.add_argument("--audio"), d.add_argument("--save", help="also write scene json")
    d.set_defaults(fn=cmd_direct)
    v = sub.add_parser("validate", help="lint a scene.json")
    v.add_argument("scene"), v.add_argument("--strict", action="store_true")
    v.set_defaults(fn=cmd_validate)
    l = sub.add_parser("list", help="list clips|faces|presets|builders|emotions")
    l.add_argument("what", choices=["clips", "faces", "presets", "builders", "emotions"])
    l.set_defaults(fn=cmd_list)
    f = sub.add_parser("faces", help="faces search '#happy #laughing'")
    f.add_argument("action", choices=["search"]), f.add_argument("query"), f.add_argument("--limit", type=int, default=20)
    f.set_defaults(fn=lambda a: cmd_faces(a))
    m = sub.add_parser("demo", help="render the built-in demo story (preview) to out/demo.mp4")
    m.add_argument("--out"), m.add_argument("--final", action="store_true"), m.add_argument("--size")
    m.set_defaults(fn=cmd_demo)
    c = sub.add_parser("contact", help="frame-grid contact sheet of a scene.json")
    c.add_argument("scene"), c.add_argument("--out", default="out/contact.png"), c.add_argument("--times")
    c.add_argument("--step", type=float, default=0.5), c.add_argument("--cols", type=int, default=6)
    c.add_argument("--tile-h", dest="tile_h", type=int, default=240)
    c.set_defaults(fn=cmd_contact)
    sb = sub.add_parser("storyboard", help="storyboard sheet (key frames + motion annotations + checks)")
    sb.add_argument("scene", help="scene.json or Director script .txt"), sb.add_argument("--out", default="out/storyboard.png")
    sb.add_argument("--max", type=int, default=12), sb.add_argument("--cols", type=int, default=4)
    sb.add_argument("--tile-h", dest="tile_h", type=int, default=480), sb.add_argument("--times")
    sb.add_argument("--no-minimap", dest="no_minimap", action="store_true"), sb.add_argument("--captions", action="store_true")
    sb.add_argument("--seed", type=int, default=0), sb.add_argument("--pace", default="normal")
    sb.set_defaults(fn=cmd_storyboard)
    sf = sub.add_parser("sfx", help="list the built-in synthesised sounds (or --test to check them)")
    sf.add_argument("--test", action="store_true")
    sf.set_defaults(fn=cmd_sfx)
    au = sub.add_parser("audio", help="mix only the scene's sound to a wav (no video)")
    au.add_argument("scene"), au.add_argument("--out", default="out/mix.wav")
    au.set_defaults(fn=cmd_audio)
    a = p.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
