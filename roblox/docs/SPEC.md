# r6reel SPEC (the contract every module follows)

Goal: a Python library + CLI that renders Roblox-storytime-style vertical videos (R6 avatars only)
from a JSON scene or from Python. Reference style: see docs/STYLE.md.

## Conventions
- Y-up, right-handed, units = studs (1 stud = 0.28 m in Roblox; we just use studs). Roblox forward is -Z (a character's face points to -Z at rotation 0).
- Angles in degrees at API level (public dicts), radians internally.
- Matrices are 4x4 float64 numpy, column-vector convention (`p' = M @ p`).
- Colors: floats 0..1 RGB tuples, or `"#rrggbb"` strings accepted via `r6reel.util.color(c)` (module `util.py`, owned by the renderer agent).
- Default video: 1080x1920, 30 fps, vertical 9:16. Everything must also work at e.g. 360x640 for fast previews.
- Python 3.10+, numpy, Pillow, moderngl (GL 3.3 core ONLY, so it runs on llvmpipe, Mac and Windows), ffmpeg on PATH.
- Headless: `moderngl.create_standalone_context(backend="egl")` works here; fall back to the default backend on Mac/Windows.
- No module may import a sibling module that another agent owns, EXCEPT `r6reel.mesh.Mesh` (already written) and the interfaces below. Use lazy imports inside functions when you need a sibling.

## Module ownership and public API

### mesh.py (done) — `Mesh(positions, normals, uvs, indices)`, `.transformed(m4)`, `Mesh.merge(list)`

### primitives.py + world.py (agent: world) — scenery
```python
# primitives.py: all return Mesh, centered at origin unless noted, UVs 0..1 per face
box(size=(1,1,1), bevel=0.0) -> Mesh
wedge(size=(1,1,1)) -> Mesh                 # Roblox WedgePart: slope rises toward -Z? (document it)
cylinder(radius=0.5, height=1, segments=24, axis="y") -> Mesh
sphere(radius=0.5, segments=24) -> Mesh
cone(radius=0.5, height=1, segments=24) -> Mesh
plane(size=(1,1), uv_tile=(1,1)) -> Mesh    # XZ plane facing +Y
rounded_box(size, radius, segments=3) -> Mesh

# world.py
@dataclass
class Part:  # one drawable
    mesh: Mesh; color: tuple; position=(0,0,0); rotation=(0,0,0) # euler deg XYZ
    scale=(1,1,1); texture: str|None=None   # path to image, tiled by uv
    material: str="plastic"   # plastic|smooth|grass|brick|wood|concrete|glass|neon|metal
    transparency: float=0.0; cast_shadow=True; name=""
class Prop:      # named group of Parts with a transform; has .parts, .position, .rotation, .scale, .name
    def to_draw_items(self) -> list[DrawItem]   # see renderer DrawItem
class World:
    def __init__(self, sky_top="#5aa9ff", sky_bottom="#cfe9ff", sun_dir=(-0.4,-1,-0.3), ...)
    def add(self, prop_or_part) -> prop; def get(self, name) -> Prop
    def draw_items(self) -> list[DrawItem]
    sun / ambient / fog settings live here and are passed to the renderer as `Lighting`.
# builders (functions returning Prop): ground(size, material="grass"), road(length,width), sidewalk(...),
# house(w,d,h,color,roof_color), apartment_block(floors,w,d), skyscraper(...), tree(kind="round"|"pine"),
# bush, fence(length), lamp_post, bench, table, chair, desk, locker_row, door, window_wall, sign(text_texture_optional),
# car(color) (blocky), umbrella, cloud, brick_wall(w,h), stairs, crate, ball, duck_toy, coin.
# Style: bright saturated Roblox plastic look, chunky blocky shapes, SmoothPlastic/brick/grass/concrete colors.
```

### renderer.py + util.py + post.py + video.py (agent: renderer) — moderngl backend
```python
@dataclass
class DrawItem:
    mesh: Mesh; model: np.ndarray(4,4); color: tuple=(1,1,1)
    texture: PIL.Image|np.ndarray|str|None=None   # tiled/UV-mapped albedo; if present multiplies color
    material: str="plastic"; transparency: float=0.0
    cast_shadow: bool=True; receive_shadow: bool=True
    uv_scale: tuple=(1,1); emissive: float=0.0; key: str|None=None  # key = stable id so GPU buffers/textures are cached
@dataclass
class CameraState: eye, target, up=(0,1,0), fov_y=70.0 (degrees, vertical), roll=0.0, near=0.1, far=2000.0
@dataclass
class Lighting: sun_dir=(-0.4,-1,-0.3) (direction light TRAVELS), sun_color=(1,0.96,0.88), sun_intensity=1.0,
    ambient=(0.55,0.6,0.7), sky_top, sky_bottom, fog_color=None, fog_density=0.0, shadow_extent=60.0 (ortho half-size around camera target), shadow_res=2048
@dataclass
class PostFx: bloom=0.15, vignette=0.15, saturation=1.1, contrast=1.05, exposure=1.0, grain=0.0, chroma=0.0, blur_dir=(0,0)/blur_amount (directional, for whip pans), flash=0.0 (white), fade=0.0 (to black)
class Renderer:
    def __init__(self, width=1080, height=1920, samples=4, headless=True)
    def render(self, items: list[DrawItem], camera: CameraState, lighting: Lighting, post: PostFx|None=None) -> np.ndarray  # (H,W,3) uint8
    def render_motion_blur(self, frame_fn, t, shutter=0.5, subsamples=4) -> np.ndarray   # frame_fn(t)->(items,camera,lighting,post); accumulates
    def close()
# video.py
class VideoWriter(path, width, height, fps=30, crf=18)  # pipes raw rgb to ffmpeg libx264 yuv420p, +write(frame), +close()
```
Look: Roblox "Future lighting" feel: soft sun shadow with PCF, hemispheric ambient, slight bloom, saturated colors, subtle SSAO-like darkening optional.
Bright sky gradient, optional low-poly clouds are world props. Characters read clearly at 9:16.

### rig.py + avatar.py + anim.py + clips.py (agent: rig) — R6 character
```python
# rig.py: R6 geometry and forward kinematics
PARTS = ["Head","Torso","Left Arm","Right Arm","Left Leg","Right Leg"]
# Sizes: Head 2x1x1 (rendered with Roblox head mesh shape: rounded, ~1.25 scale, flat front for face decal), Torso 2x2x1, arms 1x2x1, legs 1x2x1.
# Motor6D joints (C0 on parent, C1 on child), standard R6:
#  RootJoint  : HumanoidRootPart <-> Torso (identity, with RootJoint rot -90 X on rigs; we simplify: root == Torso center)
#  Neck: C0=(0,1,0) C1=(0,-0.5,0);  Right Shoulder: C0=(1,0.5,0) C1=(-0.5,0.5,0);  Left Shoulder: C0=(-1,0.5,0) C1=(0.5,0.5,0)
#  Right Hip: C0=(1,-1,0) C1=(0.5,1,0);  Left Hip: C0=(-1,-1,0) C1=(-0.5,1,0)
# HipHeight: standing, feet on y=0 => Torso center y=3.0 (legs 2 + half torso 1).
# A Pose is a dict: {"root": {"pos":(x,y,z) or None, "rot":(rx,ry,rz) deg}, "Neck":(rx,ry,rz), "Right Shoulder":(..), "Left Shoulder":(..), "Right Hip":(..), "Left Hip":(..)}
# missing keys = zero rotation. Rotation order for joints: Z*Y*X euler like CFrame.Angles(rx,ry,rz) (Roblox = X then Y then Z intrinsic: R = Rx*Ry*Rz).
def part_models(pose: dict, root_cf: np.ndarray) -> dict[str, np.ndarray]   # part name -> world 4x4 at part center
def part_mesh(name: str) -> Mesh                                            # cached, local space centered on the part

# avatar.py
class Avatar:
    def __init__(self, name="Noob", skin="#f5cd30"|color, shirt=None, pants=None, face="smile"|path|None,
                 hair=None, accessories=(), body_colors=None, scale=1.0, shirt_color=None, pants_color=None)
    # shirt/pants: PIL/path texture (Roblox 585x559 template layout) OR a flat color; if None -> body colors only.
    # hair/accessories: names from a built-in blocky set: "bun","bacon","ponytail","spiky","buzz","long","afro","cap","beanie","tophat","crown","glasses","headphones"... (each returns Mesh + color)
    def set_face(self, face_name_or_path)    # face resolves through r6reel.faces.get(name) when it's not a file
    def draw_items(self, pose: dict, root_cf: np.ndarray) -> list[DrawItem]
    ROBLOX-STANDARD: shirt template UVs (torso front/back/sides, arm sleeves) and pants template (legs) must be implemented so real Roblox clothing PNGs map correctly. Face = decal on Head front (-Z face).
# anim.py
class Clip: name, duration, loop(bool), keyframes=[(t, pose_dict, easing)], .sample(t)->pose_dict
easing names: linear, constant, cubic_in, cubic_out, cubic_inout, elastic_out, bounce_out, back_out (Roblox EasingStyle-like)
blend(pose_a, pose_b, w) ; layer(base, overlay, mask=None) ; add_noise(pose, t, amount, seed)  # idle breathing / handheld life
class Animator:     # per-character timeline
    def __init__(self, avatar, position=(0,0,0), facing_deg=0.0)
    def play(self, clip, at=0.0, speed=1.0, fade_in=0.1, fade_out=0.1, weight=1.0, mask=None, loop=None)
    def move_to(self, pos, t0, t1, ease="cubic_inout", face=True)   # root translation, auto-faces direction of travel with turn smoothing
    def look_at(self, target_or_name, t0, t1)   # neck turn toward point
    def face(self, name, t)                     # swap face decal at time t (expression change)
    def pose_at(self, t) -> (pose_dict, root_cf)
    def draw_items(self, t) -> list[DrawItem]
# clips.py: library via `clips.get("name")`, all return Clip. Required set (each readable at 9:16 close-up):
# idle, idle_bored, breathe, walk, run, sprint_panic, jog, jump, fall, land, sit, sit_slouch, sit_desk (writing), stand_up, wave, point, point_up,
# cheer (arms up), shrug, facepalm, laugh (hunched shaking), cry, shock (jolt back, arms up), scared (cower), angry (stomp/arms down fists),
# talk (small arm gestures), nod, shake_head, lean_in, cross_arms, hands_on_hips, tie_shoes (kneel+arms), faint (fall on back), ragdoll_fall, sleep_hug (lying), push, throw, catch, hug, dance_1..3, kick, swim, climb, salute, bow, flex.
# Style: SNAPPY. Roblox-animation feel: fast anticipation, quick overshoot (elastic/back easing), held poses (stepped-ish), exaggerated arms.
```

### faces.py + assets/faces (agent: faces)
```python
faces.search(tags: str|list, any_=False, limit=20) -> list[Face]   # "#happy #laughing" or ["happy","laughing"] (AND by default)
faces.get(name_or_id) -> path to a transparent PNG/RGBA decal ready for the head front (square)
faces.tags() -> sorted list of all tags with counts;  faces.random(tags, seed)
assets/faces/index.json: [{"id":..,"name":..,"file":"png/xxx.png","tags":["happy","smile"],"asset_id":..,"source":"roblox catalog"}]
```

### camera.py (agent: camera)
```python
class Camera:    # keyframed, time-based; deterministic
    def __init__(self, position=(0,5,-10), target=(0,3,0), fov=70, roll=0)
    def state(self, t) -> CameraState
    # tracks: position, target (point or follow(name) via resolver), fov, roll — each keyframed w/ easing
    # move builders (all take duration + start t, all return self for chaining):
    push_in(t0,t1,amount), pull_out, orbit(t0,t1,degrees,around=None), whip_pan(t0,t1,degrees), drift(t0,t1,amount) (slow handheld-ish float),
    follow(target_name, offset, damping), look_at(name or point), dolly_zoom, tilt/dutch(roll), shake(t0,t1,amp,freq), crane(t0,t1,dy), low_angle(...), snap_to(t, pos, target, fov)
presets: camera.shot("wide"|"medium"|"closeup"|"extreme_closeup"|"low_angle_hero"|"over_shoulder"|"high_angle"|"two_shot"|"pov"|"top_down", subject_pos, subject_height=5, facing_deg=0, ...) -> Camera
```

### captions.py (agent: captions)
```python
class CaptionTrack: words=[(text,t0,t1)], style
Captions.from_text("long text...", t0, t1 | wpm) ; .from_words([...])
render_caption(t, width, height, style="storytime"|"yellow_pop"|"two_line", y=0.62) -> RGBA np.ndarray (H,W,4) or None   # word-by-word pop (current word highlighted), bold rounded font, thick black outline, drop shadow
```

### scene.py + timeline.py + cli (agent: integrator, runs AFTER the others)
Scene JSON <-> Python. Shots = [t0,t1] with camera + which characters are visible; transitions: cut, whip, flash, zoom_punch, dust_cover, fade; characters with action tracks; captions; audio ignored (video only, optional audio file muxed).
`python -m r6reel render scene.json out.mp4 [--preview] [--start T --end T] ; validate ; faces search ; list-clips ; demo`

## Testing contract
Each agent writes `tests/test_<module>.py` (pytest, fast, no GL requirement except renderer tests which skip if GL missing) and a runnable `examples/<module>_demo.py` that writes a PNG into `out/` (gitignored). Do not edit files you do not own; if you need a change elsewhere, say so in your final report.
