import bpy,json
from pathlib import Path
OUT=Path('/Users/joy/Desktop/CODEX/kolkata_tram_2D_/V3_Model');scene=bpy.context.scene
def lin(v):return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
def mat(name,col,metal,rough):
    m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=tuple(lin(v) for v in col)+(1,)
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=m.diffuse_color;p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
    return m
al=mat('Roof equipment | dull aluminium',(.64,.66,.67),.82,.62)
recess=mat('Roof equipment | aluminium louvre recess',(.39,.42,.44),.75,.73)
changed=[]
for o in scene.objects:
    if o.type!='MESH':continue
    n=o.name.lower()
    if any(t in n for t in ('resistance','trolley','pole retrieval')):
        o.data.materials.clear();o.data.materials.append(recess if 'louvre' in n else al);changed.append(o.name)
scene['ROOF_FINISH']='Roof electrical equipment, pole, mountings and resistance enclosure: dull aluminium. Louvre recesses darker aluminium, not black.'
for cam,name in [('Camera | front entrance-side overview','16_aluminium_overview'),('Camera | corrected motor nose','17_aluminium_cab')]:
    scene.camera=bpy.data.objects[cam];scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
scene.camera=bpy.data.objects['Camera | front entrance-side overview']
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Kolkata_Tram_V3_4_Aluminium_Roof.blend'))
(OUT/'roof_finish_audit.json').write_text(json.dumps({'finish':'dull aluminium','changed_objects':changed,'geometry_modified':False},indent=2))
print('Updated '+str(len(changed))+' roof equipment parts; saved V3.4.')
