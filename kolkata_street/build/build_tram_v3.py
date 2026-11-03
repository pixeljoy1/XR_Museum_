"""Kolkata tram V3.10 (the 1:87 model)  ->  assets/tram_v3.blend

This turns the supplied model into something the street can use. The source is
NOT built here: it is a hand-authored 1:87 display model of 1,087 meshes and
467,000 triangles, in millimetres, with procedural materials, a display plinth,
a full interior and scores of fasteners. None of that survives a trip to a
headset, so this script opens the source, reduces it, and writes a street-scale
asset.

    blender -b -P build/build_tram_v3.py -- --src /path/Kolkata_Tram_V3_10_Rounded_Signature_Heads.blend

What it changes, and what it deliberately does not:

SCALE      1 Blender unit in the source is 1 mm of model, and the model is 1:87,
           so x 0.087 gives metres. Length over the bodies comes out at 15.5 m.
ORIENTATION unchanged. The driver's cab is at -X, the trolley pole at +X, z = 0 is
           the wheel contact, y = 0 the centre line. The street places it so the
           cab faces down the street.
DROPPED    the display plinth; every camera, light and empty; the seats, benches,
           roof locating receivers (nothing a visitor can see once the glazing is
           opaque); and every part smaller than 4.4 cm at full size (panel
           fasteners, rivets) except lamps and lenses.
KEPT       shells, both roofs, fascia, lamps, route boards, the trolley pole and
           rope, entrances (treads, risers, guards), bogies and wheels, the
           cab controller.
LIVERY     The blue/white bands are a procedural node graph, which glTF cannot
           carry. Rather than flatten it to one colour, the geometry is cut along
           the same planes and each face is assigned the flat colour the graph
           would have produced there. Thresholds are read from the source's own
           materials, not retyped from the photo.
           The trap: the graph's Texture Coordinate node is set to measure
           relative to an EMPTY at the world origin scaled 11.494x ("Modern
           livery | prototype coordinate reference"). So the thresholds
           (1.44, 2.64, ...) are in prototype METRES in WORLD space, not in each
           part's own local millimetres. Evaluating the graph on a part's local
           coordinates paints the whole shell navy and the seams light blue. The
           transform is read from that empty, not assumed.
TEXTURES   The supplied roof colour and seam normal map are kept (down-sized 4x:
           6800 x 1280 is 35 MB of GPU memory each), and so is the Route 25 board.
WHEELS     The source's wheelsets are 1.66 m between wheel centres at full size.
           The street's rails are 1,435 mm gauge, so as supplied the wheels would
           roll beside the track. Only the running gear is narrowed, about its
           own centre line, so the wheels land on the rail; the body is untouched.
NIGHT      The source drives its lamps from a custom property (enabled x 7 on the
           headlamp, x 3 on the route cards). Those values are baked in as the
           materials' emission, named so the page's night mode finds them.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klib import mesh as M, sceneutil as S

S.log_to(os.path.join(S.ROOT, 'build', 'build_tram_v3.log'))
SRC = S.argval('--src', os.path.join(S.ASSETS, 'tram_new',
               'Kolkata_Tram_V3_10_Rounded_Signature_Heads.blend'))

MODEL_TO_M = 0.087                 # 1 mm of 1:87 model = 87 mm = 0.087 m
SMALL_MM = 0.5                     # parts smaller than this (4.4 cm real) are dropped
ROOF_TRIS = 7000                   # target per roof, from 69,000
WHEEL_K = 0.8645                   # running gear lateral squeeze, see header
RAIL_HALF_GAUGE = 0.7175           # the street's rails
KEEP_INTERIOR = ('footwell', 'guard', 'riser', 'tread', 'step', 'floor',
                 'partition', 'controller', 'stool', 'doorway')
ALWAYS_KEEP = ('lamp', 'lens', 'route', 'rope', 'glass', 'pole', 'trolley')

# The two procedural livery graphs. Read from the source in read_bands(); these
# are only the defaults the assertion below checks against.
BLUE = (0.022, 0.243, 0.604)
WHITE = (0.787, 0.807, 0.787)
PALE = (0.933, 0.933, 0.933)
NAVY = (0.006, 0.025, 0.133)


WATCH = ('route 25',)


def watch(stage, objs):
    for ob in objs:
        if any(w in ob.name.lower() for w in WATCH) and ob.type == 'MESH':
            from collections import Counter
            c = Counter(p.material_index for p in ob.data.polygons)
            S.log('  watch[%s] %s: %d faces, per slot %s, mats %s' % (
                stage, ob.name, len(ob.data.polygons), dict(c),
                [m.name if m else None for m in ob.data.materials]))


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def coll_names(ob):
    return [c.name for c in ob.users_collection]


# ================================================================= livery
def read_bands():
    """Pull the thresholds out of the source's own node graphs, so this follows
    the model if its author moves a band."""
    out = {}
    m = bpy.data.materials['Modern | side blue-white bands']
    nodes = m.node_tree.nodes
    out['z_split'] = nodes['Math'].inputs[1].default_value          # blue -> white
    out['z_pale0'] = nodes['Math.001'].inputs[1].default_value      # pale pinstripe
    out['z_pale1'] = nodes['Math.002'].inputs[1].default_value
    out['z_navy'] = nodes['Math.004'].inputs[1].default_value       # white -> navy
    v = bpy.data.materials['Modern | front blue-white V'].node_tree.nodes
    out['v_slope'] = v['Math.002'].inputs[1].default_value          # |y| * slope
    out['v_off'] = v['Math.003'].inputs[1].default_value            # + offset
    out['v_half'] = v['Math.006'].inputs[1].default_value           # stripe half width
    return out


def band_colour(kind, p, T):
    z = p.z
    c = WHITE if z > T['z_split'] else BLUE
    if kind == 'bands':
        if T['z_pale0'] < z < T['z_pale1']:
            c = PALE
        if z > T['z_navy']:
            c = NAVY
    else:                                                  # the cab-front V
        if abs(z - (abs(p.y) * T['v_slope'] + T['v_off'])) < T['v_half']:
            c = WHITE
    return c


def bisect_planes(kind, T):
    """Planes (point, normal) in PROTOTYPE space at which the graph's colour can
    change. Only a face that actually straddles one needs cutting."""
    P = [((0, 0, T['z_split']), (0, 0, 1))]
    if kind == 'bands':
        P += [((0, 0, T['z_pale0']), (0, 0, 1)), ((0, 0, T['z_pale1']), (0, 0, 1)),
              ((0, 0, T['z_navy']), (0, 0, 1))]
    else:
        s, o, h = T['v_slope'], T['v_off'], T['v_half']
        for sign in (1, -1):                               # z = o +/- h + s*|y|
            for d in (h, -h):
                # plane z - sign*s*y - (o + d) = 0  ->  normal (0, -sign*s, 1)
                n = Vector((0, -sign * s, 1)).normalized()
                P.append(((0, 0, o + d), tuple(n)))
    return P


def livery_space():
    """The matrix that takes world coordinates into the livery graph's space: the
    inverse of the empty the Texture Coordinate node is pointed at."""
    e = None
    for m in bpy.data.materials:
        if m.use_nodes and m.name.startswith('Modern | '):
            for n in m.node_tree.nodes:
                if n.type == 'TEX_COORD' and n.object:
                    e = n.object
    assert e is not None, 'no livery reference empty found'
    E = e.matrix_world.copy()
    sc = E.to_scale()
    assert abs(sc.x - sc.y) < 1e-6 and abs(sc.y - sc.z) < 1e-6, 'non-uniform livery space'
    assert E.to_euler().z == 0 and E.to_euler().x == 0, 'rotated livery space'
    return E, E.inverted()


def bake_livery(ob, kind, T, E, Einv):
    """Cut `ob` (already in world space) along the band planes, then return
    {polygon index: colour}: each face gets the flat colour the procedural graph
    gives at its centre. The cut is what makes a band edge land on an edge
    instead of through the middle of a triangle."""
    me = ob.data
    src_name = ('Modern | side blue-white bands' if kind == 'bands'
                else 'Modern | front blue-white V')
    src_idx = [i for i, s in enumerate(ob.material_slots)
               if s.material and s.material.name == src_name][0]
    bm = bmesh.new()
    bm.from_mesh(me)
    for co, no in bisect_planes(kind, T):
        wco = E @ Vector(co)                       # uniform scale: normals carry over
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=wco, plane_no=Vector(no))
    bm.to_mesh(me)
    bm.free()
    out = {}
    for poly in me.polygons:
        if poly.material_index == src_idx:
            c = band_colour(kind, Einv @ poly.center, T)
            out[poly.index] = tuple(round(x, 3) for x in c)
    return out


# ================================================================= materials
def flat_material(name, base, rough=0.5, metal=0.0, emit=None, emit_str=0.0,
                  alpha=1.0, store=None):
    if store is not None and name in store:
        return store[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs['Base Color'].default_value = (*base, 1.0)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit is not None:
        b.inputs['Emission Color'].default_value = (*emit, 1.0)
        b.inputs['Emission Strength'].default_value = emit_str
    if alpha < 1.0:
        b.inputs['Alpha'].default_value = alpha
        m.blend_method = 'BLEND'
    if store is not None:
        store[name] = m
    return m


def principled_of(m):
    if not m or not m.use_nodes:
        return None
    return next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def slug(s):
    return ''.join(ch if ch.isalnum() else '_' for ch in s.lower()).strip('_')


def replacement(src, store):
    """The flat material that stands in for `src`. Image-textured materials are
    kept as they are; everything else is rebuilt from its Principled defaults."""
    n = src.name
    base_node = principled_of(src)
    if any(k in n for k in ('supplied roof', 'Route 25')):
        return src                                         # carries real textures
    g = lambda k, d=None: (base_node.inputs[k].default_value if base_node and k in base_node.inputs else d)
    base = tuple(g('Base Color', (0.5, 0.5, 0.5, 1))[:3])
    rough = float(g('Roughness', 0.5))
    metal = float(g('Metallic', 0.0))
    low = n.lower()
    # lamps, with the source's own night values baked in (enabled = 1)
    if 'headlamp' in low and 'optical lens' in low:
        return flat_material('tram_lamp_headlamp', base, rough, metal,
                             (1.0, 0.90, 0.72), 7.0, store=store)
    if 'illuminated ivory card' in low:
        return flat_material('tram_lamp_routecard', base, rough, metal,
                             (1.0, 0.83, 0.55), 3.0, store=store)
    if 'opal lamp lens' in low:
        return flat_material('tram_lamp_marker', base, rough, metal,
                             (1.0, 0.93, 0.78), 2.0, store=store)
    if 'smoked grey' in low:
        return flat_material('tram_window_smoked', base, rough, metal,
                             (1.0, 0.82, 0.55), 0.0, store=store)
    if 'clear lightly reflective glass' in low:
        return flat_material('tram_glass_clear', (0.06, 0.08, 0.09), 0.1, 0.0,
                             alpha=0.5, store=store)
    return flat_material('tram_' + slug(n), base, rough, metal, store=store)


# ================================================================= geometry
def single_user(ob):
    if ob.data.users > 1:
        ob.data = ob.data.copy()


def apply_to_world(ob):
    """Bake the object's world transform into its mesh and detach it, so the
    meshes can be joined and scaled as plain geometry."""
    single_user(ob)
    mw = ob.matrix_world.copy()
    ob.data.transform(mw)
    ob.parent = None
    ob.matrix_world = Matrix.Identity(4)
    ob.data.update()


def evaluated_copy(ob, dg=None):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    ob.data = me


def decimate_to(ob, target):
    """Collapse-decimate to roughly `target` triangles, keeping UVs and sharp
    edges where it can."""
    t = tris(ob)
    if t <= target:
        return
    md = ob.modifiers.new('dec', 'DECIMATE')
    md.decimate_type = 'COLLAPSE'
    md.ratio = max(0.02, target / t)
    md.use_collapse_triangulate = True
    dg = bpy.context.evaluated_depsgraph_get()
    evaluated_copy(ob, dg)


def vsize(ob):
    """Largest dimension of the mesh in its current units, from the vertices. The
    object's own .dimensions comes from a cached bound box that goes stale as
    soon as the mesh is edited."""
    co = [v.co for v in ob.data.vertices]
    if not co:
        return 0.0
    return max(max(c[i] for c in co) - min(c[i] for c in co) for i in range(3))


def dissolve_flat(ob, angle_deg=2.0):
    """Merge coplanar faces, stopping at material and UV boundaries so a livery
    edge or a texture seam is never dissolved away, then triangulate."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(angle_deg),
                             use_dissolve_boundaries=False,
                             verts=bm.verts[:], edges=bm.edges[:],
                             delimit={'MATERIAL', 'UV'})
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()


