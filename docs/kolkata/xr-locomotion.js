/*
 * xr-locomotion.js: WALK / FLY / RESET for any A-Frame 1.x WebXR scene (Meta Quest, desktop fallback).
 * One file, no dependencies beyond A-Frame. Proven in keralamHouseXR (v1.13).
 *
 *   <script src="xr-locomotion.js"></script>
 *   <a-scene xr-locomotion="world: #world; start: 0 0 14.5; bounds: 34 34; board: #plaque">
 *     <a-entity id="world"> ...everything the player can stand on or bump into... </a-entity>
 *   </a-scene>
 *
 * The component builds the player rig (camera + both Touch controllers), the black fade, the on-screen
 * mode text, the fly readout, the reset dialog and (desktop) the Reset button. Do NOT add your own camera.
 *
 * WORLD CONTRACT. Every mesh under the `world` entity is collision geometry:
 *   - a mesh named WALK_* (or inside a node so named), or an entity with class "walkable", can be stood on
 *     and is a valid teleport target (floors, stairs, paths, ground);
 *   - every other mesh blocks you (walls, furniture, railings).
 *   Call  document.querySelector('a-scene').components['xr-locomotion'].collect()  after the world changes
 *   (it is called for you on a gltf `model-loaded` inside `world`).
 *
 * CONTROLS (Quest)
 *   WALK  right stick: walk and turn; right trigger: walk where the hand points, harder = faster (boost);
 *         left stick forward: teleport arc (release to jump).
 *   FLY   right trigger: glide ahead (smooth curve); left trigger or right stick back: reverse;
 *         tilt the right hand up / down while a trigger is held: climb / dive (the pose at the first squeeze
 *         is "level"); left stick back / forward: up / down; wrist left / right: steer; right stick: turn.
 *   A (right) walk <-> fly      B (right) or Y (left) reset dialog      X (left) back to the board (if any)
 *   The Meta button is reserved by the system and cannot be read by a web page.
 * CONTROLS (desktop)
 *   Space trigger, WASD / arrows stick, Shift reverse, E / Q up / down (fly), F walk <-> fly, R reset,
 *   P board, Esc closes the dialog. Mouse look is A-Frame's own.
 *
 * RESET. Puts the player back at `start`, walking, facing -Z, and emits "xr-reset" on the scene.
 *   If `reload` names an entity with a gltf-model, that model is disposed and loaded again (frees GPU memory
 *   on a headset). Listen for "xr-reset" to reset anything else in your experience.
 *
 * EVENTS emitted on the scene: "xr-reset", "xr-mode" (detail.mode = 'walk' | 'fly').
 * API: scene.components['xr-locomotion'].loco  ->  { mode, toggleMode(), goToBoard(), reset(), collect() ... }
 */
