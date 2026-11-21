from __future__ import annotations

import argparse
import json
import sys

from .appearance import DEFAULT_APPEARANCE
from .errors import SceneError


def build_parser():
    p = argparse.ArgumentParser(prog="blockreel", description="Scene file in, blocky 3D frames and an MP4 out.")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check a scene file and print its timeline; renders nothing")
    v.add_argument("scene")

    r = sub.add_parser("render", help="render a scene to MP4 (or PNG frames)")
    r.add_argument("scene")
    r.add_argument("--out", default=None, help="output .mp4 path (default: out/<scene name>.mp4)")
    r.add_argument("--preview", action="store_true", help="half resolution, no supersampling: quick look")
    r.add_argument("--workers", type=int, default=None, help="parallel processes (default: half your CPU cores)")
    r.add_argument("--start", type=float, default=None, help="first second to render")
    r.add_argument("--end", type=float, default=None, help="last second to render")
    r.add_argument("--supersample", type=int, default=None, choices=[1, 2, 3, 4],
                   help="anti-aliasing factor (overrides the scene file; higher is slower)")
    r.add_argument("--frames-only", action="store_true", help="write PNG frames, skip ffmpeg")
    r.add_argument("--save-frames", default=None, help="also write PNG frames to this folder")
    r.add_argument("--crf", type=int, default=None, help="x264 quality, lower is better (default 18)")
    r.add_argument("--preset", default=None, help="x264 preset (default medium)")
    r.add_argument("--quiet", action="store_true")
    r.add_argument("--skip-preflight", action="store_true",
                   help="render even if the pre-render checks find errors (they run first by default)")

    pf = sub.add_parser("preflight", help="pre-render checks: timing, text, framing, props, stills; renders at most a few cheap frames")
    pf.add_argument("scene")
    pf.add_argument("--stills", action="store_true", help="also render a few half-size stills per shot and check them")
    pf.add_argument("--sheet", default=None, help="write a contact sheet PNG (implies --stills) with the safe zone drawn on")
    pf.add_argument("--json", action="store_true", help="print findings as JSON")
    pf.add_argument("--strict", action="store_true", help="exit non-zero on warnings too")

    cv = sub.add_parser("check-video", help="verify a rendered MP4: size, fps, frame count, no black or frozen frames")
    cv.add_argument("video")
    cv.add_argument("--scene", default=None, help="scene file; the expected frame count is taken from it")
    cv.add_argument("--frames", type=int, default=None, help="expected frame count (for a chunk)")

    sub.add_parser("appearance", help="print the default character appearance as JSON")

    m = sub.add_parser("measure", help="print the rig's exact measurements and check the built figure against them")
    m.add_argument("--rig", default="r6")

    a = sub.add_parser("avatar", help="print an avatar file's resolved look and its fingerprint")
    a.add_argument("name")
    a.add_argument("--variant", default=None)

    pc = sub.add_parser("parts", help="list parts, or check part files for mistakes")
    pc.add_argument("action", choices=["list", "check"])
    pc.add_argument("target", nargs="?", default=None, help="for check: a part .json file, a folder name, or nothing for all")

    pp = sub.add_parser("part-preview", help="render a part on the main avatar from three angles into one PNG")
    pp.add_argument("folder")
    pp.add_argument("id")
    pp.add_argument("--out", default=None)
    pp.add_argument("--avatar", default="main")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "appearance":
            print(json.dumps(DEFAULT_APPEARANCE, indent=2))
            return 0

        if args.cmd == "measure":
            from .rig import load_rig
            from .verify import check_rig
            rig = load_rig(args.rig)
            print(rig.measure_report())
            print()
            print(check_rig(rig))
            return 0

        if args.cmd == "parts":
            import json as _json
            from pathlib import Path as _P
            from .parts import FOLDERS, ROOT, all_part_ids, validate_part
            if args.action == "list":
                for folder in FOLDERS:
                    print(f"{folder}: {len(all_part_ids(folder))}  {', '.join(all_part_ids(folder))}")
                return 0
            files = []
            t = args.target
            if t and t.endswith(".json"):
                files = [_P(t)]
            else:
                for folder in ([t] if t else FOLDERS):
                    files += sorted((ROOT / "parts" / folder).glob("*.json"))
            bad = 0
            for f in files:
                folder = f.parent.name
                try:
                    validate_part(folder, _json.loads(f.read_text(encoding="utf-8")), f)
                    print(f"ok     {folder}/{f.name}")
                except (SceneError, ValueError) as e:
                    bad += 1
                    print(f"FAIL   {folder}/{f.name}: {e}")
                except _json.JSONDecodeError as e:
                    bad += 1
                    print(f"FAIL   {folder}/{f.name}: not valid JSON: {e.msg} (line {e.lineno})")
            print(f"{len(files) - bad} ok, {bad} failed")
            return 1 if bad else 0

        if args.cmd == "part-preview":
            from .preview import preview_part
            print(preview_part(args.folder, args.id, args.out, args.avatar))
            return 0

        if args.cmd == "avatar":
            from .avatar import load_avatar
            av = load_avatar(args.name, args.variant, None)
            print(f"avatar {av.label} v{av.version}  rig {av.rig.name}  locked: {av.locked}")
            print(f"file: {av.path}")
            print(f"fingerprint: {av.fingerprint}")
            print(json.dumps(av.raw_appearance, indent=2))
            return 0

        if args.cmd == "preflight":
            from .preflight import preflight
            rep = preflight(args.scene, stills=args.stills or bool(args.sheet), sheet=args.sheet)
            print(rep.to_json() if args.json else rep.text())
            if args.sheet and not args.json and rep.sheet:
                print(f"contact sheet: {rep.sheet}")
            return 2 if rep.errors else (1 if args.strict and rep.warnings else 0)

        if args.cmd == "check-video":
            from .preflight import check_video
            from .scene import Scene
            frames, size, fps = args.frames, (1080, 1920), 30.0
            if args.scene:
                sc = Scene.load(args.scene)
                frames = frames if frames is not None else sc.frame_count
                size, fps = (sc.width, sc.height), float(sc.fps)
            rep = check_video(args.video, expect_frames=frames, expect_size=size, expect_fps=fps)
            print(rep.text() if rep.findings else "check-video: ok")
            return 2 if rep.errors else 0

        from .scene import Scene

        if args.cmd == "validate":
            scene = Scene.load(args.scene)
            print(scene.report())
            return 0

        from pathlib import Path
        from .render import render_scene

        if not args.skip_preflight:
            from .preflight import preflight
            rep = preflight(args.scene)
            if rep.errors:
                print(rep.text(), file=sys.stderr)
                print("error: pre-render checks failed; fix the errors above (or pass --skip-preflight)", file=sys.stderr)
                return 2
            if rep.warnings and not args.quiet:
                print(rep.text())
        out = args.out
        if out is None and not args.frames_only:
            out = Path("out") / (Path(args.scene).stem + ".mp4")
        result = render_scene(
            args.scene, out, preview=args.preview, workers=args.workers, start=args.start, end=args.end,
            supersample=args.supersample, frames_only=args.frames_only, save_frames=args.save_frames,
            crf=args.crf, preset=args.preset, progress=not args.quiet)
        print(f"done: {result}")
        return 0
    except SceneError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
