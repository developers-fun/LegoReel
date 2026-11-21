"""Make 'back side' face parts for two-sided LDraw heads (the print on the back of the head is a second expression).
Usage: python3 tools/ldraw_expressions.py 3626cp78 3626cp0a ...   writes parts/faces/ld_<n>_back.json"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for n in sys.argv[1:]:
    src = ROOT / "parts" / "faces" / f"ld_{n}.json"
    d = json.loads(src.read_text())
    d["flip"] = True
    d["name"] = d.get("name", n) + " (back side)"
    d["title"] = d["title"] + " [back side]"
    (ROOT / "parts" / "faces" / f"ld_{n}_back.json").write_text(json.dumps(d, indent=1))
    print("wrote", f"ld_{n}_back")
