# Brief for anyone adding parts

Read `parts/SCHEMA.md` first. Work in `/home/claude/blockreel`. Never edit engine code (`blockreel/`), the avatar files, the scenes or other people's parts.
Put your own helper scripts in `/tmp/<your-name>/`, not in the project. Only create files named `<your ids>.json` / `.png` / `.obj` inside the folder you were assigned.

## Loop for each part
1. Write the JSON (and PNG if needed). Faces and torso prints: use `blockreel.partkit` (`FaceCanvas`, `TorsoCanvas`):
   ```python
   import sys; sys.path.insert(0, "/home/claude/blockreel")
   from blockreel.partkit import FaceCanvas
   f = FaceCanvas(); f.eyes_dots(); f.brows("flat"); f.mouth_smile(); f.cheeks(); f.save("parts/faces/happy_01.png")
   ```
2. `cd /home/claude/blockreel && python3 -m blockreel parts check parts/<folder>/<id>.json` must say ok.
3. `python3 -m blockreel part-preview <folder> <id> --out /tmp/<your-name>/<id>.png`, then LOOK at the PNG with the Read tool. It shows the part on the main character from three angles (front, three-quarter, side). Fix what looks wrong: parts floating off the head, sticking through the face, wrong scale, the face hidden, ugly or muddy colours, jagged edges.
4. If a part is still bad after two fixes, delete its files and say so in your report. A smaller set of good parts beats a full set with junk.

## Look to aim for
Chunky, simple, glossy toy bricks. Bold shapes, clean colours, a clear silhouette from across a room. 3 to 14 pieces per part. Hair and hats should hug the head (cylinders slightly wider than 1.6 across, e.g. 1.72) and keep the face area clear. Colours by palette slot so the avatar can recolour them; use hex only for things that should never change colour.

Good hair example (parts/hair/short_01.json): a cap cylinder on top, a back cylinder shifted toward -z so the face stays visible, two sideburn boxes, and a thin fringe disc. Use `parts/headwear/cap_01.json`, `parts/torsos/jacket_zip.json`, `parts/accessories/backpack_01.json`, `parts/sets/tree_01.json` as format examples.

## Rules
- Original designs only. No logos, brand names, trademarks, real people, or characters from films, games or comics. Generic jobs and objects (pirate, chef, astronaut, knight) are fine.
- Names are short plain English, like "Backwards cap".
- Face PNGs: 320x256 transparent RGBA. Torso PNGs: 256x240 transparent RGBA. Nothing opaque behind the features.
- Do not use OBJ files unless you were told to.

## Report back
End with a short list: `id - name - one line` for every part you kept, then the ids you dropped and why. Nothing else.
