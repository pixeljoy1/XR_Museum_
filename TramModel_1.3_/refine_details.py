import bpy, math, json, ast, bmesh
from pathlib import Path
from mathutils import Vector, Matrix
OUT=Path('/Users/joy/Desktop/CODEX/kolkata_tram_2D_/V3_Model')
S=1000/87
scene=bpy.context.scene
collections={c.name:c for c in scene.collection.children}
bodymat=bpy.data.materials['Study | warm grey shell']
trim=bpy.data.materials['Study | frame edges']
metal=bpy.data.materials['Study | axle and fittings']
dark=bpy.data.materials['Study | running gear']
roofmat=bpy.data.materials['Study | removable roof']
current='10 End fittings | grille lamps fenders'
tree=ast.parse((OUT/'build_tram.py').read_text())
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name!='camera':
        exec(compile(ast.Module(body=[node],type_ignores=[]),'helpers','exec'),globals())
existing=set(scene.objects)
for o in list(scene.objects):
    if o.name.startswith(('Motor | front grille vertical','Motor | front grille horizontal')):
        bpy.data.objects.remove(o,do_unlink=True)
# Perforated mesh built directly from a tiled planar annulus, then welded.
# Only actual outside boundaries get sidewalls; adjoining tile edges are internal.
def perforated_panel(yc,width):
    nx=round(width/.075);nz=10;dy=width/nx;dz=.77/nz
    v=[];f=[]
    for iy in range(nx):
        for iz in range(nz):
            cy=yc-width/2+(iy+.5)*dy;cz=1.65+(iz+.5)*dz
            if yc==0 and abs(cy)<.20 and 1.88<cz<2.20:continue
            outer=[];inner=[]
            for k in range(16):
                t=2*math.pi*k/16
                co,si=math.cos(t),math.sin(t)
                fac=max(abs(co),abs(si))
                outer.append((cy+co/fac*dy/2,cz+si/fac*dz/2))
                inner.append((cy+co*.026,cz+si*.026))
            start=len(v)
            v.extend([(-7.726,y,z) for y,z in outer+inner])
            for k in range(16):
                j=(k+1)%16;f.append((start+k,start+j,start+16+j,start+16+k))
    o=mesh('Motor | circular perforated grille',v,f,dark)
    bm=bmesh.new();bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(o.data);bm.free()
    m=o.modifiers.new('Screen thickness','SOLIDIFY');m.thickness=.018
    bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier=m.name)
    return o
for yc,w in ((-.78,.60),(0,.83),(.78,.60)):perforated_panel(yc,w)

# Roof end fascia, following the barrel arc; no open gap below the crown.
for tag,a,b,col in [('Motor',-7.675,.175,'03 Motor | removable roof'),('Trailer',.595,7.675,'06 Trailer | removable roof')]:
    current=col
    for xx in (a,b):
        poly=[(-1.05,2.79),(1.05,2.79)]
        for j in range(25):
            t=math.pi/2-math.pi*j/24
            poly.append((1.05*math.sin(t),2.805+.34*math.cos(t)))
        n=len(poly);v=[(xx+dx,y,z) for dx in (-.025,.025) for y,z in poly]
        f=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        mesh(tag+' | roof curved end fascia',v,f,roofmat)
    if tag=='Motor':
        box('Motor | upper route lamp surround',(a-.046,0,2.99),(.09,.36,.29),trim,.045)
        box('Motor | upper route lamp face',(a-.10,0,2.99),(.023,.25,.20),bodymat,.025)

for o in list(scene.objects):
    if o in existing or o.type!='MESH':continue
    bpy.context.view_layer.objects.active=o
    for m in list(o.modifiers):bpy.ops.object.modifier_apply(modifier=m.name)
    o.data.transform(Matrix.Scale(S,4));o.location*=S
    o['scale']='1:87; millimetres'
# Rest the wheels on the top face of the display plinth.
bpy.data.objects['Display | removable plinth'].location.z+=.03*S

# Logical assembly roots: move a roof or a rolling axle as one assembly.
current='12 Assembly controls | select to move parts'
for colname in ('03 Motor | removable roof','06 Trailer | removable roof'):
    root=bpy.data.objects.new(colname.split(' | ')[0]+' | assembly control',None)
    group(current).objects.link(root);root.empty_display_type='PLAIN_AXES';root.empty_display_size=4
    for o in list(collections[colname].objects):
        transform=o.matrix_world.copy();o.parent=root;o.matrix_world=transform
for k in range(1,4):
    col=collections[f'08 Rolling wheelsets | bogie {k}']
    axles=[o for o in col.objects if ' | axle ' in o.name]
    bpy.context.view_layer.update()
    for axle in axles:
        root=bpy.data.objects.new(axle.name+' | roll control',None)
        group(current).objects.link(root);root.empty_display_type='PLAIN_AXES';root.empty_display_size=2
        root.location=axle.location
        bpy.context.view_layer.update()
        for o in list(col.objects):
            if abs(o.location.x-axle.location.x)<.01:
                transform=o.matrix_world.copy();o.parent=root;o.matrix_world=transform
        root['operation']='Rotate local Y for rolling. Physical axle and wheel retention require fabrication review.'

bpy.context.view_layer.update()
report={'scale':'1:87','units':'mm','objects':len(scene.objects),'meshes':0,'empty':[],'non_manifold':[]}
for o in scene.objects:
    if o.type!='MESH':continue
    report['meshes']+=1
    if not len(o.data.vertices):report['empty'].append(o.name);continue
    bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bad=sum(not e.is_manifold for e in bm.edges)
    if bad:report['non_manifold'].append({'object':o.name,'edges':bad})
    bm.to_mesh(o.data);bm.free()
bpy.context.view_layer.update()
report['dimensions']={o.name:[round(float(d),3) for d in o.dimensions] for o in scene.objects if o.name in ('Motor | body shell','Trailer | body shell','Display | removable plinth')}
report['limits']=['Mesh closedness does not certify assembly clearance, minimum printable features, or historical dimensions.','Parts are separate solids; overlaps need resolving before a manufacturing export.']
(OUT/'geometry_audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
for cam,name in [('Camera | front entrance-side overview','01_overview'),('Camera | entrance-side orthographic','02_entrance_side'),('Camera | opposite-side orthographic','03_opposite_side')]:
    scene.camera=bpy.data.objects[cam];scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
for name in ('03 Motor | removable roof','06 Trailer | removable roof'):collections[name].hide_render=True
scene.camera=bpy.data.objects['Camera | interior inspection'];scene.render.filepath=str(OUT/'04_interior.png');bpy.ops.render.render(write_still=True)
for name in ('03 Motor | removable roof','06 Trailer | removable roof'):collections[name].hide_render=False
scene.camera=bpy.data.objects['Camera | front entrance-side overview']
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Kolkata_Tram_V3_Geometry.blend'))
