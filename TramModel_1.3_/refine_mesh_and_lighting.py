import bpy, json, math, bmesh
from pathlib import Path
from mathutils import Vector,Matrix
OUT=Path('/Users/joy/Desktop/CODEX/kolkata_tram_2D_/V3_Model')
# Rebuild the paired openings together with their seals, so shrinking the glass leaves no gap.
src=(OUT/'flush_glazed_windows.py').read_text()
src=src[:src.index('report={')]
src=src.replace("cutter=plate('Rounded opening cutter',center,w,h,r,rb", "cutter=plate('Rounded opening cutter',center,w*.88 if h==.255 else w,.205 if h==.255 else h,r,rb")
src=src.replace("o=seal(name+' | flush gasket',c,w,h,r,rb", "o=seal(name+' | flush gasket',c,w*.88 if h==.255 else w,.205 if h==.255 else h,r,rb")
src=src.replace("plate(name+' | fixed upper glass',c,w,h,r,rb", "plate(name+' | fixed upper glass',c,w*.88,.205,r,rb")
exec(compile(src,'rebuild-windows','exec'),globals())
white=bpy.data.materials['Modern | warm white enamel'];black=bpy.data.materials['Modern | black housings'];alloy=bpy.data.materials['Roof equipment | dull aluminium']
smoked=mat('Windows | smoked grey fixed glazing',(.075,.085,.085),.12)
p=smoked.node_tree.nodes.get('Principled BSDF');p.inputs['Roughness'].default_value=.20
for o in scene.objects:
    if o.type!='MESH':continue
    if 'safety bar' in o.name or 'sliding rain glass' in o.name or 'sliding lower sash' in o.name:
        o.data.materials.clear();o.data.materials.append(white)
        if 'sliding rain glass' in o.name:o.name=o.name.replace('sliding rain glass','solid white rain shutter')
    elif 'fixed upper glass' in o.name:
        o.data.materials.clear();o.data.materials.append(smoked)
for o in list(scene.objects):
    if 'perforated grille' in o.name or 'grille viewing cutout' in o.name or o.name.startswith(('End | destination','Motor | upper route lamp')):bpy.data.objects.remove(o,do_unlink=True)
original=set(scene.objects);current='10 End fittings | grille lamps fenders'
def wire(name,a,b):
    o=rod(name,a,b,.0045,white)
    for m in list(o.modifiers):o.modifiers.remove(m)
    return o
def grille(name,c,u,w,h):
    c=Vector(c);u=Vector(u);up=Vector((0,0,1))
    nx=round(w/.065);nz=round(h/.065)
    for i in range(nx+1):
        q=c+u*(-w/2+i*w/nx);wire(name+' | vertical wire',q-up*h/2,q+up*h/2)
    for j in range(nz+1):
        q=c+up*(-h/2+j*h/nz);wire(name+' | horizontal wire',q-u*w/2,q+u*w/2)
grille('Cab centre mesh',(A-.035,0,2.03),(0,1,0),1.48,.78)
for side in (-1,1):
    ang=side*math.atan2(.43,1.42);u=Vector((math.cos(ang),math.sin(ang),0));n=Vector((-abs(math.sin(ang)),side*math.cos(ang),0))
    grille('Cab cheek mesh',Vector((A+.47,side*half(.47,front),2.03))+n*.027,u,.62,.78)
# Matching white guard bars at the driver's right window.
x=A+1.075
for z in (1.80,2.00,2.20):
    wire('Driver right | white guard',(x-.22,half(x-.22-A,front)+.018,z),(x+.22,half(x+.22-A,front)+.018,z))
control=bpy.data.objects.new('Night lighting | enable control',None);group('12 Assembly controls | select to move parts').objects.link(control)
control['enabled']=0.0;control.id_properties_ui('enabled').update(min=0,max=1,description='0 daytime; 1 internally lit route displays and top headlamp')
def driven(socket,mult):
    d=socket.driver_add('default_value').driver;d.expression=f'enabled*{mult}'
    v=d.variables.new();v.name='enabled';v.targets[0].id=control;v.targets[0].data_path='["enabled"]'
card=mat('Route display | illuminated ivory card',(.67,.65,.55))
p=card.node_tree.nodes.get('Principled BSDF');p.inputs['Emission'].default_value=(1,.83,.55,1);driven(p.inputs['Emission Strength'],3)
lens=mat('Headlamp | optical lens',(.20,.23,.24),.25)
p=lens.node_tree.nodes.get('Principled BSDF');p.inputs['Roughness'].default_value=.12;p.inputs['Emission'].default_value=(1,.9,.72,1);driven(p.inputs['Emission Strength'],7)
# Curved-corner hollow holder, recessed replaceable route card, separate glass sheet.
def endring(name,x,z,w,h,edge,depth,material):
    return frame(name,(x,0,z),w,h,edge=edge,depth=depth,plane='END',material=material)
