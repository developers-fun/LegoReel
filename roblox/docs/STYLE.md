# Reference style (draft v1, from 6 Roblox storytime reels, 576x1024 / 720x1280 @30fps, 100-163 s each)

Measured with ffmpeg scene detect (threshold 0.25): average shot length per video 1.87 / 1.33 / 2.16 / 1.76 / 1.22 / 1.44 s,
median 1.1-1.8 s, 11-42% of shots under 1 s, longest holds 3-9 s (rare). Target default: 1.4 s average, 1.0-2.2 s typical.

## Look
- Roblox engine look: bright saturated plastic colors, hard-ish sun shadows (long, 30-50 deg elevation), blue sky gradient, bloom on highlights, slight vignette. Some videos go night (dark blue, warm lamp glow, stars) or indoor (warm light, soft shadows).
- Worlds are built from chunky blocks: suburban houses, brick buildings, sidewalks, grass, trees (round blob + trunk), low-poly mountains, clouds, interiors (school hallway with lockers, cafeteria benches, classroom desks, bedrooms).
- Characters: classic R6 blocky avatars with varied clothing (shirt/pants textures: jackets, stripes, polka dots, hoodies), hair (bun, spiky, bacon, long, afro, caps), 2D face decals that change per beat (smile, shock O-mouth, angry, sad, laugh).
- Props with gameplay-feel: speed-limit sign, leaderboard board with coins, rubber duck, lemonade jug, mice, papers flying, dust puffs, big text/number signs.

## Camera (the most important part of the feel)
- Almost never static: slow push-in (3-10 % per second), small drift, occasional slow orbit around a character. Wide establishing shots start far and creep in.
- Heights: LOW angle (camera near ground looking up) for hero/menace and for close-ups of faces and feet; eye level for dialogue; high angle for crowds/school scenes.
- Lens: wide (fov 60-80 vertical) so close-ups have strong perspective distortion (nose/arms big). Extreme close-ups let a face or a torso fill the whole 9:16 frame; arms swinging past the lens are common.
- Over-the-shoulder / two-shot for dialogue: two characters side by side, heads in upper third, ground visible.
- Frame subjects in the middle third horizontally; captions sit around 55-65 % down the frame (v4/v6) or center, so heads go above or below.
- Shots with action follow the character (camera trails behind/at the side while running; ahead-facing chase shots).

## Cuts and transitions
- Overwhelmingly HARD CUTS on caption/word boundaries; ~1 cut every 1.2-2.2 s; cuts often alternate wide -> close -> medium -> close (size changes every cut).
- Cuts hidden in motion: a character/arm/object sweeps through the lens, a dust puff covers frame, a whip pan (motion-blurred horizontal smear for 2-4 frames), vertical whip tilt up a building.
- Quick whip/blur frames (3-5 frames) between locations; occasional zoom-punch (scale 1.0 -> 1.15 in 4 frames) on a reveal or joke beat.
- No fades except end; flash frame (1-2 frames white) for explosions/shock.
- Same scene re-shot from a new angle on consecutive cuts (continuity: character in the same pose, camera jumps 30-90 deg or changes size).

## Character motion
- Poses are held with sudden snaps: anticipation 2-4 frames, fast move, small overshoot, then hold (looks like ~12 fps keyframing mixed with smooth interpolation).
- Run: arms pump wide, torso leans forward 10-20 deg, dust puffs at feet; sprint-panic: arms flung back.
- Idle: small breathing sway, head turns toward whoever speaks, arms slightly out; lots of "arms spread" and "hands on hips" acting.
- Reactions: shock = whole body jerks back + arms up + O-mouth face + camera punches in; anger = lean in, fists, brow face; sad = head down, shoulders slump; laugh = body shakes, head tilted back, mouth wide.
- Props animate too (papers flutter, doors slam, signs spin, coins rain, crowds run in the background).
- Crowds: 4-15 identical-ish extra avatars (varied hair/shirt color), in simple stand/walk/cheer loops.

