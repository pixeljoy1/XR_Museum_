import bpy, math, json, ast, bmesh
from pathlib import Path
from mathutils import Vector, Matrix
OUT=Path('/Users/joy/Desktop/CODEX/kolkata_tram_2D_/V3_Model')
S=1000/87
scene=bpy.context.scene
collections={c.name:c for c in scene.collection.children}
current='04 Trailer | shell'
bodymat=bpy.data.materials['Study | warm grey shell']
trim=bpy.data.materials['Study | frame edges']
metal=bpy.data.materials['Study | axle and fittings']
dark=bpy.data.materials['Study | running gear']
tree=ast.parse((OUT/'build_tram.py').read_text())
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name not in ('camera',):
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(OUT/'build_tram.py'),'exec'),globals())
old=next(o for o in scene.objects if o.name=='Trailer | body shell')
print('Prior trailer shell vertices:',len(old.data.vertices))
old.name='Trailer | rejected shell'
shell=prism('Trailer | body shell',outline(.595,7.675,2.9),.66,2.86,bodymat)
inner=prism('Cavity',outline(.68,7.59,2.73,.34),.61,2.93,None)
def subtract_one(c):
    bpy.context.view_layer.objects.active=shell
    m=shell.modifiers.new('Opening','BOOLEAN');m.operation='DIFFERENCE';m.solver='EXACT';m.object=c
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(c,do_unlink=True)
    if not len(shell.data.vertices):raise RuntimeError('Boolean erased shell')
subtract_one(inner)
print('Hollow shell vertices:',len(shell.data.vertices))
for side,xs in [(-1,[1.18,1.88,3.66,4.36,5.06,5.76,6.46]),(1,[1.14,1.79,2.44,3.09,3.74,4.39,5.04,5.69,6.34,6.99])]:
    for x in xs:
        w=.54 if side==1 else .57
        for z,h in [(1.83,.62),(2.4,.255)]:
            subtract_one(cutbox('Void',(x,side*1.44,z),(w,.38,h)))
subtract_one(cutbox('Entrance',(2.61,-1.43,1.53),(1.04,.46,2.02),.02))
for z,h in [(1.83,.62),(2.4,.255)]:
    subtract_one(cutbox('Corner void',(7.13,-1.43,z),(.37,.4,h)))
for x in (.595,7.675):
    for j,y in enumerate((-.78,0,.78)):
        subtract_one(cutbox('End void',(x,y,2.03),(.4,.84 if j==1 else .61,.78),.04))
bevel(shell,.008,2)
bpy.context.view_layer.objects.active=shell
bpy.ops.object.modifier_apply(modifier=shell.modifiers[0].name)
shell.data.transform(Matrix.Scale(S,4));shell.location*=S
shell['scale']='1:87; millimetres'
bpy.data.objects.remove(old,do_unlink=True)

# Recalculate face normals for all meshes, and report closedness per component.
report={'scale':'1:87','units':'mm','objects':len(scene.objects),'meshes':0,'empty':[], 'non_manifold':[]}
for o in scene.objects:
    if o.type!='MESH':continue
    report['meshes']+=1
    if not len(o.data.vertices):report['empty'].append(o.name);continue
    bm=bmesh.new();bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bad=sum(not e.is_manifold for e in bm.edges)
    if bad:report['non_manifold'].append({'object':o.name,'edges':bad})
    bm.to_mesh(o.data);bm.free()
report['dimensions']={o.name:[round(float(d),3) for d in o.dimensions] for o in scene.objects if o.name in ('Motor | body shell','Trailer | body shell','Display | removable plinth')}
(OUT/'geometry_audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
for cam,name in [('Camera | front entrance-side overview','01_overview'),('Camera | entrance-side orthographic','02_entrance_side'),('Camera | opposite-side orthographic','03_opposite_side')]:
    scene.camera=bpy.data.objects[cam];scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
for name in ('03 Motor | removable roof','06 Trailer | removable roof'):collections[name].hide_render=True
scene.camera=bpy.data.objects['Camera | interior inspection'];scene.render.filepath=str(OUT/'04_interior.png');bpy.ops.render.render(write_still=True)
for name in ('03 Motor | removable roof','06 Trailer | removable roof'):collections[name].hide_render=False
scene.camera=bpy.data.objects['Camera | front entrance-side overview']
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Kolkata_Tram_V3_Geometry.blend'))
