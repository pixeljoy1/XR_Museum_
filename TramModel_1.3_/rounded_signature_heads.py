import bpy,bmesh,ast,math,json
from pathlib import Path
from mathutils import Vector,Matrix
OUT=Path('/Users/joy/Desktop/CODEX/kolkata_tram_2D_/V3_Model');S=1000/87;scene=bpy.context.scene;collections={c.name:c for c in scene.collection.children}
bodymat=bpy.data.materials['Modern | warm white enamel'];trim=bodymat;metal=bpy.data.materials['Roof equipment | dull aluminium'];dark=bpy.data.materials['Modern | black housings']
for node in ast.parse((OUT/'build_tram.py').read_text()).body:
 if isinstance(node,ast.FunctionDef) and node.name!='camera':exec(compile(ast.Module(body=[node],type_ignores=[]),'helpers','exec'),globals())
A=-7.675;B=7.675
gold=bpy.data.materials['Modern | ochre roof rim'];roofmat=bpy.data.materials['Modern | supplied roof colour and seam map'];rubber=bpy.data.materials['Windows | thin black rubber seals'];glass=bpy.data.materials['Windows | clear lightly reflective glass'];card=bpy.data.materials['Route display | illuminated ivory card'];lens=bpy.data.materials['Headlamp | optical lens']
# Preserve earlier checkpoints; replace only roof skins and obsolete applied head fittings.
for o in list(scene.objects):
 if o.name.startswith(('Route display |','Top headlight |')) or 'roof curved end fascia' in o.name or 'lift-off barrel roof' in o.name or 'plain inset roof end' in o.name:
  bpy.data.objects.remove(o,do_unlink=True)
original=set(scene.objects)
def half(d,pts):
 for (a,u),(b,v) in zip(pts,pts[1:]):
  if d<=b:return u+(v-u)*max(0,d-a)/(b-a)
 return pts[-1][1]
def width(x,motor):
 if motor:return min(half(x-A,[(0,.84),(.13,1.02),(1.55,1.45)]),half(.175-x,[(0,1.15),(.30,1.45)]))
 return min(half(B-x,[(0,.90),(.16,1.07),(1.15,1.45)]),half(x-.595,[(0,1.15),(.30,1.45)]))
