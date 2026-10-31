# XR_Museum_: a museum floor in the language of the Bihar Museum

A WebXR gallery for three downloaded masterpieces, built for Meta Quest 3 (Quest Browser) and
usable in a normal desktop browser. The movement, the information board and the reset are the
ones from keralamHouseXR, unchanged in behaviour: WALK, FLY, teleport, and the PLAQUE construct.

- Page and logic: `docs/index.html`
- Board template: `docs/plaque.js` (copied from `XR_Locomotion/plaque/plaque.js`, do not fork it)
- Models: `docs/models/museum.glb` + `caesar.glb`, `nefertiti.glb`, `rocket.glb`
- Blender sources: `build/build_museum.py` (the room), `build/prep_models.py` (the three pieces)
- Local preview: `cd docs && python3 -m http.server 4210`

## 1. The building

The real Bihar Museum (Maki and Associates with Opolis, Patna) sequences a visitor through a
lobby, a compressed corridor and then the gallery. This floor does the same:

| Space | What it is |
|---|---|
| Lobby | Backlit teak screen walls of short blocks, a sandstone dado, a travertine reception block, and an oval dish of light in the ceiling. You start here, just inside the shut entrance doors. |
| Corridor | 12 m, tapering open towards the hall, walls leaning in at the top, with recessed vertical light slots in a stepped rhythm. |
| Hall | An equilateral triangle, 14 m circumradius, with each corner cut back 4.8 m into an alcove. One masterpiece per alcove. A 9.5 x 6.5 m elliptical skylight dish is the centre of the ceiling. |

The hall's three walls are deliberately three different materials, as the real building does:
red travertine, Dholpur-coloured sandstone ashlar with four tall slot windows (the raking light
of the reference photographs), and a full-height backlit teak screen.

**The three corners**

| Alcove | Piece | Display height | Plinth |
|---|---|---|---|
| North (on axis from the corridor, seen as you arrive) | Bust of Nefertiti | 0.60 m | 1.05 m |
| South-west | Bust of Julius Caesar | 0.85 m | 0.95 m |
| South-east | Stephenson's Rocket | 3.00 m | 0.20 m platform |

## 2. Lighting

Baked in Cycles, not lit at runtime. A light-tight shell is built around the whole building for
the bake so the only light is the designed light: a low raking sun through the slot windows,
daylight onto both skylight dishes, warm emission behind the teak screens, cove slots in the
alcoves, a key and a fill spot on each piece, and a grazing wash down the travertine.

Each of the 11 mesh groups is unwrapped and baked to its own atlas, saved through the Filmic
view transform, and re-imported as a pure emission material. So in the browser:

- the room needs no lights at all and costs nothing to light;
- the only runtime lights in the page are the point lights over the three pieces, placed to
  match the baked spots, so the sculptures sit in the same light as the room around them.

Two Blender 3.6 traps worth remembering: `bpy.ops.uv.pack_islands` crashes in background mode,
and so does unwrapping many objects in one multi-object edit. The build unwraps and bakes each
group on its own, which is why there are 11 textures and not one atlas.

## 3. Movement (identical to keralamHouseXR)

| Input | Action |
|---|---|
| Right trigger | Walk where you aim (hold with the stick for extra speed) |
| Right stick | Turn left and right, walk forward and back |
| Left stick forward, release | Teleport (green arc = valid, red = not) |
| A | Toggle WALK and FLY |
| X | Back to the information board |
| B or Y | Reset dialog |
| Desktop | Space, WASD/arrows, F, P, R, Esc, E/Q for up and down while flying |

Gameplay comes from the object names, as in the spec: `WALK_floors` is the only standable mesh,
everything named `SOLID_*` blocks. The masterpieces are **not** in `#world`: at 55-70k triangles
each they would make every collision raycast expensive, so they are decoration under `#art` and
three invisible boxes inside `#world` stand in for them.

Play bounds are 17 m in x, 28 m in z and 8.5 m up, which keeps flying inside the building.

## 4. Rebuilding

```bash
# the three pieces: decimate, re-orient, scale to display height, origin on the base
/Applications/Blender.app/Contents/MacOS/Blender -b -P build/prep_models.py

# the room: Cycles stills to build/preview_*.png for checking the look
/Applications/Blender.app/Contents/MacOS/Blender -b -P build/build_museum.py -- preview 24

# the room: bake the lighting and export docs/models/museum.glb (about 20 minutes)
/Applications/Blender.app/Contents/MacOS/Blender -b -P build/build_museum.py -- bake
```

Progress goes to `build/build.log` (Blender block-buffers stdout when it is redirected, so the
log file is the only way to watch a headless run).

## 5. Version rule

Every publish bumps the build number by 0.01. Change it in the plaque `version`, in the three
label plaques, and in the `?v=` on `plaque.js` and on every model URL, because GitHub Pages and
the Quest cache hard. Current: **1.01**.

## 6. Checked vs not yet checked

Checked on desktop, by driving the real components rather than moving the camera:

- Walks the whole route: start (z 25.2) through the lobby and corridor into the hall, stopping
  against a bench at z 5.2. Collision, wall sliding and floor following all behave.
- Fly: A toggles, climbing from 1.6 m rises through the skylight opening and stops at 7.9 m
  inside the dome dish. You can fly up into the skylight, which is worth keeping.
- Teleport: the arc lands on the floor and reports valid; 14 collision targets are collected
  (11 room groups plus the three masterpiece blockers).
- The page loads with no JavaScript errors and reports a missing model correctly.

Not yet checked: **anything on a headset** - controller aim, trigger feel, frame rate, and
whether the text on the board and the three labels is readable at the right distance.

### Faults found by walking it, and fixed

1. The corridor walls were built with a direct `box()` call that never got its rotation, so both
   lay *across* the corridor as 12 m slabs and the route to the hall was blocked. They had also
   made the corridor render black in every preview, which was misread as "a dark corridor".
2. The hall ceiling bridged its two loops by arc length instead of by polar angle, so the ring
   came out twisted and sealed the skylight over.
3. The ashlar texture was mapped in plan, so walls showed vertical stripes instead of courses.
4. The floor was baked glossy: a bake has no view direction, so every texel reflected the
   skylight straight back and the whole floor came out an even grey.
