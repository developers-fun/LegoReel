# stick: 2D stick-figure animation (side project of LegoReel)

Date: 2026-11-21. Goal from the owner: stop using the 3D Lego renderer, learn a 2D stick-figure rendering method by
recreating reference stick-figure videos 1:1. First reference: the "dig skit" by @cubemonsters (two stick figures,
YOU and FRIEND, dig tunnels toward a gold wall, a token, a zoomed gold finale). The reference video and its frames are
NOT in this repo (someone else's work). Do not post a recreation as is: it copies their format and share-bait text.

## What exists (all pure Python, Pillow + numpy + OpenCV + scipy)
- `stickreel/engine.py`: camera (zoom/pan), drawing helpers (poly, ellipse, glow, star, vertical gradient, text with
  tracking/outline/gradient). Authoring space is 576x1024; canvas is 2x, final downscale to 576x1024.
- `stickreel/figure.py`: the template figure. Points (head, neck, hip, 2 hands, 2 feet), two-bone IK for arms and
  legs with cartoon stretch and a bend side (+1/-1), capsule limbs with outline and edge shading, pickaxe prop.
- `stickreel/chop.py`: **the hand-keyed chop cycle**. Both hands on ONE grip point, the pick is a rigid stick that
  swings around the grip. 11 keys (wind-up, snap, contact, hold, pull, recoil, raise, high, overhead, back), period
  22 frames, periodic PCHIP interpolation. This is the method that finally looked right.
- `stickreel/dig_bg.py`: sky, sun rays, dirt, tunnels (jagged edge), gold wall, sign, token, labels, hook text.
- `stickreel/rotofit.py`: rotoscope fitter (silhouette IoU + chamfer, coordinate descent). Kept for reference.
- `scene_dig.py`: renders frames 1-152 (first ~5 s) with motion blur (`BLUR=4` env var = 4 sub-frames).
  Needs the reference frames in `A_all/fNNN.png` (not included) for tunnel growth and the strike-flash brightness.
  Contact frames (strike timing) are hard-coded: YOU 9, 30, 54, 84, 106, 127; FRIEND 13 + 18k.
- `tools/`: the rotoscope pipeline and helpers. Run from a folder that has `A_all/` (frames extracted with ffmpeg).
- `data/`: tunnel growth measurements, last fit (used for hip x drift only), last pick angles (no longer used).

## What I did (in order) and what happened
1. Built the engine, background and figure rig. First frame matched closely.
2. Tried to rotoscope the whole video: per-frame optimisation of 12 rig parameters against the white silhouette.
   - IoU-only loss drifted; chamfer + IoU with restarts worked on early frames.
   - Coordinate descent could not move the arms far; added polar enumeration of hand/foot targets (`refit.py`).
   - The optimiser CHEATED: it folded arms to zero length at the shoulder, because that looked fine in a skeleton
     overlay. Only rendering the real figure exposed it. Fixed with a minimum reach penalty in `Fitter.loss`.
   - The TikTok watermark is a don't-care box that hides the friend's torso and legs, so his fit was junk.
     Frozen planted feet and an upright torso as a workaround (`refit_friend.py`).
   - Pick angle: template scoring + Viterbi flattened the swing; metal-blob centroid near the grip (`pickfit3.py`)
     was better but still unreliable after the first cycle.
   - Result: silhouette IoU about 0.36-0.40. Not 1:1. Arms and pick jittered; the owner said so.
3. Owner's ideas that fixed it: (a) 10 fps keys then interpolate with motion blur, (b) one template figure, both
   hands on a single point on the pickaxe, code the key frames by hand. Done in `chop.py`.
   Looking at a large grid-annotated sheet of one real cycle (frames 26-50) was what made the keys right.
4. Timing comes from the original's strike flashes (bright pixels at the tunnel end): clean for FRIEND (every 18
   frames), irregular for YOU (21, 24, 30 ... frames apart; the last few are guesses).

## What I did NOT do
- Only frames 1-152 (0-5 s). NOT built: dig-down shaft growth with the figures, the drop-in and meeting, "ONE MORE
  GAME." beat (text drawn but figures wrong), the zoom/gold finale (rings, rays, tinted figures), text, fade.
- Not a measured 1:1: after the hand-keyed version I only compared by eye. The 0.36 IoU was for the old fit version.
- Strike flashes and tunnel growth are read from the reference frames, not authored. Stone chips/dust not built.
- Proportions differ a little (my legs look longer, head smaller). The friend's forward steps (about 4.2-4.9 s) are
  not reproduced (his hip x comes from the old noisy fit, smoothed).
- Font: Montserrat stand-in, not the original techno font.
- No second stick-figure reference recreated yet. TikTok cannot be fetched from the shell; the owner must attach
  videos. Only the cubemonsters video of the three attachments was a stick figure.

## Lessons
- Look at the actual rendered figure, not a skeleton overlay, before trusting a fit.
- For loops, author a template with a few keys and time it from events in the reference; do not fit every frame.
- Keep hands on one grip and make the prop rigid; that alone removes most arm/pick jitter.
- Render at 10 fps keys and interpolate; add motion blur by averaging sub-frames of the figure layer.
- Next: key the dig-down (pick pointing down, shaft growing) and the finale the same way, then a second reference.
