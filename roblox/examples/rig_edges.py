"""GL close-ups: smooth vs classic edge style at 3 poses -> out/rig_edges.png"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from PIL import Image
from r6reel.renderer import Renderer, CameraState, Lighting
from r6reel.avatar import Avatar
from r6reel import rig

POSES = [
    {"Right Shoulder": (165, 0, 20), "Left Shoulder": (40, 0, -30)},
    {"Right Shoulder": (82, 0, -58), "Left Shoulder": (96, 0, 58)},
    {"Right Hip": (80, 0, 3), "Left Hip": (-15, 0, -3), "Right Shoulder": (-30, 0, 25), "Left Shoulder": (50, 0, -15)},
]


def main(out="out/rig_edges.png"):
    r = Renderer(300, 420, samples=4)
    rows = []
    for style in ("smooth", "classic"):
        av = Avatar(name=style, hair="bun", shirt_color="#d9483b", pants_color="#2b3a67", face="smile",
                    accessories=["backpack"], edge_style=style)
        row = []
        for p in POSES:
            pose = {"root": {"pos": (0, 0, 0), "rot": (0, 0, 0)}, **p}
            pose = rig.with_root_offset(pose, rig.ground_lift(pose))
            cam = CameraState(eye=(3.2, 4.2, -8.5), target=(0, 3.0, 0), fov_y=42)
            row.append(r.render(av.draw_items(pose, np.eye(4)), cam, Lighting()))
        rows.append(np.concatenate(row, 1))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    Image.fromarray(np.concatenate(rows, 0)).save(out)
    print("saved", out)


if __name__ == "__main__":
    main()