## Captions (burned in)
- Word-by-word (1-3 words visible at a time, 2.5-4 words/second), bold rounded sans (Baloo/Fredoka-like or Montserrat Black), white fill + thick black outline + soft shadow; some videos use yellow for the current word.
- Position: upper-middle (y about 35 %) in some videos, lower-middle (y about 62 %) in others; never covers the face when possible.
- Pop-in scale (0.8 -> 1.05 -> 1.0) over 3-4 frames on each word.
- TikTok handle watermark at lower-right (do NOT reproduce).

## Environments seen
Giant underground city cutaway, airport/airplane interior, billionaire bunker, leaderboard town square at night, suburban street with sidewalk, brick tower/castle, school hallway/cafeteria/classroom, lemonade-stand street, snowy blizzard park, bedroom, fence/yard.

(See STYLE_FINAL.md once analysis is complete.)

---
# Addendum v2 (after dense frame passes on v3/v4/v5/v6, 5-10 fps)

## Shot-size rhythm (what the editors do)
- Pattern per beat of narration: ESTABLISH (wide, character small, long lens, 1.5-2.5 s) -> REACT (extreme close-up of head/torso, 1.0-2.5 s, slow push-in 5-8 %/s + 3-6 deg dutch roll) -> ACTION (medium, camera low, follows) -> INSERT (prop or hand/belly close-up, 0.5-1.2 s) -> repeat.
- ~35-45 % of all shots in the character-driven reels (v3, v5, v6) are head close-ups where the head+neck fill the frame width: fov about 75-85, camera 2-3 studs from the face, slightly below eye line, face decal clearly readable. Captions overlay the forehead/hair area or sit below the chin.
- Insert shots of one object (clock, timer device, sign, coin, mouse, pencil): fill the frame, 0.5-1.5 s.
- Wide environment reveals (city, castle, street) are slow: camera pushes/cranes/pans 5-15 deg over 2-3 s with no cut.

## Cut hiding that appears repeatedly
1. Object/limb sweeps through the lens (arm, torso, car) on the last 3-5 frames of shot A; shot B begins with the same sweep exiting.
2. Dust/smoke puff expands to fill frame at the cut (v5 12.3-12.8 s): 5-8 frame cartoon puff, grey-white, fades out in shot B.
3. Whip pan: horizontal smear 2-4 frames.
4. Match-on-action: runner exits left, next shot runner enters from the left.
5. Cut on caption word change; never mid-word.

## Face acting
- Faces swap constantly (every 0.5-2 s) and also animate within a shot: eyes shift to look direction, quick blink, O-mouth for talk/shock. A face library with many expressions is core (hence assets/faces). Mouth flap while the narrator speaks is NOT used in storytime (narration is voice-over), faces change on emotional beats instead.
- Eyebrows/brow faces for anger, spiral/dizzy, big white eyes for fear/shock (googly circles), blue frozen eyes, tears.

## Lighting/time-of-day presets (needed)
day (blue sky, hard sun shadows), sunset (orange sky gradient, long warm light, strong rim), night (deep blue ambient, lamp glow, stars optional), snow/blizzard (white-blue fog, low contrast, snow particles), indoor_warm (warm ambient 3000K, soft), school_day (bright, cool fluorescent ambient), cinematic_dark.

## Particles / FX seen
dust puffs at feet and at cuts, snow, falling leaves/debris, coin shower, thrown papers, speed lines are NOT used, motion blur only on whips and fast limbs, lens bloom, vignette, slight chromatic aberration on shock beats.

## Captions - 4 variants in the sample set
- A: yellow/white bold rounded, one word at a time, center (v1).
- B: small white one word with thick outline at center-lower (v2, v3).
- C: white bold 1-3 words, lower-middle (v4, v5).
- D: 2-line sentence blocks, white, thin black outline, upper-middle (v6).
All use rounded geometric sans; all burn in at about 3-4 words/s.

## Characters seen (for avatar variety defaults)
Brown spiky hair + black leather jacket + blue guitar tee; pink hoodie girl with pigtails and rollerblades; striped orange shirt kid; blue star-print bomber jacket + jeans; red varsity jacket; polka-dot pajamas; elderly lady with gray bun and purple floral dress; blue police-style uniform; green tee + khaki shorts; yellow-black striped shirt; black long hair girl in white. Everything is an R6 body (blocky limbs) with a standard head and decal face.
