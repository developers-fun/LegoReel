# Reference style -> API

| Trait (STYLE.md) | Where / how |
|---|---|
| ~1.4 s average shot, 1.0-2.2 typical, size changes every cut | `Director(avg_shot_len=, pace=)`, `presets.SHOT_LENGTHS`, `_plan_shots` size filter; `Scene.validate()` warns on long/short |
| Establish wide -> reaction extreme close-up -> action medium -> insert | `presets.RHYTHM`, Director roles (establish/react/action/insert); weights `shot_mix` |
| Slow push-in 5-8 %/s | shot move `{"type":"push_in","rate":0.06}` |
| Dutch roll 3-6 deg on reactions | `{"type":"dutch","degrees":5}` (sign alternates per shot) |
| Low angle, wide lens close-ups | `Shot.elevation=-8`, `fov=82`, kinds `closeup`/`extreme_closeup`/`low_angle_hero` |
| Hard cuts on caption word boundaries | Director snaps inner cuts to word starts (`_lengths`) |
| Whip pan blur 2-4 frames | `transition={"type":"whip","direction":"right","dur":0.17}` (+ auto motion blur) |
| Dust puff covering the cut | `transition={"type":"dust_cover"}` (fx.DustCover) |
| Object sweeps through lens | `transition={"type":"sweep"}` |
| Zoom punch / flash on shock | `[{"type":"zoom_punch"},{"type":"flash"}]`; Director does it for shocked/scared |
| Faces swap every 0.5-2 s | `Scene.face()`; Director swaps on the reaction cut and mid-shot (`face_variety`) |
| Run: dust at feet, leaning arms | `fx footsteps`; clips `run`/`sprint_panic` via `move_to` gait |
| Time of day presets | `presets.LIGHTING` (day, sunset, night, snow, indoor_warm, school_day, cinematic_dark); `Shot.lighting` |
| Particles (snow, leaves, coins, papers, sparkles) | `scene.add_fx("coins", t=.., pos=[..])`, `fx.FX_TYPES` |
| Captions 3-4 words/s, 4 variants | `Director(style="A".."D")`, `Scene.add_caption(style=, y=)` |
| Props that animate | `Scene.add_prop(..., keys=[{t, position, rotation, ease}], attach={...})` |
