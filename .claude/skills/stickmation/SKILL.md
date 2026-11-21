---
name: stickmation
description: Make, edit or recreate 2D stick-figure videos with the stickreel engine (keyframes, 3D turnaround, faces, phone/pickaxe items, sound effects). Use for /stickmation, "stick figure", "stickreel", or "recreate this video".
---
Stickmation = the stickreel engine plus its Notion directory. Do these in order:
1. Follow the Brain protocol: fetch Brain root https://app.notion.com/p/41ec4c505ccf81bab83fd3d6a89aebd6, then Rules, then Owner profile.
2. Fetch the hub row "Spec - Stickmation hub (start here)" in the Notes database (collection://41ec4c50-5ccf-81d7-91a9-000b770697f5). Open only the child pages the task needs.
3. Get the code: repo developers-fun/LegoReel, branch `stick`, folder `stick/` (add it with add_repo if missing). No repo? Download the bundle from the hub and run `python3 tools/bundle.py --extract FILE OUT`.
4. Run `cd stick && python3 -m stickreel docs` and read it. It is the always-current reference; trust it over memory.
5. Author a JSON scene. Loop: `validate`, `sheet --times ...` (look at the picture), fix, then `render`. To copy a reference video use `compare` (see the hub's recreate playbook).
6. Sound: built-in synthesised cues in the scene's "audio" section; `sfx` lists them. Nobody has auditioned them, so say so.
7. Ask which app (Sand Blast! or Lazy Blocks) before any promo work. Plain copy, no hype, no share-bait asks. Confirm stickreel is allowed for promos (open question in Notes).
8. Never post or publish; hand the MP4 to the owner. Say at the end what you did not test.
9. Save what you learned to the Brain (new rows, one fact one place) and end with a "Session log - YYYY-MM-DD" row.
