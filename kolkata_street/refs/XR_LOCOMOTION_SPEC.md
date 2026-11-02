# XR Locomotion Spec (A-Frame / WebXR, Meta Quest controllers)

Reusable interaction design for moving a player through a WebXR scene. Written from the keralamHouseXR project so the behaviour never has to be reinvented. Part A is shared plumbing, Part B is WALK, Part C is FLY. Use B, C or both per experience.

Status of each part (be honest about this when reusing):
- WALK: shipped in keralamHouseXR. Verified on desktop by simulation (routes, stairs, walls). Not yet felt on a Quest headset.
- FLY: built, simulated on desktop, then removed from keralamHouseXR when the user rejected the drone look (front propellers in view) and behaviour. It was never tested on a headset, and the user's verdict on the first version was that it did not feel like a real FPV drone. Treat Part C as a starting point with known gaps (section C.9), not a finished feel.

Stack: A-Frame 1.7.0 (three.js r173), `oculus-touch-controls`, no other dependencies. All code below is plain JS inside one HTML file.

---

## Part A. Shared plumbing (needed by both modes)

### A.1 Scene structure
```html
<a-entity id="world">            <!-- everything collidable lives here -->
  <a-plane class="walkable" rotation="-90 0 0" width="160" height="160" color="#5d8a3f"></a-plane>
  <a-entity id="house" gltf-model="url(model.glb?v=N)"></a-entity>
</a-entity>

<a-entity id="rig" position="0 0 14.5" locomotion>   <!-- the player -->
  <a-camera id="cam"></a-camera>
  <a-entity id="lhand" oculus-touch-controls="hand: left"></a-entity>
  <a-entity id="rhand" oculus-touch-controls="hand: right"></a-entity>
</a-entity>
```
Rule: never move the camera. Move `#rig`. Hands and camera are children of the rig, so they travel with it, and the headset's real-world tracking still works on top.

### A.2 Naming convention for collision (set in the 3D tool)
- Mesh object named `WALK_*` (or any entity with class `walkable`): can be stood on and is a valid teleport target.
- Everything else (`House_*`, props, furniture, roof): blocks the player.
- `collect()` walks `#world` once and sorts meshes into `floors` (WALK_) and `solid` (the rest) plus `all`. Call it after the model loads and after a reload.
- Split large merged meshes into spatial cells (about 6 m). three.js raycasts test every triangle of a mesh whose bounding sphere is hit, so one 60k-triangle mesh costs far more than 60 small chunks. Chunk names keep the `WALK_` prefix.
- Export glTF without normals if you want small files (vertices merge; three.js flat-shades).

### A.3 Reading the controller
| Event (on the hand entity) | Detail | Use |
|---|---|---|
| `triggerchanged` | `{value 0..1}` | analog throttle |
| `triggerdown` / `triggerup` | none | binary press, UI clicks |
| `thumbstickmoved` | `{x, y}`; y < 0 means pushed forward | stick |
| `bbuttondown` (right), `ybuttondown` / `xbuttondown` (left) | none | buttons |

Store the latest values on the component (`this.trig`, `this.sx`, `this.sy`) and read them in `tick`. Apply a dead zone: `dead(v) = |v|<0.15 ? 0 : sign(v)*(|v|-0.15)/0.85`.

### A.4 Aim direction ("where the controller points")
World position and quaternion of the hand entity, forward = local -Z:
```js
var AIM_Q = new T.Quaternion().setFromAxisAngle(new T.Vector3(1,0,0), (parseFloat(QS.get('aim'))||0)*Math.PI/180);
var _aq = new T.Quaternion();
function aimRay(el, origin, dir){
  el.object3D.getWorldPosition(origin);
  el.object3D.getWorldQuaternion(_aq).multiply(AIM_Q);
  dir.set(0,0,-1).applyQuaternion(_aq);
}
```
`?aim=<degrees>` is a tuning URL parameter (positive tilts the aim up). The Quest controller's pose axis may sit above or below the natural pointing direction. Verify on a headset and bake the right value in as default.

### A.5 Turning or tilting the rig about the head (critical)
Rotating the rig about its own origin swings the player around the room. Always rotate about the head:
```js
rotateRig(yaw, pitch, roll){
  cam.getWorldPosition(a);
  rig.rotation.set(pitch, yaw, roll, 'YXZ');   // Euler order matters
  rig.updateMatrixWorld(true);
  cam.getWorldPosition(b);
  rig.position.add(a.sub(b));                   // cancel the head's movement
}
```

