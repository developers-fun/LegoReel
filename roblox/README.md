# r6reel

Roblox R6 storytime-style vertical videos from Python or JSON. Chunky blocky worlds, R6 avatars with changing
face decals, snappy clips, dutch/low-angle/push-in cameras, whip / dust / zoom-punch cut hiders, word-by-word
captions. An auto-**Director** turns a script into a fully directed scene in the reference style.

## Install
    pip install -e .            # numpy, pillow, moderngl; ffmpeg must be on PATH
Headless GL (EGL/llvmpipe) works; Mac/Windows use the default GL 3.3 backend.

## Quickstart
CLI:

    python -m r6reel demo                                  # 17 s story -> out/demo.mp4 (preview quality)
    python -m r6reel direct examples/script.txt out/s.mp4 --seed 3 --pace fast --preview
    python -m r6reel render examples/story_demo.json out/x.mp4 --size 720x1280
    python -m r6reel validate scene.json ; python -m r6reel contact scene.json --out out/c.png
    python -m r6reel list clips|faces|presets|builders|emotions ; python -m r6reel faces search "#happy #laughing"

Python:

    from r6reel.director import Director, Beat
    scene = Director([Beat("Then Milo dropped his tray.", character="Milo", location="cafeteria",
                           emotion="shocked", action="drop")], seed=7, size=(720, 1280)).build()
    scene.render("out/a.mp4")                  # final quality;  preview=True for 360x640 fast

## 5-minute tutorial
**By hand** (everything is plain data, see docs/SCENE_SCHEMA.md):

    from r6reel.scene import Scene
    s = Scene(720, 1280, world="street")                       # location preset
    s.add_character("Milo", position=(0, 0.1, 7.5), hair="spiky:#5a3a22", shirt_color="#c4281c")
    s.add_character("Ava", position=(4, 0.1, 7.5), facing=90, hair="pigtails:#e7a1c0")
    s.play("Milo", "wave", at=0.4); s.face("Milo", "shock", 1.0)
    s.move_to("Ava", (-8, 0.1, 7.5), 0.5, 2.5)
    s.add_shot(0, 1.2, "wide", subject="Milo", moves=[{"type": "push_in", "rate": 0.07}])
    s.add_shot(1.2, 2.4, "extreme_closeup", subject="Milo", elevation=-8,
               moves=[{"type": "dutch", "degrees": 5}], transition={"type": "zoom_punch"})
    s.add_shot(2.4, 3.6, "medium", subject="Ava", follow=True, transition={"type": "whip"})
    s.add_caption("He waved at nobody in particular", 0.1, 3.5)
    print(s.validate()); s.contact_sheet().save("out/c.png"); s.render("out/s.mp4", preview=True)

**Via Director**: give beats (or a script string). Script syntax: `@location` lines, `Name (emotion, action, to=Other,
prop=tray, dur=2.5): text`, or bare narration (emotion/action/character inferred). Knobs: `seed`, `pace`
(fast/normal/slow), `style` (storytime/yellow_pop/two_line or variant A-D), `shot_mix`, `avg_shot_len`, `lighting`,
`transitions`, `face_variety`. Per-beat overrides: `shot=["wide","closeup"]`, `transition=`, `camera={"azimuth":..}`,
`face=`, `lighting=`. Afterwards edit `scene.shots/actions/...` freely and `scene.to_json(path)`.

## Render time
~0.066 s/frame preview (360x640) and ~0.21 s/frame at 720x1280 final on CPU llvmpipe (1080x1920 ~0.36 s);
much faster on a real GPU. Whip frames render 3-4 sub-frames (motion blur "auto"; `motion_blur=False` disables).

## Real Roblox clothing and faces
`Scene.add_character(..., shirt="path/shirt.png", pants="path/pants.png")` takes the 585x559 Roblox templates.
Faces: any PNG path or a `faces.get(name)` id works as a face name (`s.face("Milo", "/path/f.png", t)`); the faces
library (assets/faces + r6reel/faces.py, tags like `#happy`) is used by the Director automatically when present and
falls back to built-in procedural faces. New avatars: add dicts to `presets.OUTFITS` or pass `characters={...}`.

## Layout
docs/SPEC.md contract, docs/STYLE.md reference style, docs/STYLE_USAGE.md style -> API map, AGENTS.md handoff.
