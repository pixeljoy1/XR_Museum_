import bpy,json
from pathlib import Path
s=bpy.context.scene;out=Path('/Users/joy/Desktop/CODEX/kolkata_tram_2D_/V3_Model')
bars=[o for o in s.objects if 'safety bar' in o.name]
print(json.dumps({'white_guard_bars':len(bars),'guard_materials':sorted(set(m.name for o in bars for m in o.data.materials)),'night_setting':bpy.data.objects['Night lighting | enable control']['enabled']}))
m=bpy.data.materials['Windows | smoked grey fixed glazing'];p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Transmission'].default_value=.12;p.inputs['IOR'].default_value=1.45
s.camera=bpy.data.objects['Camera | opposite-side orthographic'];s.render.resolution_x=1800;s.render.resolution_y=650;s.render.filepath=str(out/'26_white_right_side_guards.png');bpy.ops.render.render(write_still=True)
s.camera=bpy.data.objects['Camera | corrected motor nose'];s.render.resolution_x=1400;s.render.resolution_y=1100
bpy.ops.wm.save_as_mainfile(filepath=str(out/'Kolkata_Tram_V3_7_Mesh_And_Lighting.blend'))
