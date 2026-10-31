"""
Normalise the three downloaded masterpiece GLBs into display pieces.

For each: flatten the parent empties, decimate to a WebXR-friendly triangle count, shrink the
textures, rotate so the piece faces -Y in Blender (which becomes +Z in the A-Frame page, i.e.
towards a viewer standing in front of it), scale to the display height we want in the gallery,
and move the origin to the centre of its base so it can be dropped straight onto a plinth.

Run:  /Applications/Blender.app/Contents/MacOS/Blender -b -P build/prep_models.py
Out:  site/models/*.glb  +  build/models_report.json
"""
import bpy, json, math
from mathutils import Vector, Matrix

SRC = '/Users/joy/Desktop/VSCODE/XR_Museum_/'
OUT = SRC + 'site/models/'

# source file, output file, triangle budget, max texture px, display height (m), yaw so the front faces -Y
JOBS = [
    ('cesar_-_louvre_museum.glb',             'caesar.glb',    55000, 2048, 0.85, -90),
    ('nefertitis_bust_like_in_the_museum.glb', 'nefertiti.glb', 55000, 2048, 0.60,  90),
    ('stephensons_rocket.glb',                 'rocket.glb',    70000, 2048, 3.00,   0),
]

report = {}

for src, dst, target, texmax, height, yaw in JOBS:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=SRC + src)

    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    for o in meshes:                                   # keep the world position, drop the parent empties
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    for o in [o for o in bpy.context.scene.objects if o.type != 'MESH']:
        bpy.data.objects.remove(o, do_unlink=True)

    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = dst[:-4]

    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    if tris > target:
        md = ob.modifiers.new('dec', 'DECIMATE')
        md.ratio = target / tris
        bpy.ops.object.modifier_apply(modifier=md.name)

    def bounds():
        bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        return (Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb))),
                Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb))))

    mn, mx = bounds()
    k = height / (mx.z - mn.z)
    ob.matrix_world = Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Scale(k, 4) @ ob.matrix_world
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    mn, mx = bounds()                                   # origin to the centre of the base
    ob.data.transform(Matrix.Translation((-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z)))
    ob.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()
    mn, mx = bounds()

    for im in bpy.data.images:
        if max(im.size) > texmax:
            s = texmax / max(im.size)
            im.scale(int(im.size[0] * s), int(im.size[1] * s))

    # these are photogrammetry scans: keep them matte so the gallery spotlights read as the light source
    for m in ob.data.materials:
        if m and m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == 'BSDF_PRINCIPLED':
                    n.inputs['Roughness'].default_value = max(n.inputs['Roughness'].default_value, 0.6)
                    n.inputs['Metallic'].default_value = 0.0

    report[dst] = dict(tris_before=tris,
                       tris=sum(len(p.vertices) - 2 for p in ob.data.polygons),
                       size=[round(v, 3) for v in (mx - mn)],
                       min=[round(v, 3) for v in mn], max=[round(v, 3) for v in mx])

    bpy.ops.export_scene.gltf(filepath=OUT + dst, export_format='GLB', export_image_format='JPEG',
                              export_jpeg_quality=85, export_apply=True, export_yup=True,
                              export_cameras=False, export_lights=False)

json.dump(report, open(SRC + 'build/models_report.json', 'w'), indent=1)
print('PREP DONE', json.dumps(report))
