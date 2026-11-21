"""Avatar files: one named, locked look that every scene refers to by name.

avatars/<name>.json:
{
  "name": "main", "version": 1, "locked": true, "rig": "r6",
  "appearance": { ...full appearance... },
  "variants_may_change": ["outfit", "accessories", "hair"],
  "variants": { "guest": { "outfit": {...} } }
}
A scene says {"avatar": "main"} (or with "variant": "guest"). Inline appearance overrides are
refused when the style requires avatars, so the same character cannot drift between videos.
The fingerprint is a short hash of the rig and the resolved look; `validate` prints it, and a
scene can pin it with "avatar_fingerprint" so a later edit to the file is caught.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .appearance import DEFAULT_APPEARANCE, _merge, resolve_appearance
from .errors import SceneError
from .rig import ROOT, load_rig

DEFAULT_VARIANT_KEYS = ("outfit", "accessories", "hair")


class Avatar:
    def __init__(self, name, variant, version, rig, raw_appearance, appearance, path, locked):
        self.name, self.variant, self.version = name, variant, version
        self.rig, self.raw_appearance, self.appearance = rig, raw_appearance, appearance
        self.path, self.locked = path, locked
        from .character import FIGURE_VERSION
        blob = json.dumps({"rig": rig.fingerprint_data(), "appearance": raw_appearance, "figure": FIGURE_VERSION}, sort_keys=True)
        self.fingerprint = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10]

    @property
    def label(self):
        return f"{self.name}" + (f"/{self.variant}" if self.variant else "")


def find_file(kind, name, base_dir):
    dirs = []
    if base_dir:
        dirs += [Path(base_dir) / kind, Path(base_dir).parent / kind]
    dirs.append(ROOT / kind)
    seen = []
    for d in dirs:
        p = d / f"{name}.json"
        if p in seen:
            continue
        seen.append(p)
        if p.exists():
            return p
    raise SceneError(f"{kind[:-1]} '{name}' not found. Looked in: {', '.join(str(p.parent) for p in seen)}")


def load_avatar(name, variant, base_dir):
    path = find_file("avatars", name, base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SceneError(f"{path}: not valid JSON: {e.msg} (line {e.lineno})")
    if data.get("rig") in ("brick", "minifig"):
        from .figure import load_brick_avatar
        return load_brick_avatar(path, data, variant, base_dir)
    unknown = set(data) - {"name", "version", "locked", "rig", "notes", "appearance", "variants_may_change", "variants"}
    if unknown:
        raise SceneError(f"{path}: unknown keys {', '.join(sorted(unknown))}")
    rig = load_rig(data.get("rig", "r6"), str(base_dir) if base_dir else None)
    base = _merge(DEFAULT_APPEARANCE, data.get("appearance", {}), f"{path.name}.appearance")
    raw = base
    if variant:
        variants = data.get("variants", {})
        if variant not in variants:
            raise SceneError(f"avatar '{name}' has no variant '{variant}'. Variants: {', '.join(variants) or 'none'}")
        allowed = set(data.get("variants_may_change", DEFAULT_VARIANT_KEYS))
        bad = set(variants[variant]) - allowed
        if bad:
            raise SceneError(f"avatar '{name}' variant '{variant}' changes {', '.join(sorted(bad))}; "
                             f"only {', '.join(sorted(allowed))} may vary (skin, face and rig stay fixed)")
        raw = _merge(base, variants[variant], f"{path.name}.variants.{variant}")
    resolved = resolve_appearance(raw)   # validates every field
    return Avatar(data.get("name", name), variant, data.get("version", 1), rig, raw, resolved, path,
                  bool(data.get("locked", True)))
