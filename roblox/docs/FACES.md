# Faces

50 flat face decals in `assets/faces/decal/`, searchable by tag. 30 are drawn in the classic Roblox cartoon style
(`tools/make_faces.py`), 20 are real Roblox catalog faces converted from their thumbnails to flat decals
(`tools/decalize_faces.py`, then hand-picked and hand-tagged by `tools/curate_faces.py`).
The full download (859 thumbnails, `tools/download_faces.py`) is kept in `assets/faces/index_full.json` and `assets/faces/_archive/`.

```python
from r6reel import faces
faces.search("#happy #laughing")        # AND by default; any_=True for OR
faces.get("classic_shocked")            # -> absolute PNG path (also accepts an id, a name, a tag, or a path)
faces.random("#angry", seed=3)
faces.tags()                            # tag -> count
```
CLI: `python -m r6reel faces search "#shocked"` and `python -m r6reel list faces`.

Tags: happy, laughing, shocked, surprised, scared, angry, sad, crying, confused, bored, smirk, worried, nervous, embarrassed,
cool, silly, love, evil, sick, dizzy, sleepy, neutral, serious, wink, tongue, blush, open_mouth, closed_eyes, big_eyes, cute, smile, default.

Add your own: drop a square transparent PNG into `assets/faces/decal/` and add an entry to `assets/faces/index.json`
(`id`, `name`, `file`, `tags`, `kind: "decal"`), or pass a PNG path straight to `Avatar(face="path.png")` / `Scene.face(...)`.
Real Roblox faces are catalog assets; check usage rights for anything you publish.