(function () {
  if (typeof AFRAME === 'undefined') throw new Error('xr-locomotion: load A-Frame first');
  var T = AFRAME.THREE;
  var S = null;                                   // the one active instance's settings and entities

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function dead(v) { var a = Math.abs(v); return a < 0.15 ? 0 : Math.sign(v) * (a - 0.15) / 0.85; }
  function mk(parent, tag, attrs) {
    var n = document.createElement(tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    parent.appendChild(n); return n;
  }

  // Where a controller "points". Add ?aim=<degrees> to the URL to tilt it if it feels off on your headset.
  var AIM_Q = new T.Quaternion().setFromAxisAngle(new T.Vector3(1, 0, 0),
    (parseFloat(new URLSearchParams(location.search).get('aim')) || 0) * Math.PI / 180);
  var _aq = new T.Quaternion();
  function aimRay(el, origin, dir) {
    el.object3D.getWorldPosition(origin);
    el.object3D.getWorldQuaternion(_aq).multiply(AIM_Q);
    dir.set(0, 0, -1).applyQuaternion(_aq);
  }
  function isWalkMesh(obj) {
    for (var o = obj; o; o = o.parent) {
      if (o.name && S.walkRe.test(o.name)) return true;
      if (o.el && o.el.classList && o.el.classList.contains(S.walkClass)) return true;
    }
    return false;
  }
  function disposeTree(root) {
    root.traverse(function (o) {
      if (o.geometry) o.geometry.dispose();
      var ms = Array.isArray(o.material) ? o.material : [o.material];
      ms.forEach(function (m) {
        if (!m) return;
        for (var k in m) { var v = m[k]; if (v && v.isTexture) v.dispose(); }
        m.dispose();
      });
    });
  }

  // ------------------------------------------------------------------ scene component: builds everything
  AFRAME.registerComponent('xr-locomotion', {
    schema: {
      world:     { type: 'selector' },                  // entity whose meshes are the collision world
      start:     { type: 'vec3', default: { x: 0, y: 0, z: 0 } },
      bounds:    { type: 'vec2', default: { x: 34, y: 34 } },   // half-size of the play square (x, z), metres
      ceiling:   { default: 36 },                       // highest the player can fly
      board:     { type: 'selector' },                  // optional entity (e.g. a plaque) for the X button / P key
      boardDistance: { default: 1.9 },
      reload:    { type: 'selector' },                  // optional gltf entity to dispose and reload on reset
      walkPrefix:{ default: 'WALK_' },                  // mesh name prefix that marks standable surfaces
      walkClass: { default: 'walkable' },               // or an entity class
      walkSpeed: { default: 2.1 },                      // m/s
      flySpeed:  { default: 8 },                        // m/s at full trigger
      flyBack:   { default: 6 },                        // m/s reverse at full trigger
      climb:     { default: 5 },                        // m/s top climb / dive from hand tilt
      ui:        { default: true },                     // desktop Reset button and status line
      hud:       { default: true }                      // fly readout under the view
    },

    init: function () {
      var d = this.data, scene = this.el, self = this;
      S = this.S = {
        scene: scene, world: d.world, walkRe: new RegExp('^' + d.walkPrefix), walkClass: d.walkClass,
        start: d.start, BX: d.bounds.x, BZ: d.bounds.y, BY: d.ceiling, board: d.board, boardDist: d.boardDistance,
        reload: d.reload, reloadUrl: d.reload ? d.reload.getAttribute('gltf-model') : null,
        walkSpeed: d.walkSpeed, flySpeed: d.flySpeed, flyBack: d.flyBack, climb: d.climb, hudOn: d.hud
      };
      // player rig: moving the rig moves the player, never the camera
      var rig = S.rig = mk(scene, 'a-entity', { id: 'xrl-rig', position: d.start.x + ' ' + d.start.y + ' ' + d.start.z });
      var cam = S.cam = mk(rig, 'a-camera', { id: 'xrl-cam' });
      S.fade = mk(cam, 'a-plane', { width: 2, height: 2, position: '0 0 -0.1', visible: false,
        material: 'shader: flat; color: #000; transparent: true; opacity: 0; depthTest: false', 'render-order': 999 });
      S.hud = mk(cam, 'a-text', { value: '', align: 'center', color: '#9fe3ff', position: '0 -0.42 -1', width: 1.1, visible: false });
      S.modetxt = mk(cam, 'a-text', { value: '', align: 'center', color: '#ffd84d', position: '0 -0.3 -1', width: 1.6, visible: false });
      S.lhand = mk(rig, 'a-entity', { 'oculus-touch-controls': 'hand: left', 'xr-loco-teleport': '' });
      S.rhand = mk(rig, 'a-entity', { 'oculus-touch-controls': 'hand: right' });
      // reset dialog
      var dlg = S.dialog = mk(scene, 'a-entity', { visible: false });
      mk(dlg, 'a-plane', { color: '#222', width: 1.8, height: 0.9, opacity: 0.95, transparent: true });
      mk(dlg, 'a-text', { value: 'Reset the experience?', align: 'center', color: '#fff', position: '0 0.1 0.01', width: 1.5 });
      S.yes = mk(dlg, 'a-plane', { color: '#b3261e', width: 0.8, height: 0.3, position: '-0.45 -0.27 0.01' });
      mk(S.yes, 'a-text', { value: 'RESET', align: 'center', position: '0 0 0.01', width: 1.4 });
      S.no = mk(dlg, 'a-plane', { color: '#4a4a4a', width: 0.8, height: 0.3, position: '0.45 -0.27 0.01' });
      mk(S.no, 'a-text', { value: 'CANCEL', align: 'center', position: '0 0 0.01', width: 1.4 });
      dlg.setAttribute('visible', false);
      rig.setAttribute('xr-loco-move', '');

      if (d.ui) {                                        // desktop helpers
        var b = this.btn = document.createElement('button');
        b.type = 'button'; b.textContent = 'Reset'; b.title = 'Reset the experience (R)';
        b.style.cssText = 'position:fixed;right:12px;top:12px;z-index:10;padding:7px 14px;font:600 13px system-ui,sans-serif;' +
          'color:#fff;background:rgba(0,0,0,.6);border:1px solid rgba(255,255,255,.4);border-radius:6px;cursor:pointer';
        b.addEventListener('click', function () { self.loco && self.loco.openDialog(); });
        document.body.appendChild(b);
        scene.addEventListener('enter-vr', function () { b.style.display = 'none'; });
        scene.addEventListener('exit-vr', function () { b.style.display = ''; });
      }
      // collect collision meshes whenever a model inside the world finishes loading
      if (d.world) {
        d.world.addEventListener('model-loaded', function () { self.collect(); });
        scene.addEventListener('loaded', function () { self.collect(); });
      }
      scene.addEventListener('renderstart', function () { self.collect(); });
    },
    // the move component registers itself here once it exists
    attach: function (loco) { this.loco = loco; loco.collect(); },
    collect: function () { if (this.loco) this.loco.collect(); },
    remove: function () {
      if (this.btn && this.btn.parentNode) this.btn.parentNode.removeChild(this.btn);
      var r = this.S && this.S.rig; if (r && r.parentNode) r.parentNode.removeChild(r);
      var dlg = this.S && this.S.dialog; if (dlg && dlg.parentNode) dlg.parentNode.removeChild(dlg);
    }
  });

  // ------------------------------------------------------------------ teleport (left stick forward)
  AFRAME.registerComponent('xr-loco-teleport', {
    init: function () {
      var self = this;
      this.aiming = false; this.last = null; this.targets = [];
      this.raycaster = new T.Raycaster(); this.N = 26;
      this._o = new T.Vector3(); this._d = new T.Vector3();
      var geo = new T.BufferGeometry();
      geo.setAttribute('position', new T.BufferAttribute(new Float32Array((this.N + 1) * 3), 3));
      this.line = new T.Line(geo, new T.LineBasicMaterial({ color: 0x44ff88 }));
      this.dots = new T.Points(geo, new T.PointsMaterial({ color: 0x44ff88, size: 0.06 }));
      this.line.frustumCulled = this.dots.frustumCulled = false;
      this.line.visible = this.dots.visible = false;
      this.marker = new T.Mesh(new T.RingGeometry(0.22, 0.32, 32).rotateX(-Math.PI / 2),
                               new T.MeshBasicMaterial({ color: 0x44ff88, side: T.DoubleSide }));
      this.marker.visible = false;
      this.el.sceneEl.object3D.add(this.line, this.dots, this.marker);
      this.el.addEventListener('thumbstickmoved', function (e) { self.onStick(e.detail.x, e.detail.y); });
    },
    collect: function () {
      var list = [];
      S.world.object3D.traverse(function (o) { if (o.isMesh) list.push(o); });
      this.targets = list;
    },
    computeArc: function (origin, dir) {
      var v = 10, g = 9.8, dt = 0.05;
      var pts = [origin.clone()], p0 = origin.clone(), hit = null, valid = false;
      for (var i = 1; i <= this.N; i++) {
        var t = i * dt;
        var p1 = new T.Vector3(origin.x + dir.x * v * t, origin.y + dir.y * v * t - 0.5 * g * t * t, origin.z + dir.z * v * t);
        var seg = p1.clone().sub(p0), len = seg.length();
        this.raycaster.set(p0, seg.normalize()); this.raycaster.far = len;
        var hits = this.raycaster.intersectObjects(this.targets, false);
        if (hits.length) {
          var h = hits[0], n = h.face.normal.clone().transformDirection(h.object.matrixWorld);
          valid = isWalkMesh(h.object) && n.y > 0.9; hit = h.point.clone(); pts.push(hit); break;
        }
        pts.push(p1.clone()); p0 = p1;
      }
      return { pts: pts, hit: hit, valid: valid };
    },
    onStick: function (x, y) {
      var L = S.loco;
      if (L) L.ls = y;                                  // fly mode also reads the left stick for height
      if (!this.aiming && y < -0.75 && !(L && (L.paused || L.mode === 'fly'))) {
        this.aiming = true; this.collect(); this.line.visible = this.dots.visible = true;
      } else if (this.aiming && y > -0.35) {
        this.aiming = false; this.line.visible = this.dots.visible = this.marker.visible = false;
        if (this.last && this.last.valid) this.teleportTo(this.last.hit);
      }
    },
    teleportTo: function (p) {                          // the HEAD lands on the target, not the rig origin
      var head = this._o, rig = S.rig.object3D;
      S.cam.object3D.getWorldPosition(head);
      rig.position.x += clamp(p.x, -S.BX, S.BX) - head.x;
      rig.position.z += clamp(p.z, -S.BZ, S.BZ) - head.z;
      rig.position.y = p.y;
    },
    tick: function () {
      if (!this.aiming) return;
      var o = this._o, d = this._d; aimRay(this.el, o, d);
      var r = this.last = this.computeArc(o, d), pos = this.line.geometry.attributes.position;
      r.pts.forEach(function (p, i) { pos.setXYZ(i, p.x, p.y, p.z); });
      this.line.geometry.setDrawRange(0, r.pts.length); pos.needsUpdate = true;
      var c = r.valid ? 0x44ff88 : 0xff4444;
      this.line.material.color.setHex(c); this.dots.material.color.setHex(c); this.marker.material.color.setHex(c);
      this.marker.visible = !!r.hit;
      if (r.hit) this.marker.position.set(r.hit.x, r.hit.y + 0.02, r.hit.z);
    },
    remove: function () {
      this.el.sceneEl.object3D.remove(this.line, this.dots, this.marker);
      this.line.geometry.dispose(); this.line.material.dispose(); this.dots.material.dispose();
      this.marker.geometry.dispose(); this.marker.material.dispose();
    }
  });

  // ------------------------------------------------------------------ walk / fly / reset
  var WALK_BACK = 1.2, WALK_ACCEL = 10, WALK_BRAKE = 14, STICK_YAW = 1.9, WALK_BOOST = 1.2, WALK_RAMP = 3.5;
  var TILT_DEAD = 0.05, TILT_FULL = 0.42, CLIMB_STICK = 1.4;
  var FLY_ACCEL = 4.5, FLY_REV = 9.0, FLY_BRAKE = 3.5;
  var AIM_DEAD = 0.1, AIM_GAIN = 3.4, AIM_MAX = 2.6;
  var FLY_RADIUS = 0.4, FLY_MIN_ALT = 0.7, BSOFT = 8;
  var WALK_RADIUS = 0.3, MAX_STEP_UP = 0.36, MAX_DROP = 0.6;
  var BODY_RAYS = [0.2, 0.55, 1.05, 1.5];

  AFRAME.registerComponent('xr-loco-move', {
    init: function () {
      var self = this;
      S.loco = this; this.S = S;
      this.paused = false; this.dialogOpen = false; this.mode = 'walk';
      this.trig = 0; this.keyTrig = 0; this.ltrig = 0; this.keyLTrig = 0; this.gUp = 0; this.gDn = 0;
      this.sx = 0; this.sy = 0; this.kx = 0; this.ky = 0; this.ls = 0; this.kls = 0;
      this.vel = new T.Vector3(); this.yawRate = 0; this.groundY = 0; this._hud = 0; this._tilt = 0;
      this.aimOverride = null; this.vrTest = false;          // test hooks
      this.raycaster = new T.Raycaster();
      this.cam = S.cam; this.hand = S.rhand;
      this.all = []; this.solid = []; this.floors = []; this.flyHit = [];
      this._h = new T.Vector3(); this._o = new T.Vector3(); this._d = new T.Vector3();
      this._t = new T.Vector3(); this._a = new T.Vector3(); this._q = new T.Quaternion();
      this._u = new T.Vector3(); this._w1 = new T.Vector3(); this._w2 = new T.Vector3();
      this.pickRay = new T.Raycaster();
      var lh = S.lhand, rh = S.rhand;

      rh.addEventListener('triggerchanged', function (e) { self.trig = e.detail.value; });
      rh.addEventListener('triggerdown', function () {
        self.trig = 1;
        if (self.dialogOpen) {                             // dialog is up: the trigger presses the button we point at
          var hq = new T.Quaternion(), ho = new T.Vector3();
          rh.object3D.getWorldPosition(ho); rh.object3D.getWorldQuaternion(hq);
          self.pickRay.set(ho, new T.Vector3(0, 0, -1).applyQuaternion(hq));
          self.pickDialog();
        }
      });
      rh.addEventListener('triggerup', function () { self.trig = 0; });
      lh.addEventListener('gripchanged', function (e) { self.gUp = e.detail.value; });      // spare height controls
      lh.addEventListener('gripdown', function () { self.gUp = 1; });
      lh.addEventListener('gripup', function () { self.gUp = 0; });
      rh.addEventListener('gripchanged', function (e) { self.gDn = e.detail.value; });
      rh.addEventListener('gripdown', function () { self.gDn = 1; });
      rh.addEventListener('gripup', function () { self.gDn = 0; });
      lh.addEventListener('triggerchanged', function (e) { self.ltrig = e.detail.value; }); // left trigger = reverse
      lh.addEventListener('triggerdown', function () { self.ltrig = 1; });
      lh.addEventListener('triggerup', function () { self.ltrig = 0; });
      rh.addEventListener('thumbstickmoved', function (e) { self.sx = e.detail.x; self.sy = e.detail.y; });
      lh.addEventListener('ybuttondown', function () { self.openDialog(); });
      lh.addEventListener('xbuttondown', function () { self.goToBoard(); });
      rh.addEventListener('abuttondown', function () { self.toggleMode(); });
      rh.addEventListener('bbuttondown', function () { self.openDialog(); });

      var keys = {};
      function stickKeys() {
        self.kx = (keys.ArrowRight || keys.KeyD ? 1 : 0) - (keys.ArrowLeft || keys.KeyA ? 1 : 0);
        self.ky = (keys.ArrowDown || keys.KeyS ? 1 : 0) - (keys.ArrowUp || keys.KeyW ? 1 : 0);
        self.keyLTrig = (keys.ShiftLeft || keys.ShiftRight) ? 1 : 0;
        self.kls = (keys.KeyE ? 1 : 0) - (keys.KeyQ ? 1 : 0);
      }
      window.addEventListener('keydown', function (e) {
        keys[e.code] = true; stickKeys();
        if (e.code === 'Space') { self.keyTrig = 1; e.preventDefault(); }
        else if (e.code === 'KeyR') self.openDialog();
        else if (e.code === 'KeyF') self.toggleMode();
        else if (e.code === 'KeyP') self.goToBoard();
        else if (e.code === 'Escape') self.closeDialog();
      });
      window.addEventListener('keyup', function (e) {
        keys[e.code] = false; stickKeys();
        if (e.code === 'Space') self.keyTrig = 0;
      });
      var sc = S.scene;
      function bindMouse() {
        if (bindMouse.done || !sc.canvas) return;
        bindMouse.done = true;
        sc.canvas.addEventListener('click', function (e) {
          if (!self.dialogOpen || sc.is('vr-mode')) return;
          var r = sc.canvas.getBoundingClientRect();
          self.pickRay.setFromCamera(new T.Vector2((e.clientX - r.left) / r.width * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), sc.camera);
          self.pickDialog();
        });
      }
      sc.addEventListener('render-target-loaded', bindMouse);
      if (sc.canvas) bindMouse();
      var comp = sc.components['xr-locomotion'];
      if (comp) comp.attach(this); else sc.addEventListener('loaded', function () { sc.components['xr-locomotion'].attach(self); });
    },

    // ----- collision world
    collect: function () {
      if (!S.world) return;
      var all = [], solid = [], floors = [];
      S.world.object3D.traverse(function (o) {
        if (!o.isMesh) return;
        all.push(o); (isWalkMesh(o) ? floors : solid).push(o);
      });
      this.all = all; this.solid = solid; this.floors = floors; this.flyHit = solid.concat(floors);
      // static world: cache each chunk's world box so per-frame tests only touch chunks near the player
      S.world.object3D.updateMatrixWorld(true);
      all.forEach(function (o) {
        if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
        o.userData.box = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld);
      });
    },
    rotateRig: function (yaw) {                           // turn about the head so the head stays put
      var rig = this.el.object3D, a = this._w1, b = this._w2;
      this.cam.object3D.getWorldPosition(a);
      rig.rotation.set(0, yaw, 0, 'YXZ'); rig.updateMatrixWorld(true);
      this.cam.object3D.getWorldPosition(b);
      rig.position.add(a.sub(b));
    },
    getAim: function () {                                 // the controller in VR, the head on desktop
      var d = this._a;
      if (this.aimOverride) return d.copy(this.aimOverride).normalize();
      if (!this.vrTest && !S.scene.is('vr-mode')) {
        this.cam.object3D.getWorldQuaternion(this._q);
        return d.set(0, 0, -1).applyQuaternion(this._q);
      }
      aimRay(this.hand, this._o, d);
      return d;
    },
    groundAt: function (x, z, fromY) {
      this.raycaster.set(this._o.set(x, fromY, z), this._d.set(0, -1, 0));
      this.raycaster.far = fromY + 20;
      var hits = this.raycaster.intersectObjects(this.floors, false);
      return hits.length ? hits[0].point.y : null;
    },
    passable: function (head, base, sx, sz) {
      var len = Math.hypot(sx, sz);
      if (len < 1e-6) return true;
      var dx = sx / len, dz = sz / len, px = -dz, pz = dx;
      this.raycaster.far = len + WALK_RADIUS;
      for (var i = 0; i < BODY_RAYS.length; i++) {
        var wide = BODY_RAYS[i] > 0.3 && BODY_RAYS[i] < 1.3;       // railings live at knee to chest height
        for (var s = 0; s < 3; s++) {
          if (!wide && s !== 1) continue;
          var off = (s - 1) * 0.25;
          this.raycaster.set(this._o.set(head.x + px * off, base + BODY_RAYS[i], head.z + pz * off), this._d.set(dx, 0, dz));
          if (this.raycaster.intersectObjects(this.nearS, false).length) return false;
        }
      }
      var g = this.groundAt(head.x + dx * (len + 0.15), head.z + dz * (len + 0.15), base + MAX_STEP_UP + 0.1);
      return g !== null && g - base <= MAX_STEP_UP && base - g <= MAX_DROP;
    },
    near: function (list, p, R) {
      var out = [];
      for (var i = 0; i < list.length; i++) {
        var b = list[i].userData.box;
        if (b && b.distanceToPoint(p) < R) out.push(list[i]);
      }
      return out;
    },

    // ----- modes
    goToBoard: function () {
      if (this.paused || !S.board) return;
      var rig = this.el.object3D, pe = S.board.object3D, p = pe.position, head = this._h;
      var yaw = pe.rotation.y, tx = p.x + Math.sin(yaw) * S.boardDist, tz = p.z + Math.cos(yaw) * S.boardDist;
      this.mode = 'walk'; this.vel.set(0, 0, 0); this.yawRate = 0; this.mv = undefined;
      S.hud.setAttribute('visible', false);
      this.rotateRig(yaw);
      this.cam.object3D.getWorldPosition(head);
      rig.position.x += tx - head.x; rig.position.z += tz - head.z;
      var g = this.groundAt(tx, tz, rig.position.y + 30);
      this.groundY = g !== null ? g : 0; rig.position.y = this.groundY;
    },
    toggleMode: function () {
      if (this.paused) return;
      this.mode = this.mode === 'walk' ? 'fly' : 'walk';
      S.hud.setAttribute('visible', this.mode === 'fly' && S.hudOn);
      this.vel.set(0, 0, 0); this.yawRate = 0;
      this.rotateRig(this.el.object3D.rotation.y);
      if (this.mode === 'walk') {                           // land on whatever floor is below
        this.cam.object3D.getWorldPosition(this._h);
        var g = this.groundAt(this._h.x, this._h.z, this._h.y + 0.05);
        this.groundY = g !== null ? g : 0;
      }
      var t = S.modetxt;
      t.setAttribute('value', this.mode === 'fly' ? 'FLY MODE   (A = walk)' : 'WALK MODE   (A = fly)');
      t.setAttribute('visible', true);
      clearTimeout(this._mt); this._mt = setTimeout(function () { t.setAttribute('visible', false); }, 2200);
      S.scene.emit('xr-mode', { mode: this.mode });
    },
    pollSticks: function () {                               // read the left stick straight from the gamepad
      var xr = S.scene.renderer && S.scene.renderer.xr, ss = xr && xr.getSession && xr.getSession();
      if (!ss || !ss.inputSources) return;
      for (var i = 0; i < ss.inputSources.length; i++) {
        var src = ss.inputSources[i], gp = src.gamepad;
        if (src.handedness !== 'left' || !gp || !gp.axes) continue;
        var a3 = gp.axes[3] || 0, a1 = gp.axes[1] || 0;
        this.ls = Math.abs(a3) >= Math.abs(a1) ? a3 : a1;
      }
    },

    tick: function (time, dtMs) {
      if (this.paused) return;
      var dt = Math.min(dtMs, 50) / 1000, rig = this.el.object3D, vel = this.vel;
      var trig = Math.max(this.trig, this.keyTrig);
      this.pollSticks();
      var sx = dead(this.sx + this.kx), sy = dead(this.sy + this.ky);      // sy < 0 = stick pushed forward
      var fly = this.mode === 'fly', aim = this.getAim();

      var yawT = -sx * STICK_YAW;                                         // stick turns; flying, the wrist steers too
      if (fly && trig > 0.15 && (this.vrTest || S.scene.is('vr-mode'))) {
        var off = Math.atan2(-aim.x, -aim.z) - rig.rotation.y;
        off = Math.atan2(Math.sin(off), Math.cos(off));
        var ex = Math.abs(off) - AIM_DEAD;
        if (ex > 0) yawT += Math.sign(off) * Math.min(ex * AIM_GAIN, AIM_MAX);
      }
      this.yawRate += (yawT - this.yawRate) * (1 - Math.exp(-9 * dt));
      if (Math.abs(this.yawRate) > 1e-3) this.rotateRig(rig.rotation.y + this.yawRate * dt);

      if (fly) {
        var c = clamp(trig - Math.max(this.ltrig, this.keyLTrig) - sy, -1, 1);
        var ls = clamp(dead(this.ls + this.kls) + this.gUp - this.gDn, -1, 1);
        var hh = this._u.set(aim.x, 0, aim.z);
        if (hh.lengthSq() < 1e-4) { this.cam.object3D.getWorldQuaternion(this._q); hh.set(0, 0, -1).applyQuaternion(this._q); hh.y = 0; }
        hh.normalize();
        var sp = c >= 0 ? S.flySpeed * c * c * (3 - 2 * c) : -S.flyBack * c * c * (3 + 2 * c);
        var tg = this._t.copy(hh).multiplyScalar(sp);
        // hand tilt = climb / dive; the pose when a trigger is first squeezed is "level"
        var thr = trig > 0.05 || this.ltrig > 0.05 || this.keyLTrig > 0;
        if (thr && !this._thr) this._pn = aim.y;
        this._thr = thr;
        var dp = thr ? aim.y - this._pn : 0, ad = Math.abs(dp), g = 0;
        if (ad > TILT_DEAD) { g = clamp((ad - TILT_DEAD) / (TILT_FULL - TILT_DEAD), 0, 1); g = Math.pow(g, 1.5) * Math.sign(dp); }
        this._tilt += (g - this._tilt) * (1 - Math.exp(-14 * dt));
        tg.y = clamp(ls * CLIMB_STICK + this._tilt * S.climb, -S.climb, S.climb);
        var braking = Math.abs(c) < 0.05 && Math.abs(ls) < 0.05;
        var k = braking ? FLY_BRAKE : (c < -0.05 ? FLY_REV : FLY_ACCEL);
        var ke = 1 - Math.exp(-k * dt), kv = 1 - Math.exp(-Math.max(k, 5) * dt);
        vel.x += (tg.x - vel.x) * ke; vel.z += (tg.z - vel.z) * ke; vel.y += (tg.y - vel.y) * kv;
        if (braking && vel.lengthSq() < 0.0004) vel.set(0, 0, 0);
        this._hud += dt;
        if (S.hudOn && this._hud > 0.15) {
          this._hud = 0;
          S.hud.setAttribute('value', 'height ' + rig.position.y.toFixed(1) + ' m   stick ' + (this.ls || 0).toFixed(2) + '  tilt ' + this._tilt.toFixed(2));
        }
        this.stepFly(dt); this.keepInside(); this.fadeNearWalls();
        return;
      }

      // walk: stick forward / back walks; the trigger alone also walks; the trigger on top adds speed
      var stick = Math.abs(sy) > 0.02, fwd = clamp(stick ? -sy : trig, -1, 1);
      var h = this._u.set(aim.x, 0, aim.z);
      if (h.lengthSq() < 1e-4) { this.cam.object3D.getWorldQuaternion(this._q); h.set(0, 0, -1).applyQuaternion(this._q); h.y = 0; }
      h.normalize();
      var boost = fwd > 0 ? 1 + WALK_BOOST * trig : 1;
      var speed = fwd >= 0 ? S.walkSpeed * fwd * boost : WALK_BACK * fwd;
      var tgt = this._t.copy(h).multiplyScalar(speed);
      var acc = Math.abs(fwd) < 0.02 ? WALK_BRAKE : (trig > 0.05 && fwd > 0 ? WALK_RAMP : WALK_ACCEL);
      vel.lerp(tgt, 1 - Math.exp(-acc * dt));
      if (Math.abs(fwd) < 0.02 && vel.lengthSq() < 0.0004) vel.set(0, 0, 0);
      this.stepWalk(dt); this.keepInside(); this.fadeNearWalls();
    },

    fadeNearWalls: function () {                           // head inside a wall (room scale): fade to black
      var f = S.fade, head = this._h, near = 1, i;
      this.cam.object3D.getWorldPosition(head);
      var ns = this.near(this.solid, head, 0.3);
      this.raycaster.far = 0.14;
      for (i = 0; i < 4; i++) {
        this.raycaster.set(head, this._d.set(i === 0 ? 1 : i === 1 ? -1 : 0, 0, i === 2 ? 1 : i === 3 ? -1 : 0));
        var h = this.raycaster.intersectObjects(ns, false)[0];
        if (h) near = Math.min(near, h.distance / 0.14);
      }
      var a = near < 1 ? Math.min(0.95, 1 - near) : 0;
      if (a !== this._fa) { this._fa = a; f.setAttribute('material', 'opacity', a); f.setAttribute('visible', a > 0.01); }
    },
    stepFly: function (dt) {                               // slide along anything solid, stay above the floor
      var rig = this.el.object3D, head = this._h, vel = this.vel;
      this.cam.object3D.getWorldPosition(head);
      var lim = [[head.x, S.BX, 'x'], [head.z, S.BZ, 'z'], [head.y, S.BY, 'y']];
      for (var i = 0; i < 3; i++) {                        // soft wall at the edge of the play area
        var p = lim[i][0], L = lim[i][1], ax = lim[i][2], v = vel[ax];
        var dd = v > 0 ? L - p : v < 0 && ax !== 'y' ? L + p : 99;
        if (dd < BSOFT) vel[ax] *= Math.exp(-(1 - Math.max(dd, 0) / BSOFT) * 8 * dt);
      }
      var speed = vel.length();
      if (speed > 0.001) {
        var dir = this._d.copy(vel).divideScalar(speed);
        var u = this._u.set(0, 1, 0).cross(dir);
        if (u.lengthSq() < 1e-4) u.set(1, 0, 0);
        u.normalize().multiplyScalar(FLY_RADIUS * 0.7);
        var w = this._w1.copy(dir).cross(u);
        var offs = [[0, 0, 0], [u.x, u.y, u.z], [-u.x, -u.y, -u.z], [w.x, w.y, w.z], [-w.x, -w.y, -w.z]];
        var best = null, fl = this.near(this.flyHit, head, 1.2);
        this.raycaster.far = speed * dt + FLY_RADIUS;
        for (var j = 0; j < offs.length; j++) {
          this.raycaster.set(this._o.set(head.x + offs[j][0], head.y + offs[j][1], head.z + offs[j][2]), dir);
          var hit = this.raycaster.intersectObjects(fl, false)[0];
          if (hit && (!best || hit.distance < best.distance)) best = hit;
        }
        if (best && best.face) {
          var n = best.face.normal.clone().transformDirection(best.object.matrixWorld);
          var vn = vel.dot(n);
          if (vn < 0) vel.addScaledVector(n, -vn);
        }
        rig.position.addScaledVector(vel, dt);
      }
      this.cam.object3D.getWorldPosition(head);
      var gy = this.groundAt(head.x, head.z, head.y + 0.05);
      var minY = (gy !== null ? gy : 0) + FLY_MIN_ALT;
      if (head.y < minY) { rig.position.y += minY - head.y; if (vel.y < 0) vel.y = 0; }
    },
    keepInside: function () {
      var rig = this.el.object3D, head = this._h;
      this.cam.object3D.getWorldPosition(head);
      rig.position.x += clamp(head.x, -S.BX, S.BX) - head.x;
      rig.position.z += clamp(head.z, -S.BZ, S.BZ) - head.z;
      if (head.y > S.BY) { rig.position.y -= head.y - S.BY; if (this.vel.y > 0) this.vel.y = 0; }
    },
    stepWalk: function (dt) {
      var rig = this.el.object3D, head = this._h;
      this.cam.object3D.getWorldPosition(head);
      var gy = this.groundAt(head.x, head.z, rig.position.y + MAX_STEP_UP + 0.1);
      if (gy !== null) this.groundY = gy;
      var base = Math.max(rig.position.y, this.groundY);
      if (this.vel.lengthSq() > 0) {
        var sx = this.vel.x * dt, sz = this.vel.z * dt;
        this.frame = (this.frame || 0) + 1;                // the wall test runs every other frame, answer reused
        if (this.frame % 2 === 0 || this.mv === undefined) {
          this.nearS = this.near(this.solid, head, 0.75);
          this.mv = this.passable(head, base, sx * 2, sz * 2) ? 3
                  : (Math.abs(sx) > 1e-5 && this.passable(head, base, sx * 2, 0)) ? 1       // slide along walls
                  : (Math.abs(sz) > 1e-5 && this.passable(head, base, 0, sz * 2)) ? 2 : 0;
        }
        if (this.mv & 1) rig.position.x += sx;
        if (this.mv & 2) rig.position.z += sz;
      } else this.mv = undefined;
      var st = (this.groundY - rig.position.y) * (1 - Math.exp(-12 * dt));      // follow the floor, smooth over stairs
      rig.position.y += Math.max(-6 * dt, Math.min(3 * dt, st));
    },

    // ----- reset
    reset: function () {
      this.vel.set(0, 0, 0); this.yawRate = 0; this.mode = 'walk';
      this.trig = this.keyTrig = this.sx = this.sy = 0; this._thr = false; this._tilt = 0;
      S.hud.setAttribute('visible', false);
      var rig = this.el.object3D;
      this.rotateRig(0);
      rig.position.set(S.start.x, S.start.y, S.start.z); this.groundY = S.start.y;
      if (S.reload) {                                        // throw the model away and load it again (frees GPU memory)
        var ent = S.reload, mesh = ent.getObject3D('mesh');
        if (mesh) disposeTree(mesh);
        ent.removeAttribute('gltf-model');
        this.all = []; this.solid = []; this.floors = []; this.flyHit = [];
        T.Cache.clear();
        var r = S.scene.renderer;
        if (r) { r.renderLists.dispose(); if (r.info.reset) r.info.reset(); }
        setTimeout(function () { ent.setAttribute('gltf-model', S.reloadUrl); }, 150);
      }
      S.scene.emit('xr-reset');
    },

    // ----- reset dialog
    openDialog: function () {
      if (this.dialogOpen) return;
      var d = S.dialog, cam = this.cam.object3D, p = new T.Vector3(), q = new T.Quaternion(), f = new T.Vector3(0, 0, -1);
      cam.getWorldPosition(p); cam.getWorldQuaternion(q); f.applyQuaternion(q); f.y = 0;
      if (f.lengthSq() < 1e-4) f.set(0, 0, -1);
      f.normalize();
      d.object3D.position.set(p.x + f.x * 1.4, p.y - 0.1, p.z + f.z * 1.4);
      d.object3D.lookAt(p.x, p.y - 0.1, p.z);
      d.setAttribute('visible', true);
      this.dialogOpen = this.paused = true; this.vel.set(0, 0, 0);
      var h = S.rhand;                                      // the green pointer ray exists only while the dialog is up
      if (!h.components.raycaster) h.setAttribute('raycaster', 'objects: [data-xrl-btn]; far: 8; showLine: true; lineColor: #44ff88');
      S.yes.setAttribute('data-xrl-btn', ''); S.no.setAttribute('data-xrl-btn', '');
    },
    closeDialog: function () {
      if (!this.dialogOpen) return;
      S.dialog.setAttribute('visible', false);
      this.dialogOpen = this.paused = false;
      S.rhand.removeAttribute('raycaster');
    },
    pickDialog: function () {
      var yes = S.yes.getObject3D('mesh'), no = S.no.getObject3D('mesh');
      if (!yes || !no) return;
      var hit = this.pickRay.intersectObjects([yes, no], false)[0];
      if (!hit) return;
      this.closeDialog();
      if (hit.object === yes) this.reset();
    }
  });
})();
