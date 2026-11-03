import bpy,bmesh,math,ast,json
from pathlib import Path
from mathutils import Vector,Matrix
OUT=Path('/Users/joy/Desktop/CODEX/kolkata_tram_2D_/V3_Model');S=1000/87;scene=bpy.context.scene;collections={c.name:c for c in scene.collection.children}
bodymat=bpy.data.materials['Modern | warm white enamel'];trim=bodymat;metal=bpy.data.materials['Roof equipment | dull aluminium'];dark=bpy.data.materials['Modern | black housings']
for node in ast.parse((OUT/'build_tram.py').read_text()).body:
 if isinstance(node,ast.FunctionDef) and node.name!='camera':exec(compile(ast.Module(body=[node],type_ignores=[]),'helpers','exec'),globals())
roofmat=bpy.data.materials['Modern | supplied roof colour and seam map'];gold=bpy.data.materials['Modern | ochre roof rim'];recess=bpy.data.materials['Roof equipment | aluminium louvre recess'];rubber=bpy.data.materials['Windows | thin black rubber seals']
def scale_obj(o):
 bpy.context.view_layer.objects.active=o
 for m in list(o.modifiers):bpy.ops.object.modifier_apply(modifier=m.name)
 o.data.transform(Matrix.Scale(S,4));o.location*=S;return o
def union(a,b):
 bpy.context.view_layer.objects.active=a;m=a.modifiers.new('Continuous closed roof return','BOOLEAN');m.operation='UNION';m.solver='EXACT';m.object=b;bpy.ops.object.modifier_apply(modifier=m.name);bpy.data.objects.remove(b,do_unlink=True)
for tag,end,sgn,current in [('Motor',.175,-1,'03 Motor | removable roof'),('Trailer',.595,1,'06 Trailer | removable roof')]:
 roof=bpy.data.objects[tag+' | rounded signature roof'];cut=end+sgn*.32
 cutter=scale_obj(cutbox('Remove open inner roof end',(end-sgn*.35,0,3.2),(1.34,3.5,1.1),0));boolean(roof,[cutter])
 # Closed quarter-round hood extends down to the header, including the two shoulders.
 vs=[];N=64;M=32
 for i in range(M+1):
  theta=math.pi/2*i/M;distance=.33*(1-math.sin(theta));x=end+sgn*distance
  hw=1.15+.30*min(distance/.30,1);height=.345*math.cos(theta)
  for j in range(N+1):
   t=-math.pi/2+math.pi*j/N;vs.append((x,hw*math.sin(t),2.85+height*math.cos(t)))
 # Bottom surface follows the same footprint for a watertight volume.
 n=len(vs);vs += [(x,y,2.795) for x,y,z in vs];fs=[]
 for k in range(2):
  for i in range(M):
   for j in range(N):
    q=k*n+i*(N+1)+j;f=(q,q+N+1,q+N+2,q+1);fs.append(f if k==0 else tuple(reversed(f)))
 boundary=list(range(N+1))+[i*(N+1)+N for i in range(1,M+1)]+list(range(M*(N+1)+N-1,M*(N+1)-1,-1))+[i*(N+1) for i in range(M-1,0,-1)]
 for i,q in enumerate(boundary):r=boundary[(i+1)%len(boundary)];fs.append((q,r,r+n,q+n))
 hood=scale_obj(mesh(tag+' | smooth inner roof return',vs,fs,roofmat))
 for p in hood.data.polygons:p.use_smooth=True
 union(roof,hood)
# Remove only the large rear headlamp assembly, retain lower marker and retrieval reel.
removed=[]
for o in list(scene.objects):
 if o.name.startswith('End | headlamp') and o.matrix_world.translation.x>0:removed.append(o.name);bpy.data.objects.remove(o,do_unlink=True)
 if 'thick centre grab pillar' in o.name:
  # Cylinders are oriented along Z; reduce cross-section by 30 percent.
  o.scale.x*=.70;o.scale.y*=.70;o.data.materials.clear();o.data.materials.append(dark)
 if 'grab pillar foot' in o.name:o.data.materials.clear();o.data.materials.append(dark)
# Larger fused light box and wider rectangular optical aperture.
current='03 Motor | removable roof';roof=bpy.data.objects['Motor | rounded signature roof'];A=-7.675
for o in list(scene.objects):
 if o.name.startswith('Top headlight |'):bpy.data.objects.remove(o,do_unlink=True)
