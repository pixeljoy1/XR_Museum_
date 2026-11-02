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

      function placeOne(name, root) {
        prepare(root);
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
        document.getElementById('rig').components['street-rig'].goToView(i);
      });
      box.appendChild(b);
    });
  }

  // ---------------------------------------------------------------- locomotion
  AFRAME.registerComponent('street-rig', {
    schema: {
      walkSpeed: { default: 2.4 },
      runSpeed: { default: 6.5 },
      flySpeed: { default: 9.0 },
      eye: { default: 1.62 },
      snap: { default: 30 }
    },

    init: function () {
      this.keys = {};
      this.fly = false;
      this.view = -1;
      this.stick = { x: 0, y: 0 };
      this.turnStick = 0;
      this.turnReady = true;
      this.run = false;
      this.tramsRun = false;   // T sets them running
      this.down = new THREE.Raycaster();
      this.down.far = 60;
      this.tmp = new THREE.Vector3();
      this.start = this.el.object3D.position.clone();
      this.startRotY = this.el.object3D.rotation.y;
      this.head = document.getElementById('head');

      var self = this;
      window.addEventListener('keydown', function (e) {
        self.keys[e.code] = true;
        self.onKey(e);
      });
      window.addEventListener('keyup', function (e) { self.keys[e.code] = false; });
      this.el.sceneEl.addEventListener('city-ready', function () {
        self.goToView(0);
      });
      // In VR the shadow pass is the first thing worth giving up.
      this.el.sceneEl.addEventListener('enter-vr', function () {
        self.setShadows(false);
      });
      this.el.sceneEl.addEventListener('exit-vr', function () {
        self.setShadows(true);
      });
      this.help();
    },

    onKey: function (e) {
      if (e.code === 'KeyF') { this.fly = !this.fly; this.help(); }
      if (e.code === 'KeyR') { this.reset(); }
      if (e.code === 'KeyV') { this.goToView(this.view + 1); }
      if (e.code === 'KeyT') { this.tramsRun = !this.tramsRun; this.help(); }
      if (e.code === 'KeyL') { this.setShadows(null); }
      if (e.code === 'KeyH') {
        var p = document.getElementById('helppanel');
        p.setAttribute('visible', !p.getAttribute('visible'));
      }
      var m = /^Digit([0-9])$/.exec(e.code);
      if (m) { this.goToView((parseInt(m[1], 10) + 9) % 10); }
    },

    setShadows: function (on) {
      var r = this.el.sceneEl.renderer;
      if (!r) { return; }
      r.shadowMap.enabled = (on === null) ? !r.shadowMap.enabled : on;
      r.shadowMap.needsUpdate = true;
      this.help();
    },

    help: function () {
      var t = document.getElementById('helptext');
      if (!t) { return; }
      t.setAttribute('value',
        'KOLKATA STREET\n\n' + (this.fly ? 'FLY' : 'WALK') +
        '   trams ' + (this.tramsRun ? 'running' : 'held') +
        '\n\nleft stick  move\nright stick  turn\ntrigger  run\n' +
        'A  walk / fly\nX  next viewpoint\nB or Y  reset');
    },

    reset: function () {
      this.el.object3D.position.copy(this.start);
      this.el.object3D.rotation.y = this.startRotY;
      this.fly = false;
      this.view = -1;
      this.help();
    },

    goToView: function (i) {
      var L = this.el.sceneEl.layout;
      if (!L || !L.viewpoints.length) { return; }
      i = ((i % L.viewpoints.length) + L.viewpoints.length) % L.viewpoints.length;
      this.view = i;
      var v = L.viewpoints[i];
      var o = this.el.object3D;
      o.position.set(v.pos[0], v.pos[1] - this.data.eye, v.pos[2]);
      // Yaw only: in VR the headset owns pitch, and forcing it is what makes
      // people ill. The viewpoint height and heading are enough to reproduce
      // the shot; look up and the wires are where they were.
      // A three.js camera looks down its local -Z, so an object yawed by t faces
      // (-sin t, -cos t). To face (dx, dz): t = atan2(-dx, -dz). Adding PI here
      // is the classic slip, and it points you back down an empty street.
      var dx = v.aim[0] - v.pos[0], dz = v.aim[2] - v.pos[2];
      o.rotation.y = Math.atan2(-dx, -dz);
      // Hold height for shots that are not at standing eye level -- the camera a
      // hand-span above the road, the balcony, the one up among the wires --
      // otherwise ground-following snaps them all back to 1.62 m.
      this.fly = (v.pos[1] < 1.15 || v.pos[1] > 2.6);
      say(v.label + ' - ' + v.lens + ' mm. ' + v.note);
      hud.style.opacity = '1';
      this.help();
    },

    // --- VR controller events, forwarded by vr-input
    onStick: function (hand, x, y) {
      if (hand === 'left') { this.stick.x = x; this.stick.y = y; }
      else { this.turnStick = x; }
    },
    onButton: function (name) {
      if (name === 'a') { this.fly = !this.fly; this.help(); }
      if (name === 'x') { this.goToView(this.view + 1); }
      if (name === 'b' || name === 'y') { this.reset(); }
      if (name === 'trigger-down') { this.run = true; }
      if (name === 'trigger-up') { this.run = false; }
    },

    tick: function (time, dt) {
      if (!dt) { return; }
      var s = Math.min(dt, 50) / 1000;
      var o = this.el.object3D;
      var k = this.keys;

      // --- snap turn, right stick or arrow keys
      var turn = this.turnStick;
      if (Math.abs(turn) > 0.6 && this.turnReady) {
        o.rotation.y -= Math.sign(turn) * THREE.MathUtils.degToRad(this.data.snap);
        this.turnReady = false;
      } else if (Math.abs(turn) < 0.3) {
        this.turnReady = true;
      }
      if (k.ArrowLeft) { o.rotation.y += 1.6 * s; }
      if (k.ArrowRight) { o.rotation.y -= 1.6 * s; }

      // --- movement, in the direction the head is facing
      var fwd = (k.KeyW ? 1 : 0) - (k.KeyS ? 1 : 0) + this.stick.y * -1;
      var side = (k.KeyD ? 1 : 0) - (k.KeyA ? 1 : 0) + this.stick.x;
      var lift = (k.KeyE ? 1 : 0) - (k.KeyQ ? 1 : 0);
      var running = this.run || k.ShiftLeft || k.ShiftRight;
      var speed = this.fly ? this.data.flySpeed
                           : (running ? this.data.runSpeed : this.data.walkSpeed);

      if (fwd || side) {
        var yaw = o.rotation.y + (this.head.object3D ? this.head.object3D.rotation.y : 0);
        var len = Math.min(1, Math.hypot(fwd, side));
        var dirX = (Math.sin(yaw) * -fwd + Math.cos(yaw) * side);
        var dirZ = (Math.cos(yaw) * -fwd - Math.sin(yaw) * side);
        var n = Math.hypot(dirX, dirZ) || 1;
        o.position.x += (dirX / n) * len * speed * s;
        o.position.z += (dirZ / n) * len * speed * s;
      }
      if (this.fly && lift) { o.position.y += lift * speed * s; }

      // --- stay in the street, and on the ground
      var L = this.el.sceneEl.layout;
      if (L) {
        var st = L.street;
        o.position.x = clamp(o.position.x, st.x0 + 4, st.x1 - 4);
        if (!this.fly) {
          // the corridor between the two building lines
          o.position.z = clamp(o.position.z, -9.0, 9.0);
          o.position.y = this.groundAt(o.position);
        } else {
          o.position.y = clamp(o.position.y, 0.2, 34);
          o.position.z = clamp(o.position.z, -40, 40);
        }
      }

      this.moveTrams(s);
    },

    // Ground following: one ray straight down onto the WALK_ meshes. The road has
    // a camber and the footpath a kerb, so a fixed height would float or sink.
    groundAt: function (p) {
      var walk = this.el.sceneEl.walkables;
      if (!walk || !walk.length) { return p.y; }
      this.tmp.set(p.x, p.y + 6, p.z);
      this.down.set(this.tmp, new THREE.Vector3(0, -1, 0));
      var hits = this.down.intersectObjects(walk, false);
      if (!hits.length) { return p.y; }
      // ease, so stepping on and off the kerb is not a jolt
      return p.y + (hits[0].point.y - p.y) * 0.35;
    },

    moveTrams: function (s) {
      if (!this.tramsRun) { return; }
      var trams = this.el.sceneEl.trams;
      var L = this.el.sceneEl.layout;
      if (!trams || !L) { return; }
      var x0 = L.street.x0, x1 = L.street.x1;
      for (var i = 0; i < trams.length; i++) {
        var t = trams[i];
        t.obj.position.x += t.dir * 4.0 * s;     // ~14 km/h
        if (t.obj.position.x > x1) { t.obj.position.x = x0; }
        if (t.obj.position.x < x0) { t.obj.position.x = x1; }
      }
    }
  });

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  // ---------------------------------------------------------------- VR input
  AFRAME.registerComponent('vr-input', {
    schema: { hand: { default: 'left' } },
    init: function () {
      var hand = this.data.hand;
      var rig = function () {
        return document.getElementById('rig').components['street-rig'];
      };
      var self = this;
      this.el.addEventListener('thumbstickmoved', function (e) {
        rig().onStick(hand, e.detail.x, e.detail.y);
      });
      ['abuttondown', 'bbuttondown', 'xbuttondown', 'ybuttondown'].forEach(function (ev) {
        self.el.addEventListener(ev, function () { rig().onButton(ev[0]); });
      });
      this.el.addEventListener('triggerdown', function () {
        rig().onButton('trigger-down');
      });
      this.el.addEventListener('triggerup', function () {
        rig().onButton('trigger-up');
      });
    }
  });
})();
