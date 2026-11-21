"""The brick figure: rig numbers plus swappable part templates, posed into render Items."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .character import FIGURE_VERSION, Item
from .errors import SceneError
from .mathutil import mat_mul, rot_x, rot_y, rot_z, scale_m, translate
from .parts import DEFAULT_PALETTE, load_part, pieces_to_items, resolve_color

ROOT = Path(__file__).resolve().parent.parent
PART_SLOTS = ("face", "hair", "headwear", "torso", "legs")


class BrickRig:
    def __init__(self, data, path):
        self.name = data["name"]
        self.data = data
        self.path = path
        self.p = data["parts"]
        self.waist = np.array(data["waist_pivot"], dtype=np.float64)
        self.height = float(data["height"])

    def fingerprint_data(self):
        return self.data


def load_brick_rig(name="brick", base_dir=None):
    dirs = ([Path(base_dir) / "rigs", Path(base_dir).parent / "rigs"] if base_dir else []) + [ROOT / "rigs"]
    for d in dirs:
        p = d / f"{name}.json"
        if p.exists():
            return BrickRig(json.loads(p.read_text(encoding="utf-8")), p)
    raise SceneError(f"rig '{name}' not found in {', '.join(str(d) for d in dirs)}")


def _merge_palette(*layers):
    out = dict(DEFAULT_PALETTE)
    for l in layers:
        out.update(l or {})
    return out


class BrickAvatar:
    """A resolved brick avatar: rig, palette, chosen parts, and a fingerprint over all of it."""

    def __init__(self, name, variant, version, rig, palette, parts, expressions, path, locked):
        self.name, self.variant, self.version = name, variant, version
        self.rig, self.palette, self.parts, self.expressions = rig, palette, parts, expressions
        self.path, self.locked = path, locked
        self.appearance = self               # lets the renderer tell a brick avatar from an R6 one
        h = hashlib.sha256()
        h.update(json.dumps({"rig": rig.fingerprint_data(), "palette": palette, "figure": FIGURE_VERSION,
                             "parts": {k: (v.id if hasattr(v, "id") else [a.id for a in v]) for k, v in parts.items() if v},
                             "expressions": {k: v.digest() for k, v in expressions.items()}},
                            sort_keys=True).encode("utf-8"))
        for k in sorted(parts):
            v = parts[k]
            for part in ([v] if hasattr(v, "digest") else (v or [])):
                h.update(part.digest().encode("utf-8"))
        self.fingerprint = h.hexdigest()[:10]
        self.raw_appearance = {"palette": palette,
                               "parts": {k: (v.id if hasattr(v, "id") else [a.id for a in v]) for k, v in parts.items() if v},
                               "expressions": {k: v.id for k, v in expressions.items()}}

    @property
    def label(self):
        return self.name + (f"/{self.variant}" if self.variant else "")

    def face_for(self, expression):
        return self.expressions.get(expression) or self.parts["face"]


def _load_parts(spec, base_dir, ctx):
    from .parts import FOLDERS
    folder_of = {"face": "faces", "hair": "hair", "headwear": "headwear", "torso": "torsos", "legs": "legs"}
    out = {}
    for slot in PART_SLOTS:
        pid = spec.get(slot)
        out[slot] = load_part(folder_of[slot], pid, base_dir) if pid else None
    out["accessories"] = [load_part("accessories", a, base_dir) for a in (spec.get("accessories") or [])]
    for slot in ("face", "torso", "legs"):
        if out[slot] is None:
            raise SceneError(f"{ctx}: parts.{slot} is required")
    return out


def load_brick_avatar(path, data, variant, base_dir):
    ctx = path.name
    unknown = set(data) - {"name", "version", "locked", "rig", "notes", "palette", "parts", "expressions",
                           "variants_may_change", "variants"}
    if unknown:
        raise SceneError(f"{path}: unknown keys {', '.join(sorted(unknown))}")
    rig = load_brick_rig(data.get("rig", "brick"), str(base_dir) if base_dir else None)
    palette = _merge_palette(data.get("palette"))
    parts = dict(data.get("parts", {}))
    if variant:
        variants = data.get("variants", {})
        if variant not in variants:
            raise SceneError(f"avatar '{data.get('name')}' has no variant '{variant}'. Variants: {', '.join(variants) or 'none'}")
        v = variants[variant]
        allow = data.get("variants_may_change", {"parts": ["hair", "headwear", "torso", "legs", "accessories"],
                                                  "palette": ["primary", "secondary", "accent", "pants", "shoes", "hair", "metal"]})
        bad_top = set(v) - {"parts", "palette"}
        if bad_top:
            raise SceneError(f"{ctx}: variant '{variant}' may only set parts and palette, not {', '.join(sorted(bad_top))}")
        bad_p = set(v.get("parts", {})) - set(allow.get("parts", []))
        bad_c = set(v.get("palette", {})) - set(allow.get("palette", []))
        if bad_p or bad_c:
            raise SceneError(f"{ctx}: variant '{variant}' changes {', '.join(sorted(bad_p | bad_c))}, which is locked. "
                             f"Only parts [{', '.join(allow.get('parts', []))}] and palette [{', '.join(allow.get('palette', []))}] "
                             f"may vary (the face, skin and rig stay fixed so it is always the same character)")
        parts.update(v.get("parts", {}))
        palette = _merge_palette(data.get("palette"), v.get("palette"))
    loaded = _load_parts(parts, base_dir, ctx)
    expr = {}
    for ename, fid in (data.get("expressions") or {}).items():
        expr[ename] = load_part("faces", fid, base_dir)
    return BrickAvatar(data.get("name"), variant, data.get("version", 1), rig, palette, loaded, expr, path,
                       bool(data.get("locked", True)))


# ---- posing ---------------------------------------------------------------------------------------

def _split_pieces(pieces, frame_ld, frame_c, pal, part_dir):
    """LDraw pieces use the part's LDraw frame; brick pieces use the centred frame."""
    ld = [p for p in pieces if p["shape"] == "ldraw"]
    br = [p for p in pieces if p["shape"] != "ldraw"]
    out = []
    if ld:
        out += pieces_to_items(ld, frame_ld, pal, part_dir, Item)
    if br:
        out += pieces_to_items(br, frame_c, pal, part_dir, Item)
    return out


