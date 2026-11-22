#!/usr/bin/env python3
"""Put the owner's real gameplay recording into the green screen of a promo3 video, keeping the cartoon finger on top.
usage: overlay_recording.py BASE.mp4 REC.mp4 OUT.mp4 --video promo3_a_one_more_game [--rec-start SECONDS]
How: the recording is cropped to the screen shape, tilted to match, and placed BEHIND the base video; the base video's pure green is then
keyed out, so everything drawn over the screen (the finger, the touch ring, the bezel) stays on top. Geometry comes from promo3_geometry.json.
"""
import argparse, json, os, subprocess, math
ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("rec"); ap.add_argument("out"); ap.add_argument("--video", required=True)
ap.add_argument("--rec-start", type=float, default=None, help="scene time when the recording starts (default: start of the hold)")
ap.add_argument("--similarity", type=float, default=0.22); ap.add_argument("--blend", type=float, default=0.06)
a = ap.parse_args()
geo = {g["video"]: g for g in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scenes", "promo3_geometry.json")))}[a.video]
w, h = geo["screen_px"]; cx, cy = geo["centre_px"]; th = math.radians(geo["angle_deg"]); t0 = a.rec_start if a.rec_start is not None else geo["hold_start"]
w2, h2 = w + 24, h + 24                                   # a little oversize: the bezel on top hides the extra
d = int(math.hypot(w2, h2)) + 2
fc = (f"[1:v]scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2},format=rgba,"
      f"rotate={th:.6f}:ow={d}:oh={d}:c=none,setpts=PTS+{t0}/TB[rec];"
      f"color=c=black:s=1080x1920:r=30[bg];[bg][rec]overlay=x={int(cx - d / 2)}:y={int(cy - d / 2)}:eof_action=pass:shortest=0[under];"
      f"[0:v]colorkey=0x00ff00:{a.similarity}:{a.blend}[top];[under][top]overlay=shortest=1,format=yuv420p[v]")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.base, "-i", a.rec, "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy", a.out], check=True)
print("wrote", a.out)
