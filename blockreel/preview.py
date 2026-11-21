"""Part preview: render a part on the main avatar from three angles and save one picture."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PIL import Image

from .errors import SceneError
from .parts import FOLDERS, ROOT, find_part

CLOSE = ("faces", "hair", "headwear")


def preview_part(folder, pid, out_path=None, avatar="main", size=420):
    from .render import render_frame
    from .scene import Scene
    find_part(folder, pid)    # raises if it does not exist
    base = json.loads((ROOT / "avatars" / f"{avatar}.json").read_text(encoding="utf-8"))
    parts = dict(base["parts"])
    props = []
    if folder == "faces":
        parts["face"] = pid
    elif folder == "hair":
        parts["hair"], parts["headwear"] = pid, None
    elif folder == "headwear":
        parts["headwear"] = pid
    elif folder == "torsos":
        parts["torso"] = pid
    elif folder == "legs":
        parts["legs"] = pid
    elif folder == "accessories":
        parts["accessories"] = [pid]
    elif folder == "sets":
        props = [{"id": "p", "template": pid, "position": [0, 0, 0]}]
    tmp = Path(tempfile.mkdtemp(prefix="blockreel_preview_"))
    (tmp / "avatars").mkdir()
    base["parts"] = parts
    base["variants"] = {}
    (tmp / "avatars" / "preview.json").write_text(json.dumps(base), encoding="utf-8")
    if folder == "sets":
        chars = {"p": {"avatar": "preview", "position": [30, 0, 30]}}
        cams = [{"position": [0, 6, 16], "look_at": [0, 3, 0], "fov": 50},
                {"position": [11, 7, 11], "look_at": [0, 3, 0], "fov": 50},
                {"position": [-11, 5, 11], "look_at": [0, 3, 0], "fov": 50}]
        yaws = [0, 0, 0]
    else:
        chars = {"p": {"avatar": "preview", "position": [0, 0, 0]}}
        yaws = [0, 35, -75] if folder != "accessories" else [0, 150, 90]
        if folder in CLOSE:
            cams = [{"preset": "close", "focus": [0, 0.8, 0]}] * 3
        else:
            cams = [{"preset": "medium", "focus": [0, 0, 0]}] * 3
    shots = []
    for i, (c, y) in enumerate(zip(cams, yaws)):
        shots.append({"id": f"v{i}", "duration": 0.2, "camera": c,
                      "actions": [{"t": 0, "character": "p", "face": y, "turn": 0.0}]})
    scene = Scene({"meta": {"title": "preview", "width": size, "height": int(size * 16 / 9) // 2 * 2, "supersample": 2,
                            "look": {"dof": None}},
                   "characters": chars, "props": props, "shots": shots}, tmp, width_scale=1.0)
    frames = [render_frame(scene, int(round((i * 0.2 + 0.1) * scene.fps))) for i in range(3)]
    w, h = frames[0].size
    sheet = Image.new("RGB", (w * 3, h))
    for i, im in enumerate(frames):
        sheet.paste(im, (i * w, 0))
    out = Path(out_path) if out_path else Path(tempfile.gettempdir()) / f"preview_{folder}_{pid}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