def _ld_item(part, frame, colour, casts=True, spec=1.0, scale=None):
    from .parts import LD_SCALE
    s = LD_SCALE if scale is None else scale
    return Item(mat_mul(frame, scale_m(s)), (1.0, 1.0, 1.0), colour, "ldraw", 0, casts, {"spec": spec, "file": part})


def build_minifig_items(av, pos, yaw, pose, expression=None):
    """The figure built from real part geometry (LDraw). Same pose keys as the procedural brick figure."""
    from .parts import LD_SCALE
    rig, pal = av.rig, av.palette
    L = rig.data["ld"]
    S = L["scale"]
    items = []
    root = mat_mul(translate(pos[0], pos[1] + pose["root_y"], pos[2]), rot_y(yaw))
    skin, hand_col = resolve_color("skin", pal), resolve_color("hand", pal)
    legs, torso_part = av.parts["legs"], av.parts["torso"]
    ldl, ldt = legs.data.get("ldraw"), torso_part.data.get("ldraw")
    if not ldl or not ldt:
        raise SceneError(f"avatar '{av.label}': the minifig rig needs legs and torso parts with an \"ldraw\" entry "
                         f"(legs '{legs.id}', torso '{torso_part.id}')")
    pants = resolve_color(legs.data.get("hips", "pants"), pal)

    # legs and hips
    hips_o = mat_mul(root, translate(0, L["hips_origin_y"] * S, 0))
    items.append(_ld_item(ldl["hips"], hips_o, pants))
    for key, part, sx in (("r_leg_pitch", ldl["leg_r"], -1), ("l_leg_pitch", ldl["leg_l"], 1)):
        px = sx * L["leg_pivot_x"] * S
        m = mat_mul(hips_o, translate(px, 0, 0), rot_x(-pose[key]), translate(-px, 0, 0))
        items.append(_ld_item(part, m, pants))
    hips_c = mat_mul(hips_o, translate(0, -4.0 * S, 0))

    # torso, arms and hands lean about the waist
    wp = rig.waist
    torso_frame = mat_mul(root, translate(*wp), rot_y(pose["torso_yaw"]), rot_x(pose["torso_pitch"]), translate(*(-wp)))
    torso_o = mat_mul(torso_frame, translate(0, L["torso_origin_y"] * S, 0))
    base_col = resolve_color(torso_part.data.get("base", "primary"), pal)
    arm_col = resolve_color(torso_part.data.get("arm", torso_part.data.get("base", "primary")), pal)
    items.append(_ld_item(ldt["torso"], torso_o, base_col))
    tc = mat_mul(torso_o, translate(0, -L["torso_centre_below_top"] * S, 0))
    if torso_part.data.get("pieces"):
        items += _split_pieces(torso_part.data["pieces"], torso_o, tc, pal, torso_part.dir)
    ap = L["arm_pivot"]
    for key, rk, sx, part in (("r_arm_pitch", "r_arm_roll", -1, ldt["arm_r"]), ("l_arm_pitch", "l_arm_roll", 1, ldt["arm_l"])):
        piv = translate(sx * ap[0] * S, (ap[1] - L["torso_origin_y"]) * S, ap[2] * S)
        am = mat_mul(torso_o, piv, mat_mul(rot_z(sx * (pose[rk] + L.get("arm_rest_roll", 0.0))), rot_x(-pose[key])))
        items.append(_ld_item(part, am, arm_col))
        hp, hr = L["hand_pos"], L["hand_rot"]
        hm_ = mat_mul(am, translate(sx * hp[0] * S, hp[1] * S, hp[2] * S), rot_y(sx * hr[1]), rot_x(hr[0]))
        items.append(_ld_item(ldt["hand"], hm_, hand_col))
        side = "hand_r" if sx < 0 else "hand_l"
        for acc in av.parts["accessories"]:
            if acc.data["attach"] == side:
                items += pieces_to_items(acc.data["pieces"], hm_, pal, acc.dir, Item)

    # head
    head_o = mat_mul(torso_o, translate(0, L["head_offset_y"] * S, 0), rot_y(pose["head_yaw"]), rot_x(pose["head_pitch"]))
    face = av.face_for(expression)
    fld = face.data.get("ldraw")
    if not fld:
        raise SceneError(f"avatar '{av.label}': face '{face.id}' has no \"ldraw\" head; use a head from parts/faces/ld_*.json")
    # two-sided heads carry a second print on the back of the head; "flip" turns the head round to show it
    face_o = mat_mul(head_o, rot_y(180.0)) if face.data.get("flip") else head_o
    items.append(_ld_item(fld, face_o, skin))
    head_c = mat_mul(head_o, translate(0, L["head_centre_above_torso_top"] * S - L["head_offset_y"] * S, 0))
    hair, hat = av.parts["hair"], av.parts["headwear"]
    if hair and not (hat and hat.data.get("replaces_hair")):
        items += _split_pieces(hair.data["pieces"], head_o, head_c, pal, hair.dir)
    if hat:
        items += _split_pieces(hat.data["pieces"], head_o, head_c, pal, hat.dir)
    for acc in av.parts["accessories"]:
        at = acc.data["attach"]
        if at == "head":
            items += _split_pieces(acc.data["pieces"], head_o, head_c, pal, acc.dir)
        elif at == "torso":
            items += _split_pieces(acc.data["pieces"], torso_o, tc, pal, acc.dir)
        elif at == "back":
            items += _split_pieces(acc.data["pieces"], mat_mul(torso_o, translate(0, 0, -10 * S)),
                                   mat_mul(tc, translate(0, 0, -10 * S)), pal, acc.dir)
        elif at == "hips":
            items += _split_pieces(acc.data["pieces"], hips_o, hips_c, pal, acc.dir)
    return items


