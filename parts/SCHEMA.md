# Parts library format

A part is one small JSON file in `parts/<folder>/<id>.json`, plus an optional PNG or OBJ next to it.
Parts never contain final colours. They name **palette slots**, and the avatar file decides what each
slot looks like. So one hair template works in any colour.

Folders: `faces`, `hair`, `headwear`, `torsos`, `legs`, `accessories`, `sets`.
File names: lowercase, digits and underscores, like `smile_01.json`. The file name is the id.
Always run `python -m blockreel parts check <file>` and `python -m blockreel part-preview <folder> <id>` and LOOK at the picture.

Palette slots: `skin hand hair primary secondary accent pants shoes metal dark light`.
A colour is a slot name or a `#rrggbb` hex string (use hex for things that should never change colour, such as a tree).

Units are studs. +y is up, the figure faces +z, x is the figure's left/right (the viewer sees +x on the right when the figure faces them).

## Piece (used by hair, headwear, accessories, sets, and extras on torsos, legs and faces)

```json
{"shape": "box", "size": [w, h, d], "pos": [x, y, z], "rot": [rx, ry, rz], "color": "hair",
 "bevel": 0.05, "top": [1.0, 1.0], "bottom": [1.0, 1.0], "spec": true, "casts": true}
```
- `shape`: `box`, `cylinder` (round, axis along y), `sphere`, or `obj` (then `file` and `scale`, no `size`).
- `size` is the full width, height and depth. `pos` is the centre of the piece in the part's frame. `rot` is degrees.
- `top` / `bottom`: width ratios (x, z) at the top and bottom end, to taper a box or cylinder. `top: [0.1, 0.1]` on a cylinder makes a cone.
- `bevel`: edge rounding in studs (default 0.05). `spec`: plastic highlight (default true). `casts`: shadow (default true, false for obj).
- Keep a part to 3 to 14 pieces. Fewer, bolder pieces look better than many tiny ones.

## Frames (where `pos` 0,0,0 is)

- **head** (hair, headwear, face pieces, head accessories): centre of the head. The head is a cylinder, diameter 1.6, height 1.2, so the top surface is y = +0.6, the front surface is z = +0.8, the sides are x = +-0.8. The face print covers the front. Hair sits around y 0.3 to 0.8 and should wrap the head (cylinder slightly wider than 1.6, such as 1.72).
- **torso** (torso extras, `attach: torso`): centre of the torso. Torso is 2.0 wide, 1.9 tall, 1.1 deep: front z = +0.55, back z = -0.55, top y = +0.95.
- **back** (`attach: back`): the torso frame moved to the back surface (z = -0.55). Things extend toward -z.
- **hips** (leg extras, `attach: hips`): centre of the hip piece (2.0 wide, 0.5 tall, 1.1 deep). A skirt hangs from here.
- **hand_r / hand_l** (`attach`): centre of the hand. The arm is above (+y). Put a held item so the grip is at 0,0,0 and it points up (+y) or forward (+z).
- **set** (a prop or scenery piece): the ground point under the middle of the thing, y = 0 is the ground.

## faces/*.json

```json
{"kind": "face", "name": "Happy grin", "image": "grin_01.png", "tags": ["happy"]}
```
`image` is a **320x256 PNG with transparent background**. Only draw the features (eyes, brows, mouth, cheeks); the head colour shows through.
Use `blockreel.partkit.FaceCanvas` to draw them, or any other tool. Eyes sit at about y 0.42 of the image height, the mouth at about y 0.70.
Optional `pieces` (head frame) can add 3D bits such as a nose. No real people, no logos, no copyrighted characters.

## hair/*.json and headwear/*.json

```json
{"kind": "hair", "name": "Short hair", "pieces": [ ... ]}
{"kind": "headwear", "name": "Cap", "replaces_hair": false, "pieces": [ ... ]}
```
Hair uses the `hair` slot for its colour. Headwear uses `primary`, `secondary`, `accent`, `metal` or `dark`. `replaces_hair: true` hides the hair underneath (helmets, hoods). Do not cover the face area (front, z > 0.6, y between -0.5 and 0.35) unless it is meant to be a visor or mask.

## torsos/*.json

```json
{"kind": "torso", "name": "Zip jacket", "base": "primary", "arm": "primary", "image": "jacket_zip.png", "pieces": []}
```
`base` is the colour slot of the torso block, `arm` of the arms (long sleeves: same as base; short sleeves: `skin`, but then the arms are all skin, so prefer `base`). `image`: optional **256x240 transparent PNG** printed on the front (zip, stripe, pocket, star). `back_image` optional. `pieces` add 3D bits in the torso frame (a collar, a belt, a scarf).
Use `blockreel.partkit.TorsoCanvas` to draw prints.

## legs/*.json

```json
{"kind": "legs", "name": "Shorts", "hips": "pants", "bands": [
  {"from": 0, "to": 0.5, "color": "pants"}, {"from": 0.5, "to": 1, "color": "skin"}], "pieces": []}
```
`bands` colour each leg from top (0) to bottom (1). `hips` is the slot for the hip piece. `pieces` (hips frame) can add a skirt, a belt, a tool belt.

## accessories/*.json

```json
{"kind": "accessory", "name": "Backpack", "attach": "back", "pieces": [ ... ]}
```
`attach`: `head`, `torso`, `back`, `hips`, `hand_r`, `hand_l`. Held items go in a hand.

## sets/*.json (scenery and props, used with `{"template": "tree_01", "position": [x,0,z]}` in a scene)

```json
{"kind": "set", "name": "Brick tree", "pieces": [ ... ]}
```
Colours here are usually fixed hex values, or slots that a scene can override with `"palette": {...}`. Keep sets under 25 pieces.

## LDraw parts (`ld_*`)

Real geometry from the LDraw library in `ldraw/` (CC BY 4.0). Files are generated by `tools/ldraw_catalog.py`; write one by hand like this:

```json
{"kind": "face", "name": "Grin", "ldraw": "3626bp01", "title": "Minifig Head with Standard Grin Pattern", "source": "LDraw (CC BY 4.0)"}
{"kind": "torso", "ldraw": {"torso": "973p13", "arm_r": "3818", "arm_l": "3819", "hand": "3820"}, "base": "primary", "arm": "primary"}
{"kind": "legs", "ldraw": {"hips": "3815", "leg_r": "3816", "leg_l": "3817"}, "hips": "pants"}
{"kind": "hair", "pieces": [{"shape": "ldraw", "part": "3901", "color": "hair"}]}
```
A piece with `"shape": "ldraw"` takes `part` (the .dat number without extension), `pos` and `rot` in LDU in the part's frame, and `color` (a palette slot or hex). Printed parts keep their own colours; colour 16 in the part takes the slot colour. These parts only work on avatars with `rig: "minifig"`.

## What not to do

Hand-made parts must be original: no logos, no brand names, no real or fictional people or characters, no trademarked marks. Generic things (pirate, astronaut, knight, chef) are fine. The `ld_*` parts come from LDraw and include licensed themes; avoid those in promo videos (see README, Licence and trademark).
