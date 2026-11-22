"""Story demo: a ~17 s storytime reel, 3 locations, a shock beat, a chase and a dialogue, auto-directed.

    python examples/story_demo.py            # preview quality -> out/demo.mp4 (+ out/demo.json)
    python examples/story_demo.py --final    # 720x1280 final quality -> out/demo_final.mp4
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from r6reel.director import Director, Beat

STORY = [
    Beat("Lunch period at my school was supposed to be totally normal.", character="Milo", location="cafeteria",
         emotion="neutral"),
    Beat("Then Milo dropped his tray in front of everyone.", character="Milo", emotion="shocked", action="drop"),
    Beat("Ava laughed so hard. Nice one genius!", character="Ava", target="Milo", emotion="laughing"),
    Beat("Milo turned bright red. It slipped, okay?", character="Milo", target="Ava", emotion="embarrassed"),
    Beat("So Milo ran. Straight down the hallway.", character="Milo", target="Ava", emotion="scared", action="run",
         location="school_hallway"),
    Beat("And that is why he never ate lunch there again.", character="Milo", emotion="smirk", location="street",
         mood="sad"),
]


def build(seed=7, size=(1080, 1920)):
    return Director(STORY, seed=seed, pace="normal", size=size, name="demo").build()


if __name__ == "__main__":
    final = "--final" in sys.argv
    sc = build(size=(720, 1280) if final else (1080, 1920))
    os.makedirs("out", exist_ok=True)
    sc.to_json("out/demo.json")
    for w in sc.validate():
        print("warn:", w)
    out = "out/demo_final.mp4" if final else "out/demo.mp4"
    sc.render(out, preview=not final, progress=lambda i, n: print(f"\r{i}/{n}", end="") if i % 10 == 0 else None)
    print("\nwrote", out, f"({sc.duration:.1f}s)")
