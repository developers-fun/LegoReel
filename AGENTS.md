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
python3 -m unittest discover tests          # 30 tests, about 45 s
python3 examples/make_demo_scene.py         # regenerates examples/demo_three_formats.json
```
Needs ffmpeg. Python 3.13, numpy, Pillow.

### Setup after a git clone (important)
`ldraw/` (130 MB of parts) is NOT in git. Download https://library.ldraw.org/library/updates/complete.zip, unzip it, then `python3 tools/ldraw_bundle.py <unzipped>/ldraw --list tools/ldraw_names.txt` and `python3 -m blockreel parts check`. The licence files and LDConfig.ldr are in git.

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

## Licensing and IP (tell the owner every time it matters)
- `ldraw/` is CC BY 4.0: keep `CAlicense.txt` / `CAreadme.txt` and credit LDraw when publishing.
- Many LDraw parts copy real product designs, including licensed themes (film, comic, game characters). For promo videos use plain generic parts. Do not use the LEGO name or logos in copy. Check platform and App Store rules for anything that looks like a branded toy.
- The Wants and Needs study is analysis only. Use principles, never their look, name, lines or products, and never present anything as theirs.

## Wants and Needs study (in the Notion brain)
Two notes in the Notes data source (`collection://41ec4c50-5ccf-81d7-91a9-000b770697f5`): "Wants and Needs: account data and what the numbers show" (Fact) and "Wants and Needs: video taste playbook (study notes)" (Playbook). Summary: borrowed internet formats (challenges, game clips, skits) with the product as the payoff, 17 to 32 s, one idea and one payoff, sales line in the caption (not the hook), numbered drops with dates and scarcity, candid founder voice, neutral clothing palette. Skits earned about 10x the views of product-only posts; recent posts are weaker than spring 2026 (cause unknown). Visual details are inferred from captions and transcripts; nobody has watched the videos yet. Manifold credits: about 9 used of a roughly 25 budget. Their TikTok is `@wantsandneedsbrand`; the Instagram handle `wantsandneeds` is an unrelated account.

## Notion brain
Every session must follow `docs/BRAIN_SYSTEM_PROMPT.md` (also loaded via `CLAUDE.md`): read the Brain before work, write to it as you go, end with a Session log row. The 2D engine is documented in `stick/README.md` (`python3 -m stickreel docs` prints the live reference).
Brain root: https://app.notion.com/p/41ec4c505ccf81bab83fd3d6a89aebd6. Spec page for this project: "Spec - Brick figure and part templates (blockreel)" (updated with the minifig and expression sections). Old R6 notes are archived as "OLD notes - ...". The Notion free-plan block grace period ends 2026-11-23; after that writes need a paid plan, so keep important notes in this repo.

## Green-screen promo reels (2026-11-21)
`reels/make_promo_reels.py` writes `reels/sand_blast_cover_reveal.json` and `reels/lazy_blocks_row_clear.json`. Both end on the same fixed straight-on iPad shot whose screen is a flat green box, so the owner can lay a gameplay recording over it.
- Keep the green flat: `meta.look` vignette 0, bloom 0, gloss 0, dof None, tint [1,1,1], and `light.spec_strength` 0. The screen prop uses bevel 0 and no shadow. Measured result: the rectangle is x 168 to 911, y 502 to 1491 (744 x 990 px, 3:4) in a 1080 x 1920 frame, RGB about (6, 228, 8) after H.264. Identical in both reels.
- Overlay with ffmpeg: scale the recording to 744 x 990 (crop to fit, do not stretch), `overlay=168:502:enable='gte(t,START)'`. Green starts at 6.3 s in Sand Blast! and 7.5 s in Lazy Blocks.
- Render only the moving part, then loop one still frame: the held shot is static, so make the hold with `ffmpeg -loop 1 -framerate 30 -i frame.png -frames:v N` using the same flags as the renderer (`scale=out_color_matrix=bt709:out_range=tv,format=yuv420p`, libx264 crf 18, bt709 tags), then `concat -c copy`. This cut a 36 minute render to about 16 minutes. Check that two frames a few tenths apart are pixel-identical first: hook text animates in for about 0.5 s after it starts, and a still taken during that fade freezes a half-faded caption.
- `--workers 2` was used; about 2.2 s per frame at 1080 x 1920, supersample 2.
- A prop `track` can include keys later than its shot's length (they are ignored), but times are relative to the named shot, so put follow-up motion in the shot where you want to see it.
- To clear a character out of a held shot, `teleport` it at t 0 of that shot (the hero in the Sand Blast! reel goes to x 9).

## Sound effects (2026-11-21)
`tools/sfx_fetch.py "<sound>" --n 3 --max-ms 3000 --out sfx/` searches Openverse for CC0 audio (no key) and downloads preview mp3s, logging title, creator and page in `credits.json`. Anonymous limit is 20 requests a minute and 200 a day. Do not use `category=sound_effect` (Freesound items have none, so it returns 0). The duration filter does nothing, so the script filters on the `duration` field in milliseconds. The API sometimes returns 500 on the first try; the script retries. Audio has not been played back or muxed into a reel yet (`meta.audio` is still untested); mix with ffmpeg after the render.

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

## Dig skit reel (2026-11-21)
`reels/make_dig_skit.py` writes `reels/sand_blast_dig_skit.json` (15 s: side cutaway dig skit, both sit, behind, held green phone).
- New renderer options: overlay `x` / `size` (screen fraction, for labels pinned to world points), pose `snap: true` (skips the 0.2 s pose blend right after a cut/teleport), poses `dig` (loop, `speed` = chops/s) and `phone` (hold, seated).
- Props cannot rotate or scale, so digging progress is faked with dirt-coloured slices that jump away (track to y -60) as the digger steps forward (`move_to` with `then_pose`). Pickaxe = two box props whose tracks are sampled every 0.05 s from the same hand formula as the `dig` pose; during a step the hand uses phase 0.
- In an action, `move_to` cannot also carry `pose` or `face` (they count as separate kinds); use `then_pose` only.
- Avatar variant `guest` needs LDraw part 2524, which is not in the bundled library; use `jacket` for the second character.
- Render chunks 0-3.7, 3.7-7.5, 7.5-10 s (about 1.6 s per frame), hold = one still at t 10.0 looped 5 s. Green rectangle measured x 279-800, y 255-1407 (522 x 1153, 9:19.8), inside Instagram's top 230 / bottom 1440 safe zone. Sound not added yet.