### A.6 Desktop fallback (so it can be tested without a headset)
Space = trigger, arrows/WASD = thumbstick, aim = where the head looks, `R` = reset. In non-VR mode use the camera's forward as the aim.

### A.7 Hygiene
- No allocations in `tick`: reuse scratch `Vector3`/`Quaternion`.
- Clamp the frame time: `dt = min(dtMs, 50)/1000`.
- Show load state and JS errors in an on-page status line; the Quest has no console.
- Version the model URL (`?v=N`) every time it changes; GitHub Pages and the Quest cache aggressively.
- Test hooks: `aimOverride` (a fixed Vector3 aim) and `vrTest` (pretend VR) let you drive the component from the browser console. Remove the A-Frame behavior with `sceneEl.removeBehavior(comp)` and call `comp.tick(t, 16.7)` yourself for deterministic simulation.

### A.8 Reset dialog (shared UX)
- Open: left Y, key `R`, or an on-page button (flat view only).
- A panel appears 1.4 m in front of the head (horizontal heading), facing the player. Two buttons: RESET, CANCEL. Locomotion pauses while open.
- Pick buttons with your own raycast, not A-Frame's `cursor`. The cursor misses clicks that arrive without a prior hover, so a real quick click did nothing. VR: ray from the hand on `triggerdown`. Desktop: `raycaster.setFromCamera` on canvas `click`.
- RESET: zero velocity and turn, move the rig to the start, dispose geometries/materials/textures of the model, remove it, `THREE.Cache.clear()`, `renderer.renderLists.dispose()`, reload the model. It frees the model's GPU memory; it is not a full page reload.

### A.9 Play-area bounds
A hard clamp of the head to a box (`|x|,|z| <= 34`), applied every frame after movement. Fly adds a soft zone (see C.7).

---

## Part B. WALK

### B.1 What the user does (every motor input)
| User action | Result |
|---|---|
| Point the right controller anywhere | Sets the walking direction (horizontal part only; pitch ignored) |
| Pull the right trigger (analog) | Walk that way. A half pull walks at half speed |
| Push right stick left/right (while pulling trigger or not) | Turn the body smoothly (about 110 deg/s) |
| Push right stick forward | Also walks forward (adds to trigger, total clamped to 1) |
| Pull right stick back | Reverse at 1.2 m/s (with trigger held, it cancels the trigger and stops you) |
| Release everything | Quick stop (brake rate 14 per second) |
| Push left stick forward and release | Teleport (arc, release to jump) |
| Re-aim while walking | Path curves smoothly; no snap |
| Walk into a wall | Slide along it, never stick |
| Walk at stairs or a kerb | Climb it if the rise is 0.36 m or less, otherwise stop |

Point of view: the user's head is free to look anywhere; the aim hand decides the direction. Turning with the stick is smooth, not snapped.

### B.2 Constants
```js
WALK_SPEED = 2.1;  WALK_BACK = 1.2;          // m/s
WALK_ACCEL = 10;   WALK_BRAKE = 14;          // 1/s, velocity easing rate
STICK_YAW = 1.9;                              // rad/s at full stick (~110 deg/s)
WALK_RADIUS = 0.3; MAX_STEP_UP = 0.36;        // m
BODY_RAYS = [0.2, 0.43, 0.7, 1.1, 1.5];       // heights above the floor that must be clear
```

### B.3 Per-frame algorithm
```
trig = max(triggerValue, keyTrigger)
sx = dead(stickX + keyX), sy = dead(stickY + keyY)       // sy < 0 = forward

yawRate += (-sx*STICK_YAW - yawRate) * (1 - exp(-9*dt))  // eased
if |yawRate| > 0.001: rotateRig(rig.rotation.y + yawRate*dt)

fwd = clamp(trig - sy, -1, 1)
h   = normalize(aim.x, 0, aim.z)                          // if ~vertical, use head forward
tgt = h * (fwd >= 0 ? WALK_SPEED*fwd : WALK_BACK*fwd)
vel.lerp(tgt, 1 - exp(-(|fwd|>0.02 ? WALK_ACCEL : WALK_BRAKE) * dt))
if |fwd|<0.02 and |vel|^2 < 0.0004: vel = 0

stepWalk(dt); keepInside()
```

