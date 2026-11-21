"""Style files: house rules for camera and look, applied to every scene that names the style.

styles/<name>.json:
{ "name": "house", "version": 1,
  "rules": {"fixed_cameras": true, "allow_shake": false, "require_avatar": true},
  "camera_presets": { "medium": {"offset": [0, 3.4, 9], "look_offset": [0, 2.8, 0], "fov": 55} },
  "meta": { ...defaults for lighting, ground, background, shadows, look, text styles... } }
Scene meta overrides the style's meta; the rules cannot be overridden from a scene. To change a
rule, copy the style file, edit it, and set "style" in the scene's meta.
"""
from __future__ import annotations

import json

from .avatar import find_file
from .errors import SceneError

DEFAULT_RULES = {"fixed_cameras": False, "allow_shake": True, "require_avatar": False}


def load_style(name, base_dir):
    path = find_file("styles", name, base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SceneError(f"{path}: not valid JSON: {e.msg} (line {e.lineno})")
    unknown = set(data) - {"name", "version", "notes", "rules", "camera_presets", "meta"}
    if unknown:
        raise SceneError(f"{path}: unknown keys {', '.join(sorted(unknown))}")
    rules = dict(DEFAULT_RULES)
    bad = set(data.get("rules", {})) - set(rules)
    if bad:
        raise SceneError(f"{path}: unknown rules {', '.join(sorted(bad))}. Valid: {', '.join(rules)}")
    rules.update(data.get("rules", {}))
    return {"name": data.get("name", name), "version": data.get("version", 1), "path": path, "rules": rules,
            "presets": data.get("camera_presets", {}), "meta": data.get("meta", {})}
