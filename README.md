# blockreel

Turns a JSON scene file (shot list, timing, dialogue, fixed cameras) into PNG frames and an MP4, in a blocky 3D look.

**Real toy-brick minifigure built from swappable templates.** The default figure (rig `minifig`, `rigs/minifig.json`) uses real minifigure geometry from the open **LDraw parts library** (about 2,150 heads, torsos, hair, hats, legs and neckwear, with their printed faces and shirts). Each part is a small JSON file in `parts/` that points at an LDraw part number, so you add more by listing a number. Colours come from palette slots (`skin hand hair primary secondary accent pants shoes metal dark light`), so one part works in any colour; printed areas (faces, shirt prints) keep their own colours. The look is one locked avatar file (`avatars/main.json`) and every scene refers to it by name, so the character is identical in every video. The older generic brick figure (rig `brick`) and the Roblox-style figure (rig `r6`) still load if an avatar asks for them.

**Fixed cameras, no shake.** The default style (`styles/house.json`) allows one camera per shot and no screen shake. The loader refuses scenes that break this.

**Licence and trademark.** The renderer code is original. The part geometry and prints in `ldraw/` come from the community LDraw library, licensed **CC BY 4.0** (see `ldraw/CAlicense.txt` and `ldraw/CAreadme.txt`; keep them with the files and keep the credit when you publish). This is a community-made library, **not an official LEGO asset pack**; no such pack exists. Many parts are copies of real product designs, including licensed themes (film, comic and game characters). LEGO is a trademark of a company that does not sponsor this project. For promo videos, use plain generic parts (the default set), do not use LEGO names or logos in copy, and check the rules for the platform and the app store before you post anything that looks like a branded toy.

**Status:** run on Linux (Python 3.13, 2 CPU cores) only. The demo (`examples/demo_three_formats.json`, 972 frames at 1080x1920, supersample 2) is rendered with the numbers in the final summary of the last session; see "Limits" for speed. Not run on Windows. Audio muxing (`meta.audio`) was not exercised. Tests: `py -m unittest discover -s tests -v`.

## Requirements

- Python 3.10 or newer
- numpy and Pillow (`requirements.txt`; Pillow 10.1+ for the fallback font)
- ffmpeg on your PATH (only needed for MP4 output). Windows: `winget install Gyan.FFmpeg`, then open a new terminal and check `ffmpeg -version`.
- No GPU needed. Rendering is software only.

## Install and run (Windows PowerShell)

```powershell
cd blockreel
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1. check the scene file (renders nothing)
py -m blockreel validate examples\sample_scene.json

# 2. render
py -m blockreel render examples\sample_scene.json --out out\sample.mp4
```

macOS and Linux: the same, with `python3` and `source .venv/bin/activate`.

The exact command to produce the sample video:

```
py -m blockreel render examples\sample_scene.json --out out\sample.mp4
```

## Setup from a git clone

The repository does not contain the LDraw parts (about 130 MB). After cloning, rebuild `ldraw/` once:

```
# 1. download the complete LDraw library (CC BY 4.0): https://library.ldraw.org/library/updates/complete.zip and unzip it
# 2. copy the parts this project uses (about 2,150 plus what they reference)
py tools/ldraw_bundle.py C:\path\to\unzipped\ldraw --list tools/ldraw_names.txt
# 3. check everything loads
py -m blockreel parts check
```
Renders go to `out/`, which git ignores. `tools/ldraw_catalog.py` rebuilds the `ld_*` part files if you add part numbers to `tools/ldraw_names.txt`.

## First run

1. `py -m blockreel validate examples\sample_scene.json` prints the timeline and any warnings.
2. `py -m blockreel render examples\sample_scene.json --preview --end 1 --frames-only --save-frames out\check` writes a few half-size PNGs. Open one and look at it before committing to a full render.
3. Full render: the command above.

## Commands and options

| Command | What it does |
|---|---|
| `validate SCENE` | Loads and checks the scene, prints size, duration, shots and warnings. |
| `render SCENE` | Renders frames and encodes an MP4. |
| `measure` | Prints the rig's exact measurements, rebuilds the figure and checks it against them. |
| `avatar NAME [--variant V]` | Prints an avatar's resolved look and its fingerprint. |
| `appearance` | Prints the default appearance as JSON, as a starting point for a new avatar file. |

`render` options:

| Option | Meaning |
|---|---|
| `--out PATH` | Output MP4. Default `out/<scene name>.mp4`. |
| `--preview` | Half resolution, no anti-aliasing. For checking motion and framing. |
| `--start S`, `--end S` | Render only part of the scene, in seconds. |
| `--workers N` | Parallel processes. Default is half your CPU cores. Each uses a few hundred MB at 1080x1920 with supersample 2. Lower it if memory runs out. |
| `--supersample N` | Anti-aliasing, 1 to 4. 2 is the default. Cost grows with the square. |
| `--frames-only` | Write PNG frames and skip ffmpeg. |
| `--save-frames DIR` | Also write PNG frames to a folder. |
| `--crf N`, `--preset NAME` | x264 quality (default 18) and speed preset (default `medium`). |