### B.4 stepWalk (collision, wall sliding, floor following)
```js
stepWalk(dt){
  cam.getWorldPosition(head);
  gy = groundAt(head.x, head.z, rig.y + MAX_STEP_UP + 0.1);   // ray down against floors
  if (gy !== null) groundY = gy;
  base = max(rig.y, groundY);
  sx = vel.x*dt; sz = vel.z*dt;
  if (passable(head, base, sx, sz)) { rig.x += sx; rig.z += sz; }
  else if (|sx|>1e-5 && passable(head, base, sx, 0)) rig.x += sx;   // slide
  else if (|sz|>1e-5 && passable(head, base, 0, sz)) rig.z += sz;
  st = (groundY - rig.y) * (1 - exp(-12*dt));                  // follow the floor
  rig.y += max(-6*dt, min(3*dt, st));                          // capped climb 3 m/s, drop 6 m/s
}
passable(head, base, sx, sz){
  len = hypot(sx, sz); dir = (sx,sz)/len
  for h in BODY_RAYS: ray from (head.x, base+h, head.z) along dir, far = len + WALK_RADIUS; if hits a solid mesh return false
  g = groundAt(head + dir*(len+0.15), from base+MAX_STEP_UP+0.1)
  return g !== null && g - base <= MAX_STEP_UP
}
```
Notes learned the hard way:
- `groundAt` casts down from above `base`. If a floor step is higher than that start point the ray begins inside the step and misses it. Keep `MAX_STEP_UP + 0.1` headroom and keep stair risers well under `MAX_STEP_UP` (0.18 m risers, 0.28 m treads worked).
- Do not hang anything at body height inside doorways. A picture frame in a doorway at 1.5 m blocked the front door because of the 1.5 m body ray.
- Stairs and floors must be named `WALK_`; if they are solid they block you instead.
- Small decor under 0.2 m (rugs, kolam, door mats) is passable because the lowest body ray is at 0.2 m. If it must also be teleport-valid, name it `WALK_`.

### B.5 Teleport (left hand, optional)
- Push left stick forward past y < -0.75 to start aiming; release (y > -0.35) to commit.
- Arc: launch speed 10 m/s along the hand's aim, gravity 9.8, 26 segments of 0.05 s, each segment raycast against all of `#world`.
- Valid only if the first thing hit is a `WALK_` mesh (or ground) and `face normal.y > 0.9`. Green line and marker if valid, red if not.
- Commit moves the rig so the HEAD lands on the point (`rig += target - head` in x,z) and sets `rig.y = floorHeight`. Clamp to the play bounds.
- Disabled while a dialog is open.

### B.6 Walk feel goals and tuning knobs
- Faster pickup: raise `WALK_ACCEL`. Slower stop: lower `WALK_BRAKE`.
- Turn rate: `STICK_YAW`. Comfort setting idea: also offer 30 degree snap turn.
- Speed: `WALK_SPEED`. 2.1 m/s is a brisk walk, about 17 percent above the first version (1.8) after feedback that it was too slow.
- Open items: comfort vignette while turning; head-bob (not implemented); haptics on collision (not implemented).

---

## Part C. FLY (drone / FPV style)

The target feel is a DJI Avata 2 flown with the motion controller and goggles: point to fly, throttle with the trigger, stick for climb and yaw, release to brake and hover.

