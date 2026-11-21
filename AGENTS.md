# AGENTS.md: handoff notes for a new agent

Read this first. README.md is the user manual; this file is what a new agent needs to carry on the work.
Last updated 2026-11-21 by the agent that built v5. Repo: https://github.com/developers-fun/LegoReel (it was created public; the owner is switching it to private).

## What this is
`blockreel` (repo name LegoReel) is a pure Python + numpy software 3D renderer. A JSON scene file (shots, fixed cameras, dialogue, props, poses) becomes 1080x1920, 30 fps, 9:16 MP4 videos of toy-brick minifigures. The owner is a solo iOS / React Native developer who makes short-form promo videos for two apps: **Sand Blast!** and **Lazy Blocks**. The renderer is meant to be a "really good engine" for those videos.

Owner preferences that matter: be direct and honest, disagree when something is weak; lead with the conclusion; plain prose, little bullet clutter; no hype or corny copy in app/marketing text; if a promo task does not say which app it is for, ask which app before doing any work; the owner is often asleep or away, so work unattended and say at the end what was not tested.

## Run it (Linux sandbox or Windows PowerShell)
```
python3 -m blockreel validate examples/demo_three_formats.json     # checks only
python3 -m blockreel render examples/demo_three_formats.json --preview --start 8 --end 8.04 --frames-only --save-frames /tmp/fr   # cheap look
python3 -m blockreel render examples/demo_three_formats.json --start 0 --end 8.3 --out out/chunk0.mp4          # full quality chunk
python3 -m blockreel avatar main            # resolved look + fingerprint
python3 -m blockreel parts check            # validate all parts
python3 -m blockreel part-preview faces ld_3626bp05 --out face.png
python3 -m unittest discover tests          # 119 tests, about 75 s
python3 -m blockreel preflight reels/x.json --sheet out/x_sheet.png   # pre-render checks + contact sheet (run BEFORE any full render)
python3 -m blockreel check-video out/x.mp4 --scene reels/x.json       # verify a finished MP4
python3 examples/make_demo_scene.py         # regenerates examples/demo_three_formats.json
```
Needs ffmpeg. Python 3.13, numpy, Pillow.

### Setup after a git clone (important)
`ldraw/` (130 MB of parts) is NOT in git. Download https://library.ldraw.org/library/updates/complete.zip, unzip it, then `python3 tools/ldraw_bundle.py <unzipped>/ldraw --from-parts` (derives the part list from `parts/`; the old `--list tools/ldraw_names.txt` is stale and misses 111 accessory parts) and `python3 -m blockreel parts check`. The licence files and LDConfig.ldr are in git.

### Render speed and how to run long renders
About 3 to 4 s per frame at full quality on 2 cores (the 987-frame demo takes about 50 to 65 minutes). Foreground tool calls cap at 10 minutes and background processes are killed when a chat reply ends, so: render in chunks of about 8 s with `--start/--end` (frame boundaries must be multiples of 1/30), run them with `nohup` from a script while the turn is still going, poll with `sleep`, then join with `ffmpeg -f concat -safe 0 -i list.txt -c copy out.mp4`. Always check `ffprobe -count_frames` (987 frames expected for the demo).

## Architecture (blockreel/)
`scene.py` loads and validates scenes, camera rules and lookups; `render.py` builds items per frame, ground studs, lip flap, post effects, multiprocessing, ffmpeg export; `raster.py` is the software rasterizer (z-buffer, Gouraud lighting, perspective-correct interpolation, near clip, ground ray-cast with shadows, fog); `figure.py` builds the figure from rig + avatar + parts (`build_minifig_items` for the real minifig, `build_brick_items` dispatches; the older generic brick figure and R6 are kept); `ldraw.py` imports LDraw .dat files (sub-files, BFC winding, colour 16/24, per-vertex print colours); `parts.py` loads and validates part templates (`PIECE_KEYS`, `TOP_KEYS`, `SHAPES`); `avatar.py`/`appearance.py` avatar files, variants, fingerprint; `poses.py` procedural pose clips; `meshes.py` boxes, prisms, studs, spheres, obj, ldraw meshes; `overlay.py` text; `style.py` style files and rules; `preview.py` part previews.

