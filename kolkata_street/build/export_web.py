"""Export the street for the browser  ->  docs/kolkata/

The WebXR page does not load one enormous model. It loads one GLB per asset --
the tram, the taxi, each building type, the poles, the trees -- plus one for the
ground, and a layout.json that says where to put them. That mirrors how the
Blender scene is put together (model once, instance many), keeps every file
small, and means the browser holds one copy of each mesh however many times it
appears.

glTF cannot carry a procedural material. Blender's exporter writes either an
image texture or the constant sitting on the socket, and for a linked Base Color
that constant is whatever was left there -- usually 0.8 grey. So every material
is flattened first: the node tree is walked to a representative colour, the link
is cut, and the constant is set. The detail is lost; the colour is not.

Axes: Blender is Z-up, glTF is Y-up. (x, y, z) -> (x, z, -y), and a rotation
about Blender +Z becomes the same rotation about glTF +Y.

Run (make_web.sh does all three):
    blender -b -P build/build_street.py -- --append --out scene/_flat.blend
    blender -b scene/_flat.blend -P build/export_web.py
"""
import bpy, json, math, os, sys
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klib import mesh as M, sceneutil as S

WEB = os.path.join(os.path.dirname(S.ROOT), 'docs', 'kolkata')
MODELS = os.path.join(WEB, 'models')
os.makedirs(MODELS, exist_ok=True)
S.log_to(os.path.join(S.ROOT, 'build', 'export_web.log'))

GROUND = ['WALK_road', 'SOLID_track', 'WALK_footpath', 'WALK_far_ground',
          'overhead']
MID_GREY = (0.5, 0.5, 0.5)


# ------------------------------------------------------------------ materials
def _avg(cols):
    cols = [c for c in cols if c]
    if not cols:
        return MID_GREY
    n = len(cols)
    return tuple(sum(c[i] for c in cols) / n for i in range(3))


def resolve_colour(sock, depth=0):
    """A representative flat colour for a socket that may be driven by nodes."""
    if depth > 8:
        return MID_GREY
    if not sock.is_linked:
        v = sock.default_value
        return tuple(v[:3]) if hasattr(v, '__len__') else (v, v, v)
    n = sock.links[0].from_node
    t, b = n.type, n.bl_idname
    if t == 'RGB':
        return tuple(n.outputs[0].default_value[:3])
    if t == 'VALTORGB':                                   # ColorRamp
        return _avg([tuple(e.color[:3]) for e in n.color_ramp.elements])
    if t == 'TEX_BRICK':
        return _avg([resolve_colour(n.inputs[k], depth + 1)
                     for k in ('Color1', 'Color2', 'Mortar')])
    if b == 'ShaderNodeMix':
        return _avg([resolve_colour(n.inputs[6], depth + 1),
                     resolve_colour(n.inputs[7], depth + 1)])
    if t == 'MIX_RGB':
        return _avg([resolve_colour(n.inputs['Color1'], depth + 1),
                     resolve_colour(n.inputs['Color2'], depth + 1)])
    if t in ('TEX_NOISE', 'TEX_WAVE', 'TEX_VORONOI', 'TEX_MUSGRAVE'):
        return MID_GREY
    for i in n.inputs:                                     # last resort
        if i.type == 'RGBA':
            return resolve_colour(i, depth + 1)
    return MID_GREY


def resolve_float(sock, default=0.6, depth=0):
    if depth > 8:
        return default
    if not sock.is_linked:
        v = sock.default_value
        return float(v[0]) if hasattr(v, '__len__') else float(v)
    n = sock.links[0].from_node
    if n.bl_idname == 'ShaderNodeMix':
        return (resolve_float(n.inputs[2], default, depth + 1)
                + resolve_float(n.inputs[3], default, depth + 1)) / 2
    if n.type == 'MIX_RGB':
        return (resolve_float(n.inputs['Color1'], default, depth + 1)
                + resolve_float(n.inputs['Color2'], default, depth + 1)) / 2
    if n.type == 'VALTORGB':
        return _avg([tuple(e.color[:3]) for e in n.color_ramp.elements])[0]
    return default