for x,sgn in ((A,-1),(B,1)):
    box('Route display | back case',(x+sgn*.025,0,2.65),(.045,1.12,.23),white,.025)
    endring('Route display | rubber gasket',x+sgn*.063,2.65,1.12,.23,.025,.024,black)
    box('Route display | replaceable illuminated card',(x+sgn*.051,0,2.65),(.006,1.05,.165),card,.018)
    box('Route display | protective glass',(x+sgn*.078,0,2.65),(.004,1.065,.178),glass,.018)
# Top-centre headlight: recessed optical assembly, slim metal bezel and lens.
box('Top headlight | housing',(A-.035,0,2.99),(.09,.29,.26),white,.025)
endring('Top headlight | dark seal',A-.087,2.99,.255,.225,.020,.016,black)
endring('Top headlight | aluminium bezel',A-.100,2.99,.230,.200,.013,.014,alloy)
box('Top headlight | recessed lens',(A-.100,0,2.99),(.008,.202,.172),lens,.022)
for o in list(scene.objects):
    if o in original or o.type!='MESH':continue
    bpy.context.view_layer.objects.active=o
    for m in list(o.modifiers):bpy.ops.object.modifier_apply(modifier=m.name)
    o.data.transform(Matrix.Scale(S,4));o.location*=S
    if o.name.startswith('Top headlight'):
        bpy.context.view_layer.update();mw=o.matrix_world.copy();o.parent=bpy.data.objects.get('03 Motor | assembly control');o.matrix_world=mw
# Small warm source inside each route holder, controlled with the same night switch.
for x,sgn in ((A,-1),(B,1)):
    ld=bpy.data.lights.new('Route holder | internal light','AREA');ld.shape='RECTANGLE';ld.size=.8*S;ld.size_y=.10*S
    ob=bpy.data.objects.new(ld.name,ld);group(current).objects.link(ob);ob.location=(Vector((x+sgn*.060,0,2.65))*S);ob.rotation_euler=Vector((sgn,0,0)).to_track_quat('-Z','Y').to_euler();ld.color=(1,.83,.60)
    dr=ld.driver_add('energy').driver;dr.expression='enabled*1.5';v=dr.variables.new();v.name='enabled';v.targets[0].id=control;v.targets[0].data_path='["enabled"]'
scene['DETAIL_REVISION']='V3.7: thin white cab wire mesh; white guards and opaque rain shutters; smaller grey upper glazing; recessed glazed route holders and switched top headlight.'
report={'revision':'V3.7','solid_shutters':sum('solid white rain shutter' in o.name for o in scene.objects),'fixed_upper_glass':sum('fixed upper glass' in o.name for o in scene.objects),'perforated_panels_remaining':sum('perforated grille' in o.name for o in scene.objects),'empty_meshes':[],'non_manifold':[]}
for o in scene.objects:
    if o.type!='MESH':continue
    if not len(o.data.vertices):report['empty_meshes'].append(o.name)
    bm=bmesh.new();bm.from_mesh(o.data);bad=sum(not e.is_manifold for e in bm.edges);bm.free()
    if bad:report['non_manifold'].append([o.name,bad])
(OUT/'mesh_lighting_audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
scene.eevee.taa_render_samples=64
scene.render.resolution_percentage=100;scene.render.resolution_x=1400;scene.render.resolution_y=1100
scene.camera=bpy.data.objects['Camera | corrected motor nose'];scene.render.filepath=str(OUT/'23_wire_mesh_cab.png');bpy.ops.render.render(write_still=True)
scene.camera=bpy.data.objects['Rear transition window inspection'];scene.render.filepath=str(OUT/'24_white_shutters_grey_glazing.png');bpy.ops.render.render(write_still=True)
control['enabled']=1.0;bpy.context.view_layer.update();scene.camera=bpy.data.objects['Camera | corrected motor nose'];scene.render.filepath=str(OUT/'25_illuminated_route_holder.png');bpy.ops.render.render(write_still=True)
control['enabled']=0.0;bpy.context.view_layer.update()
scene.camera=bpy.data.objects['Camera | front entrance-side overview']
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Kolkata_Tram_V3_7_Mesh_And_Lighting.blend'))