Key facts:
- Real figure geometry and prints come from the LDraw library (CC BY 4.0), not an official LEGO asset pack (none exists). Assembly offsets were read from LDraw `parts/76382p00.dat` and live in `rigs/minifig.json`. LDU to world scale is `LD_SCALE = 0.0582` (92 LDU body = 5.35 studs); axes flip (x, -y, -z).
- Printed parts keep per-vertex colours (colour code >= 0); colour 16 = take the palette slot. Explicit-colour vertices use a 0.9975 depth bias so prints sit over the base surface.
- Part files are generated: `tools/ldraw_catalog.py` writes `parts/<folder>/ld_<number>.json` for about 2,150 parts; `tools/ldraw_expressions.py <numbers>` writes `ld_<n>_back.json` (two-sided heads: `"flip": true` turns the head 180 degrees to show the back print).
- Avatars: `avatars/main.json` is the one locked character (rig minifig, painted: yellow skin, brown hair, blue shirt, navy trousers; variants plain, jacket, host, guest). `avatars/gray.json` is the plain gray look the owner asked for earlier. A locked avatar's skin and rig cannot change per scene; variants may change only what `variants_may_change` lists. Bump `version` when you change `main`.
- Expressions on main: calm, happy, laugh, sad, angry, scared, surprised, smirk, cool, sleepy (each `name`, `name_2`, `name_3`...) and `talk_1..4`. Lip flap runs while a character is a dialogue `speaker` and has no expression set (`render._mouth_frame`).
- Ground: `meta.ground.geo_studs` builds real raised studs on the lattice (pitch = `tile` = 1.164, radius = `studs` x tile) near the camera; the flat painted circles still cover the distance. Zones must use the same tile.
- House style rules (`styles/house.json`): one fixed camera per shot, no shake, loader refuses violations. Text must be readable (the validator warns if words per second is too high: roughly 3.5 words per second at most).
- Scene generation for the demo is in `examples/make_demo_scene.py` (three formats: EDIT RUN, REVEAL SKIT, CUP CHALLENGE, with a made-up "Bluebox" product). It is a sample, not a template for the owner's real promos.

