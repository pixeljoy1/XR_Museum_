"""Render a quick turnaround of one linked asset, so a model can be LOOKED at
before it goes anywhere near the street.

    blender -b -P build/preview_asset.py -- --blend assets/tram_v3.blend --coll TRAM_V3 \
            --out renders/_tram_v3 [--samples 48]
"""
import bpy, math, os, sys
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klib import mesh as M, mat as T, sceneutil as S, cam as C

bl = S.argval('--blend'); cn = S.argval('--coll'); out = S.argval('--out')
S.reset('Preview')
coll = S.link_collection(bl, cn, link=False)
bpy.context.scene.collection.children.link(coll)
obs = [o for o in coll.all_objects if o.type == 'MESH']
mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
for o in obs:
    for v in o.data.vertices:
        w = o.matrix_world @ v.co
        mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
ctr = (mn + mx) / 2
span = max(mx - mn)
S.cycles(samples=S.argval('--samples', 40, int), res=(1280, 720), bounces=4)
sc = bpy.context.scene
sc.world = bpy.data.worlds.new('w'); sc.world.use_nodes = True
bg = sc.world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.62, 0.68, 0.76, 1); bg.inputs[1].default_value = 1.6
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
sun.data.energy = 3.2; sun.data.angle = math.radians(4)
sun.rotation_euler = (math.radians(50), 0, math.radians(125)); sc.collection.objects.link(sun)
M.plane((80, 40), (0, 0, mn.z - 0.001), name='gnd', mat=T.base('g', (0.09, 0.09, 0.095), 0.7))
shots = {
  'nose':   ((ctr.x - span * 0.62, ctr.y - span * 0.30, 1.6), (ctr.x - span * 0.46, 0, 1.5), 40),
  'side':   ((ctr.x, ctr.y - span * 1.05, 2.2), (ctr.x, 0, 1.8), 50),
  'rear3q': ((ctr.x + span * 0.62, ctr.y + span * 0.34, 3.0), (ctr.x + span * 0.2, 0, 2.2), 40),
}
cd = bpy.data.cameras.new('c'); cam = bpy.data.objects.new('c', cd)
sc.collection.objects.link(cam); sc.camera = cam
for name, (loc, aim, lens) in shots.items():
    cd.lens = lens
    cam.location = loc
    cam.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = '%s_%s.png' % (out, name)
    S.log('render %s' % name)
    bpy.ops.render.render(write_still=True)
