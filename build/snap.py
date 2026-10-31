import bpy, sys, math
from mathutils import Vector
src, dst = sys.argv[sys.argv.index('--')+1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ms=[o for o in bpy.context.scene.objects if o.type=='MESH']
bb=[o.matrix_world@Vector(c) for o in ms for c in o.bound_box]
mn=Vector([min(v[i] for v in bb) for i in range(3)]);mx=Vector([max(v[i] for v in bb) for i in range(3)])
c=(mn+mx)/2; r=(mx-mn).length
print('BOUNDS',list(mn),list(mx))
sc=bpy.context.scene; sc.render.engine='BLENDER_WORKBENCH'
sc.display.shading.light='STUDIO'; sc.display.shading.color_type='TEXTURE'
sc.render.resolution_x=900; sc.render.resolution_y=450
cam=bpy.data.objects.new('c',bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera=cam
cam.data.clip_end=1000
for i,(dx,dy,dz) in enumerate([(0,-1,0.15),(1,0,0.15),(0,0,1),(-1,-1,0.4)]):
    d=Vector((dx,dy,dz)).normalized()
    cam.location=c+d*r*1.9
    cam.rotation_euler=(-d).to_track_quat('-Z','Y').to_euler()
    sc.render.filepath=f'{dst}_{i}.png'; bpy.ops.render.render(write_still=True)
