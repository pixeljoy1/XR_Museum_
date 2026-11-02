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
          document.getElementById('world').object3D.add(root);
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
        var proxies = buildProxies(L, foot);
        // The module caches a world box per collision mesh, so it has to be told
        // the world changed. Everything above was added after it loaded.
        var xrl = self.el.sceneEl.components['xr-locomotion'];
        if (xrl) { xrl.collect(); }
        self.el.sceneEl.setAttribute('tram-run', '');
        document.getElementById('views').hidden = false;
        document.getElementById('keys').hidden = false;
        buildViewMenu(L.viewpoints);
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
  function buildProxies(layout, foot) {
    var world = document.getElementById('world').object3D;
    var made = 0;
    var mat = new THREE.MeshBasicMaterial({ visible: false });
    (layout.instances || []).forEach(function (inst) {
      var f = foot[inst.asset];
      if (!f || inst.asset === layout.tram_asset) { return; }   // trams move
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

  // ---------------------------------------------------------------- trams
  AFRAME.registerComponent('tram-run', {
    init: function () { this.on = false; },
    tick: function (t, dtMs) {
      if (!this.on || !dtMs) { return; }
      var scene = this.el, trams = scene.trams, L = scene.layout;
      if (!trams || !L) { return; }
      var dt = Math.min(dtMs, 50) / 1000;
      var x0 = L.street.x0, x1 = L.street.x1;
      for (var i = 0; i < trams.length; i++) {
        var tr = trams[i];
        tr.obj.position.x += tr.dir * 4.0 * dt;     // about 14 km/h
        if (tr.obj.position.x > x1) { tr.obj.position.x = x0; }
        if (tr.obj.position.x < x0) { tr.obj.position.x = x1; }
      }
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

  // ---------------------------------------------------------------- page keys
  function pageKeys() {
    window.addEventListener('keydown', function (e) {
      var scene = document.querySelector('a-scene');
      if (e.code === 'KeyV') { goToView((scene.viewIndex || 0) + 1); }
      else if (e.code === 'KeyT') {
        var c = scene.components['tram-run'];
        if (c) { c.on = !c.on; say(c.on ? 'Trams running (T to hold)'
                                        : 'Trams held (T to run)'); }
      }
      else if (e.code === 'KeyL') {
        var r = scene.renderer;
        if (r) { r.shadowMap.enabled = !r.shadowMap.enabled; r.shadowMap.needsUpdate = true; }
      }
      var m = /^Digit([0-9])$/.exec(e.code);
      if (m) { goToView((parseInt(m[1], 10) + 9) % 10); }
    });
  }
})();
