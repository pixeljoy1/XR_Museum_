# xr-locomotion: WALK / FLY / RESET for any A-Frame scene

Version 1.13 behaviour (from keralamHouseXR). One file: `xr-locomotion.js`. No dependencies beyond A-Frame 1.x.

## Use it

```html
<script src="https://aframe.io/releases/1.7.0/aframe.min.js"></script>
<script src="xr-locomotion.js"></script>
<a-scene xr-locomotion="world: #world; start: 0 0 14.5; bounds: 34 34; board: #plaque; reload: #house">
  <a-entity id="world"> ... </a-entity>
</a-scene>
```

Do not add your own camera or controllers: the component builds the player rig, both Touch controllers, the black fade, the mode text, the fly readout, the reset dialog and the desktop Reset button.

## World contract

Every mesh under `world` is collision geometry. A mesh named `WALK_*` (or inside a node so named), or an entity with class `walkable`, is standable and a valid teleport target. Everything else blocks. Call `scene.components['xr-locomotion'].collect()` if the world changes after load (it runs on every `model-loaded` inside `world`).

## Options

| option | default | meaning |
|---|---|---|
| world | none (required) | entity holding the collision meshes |
| start | 0 0 0 | spawn and reset position |
| bounds | 34 34 | half-size of the play square, metres |
| ceiling | 36 | highest flight altitude |
| board | none | entity for the X button / P key (stands you 1.9 m in front, facing it) |
| reload | none | gltf entity disposed and reloaded on reset (frees headset GPU memory) |
| walkPrefix / walkClass | WALK_ / walkable | what marks a standable surface |
| walkSpeed / flySpeed / flyBack / climb | 2.1 / 8 / 6 / 5 | m/s |
| ui / hud | true / true | desktop Reset button; fly readout |

## Controls

Quest: right stick walk and turn; right trigger walk where the hand points (harder = faster); left stick forward teleports. A toggles walk and fly. In fly: right trigger glides ahead, left trigger or right stick back reverses, tilt the right hand while a trigger is held to climb or dive (the pose at the first squeeze is level), left stick back/forward = up/down, wrist steers. B or Y opens the reset dialog, X goes to the board. The Meta button is system-reserved and cannot be read by a web page.

Desktop: Space trigger, WASD stick, Shift reverse, E / Q up / down, F walk or fly, R reset, P board, Esc close.

## Events and API

Scene events: `xr-reset`, `xr-mode` (detail.mode). API: `scene.components['xr-locomotion'].loco` exposes `mode`, `toggleMode()`, `goToBoard()`, `reset()`, `collect()`, `openDialog()`.

## Files

- `xr-locomotion.js` the module
- `demo/index.html` minimal scene (ground, wall, three steps) that exercises it: `cd locomotion && python3 -m http.server`, open `/demo/`
- Tuned constants live at the top of the move section of the JS (accelerations, tilt dead zone, step height 0.36 m, max drop 0.6 m).

Verified on desktop with simulated input (wall stop, step climbing, fly tilt climb, reverse, reset, dialog). Not verified in a headset outside keralamHouseXR.

keralamHouseXR still carries its own inline copy of this logic. Moving it onto this file is a separate refactor.