pod=scale_obj(box('Enlarged integral light console',(A+.075,0,3.055),(.38,.51,.39),gold,.045));union(roof,pod)
cutter=scale_obj(cutbox('Recessed console aperture',(A-.105,0,3.07),(.13,.345,.25),.045));boolean(roof,[cutter])
original=set(scene.objects)
frame('Top headlight | wider black seal',(A-.121,0,3.07),.367,.272,.019,.012,'END',rubber)
box('Top headlight | internal reflector',(A-.045,0,3.07),(.008,.32,.23),metal,.035)
glass=bpy.data.materials['Windows | clear lightly reflective glass']
box('Top headlight | transparent rectangular glass',(A-.123,0,3.07),(.004,.329,.234),glass,.044)
bulb=bpy.data.materials.new('Console | warm glowing bulb');bulb.use_nodes=True;p=bulb.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(.8,.65,.34,1);p.inputs['Emission'].default_value=(1,.65,.23,1)
d=p.inputs['Emission Strength'].driver_add('default_value').driver;d.expression='enabled*12';v=d.variables.new();v.name='enabled';v.targets[0].id=bpy.data.objects['Night lighting | enable control'];v.targets[0].data_path='["enabled"]'
bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,radius=.055,location=(A-.075,0,3.07));o=link(bpy.context.object,'Top headlight | internal warm bulb',bulb);o.scale.x=.55
# Replace flat dark stripes with raised aluminium louvre lips on all four enclosure sides.
for o in list(scene.objects):
 if 'resistance louvre' in o.name:bpy.data.objects.remove(o,do_unlink=True)
for side in (-1,1):
 for j in range(4):
  z=3.285+j*.056;yy=side*(.49-(z-3.24)/.295*.09)
  for k in range(5):
   x=-6.34+k*.295
   box('Roof box | side vent recess',(x,yy+side*.005,z),(.22,.014,.024),recess,.006)
   lip=box('Roof box | side aluminium louvre',(x,yy+side*.019,z+.012),(.23,.038,.014),metal,.004);lip.rotation_euler.x=side*math.radians(20)
 for j in range(3):
  z=3.29+j*.065;xx=-5.75+side*(.815-(z-3.24)/.295*.115)
  for yy in (-.22,.22):
   box('Roof box | end vent recess',(xx+side*.005,yy,z),(.015,.31,.025),recess,.005)
   lip=box('Roof box | end aluminium louvre',(xx+side*.018,yy,z+.012),(.038,.32,.014),metal,.004);lip.rotation_euler.y=-side*math.radians(20)
for o in list(scene.objects):
 if o in original or o.type!='MESH':continue
 scale_obj(o)
 bpy.context.view_layer.update();mw=o.matrix_world.copy();o.parent=bpy.data.objects.get('03 Motor | assembly control');o.matrix_world=mw
# Subtle procedural paint mottling and micro-roughness; preserve livery colour masks.
for name in ['Modern | warm white enamel','Modern | Kolkata sky blue','Modern | navy header','Modern | ochre roof rim','Modern | side blue-white bands','Modern | front blue-white V']:
 m=bpy.data.materials.get(name)
 if not m or not m.use_nodes:continue
 nt=m.node_tree;p=nt.nodes.get('Principled BSDF')
 if not p:continue
 tex=nt.nodes.new('ShaderNodeTexNoise');tex.name='Light weathering mottling';tex.inputs['Scale'].default_value=26;tex.inputs['Detail'].default_value=3;tex.inputs['Roughness'].default_value=.75
 ramp=nt.nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.23;ramp.color_ramp.elements[0].color=(.62,.59,.53,1);ramp.color_ramp.elements[1].position=.73;ramp.color_ramp.elements[1].color=(1,1,.97,1);nt.links.new(tex.outputs['Fac'],ramp.inputs[0])
 mix=nt.nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=.38
 old=list(p.inputs['Base Color'].links)
 if old:nt.links.new(old[0].from_socket,mix.inputs[1])
 else:mix.inputs[1].default_value=p.inputs['Base Color'].default_value
 nt.links.new(ramp.outputs[0],mix.inputs[2]);nt.links.new(mix.outputs[0],p.inputs['Base Color'])
 p.inputs['Roughness'].default_value=.68
 fine=nt.nodes.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=180;fine.inputs['Detail'].default_value=2
 bump=nt.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.13;bump.inputs['Distance'].default_value=.018;nt.links.new(fine.outputs['Fac'],bump.inputs['Height']);nt.links.new(bump.outputs['Normal'],p.inputs['Normal'])
report={'revision':'V3.11','rear_lamp_removed':removed,'non_manifold':[]}
for o in scene.objects:
 if o.type!='MESH':continue
 bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bad=sum(not e.is_manifold for e in bm.edges);bm.to_mesh(o.data);bm.free()
 if bad:report['non_manifold'].append([o.name,bad])
(OUT/'roof_return_audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
scene.render.resolution_x=1400;scene.render.resolution_y=1100
for cam,name in [('Camera | clean carriage connection','34_closed_inner_roofs.png'),('Camera | corrected motor nose','35_worn_livery_ventilated_console.png'),('Camera | corrected trailer tail','36_rear_without_headlamp.png')]:
 scene.camera=bpy.data.objects[cam];scene.render.filepath=str(OUT/name);bpy.ops.render.render(write_still=True)
ctrl=bpy.data.objects['Night lighting | enable control'];ctrl['enabled']=1.;bpy.context.view_layer.update();scene.camera=bpy.data.objects['Camera | corrected motor nose'];scene.render.filepath=str(OUT/'37_warm_console_bulb.png');bpy.ops.render.render(write_still=True);ctrl['enabled']=0.;bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Kolkata_Tram_V3_11_Roof_Returns_And_Wear.blend'))