### C.1 What the user does (every motor input)
| User action | Result |
|---|---|
| Aim the right controller | Sets the thrust direction in full 3D (pitch included: aim up to climb, down to dive) |
| Pull the right trigger (analog) | Thrust along the aim. Speed = 9 m/s x trigger^1.3, so a light pull is gentle |
| Point left or right of straight ahead (relative to the rig's heading) while holding the trigger | The drone yaws toward it. Rate proportional to the angle past a 6 degree dead zone, up to 150 deg/s |
| Right stick left/right | Yaw at up to 110 deg/s, works with or without trigger |
| Right stick forward/back | Climb / dive up to 4 m/s, works with or without trigger |
| Release trigger and stick | Brake (rate 5.5 per second, about 0.6 s to stop), level out (roll and pitch ease to zero) and hover |
| Fly into walls, floors, ceilings, roofs | Slide along the surface, never pass through. Window bars and gaps: 5-ray cluster stops it |
| Near the edge of the play box | Outward speed bleeds off over the last 8 m; hard stop at the edge; warning shown |
| Left stick | Teleport disabled while flying |
| B button | Toggle walk / fly |

Heading rule: yaw by wrist is measured relative to the rig's own yaw (`atan2(-aim.x, -aim.z) - rig.rotation.y`), not relative to the head, so looking around while flying does not steer the drone. As the rig yaws toward the aim the offset shrinks, so it converges instead of spinning forever.

### C.2 Constants
```js
FLY_SPEED = 9;  CLIMB_SPEED = 4;                // m/s
FLY_ACCEL = 3.2; FLY_BRAKE = 5.5;               // 1/s, easing toward target velocity
// climb/dive eases at max(k, 6) so vertical response is snappier than forward thrust
STICK_YAW = 1.9;                                // rad/s
AIM_DEAD = 0.1;  AIM_GAIN = 3.4;  AIM_MAX = 2.6; // wrist yaw: dead zone rad, gain 1/s, max rad/s (~150 deg/s)
YAW_EASE = 9;                                   // 1/s, eases the yaw rate
TILT_PITCH = 0.12; TILT_ROLL = 0.3; ROLL_GAIN = 0.14;   // rad; ?tilt=0 disables tilt
FLY_RADIUS = 0.4;  FLY_MIN_ALT = 0.7;           // m
BX = 34; BZ = 34; BY = 36; BSOFT = 8;           // play box and soft zone
```

### C.3 Per-frame algorithm
```
trig = max(triggerValue, keyTrigger)
sx = dead(stickX), sy = dead(stickY)
aim = controller forward (world, full 3D)

// heading
yawT = -sx * STICK_YAW
if vr and trig > 0.15:
    off = wrapPi(atan2(-aim.x, -aim.z) - rig.rotation.y)
    ex = |off| - AIM_DEAD
    if ex > 0: yawT += sign(off) * min(ex * AIM_GAIN, AIM_MAX)
yawRate += (yawT - yawRate) * (1 - exp(-YAW_EASE*dt))

// target velocity
tgt = aim * FLY_SPEED * trig^1.3
tgt.y += -sy * CLIMB_SPEED
braking = trig < 0.05 and |sy| < 0.05
k = braking ? FLY_BRAKE : FLY_ACCEL
ke = 1 - exp(-k*dt);  kv = 1 - exp(-max(k,6)*dt)
vel.x += (tgt.x - vel.x)*ke;  vel.z += (tgt.z - vel.z)*ke;  vel.y += (tgt.y - vel.y)*kv
if braking and |vel|^2 < 0.0004: vel = 0

// soft wall near the play box edge (see C.7)
// bank and nose-down (see C.5)
rotateRig(rig.rotation.y + yawRate*dt, pitch, roll)

stepFly(dt); keepInside()
```

### C.4 stepFly (collision and altitude)
```js
stepFly(dt){
  speed = vel.length();
  if (speed > 0.001) {
    dir = vel / speed;
    u = normalize(cross(up, dir)) * FLY_RADIUS*0.7;     // sideways offset
    w = cross(dir, u);                                   // vertical-ish offset
    best = nearest hit among rays from head + {0, +u, -u, +w, -w}, direction dir, far = speed*dt + FLY_RADIUS
    if (best) {                                          // slide along the surface
      n = best.face.normal transformed to world
      vn = vel.dot(n);  if (vn < 0) vel -= n*vn;
    }
    rig.position += vel*dt;
  }
  gy = groundAt(head.x, head.z, head.y + 0.05);          // floor below the drone
  minY = groundY + FLY_MIN_ALT;
  if (head.y < minY) { rig.y += minY - head.y; if (vel.y < 0) vel.y = 0; }
}
```
Why five rays: a single ray slipped through the gaps between window bars. Add a transparent (alpha 0.15) glass pane mesh in each window so the drone is stopped by glass.

### C.5 Drone-view tilt (optional comfort trade-off)
```
fwdSpeed = -vel.x*sin(yaw) - vel.z*cos(yaw)
pitchTarget = -clamp(fwdSpeed / FLY_SPEED, 0, 1) * TILT_PITCH        // nose down with speed (max 7 deg)
rollTarget  = clamp(yawRate * ROLL_GAIN, -TILT_ROLL, TILT_ROLL)      // bank into turns (max 17 deg)
pitch += (pitchTarget - pitch) * (1 - exp(-6*dt)); roll likewise
```
Applied through `rotateRig(yaw, pitch, roll)` (A.5). Rolling a VR view is a known motion-sickness trigger. Keep `?tilt=0` available and consider a default of off, or a lower `TILT_ROLL`, until tested on real users.

### C.6 Drone dressing (what was built, and why it was rejected)
- Front propellers: two head-locked prop guards (ring plus spinning two-blade rotor plus 16 percent opaque blur disc) at the bottom corners of the view, about 0.4 m left/right, 0.27 m down, 0.6 m ahead, scaled 0.7. Drawn on top (`depthTest false`, `renderOrder 999`). Spin 16 + 10*throttle revolutions per second.
- Engine whine: WebAudio sawtooth plus triangle through a low-pass, pitch and brightness rising with throttle. Started on the user's click.
- The user judged the propellers in view "very bad" and asked for the whole drone look removed. Do not include this dressing by default. If a drone cue is wanted, try a very subtle HUD or a thin frame edge first, and test on a headset.

### C.7 Play-area bounds for flying
- Soft zone: per axis, if moving outward and within `BSOFT` (8 m) of the limit: `v *= exp(-(1 - dist/BSOFT) * 8 * dt)`. Applied to x, z and upward y.
- Hard clamp: after movement, clamp head x,z to `+-34` and y to `<= 36`, zero the outward velocity.
- Visual: five translucent grid planes (4 walls plus a ceiling), opacity `clamp(1 - dist/12, 0, 1) * 0.6`, hidden when not near. A "turn back" text near the face when within 5 m.
- Floor: `FLY_MIN_ALT` above the floor found by a downward ray against `WALK_` meshes (so you can fly over a roof deck or balcony and stay above it).

### C.8 Mode switching (walk and fly in one experience)
- Choose at start with a panel (WALK / FLY) picked with the trigger; later, B toggles.
- Fly to walk: reset pitch/roll and yaw rate, level the rig, `groundAt` the head position and snap `rig.y` to the floor, stop the engine sound.
- Walk to fly: velocity zero, show props and start sound (if used).
- Keep both modes' constants separate; they share the stick and trigger with different meanings (see tables).

### C.9 Known gaps and ideas not yet done (reinvent here, not from zero)
1. Never tested in a headset. Aim pitch offset, trigger feel, comfort and frame rate are all unknown.
2. Yaw reference assumes the user physically faces the rig's forward when they start. A re-centre button or "calibrate on first trigger pull" would make this robust.
3. Thrust follows the aim directly. A real drone thrusts along its body axis; blending the thrust vector toward the body heading would feel more drone-like but less direct.
4. No gimbal / head decoupling: head look is free, which is right for VR but not identical to goggles with a gimbal.
5. No speed modes (Normal, Sport, Cine) or brake button; the Avata 2 has them. A left-trigger sport boost was considered.
6. No acceleration-based sway or micro-vibration while hovering.
7. No haptics. Add short pulses on collision and a faint continuous rumble with throttle.
8. No altitude/speed HUD readability testing; it was on the back of the left hand, small.
9. Comfort: add a vignette that tightens with yaw rate and speed.

---

## Part D. Quick reuse checklist
1. Build the model with `WALK_` and solid naming, chunk it, version the URL.
2. Copy the rig, hands, `locomotion` and `teleport` components, helpers (A.3 to A.5).
3. Pick modes: B only, C only, or both with the chooser from C.8.
4. Add the reset dialog (A.8) with own-raycast picking.
5. Add status line and desktop keys; simulate routes via the test hooks before touching a headset.
6. Test on a Quest: aim offset, trigger feel, turn rate, comfort. Record the values you settle on back into this file.

## Update v1.05 (supersedes the numbers in Part B and Part C where they differ)
- **Walk collision:** body rays are cast three abreast (centre and 0.25 m left and right) at knee-to-chest height, so thin railing balusters cannot be squeezed between. A drop of more than 0.6 m ahead blocks movement (no walking off balconies or landings). The wall test runs every other frame (the answer is reused in between) and only against chunks whose world bounding box is within 0.75 m. Head within 0.14 m of a wall fades the view to black instead of showing the inside of the wall.
- **Fly, gentle:** FLY_SPEED 4.5 m/s, accel 1.0 /s, brake 3.5 /s. Trigger glides ahead on the horizontal heading; aim pitch adds only 20 percent of speed as climb. Right stick back reverses at up to 2.2 m/s. Left stick up/down changes height at up to 1.4 m/s (teleport is off while flying). Desktop: E up, Q down.
- Measured on desktop: 0.5 s of trigger gives 1.8 m/s and 0.3 m/s climb; 3 s gives 4.3 m/s and 0.46 m/s climb.
