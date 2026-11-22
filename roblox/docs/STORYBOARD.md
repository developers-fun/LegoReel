# Storyboard (`r6reel.storyboard`)
A cheap check before a render: key frames of a scene with movement arrows, footprints, gesture arrows, a camera glyph, a top-down minimap and a text description under each frame. Red `!` lines are automatic checks.

```
python -m r6reel storyboard scene.json --out out/storyboard.png          # or a Director script .txt
  --max 12  --cols 4  --tile-h 480  --times 0.5,2.0,3.4  --no-minimap  --captions  --seed N  --pace normal
```
Also writes `storyboard.md` (panel text) and `storyboard.json`. Sheets taller than 4000 px split into `storyboard_1.png`, `_2.png`...

```python
from r6reel.storyboard import Storyboard
sb = Storyboard(scene, max_panels=12, cols=4, tile_h=480)
sb.panels(); sb.sheet(); sb.save("out/storyboard.png"); sb.markdown()
```

## Key frame choice
Every shot start (> 0.6 s long) gets a panel. Spare slots go to the highest scoring events: clip starts and peaks (gait and idle skipped), move start/mid/arrival, face changes, turns of 45+ degrees, caption starts, prop keys. 0.4 s minimum spacing.

## Reading a frame
- Blue/orange/etc. arrow = a move_to path with distance and gait; one colour per character; name tag above the head, chevron at the feet = facing.
- Shoe prints = walking/jogging/running. Step length = ref_speed x cycle / 2. Faded prints are already behind the frame time.
- Dashed curve = hand/head/body gesture over the next 0.6 s.
- Bottom-right glyph = camera move (push in, pull out, whip, orbit, crane, shake, dutch, follow, locked). Bottom-left = top-down map with the camera cone.

## Checks (heuristics, not proof)
off-screen or tiny shot subject, travelling backward (>100 deg off facing), foot slide (gait speed outside 0.6x-1.7x), overlap (< 1.6 studs), camera inside subject, camera clamped by a wall, floating or sunk character. Off-screen and tiny only fire for the shot subject and `other`.

## Not verified
Only backward walk and off-screen are tested on bad scenes. Sheet splitting and `.txt` input are untested. Footprint timing is approximate, not the real foot plants. The demo flags Milo's sprint_panic as sliding (the gait speed clamp is 0.6x): a real finding.