Export settings used by default: H.264 (libx264), yuv420p, BT.709 colour, `+faststart`, AAC 192k audio if an audio file is set, size and frame rate from the scene (default 1080x1920 at 30 fps). No render-time benchmarks exist yet, so no speed claims are made here.

## Scene file

Plain JSON (no comments). Top level: `meta`, `characters`, `props`, `shots`. Unknown keys are errors, so typos are caught by `validate`.

World: units are studs (the character is 5 studs tall). +y is up. A character with `yaw` 0 faces +z. Positive yaw turns toward +x.

### meta

| Key | Default | Notes |
|---|---|---|
| `width`, `height` | 1080, 1920 | Must be even. |
| `fps` | 30 | |
| `supersample` | 2 | 1 to 4. |
| `style` | `"house"` | `styles/<name>.json`. Sets the camera rules and look defaults. `null` for none. Scene values override the style's look settings but never its rules. |
| `background` | `{top, bottom, sun_glow}` | Sky gradient by elevation, with a sun glow. |
| `ground` | y 0, tile 4, two colours, fog | Checker plane with tile variation and thin grid lines (`line_color`, `line_width`, `line_strength`, `variation`). `fog_distance` fades it and objects into `fog_color`. |
| `light` | see `DEFAULT_META` in `scene.py` | `direction` (toward the sun), `ambient`, `sun_color`, `sun_strength`, `sky_color`, `ground_color`, `fill_strength`, `ao`. |
| `shadows` | on | Projected sun shadow on the ground: `strength`, `softness`, `range`, `contact` (disc under each character). |
| `look` | bevel 0.06 | `bevel` (edge chamfer, studs), `vignette`, `saturation`, `contrast`. |
| `audio` | none | Path relative to the scene file. Muxed in, cut at video length. Not trimmed to `--start/--end`. |
| `font_path` | system bold font | Path to a .ttf for captions. |
| `show_speaker` | false | Prefix captions with the speaker id. |
| `text_styles` | see below | Override `caption`, `hook`, `label` or add your own. |
| `export` | crf 18, preset medium | |

Text style keys: `size` (fraction of frame width), `color`, `stroke`, `stroke_width` (fraction of size), `y` (block centre, fraction of frame height), `max_width` (fraction of width), `bg` (optional `#rrggbbaa` box). The house style puts captions near 76% down and hook text near 15% down, clear of the usual platform UI areas. Check that against the platform you post to.

### characters

```json
"hero":  { "avatar": "main", "position": [0, 0, 0], "yaw": 0 },
"guest": { "avatar": "main", "variant": "guest", "position": [3, 0, 0], "yaw": -20 }
```

Under the house style every character needs `avatar`. `scale` must stay 1 and an inline `appearance` is refused, so the character cannot drift. `avatar_fingerprint` is optional: pin the value `validate` prints and the scene fails if the avatar file changes later. Without a style that requires avatars, a character can instead use `appearance` / `appearance_file` (inline values win). See "Avatars and rig".

### props

Boxes and cylinders: `{ "id", "type": "box" | "cylinder", "position": [x,y,z] (centre), "size": [w,h,d], "color", "rotation_y", "track", "bevel", "cast_shadow" }`. For a cylinder `size` is [diameter, height, diameter]. Set `cast_shadow` to false on big backdrops and floor slabs so they do not dominate the shadow map. To stand a box on the ground set `y` to half its height.

`track` moves a prop: `{ "shot": "shot_id", "keys": [ {"t": 0, "position": [x,y,z], "ease": "ease_in_out"}, ... ] }`. Times are seconds from the start of the named shot (or from the start of the video if `shot` is left out). Before the first key the prop sits at the first key's position; after the last key it stays at the last key's position. Positions are linear between keys with the easing of the earlier key. Props are solid, so a tall box hides what is behind or under it.

### shots

Shots play in order, back to back, unless `start` is given.

```json
{
  "id": "intro",
  "duration": 3.0,
  "fade_in": 0.3, "fade_out": 0.0,
  "shake": 0.0,
  "camera": [ ...keyframes... ],
  "actions": [ ... ],
  "dialogue": [ ... ],
  "overlays": [ ... ]
}
```

All times inside a shot are seconds from the start of that shot. Camera is per shot, so every shot start is a hard cut.

**Camera.** One fixed camera per shot, either a preset or an exact view:

```json
"camera": { "preset": "medium", "focus": [0, 0, 0], "yaw": 20 }
"camera": { "position": [0, 3, 9], "look_at": [0, 3, 0], "fov": 50 }
```