## Stud grid (blockreel/grid.py, tests/test_grid.py)
On by default (`meta.grid`: enabled, props, characters, zones, rotation; a prop opts out with `"grid": false`). 1 stud = `ground.tile` = 1.164 units; ground stud centres are at (i+0.5)*pitch, so edges are on whole multiples. At load: box and cylinder props become whole-stud footprints (4x6, not 3.7x5.9) with heights in whole plates (0.4 pitch; a brick is 3 plates), bottom edge on a plate line, rotation snapped to 90 degrees, edges on lattice lines (even and odd widths both handled); set pieces (prefabs) are uniformly rescaled (clamped to 0.6x to 1.6x) so the larger footprint side is whole studs, position snapped (the other side may stay fractional, it is reserved as ceil cells); characters snap x to a lattice line and z to a stud centre (a minifig is 2 wide, 1 deep) for start, move_to and teleport, y untouched; ground zone rects snap to lattice lines; prop tracks shift by the same delta; props with `"studs": true` get exactly one stud per cell so they line up with the ground. `validate` lists everything snapped. Snapping can move things into each other (the sample scene's hero walked into the table once the table grew), which is what `preflight` is for: it errors on off-grid props and on props passing through characters.

## Pre-render checks (blockreel/preflight.py, tests/test_preflight.py)
A full render costs ~40 minutes, so `render` now runs the static preflight first and refuses on errors (`--skip-preflight` overrides). Three layers: static (timing, text speed / safe zone / overlap / brand words / contrast, characters framed and facing camera, props through characters, camera variety, end hold), stills (`--stills`/`--sheet`: half-size frames per shot, blank/dark/bright, cuts that do not change the picture, determinism; the sheet draws the safe zone in red and lists shot and time, look at it), and `check-video` (frame count, size, fps, black or frozen frames). Findings are error / warn / info; fades to black are exempt from the blank check. Workflow for a new reel: write scene, `validate`, `preflight --sheet`, look at the sheet, fix, then chunked full render, then `check-video`.

## Licensing and IP (tell the owner every time it matters)
- `ldraw/` is CC BY 4.0: keep `CAlicense.txt` / `CAreadme.txt` and credit LDraw when publishing.
- Many LDraw parts copy real product designs, including licensed themes (film, comic, game characters). For promo videos use plain generic parts. Do not use the LEGO name or logos in copy. Check platform and App Store rules for anything that looks like a branded toy.
- The Wants and Needs study is analysis only. Use principles, never their look, name, lines or products, and never present anything as theirs.

## Wants and Needs study (in the Notion brain)
Two notes in the Notes data source (`collection://41ec4c50-5ccf-81d7-91a9-000b770697f5`): "Wants and Needs: account data and what the numbers show" (Fact) and "Wants and Needs: video taste playbook (study notes)" (Playbook). Summary: borrowed internet formats (challenges, game clips, skits) with the product as the payoff, 17 to 32 s, one idea and one payoff, sales line in the caption (not the hook), numbered drops with dates and scarcity, candid founder voice, neutral clothing palette. Skits earned about 10x the views of product-only posts; recent posts are weaker than spring 2026 (cause unknown). Visual details are inferred from captions and transcripts; nobody has watched the videos yet. Manifold credits: about 9 used of a roughly 25 budget. Their TikTok is `@wantsandneedsbrand`; the Instagram handle `wantsandneeds` is an unrelated account.

## Notion brain
Brain root: https://app.notion.com/p/41ec4c505ccf81bab83fd3d6a89aebd6. Spec page for this project: "Spec - Brick figure and part templates (blockreel)" (updated with the minifig and expression sections). Old R6 notes are archived as "OLD notes - ...". The Notion free-plan block grace period ends 2026-11-23; after that writes need a paid plan, so keep important notes in this repo.

## Known issues and not done
- Not tested on Windows. Audio muxing (`meta.audio`) never exercised.
- Held items and the Minifig Accessory category (826 LDraw parts) are not imported; orientation per part is unknown.
- Only about 100 of the 2,150 LDraw parts were checked on contact sheets; hair/hat offsets and neckwear placement may be off for some, and prints may z-fight on rare parts. Torsos with printed arms use plain palette arms.
- Two-sided heads keep the hair facing the front when the head turns to show the back print (looks fine on the standard hair, check others).
- Leg parts can only add pieces in the hips frame (skirts checked in standing poses only). Held items sit in front of the forearm.
- Speed: pure numpy, about 3 to 4 s per frame; no caching between frames. Ideas: cache per-avatar meshes per pose, tile-based culling, lower supersample for drafts.
- Jagged bevel corners on large boxes with subdivision; far ground is a flat decal (studs only built within 34 units).
- Props cannot rotate or change colour over time; camera cuts only; poses are procedural, limbs rigid.
- Two earlier stray "placeholder" scheduled triggers fired in a past session; nothing to do.

## Good next steps
1. Switch the repo to private (GitHub Settings, Danger Zone) if the owner has not.
2. Ask the owner which app (Sand Blast! or Lazy Blocks) a real promo is for, then build scenes for it in the studied structure (hook, one escalation, product or app reveal, 20 to 25 s) using the `main` avatar and expression faces.
3. Have the owner watch the top 5 Wants and Needs videos (or approve a frame-grab pass) to confirm the visual notes.
4. Import held items; add a `parts/` browser contact sheet script; test on Windows; speed work.
