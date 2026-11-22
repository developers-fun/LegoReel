> **Where this lives:** repo developers-fun/LegoReel, branch `robloxAnimation`, folder `roblox/` (the rest of the repo is the 3D brick renderer and the 2D stickreel engine; this folder is independent of them).
> Skill: `/robloxmotion` (`.claude/skills/robloxmotion/SKILL.md`). Long-form notes are in the owner's Obsidian vault: `work/active/Promo Engine/Project - Roblox animation renderer (r6reel).md`.
> Run all commands from this folder (`cd roblox`).

# AGENTS.md - handoff for future sessions

## Architecture
- Core (finished, do not edit casually): mesh, primitives, world (builders), renderer/post/video (moderngl),
  rig/avatar/anim/clips (R6), camera (+ shot presets), transitions, captions.
- Integration layer: `presets.py` (lighting, LOCATIONS, emotions, tables) -> `fx.py` (particles as DrawItems) ->
  `timeline.py` (Shot dataclass, build_camera, transitions, Timeline) -> `scene.py` (Scene: data, JSON, frame(t),
  render, contact_sheet, validate) -> `director.py` (Beat/script -> Scene) -> `cli.py`/`__main__.py`.
- `Scene.frame(t)` is pure: shot lookup, transition compose (post + cam offset), set items + visible characters +
  props + fx, per-shot lighting and shadow extent, eye clamp to set bounds.

## Conventions
- Camera lives on the cam_side (-Z by default) of a set; characters face `heading` (0, or 180 for cam_side +1, e.g.
  classroom). Sun z is mirrored for cam_side +1. Set `bounds` clamp the camera eye (walls).
- Each Shot owns its Camera (absolute times), so moves never leak. Whip/dust/flash windows are centred on shot.t0.
- Director only emits Scene data; everything is JSON-editable afterwards. Randomness: `np.random.default_rng([seed, beat, 17])`.
- Looping clips never end by themselves: always pass `until=` (Director does).
- Characters outside a beat are hidden through `visible` windows; `place` actions teleport at beat starts.

## Verify
`python -m pytest tests -q`; `python examples/story_demo.py` then
`python3 tools_framegrid.py out/demo.mp4 --step 6 --cols 8 --per 40 --tile-h 200 --out out/maps/demo` and view the jpgs.
`Scene.contact_sheet(times)` for quick looks without encoding. Check: face visible in close-ups, no ground clipping, cuts change size, captions readable.

## Known limits / gotchas
- Dust cover is a stack of translucent spheres (milky, faceted at low res). No stars/night lamps glow yet.
- Feet-insert and tracking shots can lose the subject (validate warns); hallway side cameras are clamped by walls.
- Prop attach uses the arm part frame (offset in studs); sit/seat clips need manual `place` with y = seat_top - 1.
- faces library optional (lazy import); blink micro-animation not implemented (only mid-shot face swaps).
- Final quality ~0.21 s/frame at 720x1280 on llvmpipe.

## Storyboard
`python -m r6reel storyboard scene.json --out out/storyboard.png` (see docs/STORYBOARD.md): key frames + arrows + footprints + checks. Run it before any big render. Skill: `/robloxstoryboard`. Code: r6reel/storyboard.py, tests/test_storyboard.py.