Presets (`wide`, `medium`, `close`, `high`, `low`) are defined in the style file as an offset from `focus`; `yaw` swings the camera around the focus point; `fov` overrides the preset. The field of view is vertical, so a 9:16 frame is narrow sideways: a character with arms out is 4 studs wide.

Camera motion (several keyframes with `t` and `ease`, `follow`, `target`) and `shake` exist, but the house style refuses them. To use them, copy `styles/house.json`, set `fixed_cameras` / `allow_shake`, and point `meta.style` at the copy. Do that only on purpose.

**Actions** (each has `t`, `character`, and exactly one of):

| Action | Example | Notes |
|---|---|---|
| `pose` | `{"pose": "wave", "duration": 1.6}` | Optional `hand`: `"left"`/`"right"`, `speed`. |
| `move_to` | `{"move_to": [3, 2.5], "speed": 3.5}` | `[x,z]` or `[x,y,z]`. Use `speed` (studs/s) or `duration`. Plays `walk` (or `pose`: `"run"`), then `then_pose` (default `idle`). Turns to face the direction unless `"face": false`. |
| `teleport` | `{"teleport": [0,0,0]}` | Instant move. |
| `face` | `{"face": 90}` or `{"face": {"toward": "id"}}` or `{"face": {"look_at": [x,z]}}` | Optional `turn` seconds. |
| `look` | `{"look": "camera"}` | Head follows `"camera"`, a character id, `[x,y,z]`, or `null`. Limited to about 75 degrees sideways and 35 up or down. |

Poses: `idle`, `walk`, `run`, `wave`, `cheer` (loop until changed); `point`, `think`, `sit`, `look_down` (hold until changed); `jump`, `surprised`, `shrug`, `nod`, `shake_head` (play once, then return to idle). `sit` needs the character's y set to the seat top minus 2 so the torso rests on the seat.

**Dialogue**: `{ "t", "duration", "speaker", "text", "style": "caption" }`. Burned in as text. There is no voice generation; supply your own audio file in `meta.audio`.

**Overlays**: `{ "t", "duration", "text", "style": "hook" }`. Same as dialogue but with no speaker.

`validate` warns when a line is above 3.5 words per second, when text runs past its shot, and when shots overlap or leave gaps.

## Avatars, parts and templates

**Rigs** (`rigs/*.json`): `minifig.json` holds the real assembly offsets taken from the library's own minifigure assembly file (arms at the shoulders with a 10 degree outward roll, hands at the wrist, head 24 LDU above the torso origin, legs 36 LDU below; 1 stud = about 17 LDU, standing height 5.35 studs). `brick.json` is the older generic figure. `parts/SCHEMA.md` is the full part format; `parts/AGENT_BRIEF.md` is the instruction sheet used to have other models generate parts.

**Avatar** (`avatars/main.json`): `rig: "minifig"`, a `palette`, the chosen `parts` (face, hair, headwear, torso, legs, accessories), `expressions` (name to face id) and `variants`. A variant may change only what `variants_may_change` lists (parts: face, hair, headwear, torso, legs, accessories; palette: primary, secondary, accent, pants, shoes, hair, metal). The skin colour and the rig stay locked. `main` is a painted figure (yellow skin, brown hair, blue shirt, navy trousers); to change it, edit the `palette` and `parts` in `avatars/main.json` (for example `avatars/gray.json` is the plain gray version). Because the avatar is locked, change `version` when you do.

Scene actions can switch faces over time: `{"t": 4.0, "character": "hero", "expression": "surprised"}`.

**Expressions.** `main` has 2 to 4 real printed faces for each of: `calm`, `happy`, `laugh`, `sad`, `angry`, `scared`, `surprised`, `smirk`, `cool`, `sleepy` (use `happy`, `happy_2`, `happy_3`; the bare name is the first), plus `talk_1` to `talk_4` (open mouths). Many LDraw heads are two-sided (a second print on the back of the head); `tools/ldraw_expressions.py 3626cp78 ...` makes `ld_<n>_back` parts that turn the head round to show it, which is where most of the sad, angry and scared faces come from. **Talking:** while a character is the `speaker` of a dialogue line and has no expression set, the mouth flaps between the resting face and the `talk_*` faces about 8 times a second. Set an expression on a speaker to stop the flap for that line.

**Parts library** (`parts/<folder>/<id>.json`): the LDraw set is the `ld_*` ids (about 2,150 parts: `ld_3626bp01` is the standard grin head, `ld_973p13` a zip-jacket torso, `ld_3901` short hair, `ld_11303` a cap, `ld_3815` plain hips and legs). Each file has a `title` and `source`; search them with `py -m blockreel parts list`. The older hand-made brick parts (faces `happy_*` etc., hair, torsos, sets for scenery) remain and the sets (trees, hills) are still used for scenery. Commands:

