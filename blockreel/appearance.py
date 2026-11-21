"""Character appearance: every visual choice is a parameter.

Body dimensions are not here: they come from the rig file (rigs/r6.json), so every
character has the same exact measurements. This module only holds the look: skin, face,
hair, outfit, accessories.

Normally a character's look lives in an avatar file (avatars/<name>.json) and scenes refer
to it by name, so it is identical everywhere. The defaults below are a plain placeholder.
Run `python -m blockreel appearance` to print the full default set as JSON.
"""
from __future__ import annotations

import copy

from .errors import SceneError
from .mathutil import parse_color

EYES = ("dots", "wide", "closed", "happy")
MOUTHS = ("smile", "flat", "open", "smirk", "frown", "o")
BROWS = ("none", "flat", "raised")
HAIR_STYLES = ("none", "flat", "spiky", "long", "bob", "mohawk")
SLEEVES = ("none", "short", "long")
ACCESSORY_TYPES = ("cap", "backpack", "scarf", "cape")

DEFAULT_APPEARANCE = {
    "skin": "#f2c9a0",
    "face": {
        "eyes": "dots",
        "mouth": "smile",
        "brows": "flat",
        "eye_color": "#1b1b1f",
        "mouth_color": "#1b1b1f",
        "brow_color": "#3a2a20",
    },
    "hair": {"style": "flat", "color": "#4a2f1c", "fringe": True},
    "outfit": {
        "shirt": "#3d7be0",
        "sleeves": "short",  # none | short | long
        "pants": "#2b2f3a",
        "shorts": False,
        "shoes": "#e8e8e8",
        # optional: {"color": "#ffffff", "y": 0.9, "height": 0.25}  (band around the torso)
        "stripe": None,
        # optional: {"color": "#ffffff", "size": 0.5}  (square on the chest)
        "chest_patch": None,
    },
    # list of {"type": "cap"|"backpack"|"scarf"|"cape", "color": "#rrggbb"}
    "accessories": [],
}


def _merge(base, over, path="appearance"):
    out = copy.deepcopy(base)
    if not isinstance(over, dict):
        raise SceneError(f"{path}: expected an object")
    for k, v in over.items():
        if k not in base:
            raise SceneError(f"{path}: unknown key '{k}'. Valid keys: {', '.join(base)}")
        if isinstance(base[k], dict) and isinstance(v, dict):
            out[k] = _merge(base[k], v, f"{path}.{k}")
        else:
            out[k] = copy.deepcopy(v)
    return out


def _choice(value, options, ctx):
    if value not in options:
        raise SceneError(f"{ctx}: '{value}' is not valid. Options: {', '.join(options)}")
    return value


def resolve_appearance(user=None):
    """Merge user values over defaults, validate, and convert colours to tuples."""
    a = _merge(DEFAULT_APPEARANCE, user or {})

    out = {}
    out["skin"] = parse_color(a["skin"], "appearance.skin")

    f = a["face"]
    out["face"] = {
        "eyes": _choice(f["eyes"], EYES, "appearance.face.eyes"),
        "mouth": _choice(f["mouth"], MOUTHS, "appearance.face.mouth"),
        "brows": _choice(f["brows"], BROWS, "appearance.face.brows"),
        "eye_color": parse_color(f["eye_color"], "appearance.face.eye_color"),
        "mouth_color": parse_color(f["mouth_color"], "appearance.face.mouth_color"),
        "brow_color": parse_color(f["brow_color"], "appearance.face.brow_color"),
    }

    h = a["hair"]
    out["hair"] = {
        "style": _choice(h["style"], HAIR_STYLES, "appearance.hair.style"),
        "color": parse_color(h["color"], "appearance.hair.color"),
        "fringe": bool(h["fringe"]),
    }

    o = a["outfit"]
    outfit = {
        "shirt": parse_color(o["shirt"], "appearance.outfit.shirt"),
        "sleeves": _choice(o["sleeves"], SLEEVES, "appearance.outfit.sleeves"),
        "pants": parse_color(o["pants"], "appearance.outfit.pants"),
        "shorts": bool(o["shorts"]),
        "shoes": parse_color(o["shoes"], "appearance.outfit.shoes"),
        "stripe": None,
        "chest_patch": None,
    }
    if o["stripe"]:
        s = o["stripe"]
        outfit["stripe"] = {
            "color": parse_color(s.get("color", "#ffffff"), "appearance.outfit.stripe.color"),
            "y": float(s.get("y", 0.9)),
            "height": float(s.get("height", 0.25)),
        }
    if o["chest_patch"]:
        p = o["chest_patch"]
        outfit["chest_patch"] = {
            "color": parse_color(p.get("color", "#ffffff"), "appearance.outfit.chest_patch.color"),
            "size": float(p.get("size", 0.5)),
        }
    out["outfit"] = outfit

    accs = []
    if not isinstance(a["accessories"], list):
        raise SceneError("appearance.accessories: expected a list")
    for i, acc in enumerate(a["accessories"]):
        if not isinstance(acc, dict) or "type" not in acc:
            raise SceneError(f"appearance.accessories[{i}]: expected an object with a 'type'")
        accs.append({
            "type": _choice(acc["type"], ACCESSORY_TYPES, f"appearance.accessories[{i}].type"),
            "color": parse_color(acc.get("color", "#d8483c"), f"appearance.accessories[{i}].color"),
        })
    out["accessories"] = accs
    return out
