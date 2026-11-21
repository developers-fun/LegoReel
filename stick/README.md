# stickreel

A 2D stick-figure animation engine built for an AI agent to drive. You write a JSON scene (keyframes, named poses,
loops, items, faces, camera, effects); it renders an MP4. No Python needed to make a video.

    python3 -m stickreel docs                      the full, always-current reference (print this first)
    python3 -m stickreel validate scene.json       errors come with did-you-mean hints
    python3 -m stickreel sheet scene.json --times 0,1,2     contact sheet: LOOK before you render video
    python3 -m stickreel poses                     sheets: every named pose, a turnaround (poses_turn.png), every face (poses_faces.png)
    python3 -m stickreel compare scene.json --ref REFDIR --frames 1,60,120    reference | mine | blend
    python3 -m stickreel render scene.json --out out.mp4 --workers 4
    python3 -m stickreel sfx                       list the synthesised sounds;  audio scene.json --out mix.wav mixes only the sound
    python3 -m unittest discover tests             27 tests
    python3 tools/bundle.py                        the whole project in ONE file: stickreel_bundle.md (--extract FILE OUT to unpack)

Needs numpy, Pillow, ffmpeg. (No scipy/OpenCV: the old `stickreel/rotofit.py` and `tools/` rotoscope code needs them and is kept only for reference.)

## The idea
One template figure with a handful of named numbers (limb angles, lean, yaw, expression). You key those numbers over
time. The engine does the rest: 2-bone IK so hands can grab things, automatic grounding so feet never float or sink,
easing, motion blur, distance-locked walk cycles, hit-timed tool loops, particles, light flashes.

- **3D turnaround**: `yaw` 0 = side, 90 = facing camera, 180 = other side, 270 = back. It tweens, so a turn is two keys.
- **Faces**: doodled expressions (`calm happy laugh sad angry scared surprised smirk cool sleepy wink dead cry blank love smug`)
  that wrap around the head, vanish from behind, and flap the mouth with `"talk": true`. Add your own in JSON.
- **Items**: any object can be held. Built in: `pick`, `phone` (screen plays a video; key `video` to swap it), plus
  rect/circle/sprite(PNG)/text. Two-handed grips and a second item in the other hand are supported.
- **Loops**: `walk`, `run`, `idle`, `wave`, `bounce`, `dance`, `chop`. Give a loop `"hits": [times]` and it retimes so
  each contact lands exactly on those times; `actor.hit` events then drive flashes, dust, and `grow` (e.g. a tunnel
  that gets longer on every strike).

## Sound
Scenes can carry an `"audio"` section: cues on fixed times or on events (`"you.hit"`, `"you.step"` for footfalls, a `{from,to,every}`
range for typing ticks), pitch jitter, pan, a music bed with fade-out. Built-in sounds are synthesised in `stickreel/sfx.py`
(thunk whoosh dirt clink coins ding sparkle riser boom shimmer tick pop step thump): no files, no downloads, no licences.
`python3 -m stickreel sfx` lists them, `sfx NAME --out x.wav` writes one, `audio scene.json --out mix.wav` mixes only the sound,
and `render` muxes it in automatically. Your own files work too (`{"file": "x.mp3", "t": 3}`). The synthesised sounds were
checked by spectrum and level only, nobody has listened yet: audition `sfx NAME` before trusting one.

## Polish switches
`canvas.out: [1080, 1920]` renders the 576x1024 authoring space at phone resolution; `canvas.post: {"vignette": 0.15, "grain": 0.02}`;
`canvas.blur: 3` motion blur; `camera.shake: {"times": "you.hit", "amp": 2, "dur": 0.15}`; faces blink by themselves
(`"blink": false` to stop); `"expr": null` hides the face (the dig-skit figures have none); actor `shadow`.

## Rules an agent must know (each one cost real time)
1. A key sets values that ARRIVE at its time; anything unmentioned holds. A prop first mentioned in a later key starts
   from its default at the previous key (it does not creep from t=0 or hold its final value backwards).
2. Reach targets (`hand_r_at`...) switch their own weight on when set and off with `null`. A hand target releases a
   two-handed `grip_rel` automatically.
3. Look at `sheet`/`compare` images, never trust numbers. Bad IK, wrong depth order and off-screen art only show up in pictures.
4. Artwork drawn for the unzoomed frame must extend past the frame edges if the camera will zoom or pan (the dig
   skit's wall and ground needed extending: black bars otherwise).
5. Time loops from events, do not key every frame: list the contact times in `hits`.

## Recreating a reference video (what worked)
Extract frames (`ffmpeg -i ref.mp4 ref/f%03d.png`), read contact sheets to find beats, write the generator script
(`scenes/dig_skit.py` is the worked example), `compare` against the reference at the beats, fix the biggest gap first.
`scenes/dig_skit.py` took the full 11.3 s reference (digging, shaft, drop, joint chop, flash, gold zoom, typed end text).

## Layout
`stickreel/`: `scene.py` (load/validate/evaluate), `skeleton.py` (3D rig + IK), `figure3d.py` (draw + faces),
`faces.py`, `poses.py` (poses and loops), `track.py` + `ease.py` (keyframes), `items.py` (phone/video), `render.py`,
`cli.py`, `art_dig.py` + `dig_bg.py` (artwork for the dig skit). `scenes/` worked example. `tests/` unit tests.

## Claude Code skill and Notion directory
`/stickmation` (`.claude/skills/stickmation/SKILL.md`, about 15 lines) only points at the Notion Brain: hub row
"Spec - Stickmation hub (start here)" with child pages (reference, code map, SFX catalog, scene recipes, gotchas, skill text).
Every session follows `docs/BRAIN_SYSTEM_PROMPT.md` (also loaded by the root `CLAUDE.md`).

## Media in this folder
`media/dig_skit.mp4` is the full 11.3 s recreation with sound (the render output folder `out/` is gitignored, so the keepers live here).
`media/all_frames.png` is a master image of all 339 frames of that video (26 per row, frame number every 10).