def flatten_materials():
    """Make every material something glTF can actually carry."""
    n = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        bsdf = next((x for x in mat.node_tree.nodes
                     if x.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        nt = mat.node_tree
        col = resolve_colour(bsdf.inputs['Base Color'])
        rough = resolve_float(bsdf.inputs['Roughness'], 0.6)
        for name in ('Base Color', 'Roughness', 'Normal', 'Metallic',
                     'Specular IOR Level', 'Specular'):
            if name in bsdf.inputs:
                for link in list(bsdf.inputs[name].links):
                    nt.links.remove(link)
        bsdf.inputs['Base Color'].default_value = (*col, 1.0)
        bsdf.inputs['Roughness'].default_value = min(1.0, max(0.04, rough))
        # glass: glTF transmission is patchy across viewers, so glazing becomes
        # a dark, mostly-opaque pane instead. It reads correctly at street scale.
        if 'glass' in mat.name.lower() or 'windscreen' in mat.name.lower():
            for key in ('Transmission Weight', 'Transmission'):
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = 0.0
            bsdf.inputs['Base Color'].default_value = (0.055, 0.075, 0.085, 1.0)
            bsdf.inputs['Roughness'].default_value = 0.10
            bsdf.inputs['Alpha'].default_value = 0.55
            mat.blend_method = 'BLEND'
        n += 1
    S.log('flattened %d materials' % n)


def merge_similar_materials(colour_step=0.045, rough_step=0.18):
    """Collapse materials that are visually the same into one.

    Every distinct material on a mesh becomes its own glTF primitive, and then
    its own draw call in the browser -- once per placement. A terrace of
    forty-five buildings and a crowd of walk-ons took this past a thousand draw
    calls, which no headset holds 72 Hz against. After flattening, most of those
    materials differ only in ways nobody can see: half a dozen near-blacks for
    trim, rubber, dashboards and ironwork. This buckets them and remaps the
    slots. Emission is part of the key, so a lamp never merges into a dark panel.
    """
    def key_of(bsdf):
        c = bsdf.inputs['Base Color'].default_value
        q = lambda v, st: int(round(v / st))
        em = (0.0, 0.0, 0.0)
        strength = 0.0
        for n in ('Emission Color', 'Emission'):
            if n in bsdf.inputs:
                em = tuple(bsdf.inputs[n].default_value[:3])
        for n in ('Emission Strength',):
            if n in bsdf.inputs:
                strength = bsdf.inputs[n].default_value
        return (q(c[0], colour_step), q(c[1], colour_step), q(c[2], colour_step),
                q(bsdf.inputs['Roughness'].default_value, rough_step),
                q(bsdf.inputs['Metallic'].default_value, 0.34),
                q(bsdf.inputs['Alpha'].default_value, 0.25),
                q(em[0] * strength, 0.5), q(em[1] * strength, 0.5),
                q(em[2] * strength, 0.5))

    canon, remap = {}, {}
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        # Glazing is left alone. Merging it saves nothing -- glass only ever
        # merges with other glass, and those live in different asset files, so
        # no primitive is combined -- and it costs the page its per-building
        # window material, which is what the night lighting varies to light the
        # terrace unevenly instead of switching every window on at once.
        if 'glass' in mat.name.lower() or 'windscreen' in mat.name.lower():
            continue
        bsdf = next((x for x in mat.node_tree.nodes
                     if x.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        k = key_of(bsdf)
        if k in canon:
            remap[mat.name] = canon[k]
        else:
            canon[k] = mat
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        for slot in ob.material_slots:
            if slot.material is not None and slot.material.name in remap:
                slot.material = remap[slot.material.name]
    S.log('merged %d materials down to %d' % (len(remap) + len(canon), len(canon)))
    return len(remap)


# ------------------------------------------------------------------ export
def select_only(objs):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objs:
        ob.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def export_glb(objs, path):
    select_only(objs)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True,
        export_apply=True, export_yup=True, export_cameras=False,
        export_lights=False, export_animations=False,
        export_materials='EXPORT', export_image_format='NONE',
        export_texcoords=False, export_normals=True,
        export_tangents=False, export_extras=False,
        export_skins=False, export_morph=False)
    tris = sum(M.tri_count(o) for o in objs if o.type == 'MESH')
    S.log('  %-22s %6d tris  %6.0f kB' %
          (os.path.basename(path), tris, os.path.getsize(path) / 1024))
    return tris


def b2g_pos(v):
    """Blender Z-up -> glTF/three.js Y-up."""
    return [round(v.x, 4), round(v.z, 4), round(-v.y, 4)]


def b2g_rot_y(e):
    return round(math.degrees(e.z), 3)


# ------------------------------------------------------------------ main
def main():
    S.log('exporting %s' % bpy.data.filepath)
    flatten_materials()
    merge_similar_materials()

    # --- which collections are actually instanced, and where
    used, instances = {}, []
    for ob in bpy.data.objects:
        c = ob.instance_collection
        if c is None:
            continue
        used.setdefault(c.name, c)
        instances.append({'asset': c.name,
                          'pos': b2g_pos(ob.location),
                          'rotY': b2g_rot_y(ob.rotation_euler)})
    S.log('%d collections, %d placements' % (len(used), len(instances)))

    # --- one GLB per asset collection
    total = 0
    root = bpy.context.scene.collection
    for name, coll in sorted(used.items()):
        linked_here = coll.name in [c.name for c in root.children]
        if not linked_here:
            root.children.link(coll)
        objs = [o for o in coll.all_objects if o.type == 'MESH']
        total += export_glb(objs, os.path.join(MODELS, '%s.glb' % name))
        if not linked_here:
            root.children.unlink(coll)

    # --- drop models the scene no longer uses. The exporter only ever writes, so
    # an asset that has been removed from the street (the tram, say) would sit in
    # models/ forever and keep shipping to every visitor as dead weight.
    keep = set(n + '.glb' for n in used) | {'ground.glb'}
    for f in os.listdir(MODELS):
        if f.endswith('.glb') and f not in keep:
            os.remove(os.path.join(MODELS, f))
            S.log('removed stale %s' % f)

    # --- the ground, as one file
    ground = [bpy.data.objects[n] for n in GROUND if n in bpy.data.objects]
    total += export_glb(ground, os.path.join(MODELS, 'ground.glb'))

    # --- the cameras become viewpoints you can jump between
    views = []
    for ob in sorted(bpy.data.objects, key=lambda o: o.name):
        if ob.type != 'CAMERA' or ob.name.startswith('CAM_'):
            continue
        aim = Vector(ob.get('aim', (0, 0, 0)))
        views.append({'name': ob.name,
                      'label': ob.name.split('_', 2)[-1].replace('_', ' '),
                      'lens': round(ob.data.lens, 1),
                      'note': ob.get('note', ''),
                      'pos': b2g_pos(ob.location),
                      'aim': b2g_pos(aim)})

    layout = {
        'generated_by': 'kolkata_street/build/export_web.py',
        'units': 'metres, glTF Y-up',
        'assets': sorted(used.keys()) + ['ground'],
        'instances': instances,
        'viewpoints': views,
        'track_y': [-1.90, 1.90],
        'street': {'x0': -90.0, 'x1': 158.0, 'road_half_width': 7.0,
                   'kerb_h': 0.155},
    }
    with open(os.path.join(WEB, 'layout.json'), 'w') as f:
        json.dump(layout, f, indent=1)
    S.log('layout.json: %d instances, %d viewpoints' % (len(instances), len(views)))
    S.log('total %d tris across %d asset files' % (total, len(used) + 1))


main()
