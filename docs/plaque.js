/*
 * plaque: an information board for any A-Frame experience. Reusable, no dependencies beyond A-Frame.
 *
 *   <script src="plaque.js?v=1.04"></script>
 *   <a-entity plaque="title: KERALAM HOUSE XR; name: Aritra Mitra;
 *       detail: BDes, Immersive Digital Environments|O.P. Jindal Global University, Class of 2028;
 *       columns: #WALK|Stick: walk, turn|Trigger: go faster ## #FLY (A)|Trigger: thrust|Stick: climb;
 *       version: 1.04"
 *       position="2.1 0 6.4"></a-entity>
 *
 * stand: true (default) = a freestanding board on two posts with a small roof; position is the spot on the
 *        ground, the board faces +Z (rotate the entity to turn it).
 * stand: false = a flat plate; position is its TOP CENTRE (use it on a wall).
 * columns: sections separated by "##"; rows separated by "|"; a row starting with "#" is a gold heading.
 * Bump `version` on every publish.
 */
AFRAME.registerComponent('plaque', {
  schema: {
    title:   { default: '' },
    name:    { default: '' },
    detail:  { default: '' },          // "|" separated rows under the name
    columns: { default: '' },          // sections split by "##"
    version: { default: '' },
    width:   { default: 1.6 },         // board width, metres
    size:    { default: 0.034 },       // body glyph width, metres (about 1.5x that is the letter height)
    stand:   { default: true },
    top:     { default: 1.95 },        // stand: height of the board's top edge above the ground
    tilt:    { default: 12 },          // degrees the board leans back, easier to read than a vertical wall
    gold:    { default: '#e2b64a' },
    board:   { default: '#2a1a10' },
    ink:     { default: '#f3ead6' },
    wood:    { default: '#6a3d20' }
  },

  init: function () { this.kids = []; },

  update: function () {
    var d = this.data, el = this.el, W = d.width, pad = 0.07, kids = this.kids;
    kids.forEach(function (k) { if (k.parentNode) k.parentNode.removeChild(k); });
    kids.length = 0;

    function add(parent, tag, attrs) {
      var n = document.createElement(tag);
      for (var a in attrs) n.setAttribute(a, attrs[a]);
      parent.appendChild(n); return n;
    }
    var flat = function (c) { return 'shader: flat; color: ' + c; };
    var lit = function (c) { return 'color: ' + c + '; roughness: 1; metalness: 0'; };

    // root of everything we add; the board is a child so it can lean back
    var root = add(el, 'a-entity', {}); kids.push(root);
    var topY = d.stand ? d.top : 0;
    var bd = add(root, 'a-entity', { position: '0 ' + topY + ' 0', rotation: (d.stand ? -d.tilt : 0) + ' 0 0' });

    function text(value, size, color, align, x, y, wrap) {
      add(bd, 'a-text', {
        value: value, color: color, align: align, anchor: align, baseline: 'top',
        width: size * wrap, 'wrap-count': wrap, position: x + ' ' + y + ' 0.016'
      });
    }

    var y = -pad;
    if (d.title) { text(d.title, 0.05, d.gold, 'center', 0, y, 40); y -= 0.085; }
    if (d.name)  { text(d.name, 0.038, d.ink, 'center', 0, y, 40);  y -= 0.07; }
    if (d.detail) {
      d.detail.split('|').forEach(function (r) { text(r, 0.022, '#cdbf9f', 'center', 0, y, 40); y -= 0.042; });
    }
    if (d.columns) {
      y -= 0.02;
      add(bd, 'a-plane', { width: W - pad * 2, height: 0.004, material: flat(d.gold), position: '0 ' + y + ' 0.014' });
      y -= 0.035;
      var secs = d.columns.split('##'), n = secs.length, cw = (W - pad * 2) / n, deepest = 0;
      var maxLen = 8;                                           // longest row decides the glyph size so nothing wraps
      secs.forEach(function (sec) { sec.split('|').forEach(function (r) { maxLen = Math.max(maxLen, r.trim().replace(/^#/, '').length * (r.trim().charAt(0) === '#' ? 1.25 : 1)); }); });
      var wrapN = Math.ceil(maxLen) + 1, S = Math.min(d.size, (cw - 0.03) / (wrapN * 0.72));   // a glyph is about 0.55 of its nominal width
      secs.forEach(function (sec, i) {
        var yy = y, x = -W / 2 + pad + i * cw;
        sec.split('|').forEach(function (r) {
          r = r.trim();
          if (!r) { yy -= S * 0.8; return; }
          var head = r.charAt(0) === '#';
          text(head ? r.slice(1) : r, head ? S * 1.25 : S, head ? d.gold : d.ink, 'left', x, yy, wrapN);
          yy -= S * (head ? 2.1 : 1.8);
        });
        deepest = Math.min(deepest, yy);
      });
      y = Math.min(deepest, y - 0.05);
    }
    if (d.version) {
      text('v' + d.version, 0.022, d.gold, 'right', W / 2 - pad, y - 0.005, 12);
      y -= 0.05;
    }
    var H = -y + pad * 0.6;

    add(bd, 'a-box', { width: W, height: H, depth: 0.03, material: lit(d.board), position: '0 ' + (-H / 2) + ' 0' });
    add(bd, 'a-box', { width: W + 0.05, height: H + 0.05, depth: 0.016, material: lit(d.gold), position: '0 ' + (-H / 2) + ' -0.008' });

    if (d.stand) {
      // two posts, a stone footing, and a small roof with a brass finial (same language as the house)
      var px = W / 2 + 0.06, ph = d.top + 0.1;
      [-1, 1].forEach(function (s) {
        add(root, 'a-cylinder', { radius: 0.05, height: ph, material: lit(d.wood), position: (s * px) + ' ' + (ph / 2) + ' -0.03' });
        add(root, 'a-box', { width: 0.24, height: 0.14, depth: 0.24, material: lit('#8f7e69'), position: (s * px) + ' 0.07 -0.03' });
      });
      add(root, 'a-box', { width: W + 0.5, height: 0.07, depth: 0.5, material: lit('#a94a2e'), position: '0 ' + (d.top + 0.17) + ' -0.03' });
      add(root, 'a-box', { width: W + 0.4, height: 0.05, depth: 0.4, material: lit(d.wood), position: '0 ' + (d.top + 0.11) + ' -0.03' });
      add(root, 'a-sphere', { radius: 0.05, material: 'color: #d6a321; roughness: 0.6; metalness: 0', position: '0 ' + (d.top + 0.25) + ' -0.03' });
    }
    this.height = H;
  },

  remove: function () {
    this.kids.forEach(function (k) { if (k.parentNode) k.parentNode.removeChild(k); });
    this.kids.length = 0;
  }
});
