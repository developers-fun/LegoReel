"""Copy the part files a list of LDraw parts needs (and everything they reference) from a full LDraw
library into the project's ldraw/ folder.

    python3 tools/ldraw_bundle.py /path/to/full/ldraw part1 part2 ...   (or --list file.txt)

The LDraw library is (c) its contributors and licensed CC BY 4.0 (see ldraw/CAreadme.txt, CAlicense.txt).
"""
import re
import shutil
import sys
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "ldraw"
SEARCH = ("parts", "p", "parts/s", "p/48", "p/8")


def find(src, name):
    rel = name.replace("\\", "/").lower().strip()
    for d in SEARCH:
        p = src / d / rel
        if p.exists():
            return p
    return None


def bundle(src, parts):
    src = Path(src)
    seen, todo, copied = set(), [p if p.endswith(".dat") else p + ".dat" for p in parts], 0
    while todo:
        name = todo.pop()
        p = find(src, name)
        if p is None or p in seen:
            continue
        seen.add(p)
        rel = p.relative_to(src)
        out = DEST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, out)
        copied += 1
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("1 "):
                t = line.split()
                if len(t) >= 15:
                    todo.append(" ".join(t[14:]))
    for f in ("LDConfig.ldr", "CAreadme.txt", "CAlicense.txt", "CAlicense4.txt"):
        if (src / f).exists():
            shutil.copyfile(src / f, DEST / f)
    return copied


if __name__ == "__main__":
    args = sys.argv[1:]
    src = args[0]
    names = []
    rest = args[1:]
    if rest and rest[0] == "--list":
        names = [l.strip() for l in Path(rest[1]).read_text().splitlines() if l.strip()]
    else:
        names = rest
    print("copied", bundle(src, names), "files into", DEST)