def build_brick_items(av, pos, yaw, pose, expression=None):
    if av.rig.data.get("kind") == "minifig":
        return build_minifig_items(av, pos, yaw, pose, expression)
    rig, P, pal = av.rig, av.rig.p, av.palette
    items = []
    I = np.eye(4)
    root = mat_mul(translate(pos[0], pos[1] + pose["root_y"], pos[2]), rot_y(yaw))

    def add(model, size, color, shape="box", bevel=0.07, casts=True, **extra):
        extra.setdefault("spec", 1.0)
        if shape == "box" and "subdiv" not in extra:
            extra["subdiv"] = 1 if min(size) >= 0.45 else 0
        items.append(Item(model, tuple(float(x) for x in size), color, shape, bevel, casts, extra))

    skin = resolve_color("skin", pal)
    hand = resolve_color("hand", pal)
    legs = av.parts["legs"]
    torso_part = av.parts["torso"]

    # ---- legs and hips (they do not lean with the torso)
    ls = P["leg"]["size"]
    hip_y = P["leg"]["hip_y"]
    for key, sx in (("r_leg_pitch", -1), ("l_leg_pitch", 1)):
        pivot = (sx * P["leg"]["x"], hip_y, 0.0)
        base = mat_mul(root, translate(*pivot), rot_x(-pose[key]))
        for b in legs.data["bands"]:
            top = -ls[1] * b["from"]
            bot = -ls[1] * b["to"]
            hgt = bot * -1 - top * -1
            add(mat_mul(base, translate(0, (top + bot) / 2.0, 0)), (ls[0], abs(top - bot) + 0.001, ls[2]),
                resolve_color(b["color"], pal), bevel=0.06)
    hips_col = resolve_color(legs.data.get("hips", "pants"), pal)
    hips_m = mat_mul(root, translate(0, P["hips"]["centre_y"], 0))
    add(hips_m, P["hips"]["size"], hips_col)
    for acc_piece_set in (legs,):
        if legs.data.get("pieces"):
            items += pieces_to_items(legs.data["pieces"], hips_m, pal, legs.dir, Item)

    # ---- torso (leans about the waist)
    wp = rig.waist
    torso_frame = mat_mul(root, translate(*wp), rot_y(pose["torso_yaw"]), rot_x(pose["torso_pitch"]), translate(*(-wp)))
    tc = mat_mul(torso_frame, translate(0, P["torso"]["centre_y"], 0))
    tsz = P["torso"]["size"]
    base_col = resolve_color(torso_part.data.get("base", "primary"), pal)
    add(tc, tsz, base_col, bevel=0.08, bottom=tuple(P["torso"]["bottom_ratio"]), subdiv=2)
    if torso_part.data.get("image"):
        items.append(Item(mat_mul(tc, translate(0, 0.0, tsz[2] / 2 + 0.006)), (1, 1, 1), (255, 255, 255), "decal", 0, False,
                          {"kind": "quad", "w": tsz[0] * 0.9, "h": tsz[1] * 0.9,
                           "image": str(torso_part.dir / torso_part.data["image"])}))
    if torso_part.data.get("back_image"):
        items.append(Item(mat_mul(tc, translate(0, 0.0, -tsz[2] / 2 - 0.006), rot_y(180)), (1, 1, 1), (255, 255, 255), "decal", 0, False,
                          {"kind": "quad", "w": tsz[0] * 0.9, "h": tsz[1] * 0.9,
                           "image": str(torso_part.dir / torso_part.data["back_image"])}))
    if torso_part.data.get("pieces"):
        items += pieces_to_items(torso_part.data["pieces"], tc, pal, torso_part.dir, Item)

    # ---- arms and hands (swing at the shoulder)
    A = P["arm"]
    arm_col = resolve_color(torso_part.data.get("arm", torso_part.data.get("base", "primary")), pal)
    hnd = P["hand"]
    for key, rk, sx in (("r_arm_pitch", "r_arm_roll", -1), ("l_arm_pitch", "l_arm_roll", 1)):
        pivot = (sx * A["shoulder"][0], A["shoulder"][1], A["shoulder"][2])
        rot = mat_mul(rot_z(sx * pose[rk]), rot_x(-pose[key]))
        am = mat_mul(torso_frame, translate(*pivot), rot)
        add(mat_mul(am, translate(0, -A["centre_below_pivot"], 0)), A["size"], arm_col, bevel=0.1)
        add(mat_mul(am, translate(0, -hnd["below_pivot"], 0)), (hnd["diameter"], hnd["height"], hnd["diameter"]), hand,
            shape="cylinder", bevel=0.1)
        side = "hand_r" if sx < 0 else "hand_l"
        for acc in av.parts["accessories"]:
            if acc.data["attach"] == side:
                items += pieces_to_items(acc.data["pieces"], mat_mul(am, translate(0, -hnd["below_pivot"], 0)), pal, acc.dir, Item)

    # ---- head
    H = P["head"]
    hm = mat_mul(torso_frame, translate(0, H["neck_y"], 0), rot_y(pose["head_yaw"]), rot_x(pose["head_pitch"]),
                 translate(0, H["height"] / 2.0, 0))
    add(hm, (H["diameter"], H["height"], H["diameter"]), skin, shape="cylinder", bevel=0.09, subdiv=1)
    hair, hat = av.parts["hair"], av.parts["headwear"]
    if not hair and not hat:
        S = P["stud"]
        add(mat_mul(hm, translate(0, H["height"] / 2 + S["height"] / 2 - 0.02, 0)), (S["diameter"], S["height"], S["diameter"]),
            skin, shape="cylinder", bevel=0.04)
    face = av.face_for(expression)
    if face.data.get("image"):
        items.append(Item(mat_mul(hm, translate(0, 0, 0)), (1, 1, 1), (255, 255, 255), "decal", 0, False,
                          {"kind": "head", "radius": H["diameter"] / 2 + 0.006, "height": H["height"] * 0.92,
                           "arc": 105.0, "image": str(face.dir / face.data["image"])}))
    if face.data.get("pieces"):
        items += pieces_to_items(face.data["pieces"], hm, pal, face.dir, Item)
    if hair and not (hat and hat.data.get("replaces_hair")):
        items += pieces_to_items(hair.data["pieces"], hm, pal, hair.dir, Item)
    if hat:
        items += pieces_to_items(hat.data["pieces"], hm, pal, hat.dir, Item)
    for acc in av.parts["accessories"]:
        at = acc.data["attach"]
        if at == "head":
            items += pieces_to_items(acc.data["pieces"], hm, pal, acc.dir, Item)
        elif at == "torso":
            items += pieces_to_items(acc.data["pieces"], tc, pal, acc.dir, Item)
        elif at == "back":
            items += pieces_to_items(acc.data["pieces"], mat_mul(tc, translate(0, 0, -tsz[2] / 2)), pal, acc.dir, Item)
        elif at == "hips":
            items += pieces_to_items(acc.data["pieces"], hips_m, pal, acc.dir, Item)
    return items