# How hard to simplify a part, by how big it is at full size (metres). A 6 cm
# spring coil does not need 760 triangles; a 7 m body shell does.
#   (largest dimension below, fraction of triangles kept, floor)
LOD = ((0.08, 0.10, 8), (0.25, 0.16, 12), (0.7, 0.26, 32), (2.5, 0.40, 80))


def simplify(ob):
    t0 = tris(ob)
    if t0 < 24:
        return
    dissolve_flat(ob)
    d = vsize(ob) * MODEL_TO_M
    keep_frac, floor = 1.0, 0
    for limit, frac, fl in LOD:
        if d < limit:
            keep_frac, floor = frac, fl
            break
    t1 = tris(ob)
    target = max(floor, int(t1 * keep_frac))
    if t1 > target:
        decimate_to(ob, target)


def downscale_image(img, factor):
    if not img or not img.size[0]:
        return img
    w, h = max(64, img.size[0] // factor), max(64, img.size[1] // factor)
    cs = img.colorspace_settings.name
    tmp = os.path.join(S.ROOT, 'build', '_tmp_' + slug(img.name) + '.png')
    img.scale(w, h)
    img.filepath_raw = tmp
    img.file_format = 'PNG'
    img.save()
    new = bpy.data.images.load(tmp)
    new.name = img.name
    new.colorspace_settings.name = cs
    new.pack()
    os.remove(tmp)
    return new


# ================================================================= main
def main():
    S.log('source %s  (%.1f MB)' % (SRC, os.path.getsize(SRC) / 1e6))
    bpy.ops.wm.open_mainfile(filepath=SRC)
    objs = list(bpy.data.objects)
    S.log('opened: %d objects, %d meshes' % (len(objs), sum(o.type == 'MESH' for o in objs)))
    T = read_bands()
    S.log('livery thresholds: %s' % {k: round(v, 3) for k, v in T.items()})
    assert abs(T['z_split'] - 1.44) < 1e-6, 'livery graph is not the one this was written against'

    # ---------------------------------------------- 1. decide what stays
    keep, dropped = [], {}

    def drop(why, ob):
        dropped.setdefault(why, []).append(ob.name)

    for ob in objs:
        if ob.type != 'MESH':
            drop('not a mesh (empty, camera, light)', ob); continue
        if ob.hide_render:
            drop('hidden in render', ob); continue
        cn = ' '.join(coll_names(ob)).lower()
        low = ob.name.lower()
        if 'display base' in cn or 'plinth' in low:
            drop('display plinth', ob); continue
        if 'interior and floor' in cn and not any(k in low for k in KEEP_INTERIOR):
            drop('interior seating and fittings', ob); continue
        if any(k in low for k in ('fastener', 'rivet', 'screw')):
            drop('fasteners', ob); continue
        if 'tread' in low and ' rib' in low:
            drop('stair tread grooves (2 cm detail)', ob); continue
        if max(ob.dimensions) < SMALL_MM and not any(k in low for k in ALWAYS_KEEP):
            drop('too small to see', ob); continue
        keep.append(ob)
    for why, names in sorted(dropped.items()):
        S.log('  dropped %-38s %4d' % (why, len(names)))
    S.log('keeping %d meshes' % len(keep))
    watch('kept', keep)

    # ---------------------------------------------- 2. modifiers -> real mesh
    for ob in keep:
        if ob.modifiers:
            single_user(ob)
            evaluated_copy(ob)
    S.log('modifiers applied: %d tris' % sum(tris(o) for o in keep))

    # ---------------------------------------------- 5. world space, squeeze
    for ob in keep:
        apply_to_world(ob)
    running = [o for o in keep if any(c.startswith(('07', '08')) for c in coll_names(o))]
    for ob in running:
        for v in ob.data.vertices:
            v.co.y *= WHEEL_K
        ob.data.update()
    S.log('running gear: %d parts narrowed x%.4f' % (len(running), WHEEL_K))

    # ---------------------------------------------- 5b. livery and materials, in WORLD space
    E, Einv = livery_space()
    S.log('livery space: world / %.5f (prototype metres)' % E.to_scale().x)
    store, nbaked = {}, 0
    fallback = flat_material('tram_unassigned', (0.5, 0.5, 0.5), 0.6, store=store)
    for ob in keep:
        single_user(ob)
        names = [s.material.name for s in ob.material_slots if s.material]
        kind = ('bands' if 'Modern | side blue-white bands' in names else
                'V' if 'Modern | front blue-white V' in names else None)
        faces = bake_livery(ob, kind, T, E, Einv) if kind else {}
        nbaked += bool(kind)
        me = ob.data
        src = [s.material for s in ob.material_slots]
        # Mesh.materials.clear() resets EVERY face's material index to 0. Without
        # this, each multi-material part collapses onto its first material: the
        # Route 25 board lost its photograph face, and windows, roof rims and
        # frames all took one colour. Save the indices, rebuild the slots, put
        # them back.
        idx = [p.material_index for p in me.polygons]
        me.materials.clear()
        for m in src:
            me.materials.append(replacement(m, store) if m else fallback)
        if not src:
            me.materials.append(fallback)
        me.polygons.foreach_set('material_index', idx)
        if faces:
            slot = {}
            for key in sorted(set(faces.values())):
                nm = {BLUE: 'blue', WHITE: 'white', PALE: 'pale', NAVY: 'navy'}.get(
                    tuple(round(x, 3) for x in key), 'band')
                me.materials.append(flat_material('tram_livery_' + nm, key, 0.40,
                                                  0.0, store=store))
                slot[key] = len(me.materials) - 1
            for pi, key in faces.items():
                me.polygons[pi].material_index = slot[key]
    S.log('livery baked into %d objects' % nbaked)
    watch('materials', keep)

    # ---------------------------------------------- 6. decimate the heavy parts
    before = sum(tris(o) for o in keep)
    for ob in keep:
        low = ob.name.lower()
        if 'rounded signature roof' in low:
            decimate_to(ob, ROOF_TRIS)           # keeps its UVs; do not dissolve
        elif 'body shell' in low:
            dissolve_flat(ob)                    # big and flat: merge, never collapse
        else:
            simplify(ob)
    S.log('decimated: %d -> %d tris' % (before, sum(tris(o) for o in keep)))
    watch('decimated', keep)

    # where the triangles are, by part type. This is the budget, and it is what
    # decides what to simplify next; keeping it in the log means a change to the
    # source model shows up here before it shows up as a slow headset.
    from collections import Counter
    by = Counter()
    for ob in keep:
        stem = ob.name.split('.')[0]
        stem = ''.join(ch for ch in stem if not ch.isdigit()).strip(' |-+')
        by[stem[:44]] += tris(ob)
    S.log('triangle budget, biggest first:')
    for k, v in by.most_common(28):
        S.log('   %7d  %s' % (v, k))

    # ---------------------------------------------- 7. textures, down-sized
    for m in {s.material for o in keep for s in o.material_slots if s.material}:
        if not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image and n.image.size[0] > 2000:
                old = n.image
                w0, h0 = old.size
                nice = 'tram_roof_normal' if 'normal' in old.name.lower() else 'tram_roof_base'
                old.name = old.name + '_orig'
                n.image = downscale_image(old, 4)
                n.image.name = nice
                S.log('texture %s %dx%d -> %dx%d' % (n.image.name, w0, h0, *n.image.size))

    # Every textured part must use the SAME UV layer name before joining. The roof
    # calls its layer "UVMap" and the Route 25 board calls its own "Supplied
    # photograph board crop"; joined, those become two layers, the material reads
    # the first, and the board samples a single dark pixel from the photograph.
    for ob in keep:
        uvs = ob.data.uv_layers
        if len(uvs) == 0:
            continue
        uvs[0].name = 'UVMap'
        while len(uvs) > 1:
            uvs.remove(uvs[1])

    # ---------------------------------------------- 8. join into one mesh
    roofs = [o for o in keep if 'rounded signature roof' in o.name.lower()]
    rest = [o for o in keep if o not in roofs]
    target = roofs[0]                                      # carries the UVMap
    watch('pre-join', keep)
    final = M.join(roofs + rest, 'TramV3')
    me = final.data
    bm = bmesh.new(); bm.from_mesh(me)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.002)
    S.log('weld: %d -> %d verts' % (n0, len(bm.verts)))
    bm.to_mesh(me); bm.free()
    me.transform(Matrix.Scale(MODEL_TO_M, 4))              # mm of model -> metres
    me.update()
    final.location = (0, 0, 0); final.rotation_euler = (0, 0, 0); final.scale = (1, 1, 1)
    S.log('joined: %d tris, %d materials, uv layers %s' % (
        tris(final), len(me.materials), [u.name for u in me.uv_layers]))

    # Only the roof and the Route 25 board are textured. In a glTF every vertex of
    # a primitive carries the same attributes, so leaving the UV layer on the one
    # joined mesh costs 8 bytes on all 280,000 vertices for two materials' sake.
    # Split the textured faces into their own mesh and take the UVs off the rest.
    textured = {i for i, m in enumerate(final.data.materials)
                if m and m.use_nodes and any(n.type == 'TEX_IMAGE' for n in m.node_tree.nodes)}
    texmesh = final.copy()
    texmesh.data = final.data.copy()
    texmesh.name = 'TramV3_textured'
    for ob_, keep_tex in ((final, False), (texmesh, True)):
        bm = bmesh.new(); bm.from_mesh(ob_.data)
        kill = [f for f in bm.faces if (f.material_index in textured) != keep_tex]
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bm.to_mesh(ob_.data); bm.free()
    for u in list(final.data.uv_layers):
        final.data.uv_layers.remove(u)
    S.log('split: plain %d tris (no UVs), textured %d tris' % (tris(final), tris(texmesh)))
    # smooth by angle: shared vertices on curved parts, split only at real edges
    for o_ in (final, texmesh):
        bpy.context.scene.collection.objects.link(o_) if o_.name not in bpy.context.scene.collection.objects else None
        M.shade_smooth(o_, 35.0)

    # ---------------------------------------------- 9. a clean file with one collection
    for o in list(bpy.data.objects):
        if o is not final and o is not texmesh:
            bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    scene = bpy.context.scene
    for c in list(scene.collection.children):
        scene.collection.children.unlink(c)
    for o_ in (final, texmesh):
        for c in list(o_.users_collection):
            c.objects.unlink(o_)
    coll = S.coll('TRAM_V3')
    coll.objects.link(final)
    coll.objects.link(texmesh)
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = 'METERS'

    co = [v.co for o_ in (final, texmesh) for v in o_.data.vertices]
    mn = Vector((min(c.x for c in co), min(c.y for c in co), min(c.z for c in co)))
    mx = Vector((max(c.x for c in co), max(c.y for c in co), max(c.z for c in co)))
    S.log('TramV3 bounds  x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f' %
          (mn.x, mx.x, mn.y, mx.y, mn.z, mx.z))
    S.log('  length %.2f m   width %.2f m   height %.2f m (to the trolley wheel)' %
          (mx.x - mn.x, mx.y - mn.y, mx.z - mn.z))
    for m in me.materials:
        S.log('  mat %s' % m.name)
    S.save(os.path.join(S.ASSETS, 'tram_v3.blend'))


main()