for motor in (True,False):
 tag='Motor' if motor else 'Trailer';current='03 Motor | removable roof' if motor else '06 Trailer | removable roof';a=A if motor else .595;b=.175 if motor else B
 # Dense rounded longitudinal shoulder: actual geometry, rather than smooth shading on a chamfer.
 xs=[a+(b-a)*i/240 for i in range(241)];N=64;verts=[]
 for inner in (False,True):
  for x in xs:
   d=x-a if motor else b-x;di=b-x if motor else x-a
   hw=width(x,motor)-(.055 if inner else 0)
   # Smooth plan folds over a short local interval, retaining the established end widths.
   if d>.08 and di>.08:hw=sum(width(max(a,min(b,x+k*.012)),motor) for k in range(-5,6))/11-(.055 if inner else 0)
   roll=math.sqrt(max(0,1-(1-min(d/.38,1))**2))
   crown=.195+.15*roll
   if di<.30:crown-=.045*(1-di/.30)**2
   for j in range(N+1):
    t=-math.pi/2+math.pi*j/N
    verts.append((x,hw*math.sin(t),2.86+crown*math.cos(t)-(.065 if inner else 0)))
 nr=len(xs);stride=nr*(N+1);faces=[];goldfaces=[]
 for layer in (0,1):
  off=layer*stride
  for i in range(nr-1):
   d=((xs[i]+xs[i+1])/2-a) if motor else (b-(xs[i]+xs[i+1])/2)
   for j in range(N):
    k=off+i*(N+1)+j;f=(k,k+N+1,k+N+2,k+1);faces.append(f if layer==0 else tuple(reversed(f)));goldfaces.append(d<.40 and layer==0)
 boundary=list(range(N+1))+[i*(N+1)+N for i in range(1,nr)]+list(range((nr-1)*(N+1)+N-1,(nr-1)*(N+1)-1,-1))+[i*(N+1) for i in range(nr-2,0,-1)]
 for ii,k in enumerate(boundary):
  j=boundary[(ii+1)%len(boundary)];faces.append((k,j,j+stride,k+stride));goldfaces.append(False)
 roof=mesh(tag+' | rounded signature roof',verts,faces,roofmat);roof.data.materials.append(gold)
 for p,g in zip(roof.data.polygons,goldfaces):p.use_smooth=True;p.material_index=int(g)
 roof.data.use_auto_smooth=True;roof.data.auto_smooth_angle=math.radians(45)
 # Thin closing panel beneath crown, inset into roof to avoid a stuck-on fascia.
 x=a if motor else b;sgn=1 if motor else -1;w=width(x,motor)
 poly=[(-w,2.79),(w,2.79)]+[(w*math.sin(math.pi/2-math.pi*j/N),2.86+.195*math.cos(math.pi/2-math.pi*j/N)) for j in range(N+1)]
 nv=len(poly);vs=[(x+sgn*d,y,z) for d in (.004,.070) for y,z in poly];fs=[tuple(reversed(range(nv))),tuple(range(nv,2*nv))]+[(i,(i+1)%nv,(i+1)%nv+nv,i+nv) for i in range(nv)]
 cap=mesh(tag+' | integrated rounded end closure',vs,fs,gold)
 if motor:
  # Raised box is blended into the crown; its recessed lens is fitted into the box.
  pod=box('Motor | fused top lamp pedestal',(A+.095,0,3.035),(.32,.40,.34),gold,.045)
  bpy.context.view_layer.objects.active=pod;bpy.ops.object.modifier_apply(modifier=pod.modifiers[0].name)
  # Union into the end closure yields a single solid gold head assembly.
  bpy.context.view_layer.objects.active=cap;mod=cap.modifiers.new('Fused lamp pedestal','BOOLEAN');mod.operation='UNION';mod.solver='EXACT';mod.object=pod;bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(pod,do_unlink=True)
  # Aperture cuts the pedestal, retaining a back wall for the optical assembly.
  cutter=cutbox('Top optical recess',(A-.045,0,3.06),(.11,.255,.24),.035);boolean(cap,[cutter])
  frame('Top headlight | inset rubber',(A-.068,0,3.06),.275,.26,.017,.012,'END',rubber)
  box('Top headlight | inset optical lens',(A-.061,0,3.06),(.005,.242,.225),lens,.032)
 # Rounded inset destination holder in the white header; no deep external plaque.
 current='10 End fittings | grille lamps fenders';sgn=-1 if motor else 1;x=A if motor else B
 shell=bpy.data.objects[tag+' | body shell']
 # Shell uses mm; cut with separately scaled rounded cutter.
 cutter=cutbox('Header display recess',(x,0,2.65),(.20,1.12,.235),.070)
 cutter.data.transform(Matrix.Scale(S,4));cutter.location*=S;boolean(shell,[cutter])
 box(tag+' | route display recessed back',(x-sgn*.050,0,2.65),(.025,1.13,.245),dark,.065)
 frame(tag+' | pill route display seal',(x+sgn*.006,0,2.65),1.15,.26,.022,.014,'END',rubber)
 box(tag+' | illuminated route card',(x-sgn*.027,0,2.65),(.004,1.075,.185),card,.060)
 box(tag+' | inset route glass',(x+sgn*.004,0,2.65),(.004,1.105,.215),glass,.063)
for o in list(scene.objects):
 if o in original or o.type!='MESH':continue
 bpy.context.view_layer.objects.active=o
 for m in list(o.modifiers):bpy.ops.object.modifier_apply(modifier=m.name)
 o.data.transform(Matrix.Scale(S,4));o.location*=S
 if any(c.name in ('03 Motor | removable roof','06 Trailer | removable roof') for c in o.users_collection):
  col=o.users_collection[0].name;root=bpy.data.objects.get(col.replace('removable roof','assembly control'))
  if root:
   bpy.context.view_layer.update();mw=o.matrix_world.copy();o.parent=root;o.matrix_world=mw
report={'revision':'V3.10','roof_end_roll_length_prototype_m':.38,'non_manifold':[]}
for o in scene.objects:
 if o.type!='MESH':continue
 bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bad=sum(not e.is_manifold for e in bm.edges);bm.to_mesh(o.data);bm.free()
 if bad:report['non_manifold'].append([o.name,bad])
(OUT/'rounded_head_audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
scene.render.resolution_x=1500;scene.render.resolution_y=1200
for cam,name in [('Camera | corrected motor nose','31_rounded_driver_head.png'),('Camera | corrected trailer tail','32_rounded_trailer_head.png')]:
 scene.camera=bpy.data.objects[cam];scene.render.filepath=str(OUT/name);bpy.ops.render.render(write_still=True)
scene.camera=bpy.data.objects['Camera | corrected motor nose'];bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Kolkata_Tram_V3_10_Rounded_Signature_Heads.blend'))
