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
      var walk = [], batches = 0;
      var allBatches = self.el.sceneEl.batches = {};

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
          document.getElementById('world').object3D.add(root);
          root.traverse(function (o) {
            if (o.isMesh && /^WALK_/.test(o.name)) { walk.push(o); }
          });
          self.el.sceneEl.walkables = walk;
          return;
        }
        var list = byAsset[name] || [];
        // Chunk along the street, but only where it buys anything. A batch that
        // spans the whole 250 m can never be frustum-culled, so every triangle
        // in it is submitted every frame; a batch of two is a draw call that
        // may as well have stayed a clone.
        var split = list.length > 14;
        var chunks = {};
        list.forEach(function (inst) {
          var c = split ? Math.floor(inst.pos[0] / CHUNK_M) : 0;
          (chunks[c] = chunks[c] || []).push(inst);
        });
        Object.keys(chunks).forEach(function (c) {
          var b = instanceBatch(root, chunks[c], city);
          if (!b) { return; }
          batches += b.meshes.length;
          (allBatches[name] = allBatches[name] || []).push(b);
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
        var proxies = buildProxies(L, foot);
        // The module caches a world box per collision mesh, so it has to be told
        // the world changed. Everything above was added after it loaded.
        var xrl = self.el.sceneEl.components['xr-locomotion'];
        if (xrl) { xrl.collect(); }
        self.el.sceneEl.setAttribute('quest-input', '');
        self.el.sceneEl.setAttribute('daynight', '');
        document.getElementById('views').hidden = false;
        document.getElementById('keys').hidden = false;
        buildViewMenu(L.viewpoints);
        buildPanel();
        hostChrome();
        pageKeys();
        diagnostics();
        goToView(0);
        var M = loco();
        say('Kolkata street - ' + L.instances.length + ' placements, ' +
            batches + ' batches, ' + proxies + ' collision proxies.' +
            (M ? '' : '\nxr-locomotion did not attach: movement will not work.'));
        setTimeout(function () {
          hud.style.transition = 'opacity 1.2s';
          hud.style.opacity = '0';
        }, 9000);
        self.el.sceneEl.emit('city-ready');
      });
    }
  });

  // One InstancedMesh per (geometry, material) in the source model, carrying
  // every placement in this chunk. Forty-five buildings stop being five hundred
  // draw calls and become about a dozen.
  function instanceBatch(src, placements, parent) {
    if (!src) { return null; }
    src.updateMatrixWorld(true);
    var parts = [];
    src.traverse(function (o) {
      if (o.isMesh && !Array.isArray(o.material)) {
        parts.push({ g: o.geometry, m: o.material, local: o.matrixWorld.clone(),
                     cast: o.castShadow, recv: o.receiveShadow });
      }
    });
    var batch = { parts: parts, meshes: [], list: placements };
    parts.forEach(function (p) {
      var im = new THREE.InstancedMesh(p.g, p.m, placements.length);
      im.castShadow = p.cast;
      im.receiveShadow = p.recv;
      parent.add(im);
      batch.meshes.push(im);
    });
    applyBatch(batch);
    return batch;
  }

  // Write every instance matrix from the layout.
  var _m = new THREE.Matrix4(), _q = new THREE.Quaternion();
  var _p = new THREE.Vector3(), _one = new THREE.Vector3(1, 1, 1);
  var _e = new THREE.Euler();
  function applyBatch(batch) {
    for (var k = 0; k < batch.meshes.length; k++) {
      var im = batch.meshes[k], local = batch.parts[k].local;
      for (var i = 0; i < batch.list.length; i++) {
        var inst = batch.list[i];
        var r = THREE.MathUtils.degToRad(inst.rotY);
        _p.set(inst.pos[0], inst.pos[1], inst.pos[2]);
        _e.set(0, r, 0); _q.setFromEuler(_e);
        _m.compose(_p, _q, _one);
        _m.multiply(local);
        im.setMatrixAt(i, _m);
      }
      im.instanceMatrix.needsUpdate = true;
      im.computeBoundingSphere();      // instance-aware, so culling stays correct
    }
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

  // ---------------------------------------------------------------- collision
  //
  // Movement is xr-locomotion.js, unmodified. Its world contract is: every mesh
  // under `world` is collision geometry, WALK_* is standable, everything else
  // blocks. That contract cannot be met by the visible city, because the city is
  // drawn with InstancedMesh -- forty-five buildings share one geometry in a
  // handful of batches, so a per-mesh world box, which is what the module caches
  // to cull its raycasts, does not exist for any single building.
  //
  // So the visible city stays outside #world, and #world gets the ground plus
  // one invisible proxy box per placement, sized from that model's own bounds as
  // it loads. The module then works exactly as written, against 118 cheap boxes.
  function buildProxies(layout, foot, out) {
    var world = document.getElementById('world').object3D;
    var made = 0;
    var mat = new THREE.MeshBasicMaterial({ visible: false });
    (layout.instances || []).forEach(function (inst) {
      var f = foot[inst.asset];
      if (!f) { return; }
      // Footprint at ground level (so you walk under a tree's canopy and are
      // stopped by its trunk), run up to the full height of the thing.
      var w = f.walk, hi = f.fly;
      var h = Math.max(0.4, hi.top - 0.0);
      var g = new THREE.BoxGeometry(w.hx * 2, h, w.hz * 2);
      var m = new THREE.Mesh(g, mat);
      m.name = 'PROXY_' + inst.asset;                 // not WALK_: it blocks
      var r = THREE.MathUtils.degToRad(inst.rotY);
      var c = Math.cos(r), sn = Math.sin(r);
      m.position.set(inst.pos[0] + w.cx * c + w.cz * sn,
                     inst.pos[1] + h / 2,
                     inst.pos[2] - w.cx * sn + w.cz * c);

      m.rotation.y = r;
      m.visible = false;
      world.add(m);
      inst.proxy = m;              // the placement carries its own proxy
      if (out) { (out[inst.asset] = out[inst.asset] || []).push(m); }
      made++;
    });
    return made;
  }

  // ---------------------------------------------------------------- viewpoints
  function loco() {
    var c = document.querySelector('a-scene').components['xr-locomotion'];
    return c && c.loco;
  }

  function goToView(i) {
    var scene = document.querySelector('a-scene');
    var L = scene.layout, M = loco();
    if (!L || !M || !L.viewpoints.length) { return; }
    i = ((i % L.viewpoints.length) + L.viewpoints.length) % L.viewpoints.length;
    scene.viewIndex = i;
    var v = L.viewpoints[i], rig = M.el.object3D;
    // A three.js camera looks down its local -Z, so an object yawed by t faces
    // (-sin t, -cos t). To face (dx, dz): t = atan2(-dx, -dz).
    var dx = v.aim[0] - v.pos[0], dz = v.aim[2] - v.pos[2];
    M.rotateRig(Math.atan2(-dx, -dz));
    rig.position.set(v.pos[0], v.pos[1] - 1.6, v.pos[2]);
    M.vel.set(0, 0, 0); M.yawRate = 0;
    // Hold height for shots that are not at standing eye level -- the camera a
    // hand-span above the road, the balcony, the one up among the wires.
    var wantFly = (v.pos[1] < 1.15 || v.pos[1] > 2.6);
    if ((M.mode === 'fly') !== wantFly) { M.toggleMode(); }
    rig.position.set(v.pos[0], v.pos[1] - 1.6, v.pos[2]);
    M.groundY = rig.position.y;
    say(v.label + ' - ' + v.lens + ' mm. ' + v.note);
    hud.style.opacity = '1';
  }

  function buildViewMenu(views) {
    var box = document.getElementById('views');
    views.forEach(function (v, i) {
      var b = document.createElement('button');
      b.innerHTML = '<b>' + ((i + 1) % 10) + '</b> &nbsp;' + v.label +
                    ' <span>' + v.lens + 'mm</span>';
      b.title = v.note;
      b.addEventListener('click', function () { goToView(i); });
      box.appendChild(b);
    });
  }

  // The host page may wrap this one. `data-back` on the scene turns on a link
  // back to wherever it is embedded; the stepper is the viewpoint list for a
  // phone, where that list is hidden. Both live here rather than in the host's
  // copy of the file, so a redeploy cannot drop them.
  function hostChrome() {
    var scene = document.querySelector('a-scene');
    var href = scene.dataset.back ||
               new URLSearchParams(location.search).get('back');
    if (href) {
      var a = document.getElementById('back');
      a.href = href;
      a.hidden = false;
      document.body.classList.add('has-back');
    }
    document.getElementById('stepper').hidden = false;
    document.getElementById('prev').addEventListener('click', function () {
      goToView((document.querySelector('a-scene').viewIndex || 0) - 1);
    });
    document.getElementById('next').addEventListener('click', function () {
      goToView((document.querySelector('a-scene').viewIndex || 0) + 1);
    });
  }

  // (The street is a still set: nothing moves, so there is no traffic component.)

  // ---------------------------------------------------------------- Quest input
  //
  // Why this exists. xr-locomotion binds `oculus-touch-controls`, which maps the
  // WebXR profiles oculus-touch, -v2 and -v3. A Quest 3 reports its controllers
  // as `meta-quest-touch-plus`, which that component does not match -- so it
  // never binds, no events are emitted, and every control is dead while the
  // scene itself renders perfectly. That is exactly the "launches fine, nothing
  // works" symptom.
  //
  // Rather than fork the module, this reads the raw WebXR gamepads every frame
  // and writes the same fields the module's own handlers would. Analog values
  // are plain assignment, so if the A-Frame component DOES bind on some other
  // headset the two agree. Buttons are edge-detected here and suppressed the
  // moment a native A-Frame button event is seen, so nothing fires twice.
  //
  // xr-standard gamepad mapping: buttons 0 trigger, 1 squeeze, 3 stick press,
  // 4 A/X, 5 B/Y; axes 2,3 are the stick (0,1 on older runtimes).
  AFRAME.registerComponent('quest-input', {
    init: function () {
      var self = this;
      this.native = false;
      this.prev = { left: [], right: [] };
      ['abuttondown', 'bbuttondown', 'xbuttondown', 'ybuttondown'].forEach(function (ev) {
        self.el.addEventListener(ev, function () { self.native = true; }, true);
      });
      this.el.addEventListener('enter-vr', function () {
        setTimeout(function () { self.report(); }, 600);
      });
    },

    report: function () {
      var ss = this.session();
      if (!ss) { return; }
      var names = [];
      for (var i = 0; i < ss.inputSources.length; i++) {
        names.push(ss.inputSources[i].handedness + ':' +
                   (ss.inputSources[i].profiles || []).slice(0, 2).join('/'));
      }
      say('VR controllers: ' + (names.join('  ') || 'none reported') +
          (this.native ? '\n(A-Frame controller events are live)'
                       : '\n(reading the gamepads directly)'));
      hud.style.opacity = '1';
    },

    session: function () {
      var xr = this.el.renderer && this.el.renderer.xr;
      return (xr && xr.getSession && xr.getSession()) || null;
    },

    tick: function () {
      var ss = this.session();
      if (!ss || !ss.inputSources) { return; }
      var M = loco();
      if (!M) { return; }
      for (var i = 0; i < ss.inputSources.length; i++) {
        var src = ss.inputSources[i], gp = src.gamepad;
        if (!gp || !gp.buttons) { continue; }
        var right = src.handedness === 'right';
        var b = gp.buttons, ax = gp.axes || [];
        var sx = ax.length > 2 ? ax[2] : (ax[0] || 0);
        var sy = ax.length > 3 ? ax[3] : (ax[1] || 0);
        var trig = b[0] ? b[0].value : 0;
        var grip = b[1] ? b[1].value : 0;

        if (right) { M.trig = trig; M.sx = sx; M.sy = sy; M.gDn = grip; }
        else { M.ltrig = trig; M.ls = sy; M.gUp = grip; }

        // button edges
        var prev = this.prev[src.handedness] || [];
        for (var k = 0; k < b.length; k++) {
          var now = b[k].pressed, was = !!prev[k];
          if (now && !was) { this.pressed(right, k, M); }
          prev[k] = now;
        }
        this.prev[src.handedness] = prev;
      }
    },

    pressed: function (right, k, M) {
      // The stick click is not used by the module, so it is free for the two
      // scene settings -- the only way to reach them without a keyboard.
      if (k === 3) {
        var scene = this.el.components;
        if (right && scene.daynight) { scene.daynight.toggle(); }
        if (!right && scene.daynight) { scene.daynight.toggleWet(); }
        return;
      }
      if (this.native) { return; }          // A-Frame is already delivering these
      if (right && k === 4) { M.toggleMode(); }
      else if (right && k === 5) { M.openDialog(); }
      else if (!right && k === 4) { goToView((document.querySelector('a-scene').viewIndex || 0) + 1); }
      else if (!right && k === 5) { M.openDialog(); }
    }
  });

  // ---------------------------------------------------------------- day / night
  //
  // The reflections in the road are the point of the whole scene, so the
  // environment map is BAKED FROM THE CITY rather than being the flat gradient
  // the page starts with: one cube render from the middle of the street, run
  // through PMREM. After that the wet road and the chrome reflect actual
  // buildings and cars, which a gradient cannot do, and it costs nothing per
  // frame. It is re-baked when the light changes.
  var LOOK = {
    day: {
      sky: '#d7dde4', fog: '#ccd3dc', fogNear: 26, fogFar: 235,
      hemi: { color: '#d8e1ec', ground: '#4c463c', intensity: 2.2 },
      sun: { color: '#fff4e4', intensity: 2.1, pos: '73 56 -39' },
      env: [[0xd9, 0xe0, 0xe8], [0xc6, 0xcb, 0xd1], [0x3b, 0x37, 0x31]],
      lamp: 0.12, shop: 0.25, window: 0.0, envI: 1.0
    },
    night: {
      sky: '#0a0e15', fog: '#0c1019', fogNear: 10, fogFar: 150,
      hemi: { color: '#36425c', ground: '#2a2015', intensity: 1.05 },
      sun: { color: '#93a9cf', intensity: 0.35, pos: '-60 70 44' },
      env: [[0x16, 0x1d, 0x2b], [0x22, 0x24, 0x2e], [0x0c, 0x0c, 0x0e]],
      lamp: 1.0, shop: 1.2, window: 1.0, envI: 0.8
    }
  };
  // Materials whose emission is a light rather than a surface.
  var LAMP_RE = /lamp|taillight|dest|neon|taxi_sign/i;
  var SHOP_RE = /shopglow/i;
  var WINDOW_RE = /city_glass/i;
  // The tram's passengers' windows are one dark material that glows warm at night,
  // as a lit saloon does. Its lamps (headlamp, route cards, markers) are named
  // tram_lamp_* and so are already caught by LAMP_RE.
  var TRAMWIN_RE = /tram_window_smoked/i;   // not the rubber seals, which are tram_windows_*
  var ROAD_RE = /^WALK_road|^SOLID_track/;

  AFRAME.registerComponent('daynight', {
    schema: { mode: { default: 'day' }, wet: { default: true } },

    init: function () {
      this.mats = null;
      this.el.addEventListener('city-ready', this.apply.bind(this));
    },

    collectMats: function () {
      var lamps = [], shops = [], windows = [], roads = [], tramWin = [], seen = {};
      this.el.object3D.traverse(function (o) {
        if (!o.isMesh) { return; }
        var isRoad = ROAD_RE.test(o.name || '');
        var ms = Array.isArray(o.material) ? o.material : [o.material];
        ms.forEach(function (m) {
          if (!m || seen[m.uuid]) { return; }
          seen[m.uuid] = 1;
          if (isRoad) { roads.push(m); m.userData.dryRough = 0.62; return; }
          var n = m.name || '';
          // m.emissive is a Color and m.emissiveIntensity defaults to 1, so both
          // are truthy on every standard material. Only a non-black emissive
          // means the material is actually a light.
          var lit = !!(m.emissive && m.emissive.getHex() !== 0);
          if (lit && m.userData.baseEI === undefined) {
            m.userData.baseEI = m.emissiveIntensity;
          }
          if (lit && SHOP_RE.test(n)) { shops.push(m); }
          else if (lit && LAMP_RE.test(n)) { lamps.push(m); }
          else if (WINDOW_RE.test(n)) { windows.push(m); }
          else if (TRAMWIN_RE.test(n)) { tramWin.push(m); }
        });
      });
      this.mats = { lamps: lamps, shops: shops, windows: windows, roads: roads,
                    tramWin: tramWin };
    },

    toggle: function () {
      this.el.setAttribute('daynight', 'mode',
                           this.data.mode === 'day' ? 'night' : 'day');
      say(this.data.mode === 'night' ? 'Night' : 'Day');
      hud.style.opacity = '1';
      syncPanel();
    },
    toggleWet: function () {
      this.el.setAttribute('daynight', 'wet', !this.data.wet);
      say(this.data.wet ? 'Wet road' : 'Dry road');
      hud.style.opacity = '1';
      syncPanel();
    },

    update: function () { this.apply(); },

    apply: function () {
      var L = LOOK[this.data.mode] || LOOK.day;
      var wet = this.data.wet;
      if (!this.mats) { this.collectMats(); }
      var m = this.mats;
      if (!m) { return; }

      this.el.setAttribute('background', 'color', L.sky);
      this.el.setAttribute('fog', { type: 'linear', color: L.fog,
                                    near: L.fogNear, far: L.fogFar });
      var hemi = this.el.querySelector('[light*="hemisphere"]');
      if (hemi) {
        hemi.setAttribute('light', { type: 'hemisphere', color: L.hemi.color,
                                     groundColor: L.hemi.ground,
                                     intensity: L.hemi.intensity });
      }
      var sun = document.getElementById('sun');
      if (sun) {
        var cfg = sun.getAttribute('light');
        cfg.color = L.sun.color;
        cfg.intensity = L.sun.intensity;
        sun.setAttribute('light', cfg);
        sun.setAttribute('position', L.sun.pos);
      }

      m.lamps.forEach(function (x) { x.emissiveIntensity = x.userData.baseEI * L.lamp; });
      m.shops.forEach(function (x) { x.emissiveIntensity = x.userData.baseEI * L.shop; });
      // Lights inside the homes: each building GLB carries its own copy of the
      // window material, so varying them by a hash of the uuid lights the
      // terrace unevenly instead of switching every window on at once.
      m.windows.forEach(function (x, i) {
        var lit = L.window * (0.5 + 0.5 * (((i * 2654435761) % 97) / 97));
        x.emissive = x.emissive || new THREE.Color();
        x.emissive.setHex(0xffcf8a);
        x.emissiveIntensity = lit * 6.0;
      });
      m.tramWin.forEach(function (x) {
        x.emissive.setHex(0xffd08a);
        x.emissiveIntensity = L.window * 1.6;
      });
      m.roads.forEach(function (x) {
        x.roughness = wet ? 0.07 : x.userData.dryRough;
        x.envMapIntensity = (wet ? 2.6 : 0.6) * L.envI;
        x.color.setRGB(wet ? 0.030 : 0.055, wet ? 0.032 : 0.056,
                       wet ? 0.035 : 0.058);
      });

      this.bake(L);
    },

    // One cube render of the street, prefiltered. This is what puts real
    // buildings in the reflections instead of a vertical gradient.
    bake: function (L) {
      var renderer = this.el.renderer;
      if (!renderer || this._baking) { return; }
      this._baking = true;
      var scene = this.el.object3D, self = this;
      setTimeout(function () {
        try {
          var rt = new THREE.WebGLCubeRenderTarget(256, { type: THREE.HalfFloatType });
          var cam = new THREE.CubeCamera(0.5, 420, rt);
          cam.position.set(0, 3.2, 0);
          scene.add(cam);
          cam.update(renderer, scene);
          scene.remove(cam);
          var pm = new THREE.PMREMGenerator(renderer);
          var env = pm.fromCubemap(rt.texture).texture;
          pm.dispose(); rt.dispose();
          if (scene.environment && scene.environment.dispose) {
            scene.environment.dispose();
          }
          scene.environment = env;
        } catch (e) {
          say('Could not bake the reflections: ' + e.message);
        }
        self._baking = false;
      }, 60);
    }
  });

  // ---------------------------------------------------------------- diagnostics
  //
  // The Quest browser has no console. When a behaviour does not work on the
  // headset there is otherwise no way to tell a dead event from a dead handler,
  // so this shows the live controller state and the last error. I, or ?diag=1.
  function diagnostics() {
    var el = document.getElementById('diag');
    var on = /[?&]diag=1/.test(location.search);
    var lastErr = '';
    window.addEventListener('error', function (e) {
      lastErr = (e.message || 'error') + ' @' +
                String(e.filename || '').split('/').pop() + ':' + e.lineno;
    });
    window.addEventListener('keydown', function (e) {
      if (e.code === 'KeyI') { on = !on; el.hidden = !on; }
    });
    el.hidden = !on;
    // Report what the module sees AND what the raw WebXR gamepads say, because
    // a stick that moves in the gamepad but not in the module means the
    // controller component is not emitting, which is a different bug entirely.
    setInterval(function () {
      if (el.hidden) { return; }
      var M = loco(), scene = document.querySelector('a-scene');
      var out = [];
      out.push('vr      ' + (scene.is('vr-mode') ? 'yes' : 'no'));
      if (!M) {
        out.push('loco    NOT ATTACHED');
      } else {
        out.push('mode    ' + M.mode + (M.paused ? '  (paused)' : ''));
        out.push('trigger R ' + (+M.trig).toFixed(2) + '   L ' + (+M.ltrig).toFixed(2));
        out.push('stick R ' + (+M.sx).toFixed(2) + ' ' + (+M.sy).toFixed(2) +
                 '   L ' + (+M.ls).toFixed(2));
        out.push('floors  ' + M.floors.length + '   solid ' + M.solid.length);
        var p = M.el.object3D.position;
        out.push('rig     ' + p.x.toFixed(1) + ' ' + p.y.toFixed(1) + ' ' + p.z.toFixed(1));
      }
      var xr = scene.renderer && scene.renderer.xr;
      var ss = xr && xr.getSession && xr.getSession();
      var srcs = (ss && ss.inputSources) || [];
      out.push('sources ' + srcs.length);
      for (var i = 0; i < srcs.length; i++) {
        var gp = srcs[i].gamepad;
        if (!gp) { out.push('  ' + srcs[i].handedness + '  no gamepad'); continue; }
        var ax = [].slice.call(gp.axes).map(function (a) { return a.toFixed(1); });
        var bt = [].slice.call(gp.buttons).map(function (b) {
          return b.pressed ? '1' : (b.value > 0.05 ? 'v' : '0'); }).join('');
        out.push('  ' + srcs[i].handedness.padEnd(5) + ' ax ' + ax.join(',') );
        out.push('        bt ' + bt);
      }
      if (lastErr) { out.push('ERROR   ' + lastErr); }
      el.textContent = out.join('\n');
    }, 200);
  }

  // ---------------------------------------------------------------- controls
  var TOGGLES = [
    { id: 'tg-night', label: 'Night',
      get: function (s) { return s.getAttribute('daynight').mode === 'night'; },
      set: function (s) { s.components.daynight.toggle(); },
      vr: 'right stick click' },
    { id: 'tg-wet', label: 'Wet road',
      get: function (s) { return s.getAttribute('daynight').wet; },
      set: function (s) { s.components.daynight.toggleWet(); },
      vr: 'left stick click' },
    { id: 'tg-shadows', label: 'Shadows',
      get: function (s) { return !!(s.renderer && s.renderer.shadowMap.enabled); },
      set: function (s) {
        var r = s.renderer;
        if (r) { r.shadowMap.enabled = !r.shadowMap.enabled; r.shadowMap.needsUpdate = true; }
      }, vr: 'L' }
  ];

  function syncPanel() {
    var scene = document.querySelector('a-scene');
    TOGGLES.forEach(function (t) {
      var el = document.getElementById(t.id);
      if (!el) { return; }
      var on = !!t.get(scene);
      el.setAttribute('aria-pressed', on ? 'true' : 'false');
      el.querySelector('.sw').textContent = on ? 'on' : 'off';
    });
  }

  function buildPanel() {
    // xr-locomotion adds its own Reset button at top right with inline styles,
    // which is exactly where the settings panel sits. Move it rather than
    // forking the module.
    var reset = document.querySelector('body > button');
    if (reset && /reset/i.test(reset.textContent || '')) {
      reset.style.top = 'auto';
      reset.style.bottom = '112px';
    }
    var box = document.getElementById('settings');
    var scene = document.querySelector('a-scene');
    TOGGLES.forEach(function (t) {
      var b = document.createElement('button');
      b.type = 'button';
      b.id = t.id;
      b.title = 'In VR: ' + t.vr;
      b.innerHTML = t.label + '<span class="sw">off</span>';
      b.addEventListener('click', function () { t.set(scene); syncPanel(); });
      box.appendChild(b);
    });
    box.hidden = false;
    syncPanel();
  }

  // ---------------------------------------------------------------- page keys
  function pageKeys() {
    window.addEventListener('keydown', function (e) {
      var scene = document.querySelector('a-scene');
      if (e.code === 'KeyV') { goToView((scene.viewIndex || 0) + 1); }
      else if (e.code === 'KeyL') {
        var r = scene.renderer;
        if (r) { r.shadowMap.enabled = !r.shadowMap.enabled; r.shadowMap.needsUpdate = true; }
        syncPanel();
      }
      else if (e.code === 'KeyN') { scene.components.daynight.toggle(); }
      else if (e.code === 'KeyG') { scene.components.daynight.toggleWet(); }
      var m = /^Digit([0-9])$/.exec(e.code);
      if (m) { goToView((parseInt(m[1], 10) + 9) % 10); }
    });
  }
})();
