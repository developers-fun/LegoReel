# Scene JSON schema (version 1)
Times in seconds, angles in degrees, y up, character faces -Z at facing 0. Example: examples/story_demo.json.

```
{ "version":1, "name":"", "width":1080, "height":1920, "fps":30, "seed":0, "duration":null, "audio":null,
  "sets": { "<name>": {"location":"cafeteria"|null, "builders":[{"builder":"house","args":{},"position":[x,y,z],
            "rotation":[..],"scale":1}], "lighting":"day"|{...}, "ground_y":0, "cam_side":-1|1,
            "bounds":[xmin,xmax,zmin,zmax] (camera eye clamp), "fx":[fx specs]} },
  "characters":[{"name":"Milo","avatar":{"skin","shirt","pants","shirt_color","pants_color","face","hair":"spiky:#hex",
                 "hair_color","accessories":["glasses","cap:#hex"],"body_colors","scale"},
                 "position":[x,y,z],"facing":0,"sets":null|[..],"visible":null|[[t0,t1],..]}],
  "actions":[ {"character","type":"play","t","clip","speed","fade_in","fade_out","weight","mask","loop","until","face"},
              {"type":"move_to","t0","t1","pos","ease","face","gait"}, {"type":"look_at","t0","t1","target"},
              {"type":"face","t","name"}, {"type":"turn","t","deg","dur"}, {"type":"place","t","pos","facing"} ],
  "props":[{"name","builder","args","position","rotation","scale","set","visible":[t0,t1],
            "keys":[{"t","position"|"attach","rotation","scale","ease"}],
            "attach":{"to":"Milo","part":"Right Arm","offset":[x,y,z],"rotation":[..],"until":t}}],
  "shots":[{"t0","t1","kind":"wide|medium|closeup|extreme_closeup|low_angle_hero|high_angle|top_down|chase_behind|
            side_tracking|two_shot|over_shoulder|pov|insert","set","subject":"Milo"|"prop:name"|[x,y,z]","other",
            "follow":false,"damping":0.3,"azimuth","elevation","fill","fov","screen_y","facing","distance",
            "focus":"head|torso|feet|hands|full","moves":[{"type":"push_in|pull_out|drift|dutch|orbit|shake|crane|
            low_angle|whip_pan|dolly_zoom|look_at|follow","at":0,"dur":null,...}],
            "camera":{"position","target","fov","roll"} (manual), "lighting":name|dict,"post":{PostFx fields},
            "transition":{"type":"cut|whip|dust_cover|zoom_punch|flash|fade_in|fade_out|shake_hit|sweep",...}|[..],
            "motion_blur":null,"label"}],
  "captions":[{"text","t0","t1"} | {"words":[[w,t0,t1],..]}, plus "style","y","font_scale"],
  "fx":[{"type":"dust|footsteps|dust_cover|snow|leaves|coins|papers|sparkles|sweep", ...,"set"}],
  "post":{PostFx fields applied to every frame} }
```
Shots must tile the timeline (`validate()` reports gaps/overlaps). A shot's `transition` is the cut INTO it, centred on
`t0`. Camera moves are relative to the shot start (`at`) and default to the whole shot.
