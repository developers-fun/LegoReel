#!/usr/bin/env python3
"""Build the lean ~50-face library: 30 drawn classic faces + 20 hand-picked real Roblox faces (decalized).
Full download index is kept in assets/faces/index_full.json, other files in assets/faces/_archive/."""
import json, os, shutil
ROOT = os.path.join(os.path.dirname(__file__), "..", "assets", "faces")
REAL = {  # last-5-digits of the Roblox asset id -> tags (checked by eye)
 "22666": ["happy", "laughing", "open_mouth"], "42153": ["happy", "smile"], "30608": ["happy", "silly", "big_eyes"],
 "14862": ["happy", "wink", "smirk"], "78843": ["laughing", "happy", "blush", "closed_eyes"], "75363": ["laughing", "closed_eyes"],
 "10438": ["laughing", "happy", "open_mouth"], "51612": ["laughing", "happy", "open_mouth"], "39188": ["shocked", "surprised"],
 "08041": ["shocked", "surprised", "open_mouth"], "24984": ["scared", "shocked", "big_eyes"], "90471": ["scared", "shocked", "big_eyes"],
 "98394": ["angry", "serious"], "90577": ["angry", "evil"], "63984": ["angry", "evil", "smirk"], "19729": ["dizzy", "confused"],
 "55664": ["bored", "blush"], "09386": ["embarrassed", "cute", "blush", "closed_eyes"], "31643": ["silly", "tongue", "cute"],
 "49143": ["silly", "happy", "tongue", "closed_eyes"]}
SKIP_CLASSIC = {"proud", "annoyed"}

def main():
    full_p = os.path.join(ROOT, "index_full.json")
    if not os.path.exists(full_p): shutil.copy(os.path.join(ROOT, "index.json"), full_p)
    full = {x["id"]: x for x in json.load(open(full_p))}
    ctags = json.load(open(os.path.join(ROOT, "decal", "_classic_tags.json")))
    out = []
    for name, tg in ctags.items():
        if name in SKIP_CLASSIC: continue
        out.append({"id": f"classic_{name}", "name": name.replace("_", " ").title(), "file": f"decal/classic_{name}.png", "tags": tg,
                    "kind": "decal", "source": "drawn (classic style)", "asset_id": None})
    for suf, tg in REAL.items():
        m = [i for i in full if i.endswith(suf)]
        assert len(m) == 1, (suf, m)
        x = full[m[0]]
        out.append({"id": x["id"], "name": x["name"], "file": f"decal/{x['id']}.png", "tags": tg, "kind": "decal",
                    "source": "roblox catalog (decalized from thumbnail)", "asset_id": x.get("asset_id")})
    keep = {os.path.basename(o["file"]) for o in out}
    arch = os.path.join(ROOT, "_archive"); os.makedirs(os.path.join(arch, "decal"), exist_ok=True)
    for f in os.listdir(os.path.join(ROOT, "decal")):
        if f not in keep and not f.startswith("_"): shutil.move(os.path.join(ROOT, "decal", f), os.path.join(arch, "decal", f))
    if os.path.isdir(os.path.join(ROOT, "png")): shutil.move(os.path.join(ROOT, "png"), os.path.join(arch, "png"))
    json.dump(out, open(os.path.join(ROOT, "index.json"), "w"), indent=1)
    print(len(out), "faces in lean index")
main()
