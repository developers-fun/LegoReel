"""Write part templates (parts/<folder>/ld_<number>.json) for the LDraw minifigure parts bundled in ldraw/.

    python3 tools/ldraw_catalog.py

Heads become faces, 973 torsos become torsos, hips and legs become legs, hair and hats become hair and
headwear, neckwear becomes accessories. Each file only names the part and holds its LDraw title; the
geometry stays in ldraw/ (LDraw library, CC BY 4.0, see ldraw/CAreadme.txt).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LD = ROOT / "ldraw" / "parts"
SRC = "LDraw (CC BY 4.0)"


def header(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:60]
    title = lines[0][2:].strip() if lines else ""
    cat = None
    for l in lines:
        if l.startswith("0 !CATEGORY"):
            cat = l[12:].strip()
    if not cat and title.lstrip("~=").startswith("Minifig"):
        cat = " ".join(title.lstrip("~=").split()[:2])
    return title, cat


def clean(title):
    t = re.sub(r"^~?\s*Minifig(ure)?\s*", "", title).strip()
    t = re.sub(r"\s*Pattern\s*$", "", t)
    t = re.sub(r"\s*\((Blocked )?Hollow Stud\)", "", t)
    return (t or title)[:110]


def write(folder, pid, data):
    d = ROOT / "parts" / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")


def main():
    rows = {}
    for f in LD.glob("*.dat"):
        title, cat = header(f)
        rows[f.stem] = (title, cat)
    n = {"faces": 0, "torsos": 0, "legs": 0, "hair": 0, "headwear": 0, "accessories": 0}
    for pid, (title, cat) in sorted(rows.items()):
        if title.startswith("~") or title.startswith("="):
            continue                                           # obsolete / alias parts
        if cat == "Minifig Head" and re.match(r"^3626[bc]", pid):
            write("faces", f"ld_{pid}", {"kind": "face", "name": clean(title), "ldraw": pid, "title": title, "source": SRC,
                                         "tags": ["lego", "head"]})
            n["faces"] += 1
        elif cat == "Minifig Torso" and re.match(r"^973(p|$)", pid) and "Arms and Hands" not in title:
            write("torsos", f"ld_{pid}", {"kind": "torso", "name": clean(title),
                                          "ldraw": {"torso": pid, "arm_r": "3818", "arm_l": "3819", "hand": "3820"},
                                          "base": "primary", "arm": "primary", "title": title, "source": SRC, "tags": ["lego", "torso"]})
            n["torsos"] += 1
        elif cat == "Minifig Hips" and re.match(r"^3815(p|$)", pid):
            write("legs", f"ld_{pid}", {"kind": "legs", "name": clean(title),
                                        "ldraw": {"hips": pid, "leg_r": "3816", "leg_l": "3817"}, "hips": "pants",
                                        "title": title, "source": SRC, "tags": ["lego", "legs"]})
            n["legs"] += 1
        elif cat == "Minifig Leg" and re.match(r"^3816", pid):
            left = "3817" + pid[4:]
            if left in rows:
                write("legs", f"ld_{pid}", {"kind": "legs", "name": clean(title),
                                            "ldraw": {"hips": "3815", "leg_r": pid, "leg_l": left}, "hips": "pants",
                                            "title": title, "source": SRC, "tags": ["lego", "legs"]})
                n["legs"] += 1
        elif cat in ("Minifig Headwear", "Minifig Hat", "Minifig Helmet", "Minifig Hair"):
            is_hair = bool(re.search(r"\bHair\b", title))
            helmet = bool(re.search(r"Helmet|Hood|Cowl", title))
            data = {"kind": "hair" if is_hair else "headwear", "name": clean(title),
                    "pieces": [{"shape": "ldraw", "part": pid, "color": "hair" if is_hair else "primary"}],
                    "title": title, "source": SRC, "tags": ["lego", "hair" if is_hair else "hat"]}
            if helmet and not is_hair:
                data["replaces_hair"] = True
            write("hair" if is_hair else "headwear", f"ld_{pid}", data)
            n["hair" if is_hair else "headwear"] += 1
        elif cat == "Minifig Neckwear":
            write("accessories", f"ld_{pid}", {"kind": "accessory", "name": clean(title), "attach": "torso",
                                               "pieces": [{"shape": "ldraw", "part": pid, "color": "accent"}],
                                               "title": title, "source": SRC, "tags": ["lego", "neck"]})
            n["accessories"] += 1
    write("legs", "ld_3815", {"kind": "legs", "name": "Plain hips and legs",
                              "ldraw": {"hips": "3815", "leg_r": "3816", "leg_l": "3817"}, "hips": "pants",
                              "title": "Minifig Hips and Legs (plain)", "source": SRC, "tags": ["lego", "legs"]})
    print(n)


if __name__ == "__main__":
    main()