```
py -m blockreel parts list            # every part id
py -m blockreel parts check           # validate all parts, clear errors
py -m blockreel part-preview faces ld_3626bp05 --out face.png    # front, 3/4 and side view (previews use the avatar `main`)
py tools/ldraw_catalog.py             # regenerate the ld_* part files from ldraw/
py tools/ldraw_bundle.py ...          # copy more parts out of a full LDraw download into ldraw/
```

`blockreel/partkit.py` has helpers for drawing face and torso prints (`FaceCanvas`, `TorsoCanvas`). To add your own: drop a JSON (and PNG) into the right `parts/` folder, run `parts check`, then `part-preview`.

**Set pieces** are props with a template: `{"id": "t1", "template": "nature_01", "position": [x,0,z], "rotation_y": 30, "scale": 1.1, "palette": {...}}`. Box and cylinder props can have `"studs": true`.

`py -m blockreel avatar main` prints the resolved look and a fingerprint (hash of rig, palette and part file contents). `validate` prints it for every character.

Ground: `meta.ground.geo_studs: true` builds real raised studs on the ground lattice (pitch = `tile`, radius = `studs` x `tile`, height about 0.6 of the radius) wherever the camera can see them, up to 34 studs away; the flat painted circles still cover the far distance. A tile of 1.164 matches the real stud pitch for the figure (1 stud = 20 LDU = 1.164 units). Zones should use the same tile.

Look keys (`meta.look`): `gloss`, `bloom`, `dof`, `tint`, `vignette`; light keys `spec_strength`, `spec_power`; ground `studs`, `zones`; background `clouds`.

## Project layout

```
blockreel/
  README.md  AGENTS.md (handoff notes for a new agent)  requirements.txt
  rigs/      minifig.json (real assembly), brick.json, r6.json (archived)
  ldraw/     the bundled LDraw parts, primitives and colour table, with CC BY 4.0 licence files
  tools/     ldraw_bundle.py, ldraw_catalog.py
  avatars/   main.json (the one locked character, with variants), gray.json
  parts/     faces hair headwear torsos legs accessories sets, SCHEMA.md, AGENT_BRIEF.md
  old_notes/ archived Roblox-style figure and notes
  styles/    house.json         fixed cameras, no shake, presets, look defaults
  tests/     test_rules.py test_parts.py test_ldraw.py
  examples/  sample_scene.json 
             make_demo_scene.py  (writes demo_three_formats.json, the three-format demo)
  blockreel/
    cli.py        command line
    scene.py      scene loading, validation, camera rules and lookups
    rig.py        loads the rig file
    ldraw.py      LDraw .dat importer (sub-files, winding, colours, normals)
    avatar.py     loads avatar files, variants, fingerprint
    figure.py     brick figure built from rig and parts
    parts.py      part loading and validation
    partkit.py    face and torso print drawing helpers
    preview.py    part previews
    style.py      loads style files and their rules
    verify.py     checks the built figure against the rig
    character.py  per-character timeline and the posed geometry
    poses.py      pose clips and blending
    appearance.py appearance defaults and validation
    camera.py     look-at camera
    meshes.py     bevelled boxes, rounded head, cylinders
    raster.py     software rasterizer (z-buffer, Gouraud lighting, sky, ground, projected shadows)
    overlay.py    caption and hook text
    render.py     frame rendering, worker processes, ffmpeg export
    mathutil.py   matrices, easing, colour parsing
```

## Limits

- Shading is per-vertex with a plastic highlight, so highlights are soft. Shadows fall on the ground only: not on tables, stages, or other characters.
- Leg parts can only put extra pieces in the hips frame, so knee pads and cargo pockets do not follow the legs when they bend. Skirts were checked in standing poses only.
- Held items sit in front of the forearm and read best in raised-arm poses (wave, cheer).
- LDraw: held items and the Minifig Accessory category (826 parts) are not imported yet; hats and hair that need a different head shape may sit slightly off; parts with complex prints were only spot-checked (about 100 of 2,150 on contact sheets). Torsos with printed arms use plain palette arms. Print overlays use a small depth bias, so rare flicker on very thin prints is possible.
- OBJ meshes are supported minimally (up to 6000 triangles per piece). Big boxes with bevels can show small jagged artifacts at corners.
- Props can move along position keyframes. They cannot rotate or change colour over time.
- Pose motion is simple procedural motion, not hand-keyed animation. Limbs are rigid.
- Camera cuts only. No cross-fades between shots (fade to black per shot is supported).
- Software rendering is slow (roughly one frame per second per core at 1080x1920 with supersample 2). Use `--preview` while working.
- Only run on Linux. Not tested on Windows. Audio muxing was not exercised.
