/* Kolkata Street - WebXR.
 *
 * Four components:
 *   street-environment  sky-and-ground environment map, so metal is not black
 *   city-builder        loads layout.json and places one clone per instance
 *   street-rig          locomotion: walk on the ground, or fly
 *   vr-input            forwards controller events to the rig
 *
 * The loader mirrors how the Blender scene is built: each asset GLB is fetched
 * and parsed ONCE, then cloned per placement. Object3D.clone() shares geometry
 * and material, so 45 buildings cost one building's worth of GPU memory.
 * Pointing 132 <a-entity gltf-model> tags at the same files would parse each
 * file again for every placement.
 */
(function () {
  'use strict';

  var THREE = AFRAME.THREE;
  var hud = document.getElementById('hud');
  var VERSION = '1.01';

  // Resolve data files against THIS SCRIPT's URL, not the document's.
  // A host may serve the page at a path with no trailing slash
  // (/artifact/<id>, /portals/kolkata), and a bare 'layout.json' then resolves
  // against the PARENT directory and 404s -- which looks exactly like a page
  // that loaded but stayed empty, because the sky still renders. The script's
  // own src always carries the right directory.
  var BASE = (function () {
    var tag = document.currentScript;
    if (!tag) {
      var all = document.getElementsByTagName('script');
      for (var i = all.length - 1; i >= 0; i--) {
        if (/street\.js(\?|$)/.test(all[i].src || '')) { tag = all[i]; break; }
      }
    }
    var src = (tag && tag.src) || '';
    return src ? src.replace(/[?#].*$/, '').replace(/[^/]*$/, '') : '';
  })();
  function asset(path) { return BASE + path; }

  // --- loading progress -----------------------------------------------------
  var inflight = {};
  function setProgress(done, total) {
    var bar = document.getElementById('prog');
    if (!bar) { return; }
    bar.hidden = false;
    var frac = 0;
    for (var k in inflight) {
      if (Object.prototype.hasOwnProperty.call(inflight, k)) { frac += inflight[k]; }
    }
    var pct = total ? Math.max(1, Math.min(100,
      Math.round(((done + frac) / total) * 100))) : 1;
    document.getElementById('prog-fill').style.width = pct + '%';
    document.getElementById('prog-label').textContent =
      'Loading the street  ' + done + ' / ' + total + ' models';
  }
  function hideProgress() {
    var bar = document.getElementById('prog');
    if (bar) { bar.hidden = true; }
  }
  var CHUNK_M = 110;          // street metres per instanced batch

  function say(msg, isError) {
    hud.style.whiteSpace = 'pre-line';
    hud.textContent = msg;
    hud.className = isError ? 'error' : '';
    if (isError) { console.error(msg); }
  }

  // ---------------------------------------------------------------- environment
  AFRAME.registerComponent('street-environment', {
    init: function () {
      var scene = this.el.object3D;
      var renderer = this.el.renderer;
      if (!renderer) {
        this.el.addEventListener('render-target-loaded', this.init.bind(this));
        return;
      }
      // A vertical gradient as an equirectangular image, pushed through PMREM.
      // Without an environment map every metal surface in the scene -- the rails,
      // the chrome on the taxi, the trolley wire -- renders black, and the wet
      // road has nothing to reflect.
      var W = 64, H = 32, data = new Uint8Array(W * H * 4);
      var sky = [0xd9, 0xe0, 0xe8], horiz = [0xc6, 0xcb, 0xd1], gnd = [0x3b, 0x37, 0x31];
      for (var y = 0; y < H; y++) {
        var t = y / (H - 1), c;
        if (t < 0.5) { c = mix(sky, horiz, Math.pow(t / 0.5, 0.7)); }
        else { c = mix(horiz, gnd, Math.pow((t - 0.5) / 0.5, 0.45)); }
        for (var x = 0; x < W; x++) {
          var i = (y * W + x) * 4;
          data[i] = c[0]; data[i + 1] = c[1]; data[i + 2] = c[2]; data[i + 3] = 255;
        }
      }
      var tex = new THREE.DataTexture(data, W, H, THREE.RGBAFormat);
      tex.mapping = THREE.EquirectangularReflectionMapping;
      tex.colorSpace = THREE.SRGBColorSpace || undefined;
      tex.needsUpdate = true;
      var pmrem = new THREE.PMREMGenerator(renderer);
      scene.environment = pmrem.fromEquirectangular(tex).texture;
      pmrem.dispose();
      tex.dispose();

      function mix(a, b, k) {
        return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k,
                a[2] + (b[2] - a[2]) * k];
      }
    }
  });

  // ---------------------------------------------------------------- city
  AFRAME.registerComponent('city-builder', {
    schema: { src: { default: 'layout.json' } },

    init: function () {
      var self = this;
      var url = asset(this.data.src);
      say('Loading layout...');
      fetch(url).then(function (r) {
        if (!r.ok) { throw new Error(url + ' -> HTTP ' + r.status); }
        return r.json();
      }).then(function (layout) {
        self.layout = layout;
        self.el.sceneEl.layout = layout;
        return self.loadAndPlace(layout);
      }).catch(function (e) {
        hideProgress();
        say('Could not build the street.\n' + e.message +
            '\nLooked in: ' + (BASE || '(the page directory)') +
            '\nIf you opened the file directly, serve the folder over http ' +
            'instead:  python3 -m http.server 4210', true);
      });
    },

    // Each asset is placed the moment it arrives, rather than after all of
    // them. The ground goes first, so within a second there is a street to
    // stand in and the rest of it builds up around you -- which is a much
    // better answer to a slow connection than several megabytes of grey.
    loadAndPlace: function (L) {
      var self = this;
      var city = document.getElementById('city').object3D;
      var loader = new THREE.GLTFLoader();
      // Some static hosts serve only a fixed set of file types and .glb is not
      // always one, so layout.json can ask for self-contained .json glTF
      // instead. GLTFLoader sniffs the content, not the name.
      var ext = L.asset_ext || '.glb';
      var walk = [], trams = [], batches = 0;

      var byAsset = {};
      L.instances.forEach(function (inst) {
        (byAsset[inst.asset] = byAsset[inst.asset] || []).push(inst);
      });

      var names = L.assets.slice().sort(function (a, b) {
        return (a === 'ground' ? -1 : 0) - (b === 'ground' ? -1 : 0);
      });
      var done = 0, total = names.length;
      setProgress(0, total);

      var foot = self.el.sceneEl.footprints = {};

      // Two boxes per asset, both in the model's own frame.
      //  walk  only the geometry below 2.2 m, so you can walk under a tree's
      //        canopy or a hoarding and are stopped by its trunk and legs.
      //  fly   the whole thing, so you cannot fly through the third floor.
      function footprint(root) {
        var lo = new THREE.Box3(), hi = new THREE.Box3(), any = false;
        lo.makeEmpty(); hi.makeEmpty();
        root.updateMatrixWorld(true);
        root.traverse(function (o) {
          if (!o.isMesh || !o.geometry) { return; }
          if (!o.geometry.boundingBox) { o.geometry.computeBoundingBox(); }
          var b = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld);
          hi.union(b);
          if (b.min.y < 2.2) { lo.union(b); any = true; }
        });
        if (hi.isEmpty()) { return null; }
        if (!any) { lo.copy(hi); }
        var box = function (x) {
          return { cx: (x.min.x + x.max.x) / 2, cz: (x.min.z + x.max.z) / 2,
                   hx: (x.max.x - x.min.x) / 2, hz: (x.max.z - x.min.z) / 2,
                   top: x.max.y };
        };
        return { walk: box(lo), fly: box(hi) };
      }

      function placeOne(name, root) {
        prepare(root);
        if (name !== 'ground') {
          var f = footprint(root);
          if (f) { foot[name] = f; }
        }
        if (name === 'ground') {
          city.add(root);
          root.traverse(function (o) {
            if (o.isMesh && /^WALK_/.test(o.name)) { walk.push(o); }
          });
          self.el.sceneEl.walkables = walk;
          return;
        }
        var list = byAsset[name] || [];
        if (name === L.tram_asset) {
          list.forEach(function (inst) {
            var o = root.clone(true);
            o.position.set(inst.pos[0], inst.pos[1], inst.pos[2]);
            o.rotation.set(0, THREE.MathUtils.degToRad(inst.rotY), 0);
            city.add(o);
            trams.push({ obj: o,
                         dir: Math.cos(THREE.MathUtils.degToRad(inst.rotY)) });
          });
          self.el.sceneEl.trams = trams;
          return;
        }
        // Chunk along the street, but only where it buys anything. A batch that
        // spans the whole 250 m can never be frustum-culled, so every triangle
        // in it is submitted every frame; a batch of two is a draw call that
        // may as well have stayed a clone.
        var span = CHUNK_M * (list.length > 14 ? 1 : 1e6);
        var chunks = {};
        list.forEach(function (inst) {
          var c = Math.floor(inst.pos[0] / span);
          (chunks[c] = chunks[c] || []).push(inst);
        });
        Object.keys(chunks).forEach(function (c) {
          batches += instanceBatch(root, chunks[c], city);
        });
      }

      return Promise.all(names.map(function (name) {
        return new Promise(function (resolve, reject) {
          loader.load(asset('models/' + name + ext), function (gltf) {
            try { placeOne(name, gltf.scene); } catch (e) { reject(e); return; }
            done++;
            delete inflight[name];
            setProgress(done, total);
            resolve();
          }, function (ev) {
            if (ev && ev.total) { inflight[name] = ev.loaded / ev.total; }
            setProgress(done, total);
          }, function (err) {
            reject(new Error('models/' + name + ext + ': ' +
                             (err.message || err)));
          });
        });
      })).then(function () {
        hideProgress();
        say('Kolkata street - ' + L.instances.length + ' placements in ' +
            batches + ' batches. Drag to look around.');
        setTimeout(function () {
          hud.style.transition = 'opacity 1.2s';
          hud.style.opacity = '0';
        }, 7000);
        document.getElementById('views').hidden = false;
        document.getElementById('keys').hidden = false;
        buildViewMenu(L.viewpoints);
        self.el.sceneEl.emit('city-ready');
      });
    }
  });

  // One InstancedMesh per (geometry, material) in the source model, carrying
  // every placement in this chunk. Forty-five buildings stop being five hundred
  // draw calls and become about a dozen.
  function instanceBatch(src, placements, parent) {
    if (!src) { return 0; }
    src.updateMatrixWorld(true);
    var parts = [];
    src.traverse(function (o) {
      if (o.isMesh && !Array.isArray(o.material)) {
        parts.push({ g: o.geometry, m: o.material, local: o.matrixWorld.clone(),
                     cast: o.castShadow, recv: o.receiveShadow });
      }
    });
    var tmp = new THREE.Matrix4(), q = new THREE.Quaternion(),
        pos = new THREE.Vector3(), one = new THREE.Vector3(1, 1, 1),
        eul = new THREE.Euler();
    parts.forEach(function (p) {
      var im = new THREE.InstancedMesh(p.g, p.m, placements.length);
      placements.forEach(function (inst, i) {
        pos.set(inst.pos[0], inst.pos[1], inst.pos[2]);
        eul.set(0, THREE.MathUtils.degToRad(inst.rotY), 0);
        q.setFromEuler(eul);
        tmp.compose(pos, q, one);
        tmp.multiply(p.local);
        im.setMatrixAt(i, tmp);
      });
      im.instanceMatrix.needsUpdate = true;
      im.castShadow = p.cast;
      im.receiveShadow = p.recv;
      im.computeBoundingSphere();      // instance-aware, so culling is correct
      parent.add(im);
    });
    return parts.length;
  }

  // Materials come out of glTF as MeshStandardMaterial. A few need adjusting for
  // the street to read: the carriageway is wet, and nothing should be a mirror.
  function prepare(root) {
    root.traverse(function (o) {
      if (!o.isMesh) { return; }
      o.castShadow = true;
      o.receiveShadow = true;
      o.frustumCulled = true;
      var mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach(function (m) {
        if (!m) { return; }
        m.envMapIntensity = 1.0;
        if (/^WALK_road|^SOLID_track/.test(o.name)) {
          // Monsoon. In Cycles the wet look comes from Fresnel at a grazing
          // angle over a near-black base; the same thing works here, but only
          // if the base really is near-black and the roughness really is low.
          m.color.setRGB(0.035, 0.037, 0.040);
          m.roughness = 0.09;
          m.metalness = 0.0;
          m.envMapIntensity = 2.6;
          o.castShadow = false;
        }
        if (m.metalness > 0.6) { m.roughness = Math.max(0.12, m.roughness); }
        if (m.transparent) { m.depthWrite = false; }
      });
    });
    return root;
  }

  function buildViewMenu(views) {
    var box = document.getElementById('views');
    views.forEach(function (v, i) {
      var b = document.createElement('button');
      b.innerHTML = '<b>' + ((i + 1) % 10) + '</b> &nbsp;' + v.label +
                    ' <span>' + v.lens + 'mm</span>';
      b.title = v.note;
      b.addEventListener('click', function () {
        document.getElementById('rig').components.locomotion.goToView(i);
      });
      box.appendChild(b);
    });
  }

  // ---------------------------------------------------------------- locomotion
  //
  // Ported from keralamHouseXR, by way of this repo's docs/index.html, which its
  // README states carries that movement unchanged. Same constants, same input
  // mapping, same feel:
  //
  //   WALK  right trigger walks where the controller points (level: pitch is
  //         ignored). Right stick turns you and also walks forward and back.
  //         Trigger on top of the stick adds up to +120% speed.
  //   FLY   A switches. Trigger glides ahead, stick back reverses, left stick
  //         (or E/Q) changes height, and with the trigger held you steer by
  //         pointing your wrist.
  //   A     walk / fly        B or Y  reset       X  next viewpoint
  //
  // One thing is NOT a port. The museum raycasts every mesh under #world to
  // decide what blocks you, with a precomputed world box per mesh. This street
  // is instanced -- forty-five buildings share one geometry in a handful of
  // InstancedMeshes -- so per-mesh boxes do not exist and a per-batch raycast
  // would test the whole terrace at once. Instead each placement contributes an
  // oriented footprint box, built from its model's bounds when it loads, and
  // the body test is circle-vs-box against the few near you. Same behaviour,
  // and it costs nothing.
  var WALK_SPEED = 2.1, WALK_BACK = 1.2;          // metres per second
  var WALK_ACCEL = 10, WALK_BRAKE = 14;           // how fast velocity follows the target (1/s)
  var STICK_YAW = 1.9;                            // rad/s at full stick (about 110 deg/s)
  var WALK_BOOST = 1.2, WALK_RAMP = 3.5;          // trigger adds up to +120% speed
  var FLY_SPEED = 4.5, FLY_BACK = 3.4, CLIMB_SPEED = 1.4, FLY_PITCH = 0.2;
  var FLY_ACCEL = 2.4, FLY_REV = 5.0, FLY_BRAKE = 3.5;
  var AIM_DEAD = 0.1, AIM_GAIN = 3.4, AIM_MAX = 2.6;          // wrist steering
  var FLY_RADIUS = 0.4, FLY_MIN_ALT = 0.7, BSOFT = 4;
  var WALK_RADIUS = 0.3, MAX_STEP_UP = 0.36, MAX_DROP = 0.6;
  var EYE = 1.62;

  function dead(v) { var a = Math.abs(v); return a < 0.15 ? 0 : Math.sign(v) * (a - 0.15) / 0.85; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  AFRAME.registerComponent('locomotion', {
    init: function () {
      var self = this;
      this.mode = 'walk';
      this.trig = 0; this.keyTrig = 0;      // right trigger 0..1, Space on desktop
      this.sx = 0; this.sy = 0;             // right thumbstick
      this.kx = 0; this.ky = 0; this.ls = 0; this.kls = 0;
      this.vel = new THREE.Vector3();
      this.yawRate = 0; this.groundY = 0;
      this.view = -1;
      this.tramsRun = false;                // T sets them running
      this.blockers = [];
      this.raycaster = new THREE.Raycaster();
      this.cam = document.getElementById('head');
      this.hand = document.getElementById('rhand');
      this.lhand = document.getElementById('lhand');
      this._h = new THREE.Vector3(); this._o = new THREE.Vector3();
      this._d = new THREE.Vector3(); this._t = new THREE.Vector3();
      this._a = new THREE.Vector3(); this._q = new THREE.Quaternion();
      this._u = new THREE.Vector3(); this._w1 = new THREE.Vector3();
      this._w2 = new THREE.Vector3();
      this.start = this.el.object3D.position.clone();

      this.hand.addEventListener('triggerchanged', function (e) { self.trig = e.detail.value; });
      this.hand.addEventListener('triggerdown', function () { self.trig = 1; });
      this.hand.addEventListener('triggerup', function () { self.trig = 0; });
      this.hand.addEventListener('thumbstickmoved', function (e) {
        self.sx = e.detail.x; self.sy = e.detail.y;
      });
      this.lhand.addEventListener('thumbstickmoved', function (e) { self.ls = e.detail.y; });
      // Right hand: A switches walk / fly, B resets. Left hand: X next
      // viewpoint, Y resets -- the museum's mapping, with the plaque button
      // standing in for the viewpoint list, since this street has no board.
      this.hand.addEventListener('abuttondown', function () { self.toggleMode(); });
      this.hand.addEventListener('bbuttondown', function () { self.reset(); });
      this.lhand.addEventListener('xbuttondown', function () { self.goToView(self.view + 1); });
      this.lhand.addEventListener('ybuttondown', function () { self.reset(); });

      // Desktop: Space = trigger, arrows / WASD = thumbstick, F = walk/fly,
      // R = reset, E/Q = up/down while flying.
      var keys = {};
      this.keys = keys;
      function stickKeys() {
        self.kx = (keys.ArrowRight || keys.KeyD ? 1 : 0) - (keys.ArrowLeft || keys.KeyA ? 1 : 0);
        self.ky = (keys.ArrowDown || keys.KeyS ? 1 : 0) - (keys.ArrowUp || keys.KeyW ? 1 : 0);
        self.kls = (keys.KeyQ ? 1 : 0) - (keys.KeyE ? 1 : 0);
      }
      window.addEventListener('keydown', function (e) {
        keys[e.code] = true; stickKeys();
        if (e.code === 'Space') { self.keyTrig = 1; e.preventDefault(); }
        else if (e.code === 'KeyR') self.reset();
        else if (e.code === 'KeyF') self.toggleMode();
        else if (e.code === 'KeyV') self.goToView(self.view + 1);
        else if (e.code === 'KeyT') { self.tramsRun = !self.tramsRun; self.flash(
          self.tramsRun ? 'TRAMS RUNNING   (T = hold)' : 'TRAMS HELD   (T = run)'); }
        else if (e.code === 'KeyL') self.toggleShadows();
        var m = /^Digit([0-9])$/.exec(e.code);
        if (m) self.goToView((parseInt(m[1], 10) + 9) % 10);
      });
      window.addEventListener('keyup', function (e) {
        keys[e.code] = false; stickKeys();
        if (e.code === 'Space') self.keyTrig = 0;
      });

      this.el.sceneEl.addEventListener('city-ready', function () {
        self.collect();
        self.goToView(0);
      });
      // In a headset the shadow pass is the first thing worth giving up.
      this.el.sceneEl.addEventListener('enter-vr', function () { self.setShadows(false); });
      this.el.sceneEl.addEventListener('exit-vr', function () { self.setShadows(true); });
    },

    // Turn each placement's footprint into a world-space oriented box.
    collect: function () {
      var L = this.el.sceneEl.layout, foot = this.el.sceneEl.footprints || {};
      var walk = [], fly = [];
      (L.instances || []).forEach(function (inst) {
        var f = foot[inst.asset];
        if (!f) { return; }
        var r = THREE.MathUtils.degToRad(inst.rotY);
        var c = Math.cos(r), sn = Math.sin(r);
        // Ry(t) maps local (x, z) to (x cos t + z sin t, -x sin t + z cos t)
        function place(b) {
          return { x: inst.pos[0] + b.cx * c + b.cz * sn,
                   z: inst.pos[2] - b.cx * sn + b.cz * c,
                   hx: b.hx, hz: b.hz, top: inst.pos[1] + b.top, c: c, s: sn };
        }
        walk.push(place(f.walk));
        fly.push(place(f.fly));
      });
      this.blockers = walk;
      this.flyBlockers = fly;
      var b = (L.street || {});
      this.bx = [(b.x0 || -90) + 4, (b.x1 || 158) - 4];
      this.bz = [-9.0, 9.0];
      this.flyBx = [(b.x0 || -90), (b.x1 || 158)];
      this.flyBz = [-42, 42];
      this.byTop = 34;
    },

    // Turn the rig about the player's head so the head stays put in the world.
    rotateRig: function (yaw) {
      var rig = this.el.object3D, a = this._w1, b = this._w2;
      this.cam.object3D.getWorldPosition(a);
      rig.rotation.set(0, yaw, 0, 'YXZ');
      rig.updateMatrixWorld(true);
      this.cam.object3D.getWorldPosition(b);
      rig.position.add(a.sub(b));
    },

    // Direction the player wants to go: the controller in VR, the head on desktop.
    getAim: function () {
      var d = this._a;
      if (!this.el.sceneEl.is('vr-mode')) {
        this.cam.object3D.getWorldQuaternion(this._q);
        return d.set(0, 0, -1).applyQuaternion(this._q);
      }
      this.hand.object3D.getWorldPosition(this._o);
      this.hand.object3D.getWorldQuaternion(this._q);
      return d.set(0, 0, -1).applyQuaternion(this._q);
    },

    // Height of the ground under (x, z). null = nothing to stand on.
    groundAt: function (x, z, fromY) {
      var walk = this.el.sceneEl.walkables;
      if (!walk || !walk.length) { return null; }
      this.raycaster.set(this._o.set(x, fromY, z), this._d.set(0, -1, 0));
      this.raycaster.far = fromY + 20;
      var hits = this.raycaster.intersectObjects(walk, false);
      return hits.length ? hits[0].point.y : null;
    },

    // Would the player's body at (x, z, base) overlap a footprint?
    blocked: function (x, z, base) {
      var b = this.blockers;
      for (var i = 0; i < b.length; i++) {
        var o = b[i];
        if (o.top < base + 0.25) { continue; }          // low enough to step over
        var dx = x - o.x, dz = z - o.z;
        if (dx * dx + dz * dz > 400) { continue; }      // cheap reject at 20 m
        var lx = dx * o.c - dz * o.s, lz = dx * o.s + dz * o.c;
        if (Math.abs(lx) < o.hx + WALK_RADIUS && Math.abs(lz) < o.hz + WALK_RADIUS) {
          return true;
        }
      }
      return false;
    },

    // Is it OK to move the body by (sx, sz)? Footprints block; steps must be low.
    passable: function (head, base, sx, sz) {
      var len = Math.hypot(sx, sz);
      if (len < 1e-6) { return true; }
      var nx = head.x + sx, nz = head.z + sz;
      if (this.blocked(nx, nz, base)) { return false; }
      if (nx < this.bx[0] || nx > this.bx[1] || nz < this.bz[0] || nz > this.bz[1]) {
        return false;
      }
      var g = this.groundAt(nx + (sx / len) * 0.15, nz + (sz / len) * 0.15,
                            base + MAX_STEP_UP + 0.1);
      return g !== null && g - base <= MAX_STEP_UP && base - g <= MAX_DROP;
    },

    toggleMode: function () {
      this.mode = this.mode === 'walk' ? 'fly' : 'walk';
      this.vel.set(0, 0, 0); this.yawRate = 0;
      this.rotateRig(this.el.object3D.rotation.y);
      if (this.mode === 'walk') {                   // land on whatever is below
        this.cam.object3D.getWorldPosition(this._h);
        var g = this.groundAt(this._h.x, this._h.z, this._h.y + 0.05);
        this.groundY = g !== null ? g : 0;
      }
      this.flash(this.mode === 'fly' ? 'FLY MODE   (A = walk)' : 'WALK MODE   (A = fly)');
    },

    reset: function () {
      this.vel.set(0, 0, 0); this.yawRate = 0; this.mode = 'walk';
      this.trig = this.keyTrig = this.sx = this.sy = this.ls = 0;
      this.view = -1;
      this.rotateRig(0);
      this.el.object3D.position.copy(this.start);
      this.groundY = 0;
      this.goToView(0);
      this.flash('RESET');
    },

    goToView: function (i) {
      var L = this.el.sceneEl.layout;
      if (!L || !L.viewpoints || !L.viewpoints.length) { return; }
      i = ((i % L.viewpoints.length) + L.viewpoints.length) % L.viewpoints.length;
      this.view = i;
      var v = L.viewpoints[i], o = this.el.object3D;
      // A three.js camera looks down its local -Z, so an object yawed by t faces
      // (-sin t, -cos t). To face (dx, dz): t = atan2(-dx, -dz).
      var dx = v.aim[0] - v.pos[0], dz = v.aim[2] - v.pos[2];
      this.rotateRig(Math.atan2(-dx, -dz));
      o.position.set(v.pos[0], v.pos[1] - EYE, v.pos[2]);
      // Hold height for shots that are not at standing eye level -- the camera a
      // hand-span above the road, the balcony, the one up among the wires.
      this.mode = (v.pos[1] < 1.15 || v.pos[1] > 2.6) ? 'fly' : 'walk';
      this.vel.set(0, 0, 0); this.yawRate = 0;
      var g = this.groundAt(v.pos[0], v.pos[2], v.pos[1] + 10);
      this.groundY = g !== null ? g : 0;
      say(v.label + ' - ' + v.lens + ' mm. ' + v.note);
      hud.style.opacity = '1';
    },

    setShadows: function (on) {
      var r = this.el.sceneEl.renderer;
      if (!r) { return; }
      r.shadowMap.enabled = (on === null) ? !r.shadowMap.enabled : on;
      r.shadowMap.needsUpdate = true;
    },
    toggleShadows: function () {
      this.setShadows(null);
      this.flash('SHADOWS ' +
        (this.el.sceneEl.renderer.shadowMap.enabled ? 'ON' : 'OFF'));
    },

    // The mode banner, on the headset as well as the screen.
    flash: function (msg) {
      var t = document.getElementById('modetxt');
      if (t) {
        t.setAttribute('value', msg);
        t.setAttribute('visible', true);
        clearTimeout(this._mt);
        this._mt = setTimeout(function () { t.setAttribute('visible', false); }, 2200);
      }
      say(msg);
      hud.style.opacity = '1';
    },

    tick: function (time, dtMs) {
      if (!dtMs) { return; }
      var dt = Math.min(dtMs, 50) / 1000, rig = this.el.object3D;
      var head = this._h, vel = this.vel;
      var trig = Math.max(this.trig, this.keyTrig);
      var sx = dead(this.sx + this.kx), sy = dead(this.sy + this.ky);
      var fly = this.mode === 'fly';
      var aim = this.getAim();

      // turn with the stick (and, flying with the trigger held, by pointing the
      // wrist left or right)
      var yawT = -sx * STICK_YAW;
      if (fly && trig > 0.15 && this.el.sceneEl.is('vr-mode')) {
        var off = Math.atan2(-aim.x, -aim.z) - rig.rotation.y;
        off = Math.atan2(Math.sin(off), Math.cos(off));
        var ex = Math.abs(off) - AIM_DEAD;
        if (ex > 0) { yawT += Math.sign(off) * Math.min(ex * AIM_GAIN, AIM_MAX); }
      }
      this.yawRate += (yawT - this.yawRate) * (1 - Math.exp(-9 * dt));
      if (Math.abs(this.yawRate) > 1e-3) {
        this.rotateRig(rig.rotation.y + this.yawRate * dt);
      }

      if (fly) {
        var c = clamp(trig - sy, -1, 1), ls = dead(this.ls + this.kls);
        var hh = this._u.set(aim.x, 0, aim.z);
        if (hh.lengthSq() < 1e-4) {
          this.cam.object3D.getWorldQuaternion(this._q);
          hh.set(0, 0, -1).applyQuaternion(this._q); hh.y = 0;
        }
        hh.normalize();
        var sp = c >= 0 ? FLY_SPEED * c * c * (3 - 2 * c) : FLY_BACK * c;
        var tg = this._t.copy(hh).multiplyScalar(sp);
        tg.y = clamp((c > 0 ? clamp(aim.y, -1, 1) * sp * FLY_PITCH : 0) - ls * CLIMB_SPEED,
                     -CLIMB_SPEED, CLIMB_SPEED);
        var braking = Math.abs(c) < 0.05 && Math.abs(ls) < 0.05;
        var k = braking ? FLY_BRAKE : (c < -0.05 ? FLY_REV : FLY_ACCEL);
        var ke = 1 - Math.exp(-k * dt), kv = 1 - Math.exp(-Math.max(k, 2.5) * dt);
        vel.x += (tg.x - vel.x) * ke; vel.z += (tg.z - vel.z) * ke;
        vel.y += (tg.y - vel.y) * kv;
        if (braking && vel.lengthSq() < 0.0004) { vel.set(0, 0, 0); }
        this.stepFly(dt);
        this.moveTrams(dt);
        return;
      }

      // walk: stick forward/back walks; the trigger alone also walks; the
      // trigger on top adds speed
      var stick = Math.abs(sy) > 0.02;
      var fwd = clamp(stick ? -sy : trig, -1, 1);
      var h = this._u.set(aim.x, 0, aim.z);
      if (h.lengthSq() < 1e-4) {
        this.cam.object3D.getWorldQuaternion(this._q);
        h.set(0, 0, -1).applyQuaternion(this._q); h.y = 0;
      }
      h.normalize();
      var boost = fwd > 0 ? 1 + WALK_BOOST * trig : 1;
      var speed = fwd >= 0 ? WALK_SPEED * fwd * boost : WALK_BACK * fwd;
      var tgt = this._t.copy(h).multiplyScalar(speed);
      var acc = Math.abs(fwd) < 0.02 ? WALK_BRAKE
              : (trig > 0.05 && fwd > 0 ? WALK_RAMP : WALK_ACCEL);
      vel.lerp(tgt, 1 - Math.exp(-acc * dt));
      if (Math.abs(fwd) < 0.02 && vel.lengthSq() < 0.0004) { vel.set(0, 0, 0); }

      this.stepWalk(dt);
      this.moveTrams(dt);
    },

    stepWalk: function (dt) {
      var rig = this.el.object3D, head = this._h;
      this.cam.object3D.getWorldPosition(head);
      var gy = this.groundAt(head.x, head.z, rig.position.y + MAX_STEP_UP + 0.1);
      if (gy !== null) { this.groundY = gy; }
      var base = Math.max(rig.position.y, this.groundY);
      if (this.vel.lengthSq() > 0) {
        var sx = this.vel.x * dt, sz = this.vel.z * dt;
        // slide along whatever you walked into, rather than stopping dead
        var mv = this.passable(head, base, sx * 2, sz * 2) ? 3
               : (Math.abs(sx) > 1e-5 && this.passable(head, base, sx * 2, 0)) ? 1
               : (Math.abs(sz) > 1e-5 && this.passable(head, base, 0, sz * 2)) ? 2 : 0;
        if (mv & 1) { rig.position.x += sx; }
        if (mv & 2) { rig.position.z += sz; }
      }
      // follow the floor, capping how fast you drop or climb
      var st = (this.groundY - rig.position.y) * (1 - Math.exp(-12 * dt));
      rig.position.y += Math.max(-6 * dt, Math.min(3 * dt, st));
    },

    stepFly: function (dt) {
      var rig = this.el.object3D, head = this._h, vel = this.vel;
      this.cam.object3D.getWorldPosition(head);
      // soft wall: speed fades out over the last BSOFT metres towards each edge
      var lim = [[head.x, this.flyBx[0], this.flyBx[1], 'x'],
                 [head.z, this.flyBz[0], this.flyBz[1], 'z'],
                 [head.y, 0.3, this.byTop, 'y']];
      for (var i = 0; i < 3; i++) {
        var p = lim[i][0], lo = lim[i][1], hi = lim[i][2], ax = lim[i][3];
        var v = vel[ax];
        var d = v > 0 ? hi - p : v < 0 ? p - lo : 99;
        if (d < BSOFT) { vel[ax] *= Math.exp(-(1 - Math.max(d, 0) / BSOFT) * 8 * dt); }
      }
      // footprints stop you in the air too, up to the height of the thing
      var nx = head.x + vel.x * dt, nz = head.z + vel.z * dt;
      if (this.blockedAt(nx, nz, head.y)) {
        if (!this.blockedAt(nx, head.z, head.y)) { vel.z = 0; }
        else if (!this.blockedAt(head.x, nz, head.y)) { vel.x = 0; }
        else { vel.x = vel.z = 0; }
      }
      rig.position.addScaledVector(vel, dt);
      // keep above whatever is below
      this.cam.object3D.getWorldPosition(head);
      var g = this.groundAt(head.x, head.z, head.y + 0.05);
      var minY = (g !== null ? g : 0) + FLY_MIN_ALT;
      if (head.y < minY) { rig.position.y += minY - head.y; if (vel.y < 0) { vel.y = 0; } }
      // and inside the street
      this.cam.object3D.getWorldPosition(head);
      rig.position.x += clamp(head.x, this.flyBx[0], this.flyBx[1]) - head.x;
      rig.position.z += clamp(head.z, this.flyBz[0], this.flyBz[1]) - head.z;
      if (head.y > this.byTop) {
        rig.position.y -= head.y - this.byTop;
        if (vel.y > 0) { vel.y = 0; }
      }
    },

    blockedAt: function (x, z, y) {
      var b = this.flyBlockers || [];
      for (var i = 0; i < b.length; i++) {
        var o = b[i];
        if (o.top < y) { continue; }
        var dx = x - o.x, dz = z - o.z;
        if (dx * dx + dz * dz > 400) { continue; }
        var lx = dx * o.c - dz * o.s, lz = dx * o.s + dz * o.c;
        if (Math.abs(lx) < o.hx + FLY_RADIUS && Math.abs(lz) < o.hz + FLY_RADIUS) {
          return true;
        }
      }
      return false;
    },

    moveTrams: function (dt) {
      if (!this.tramsRun) { return; }
      var trams = this.el.sceneEl.trams, L = this.el.sceneEl.layout;
      if (!trams || !L) { return; }
      var x0 = L.street.x0, x1 = L.street.x1;
      for (var i = 0; i < trams.length; i++) {
        var t = trams[i];
        t.obj.position.x += t.dir * 4.0 * dt;     // about 14 km/h
        if (t.obj.position.x > x1) { t.obj.position.x = x0; }
        if (t.obj.position.x < x0) { t.obj.position.x = x1; }
      }
    }
  });

})();
