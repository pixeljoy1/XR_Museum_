import bpy,math,bmesh,json
from pathlib import Path
out=Path('/Users/joy/Desktop/CODEX/kolkata_tram_2D_/V3_Model');S=1000/87
for k,o in enumerate(sorted([o for o in bpy.context.scene.objects if o.name.startswith('Manual retrieval | wound rope turn')],key=lambda o:o.name)):
 vs=[];fs=[]
 for i in range(64):
  t=2*math.pi*i/64
  for j in range(12):
   a=2*math.pi*j/12;r=.096+.010*math.cos(a);vs.append(((7.825+k*.014+.010*math.sin(a))*S,r*math.sin(t)*S,(1.48+r*math.cos(t))*S))
 for i in range(64):
  for j in range(12):fs.append((i*12+j,((i+1)%64)*12+j,((i+1)%64)*12+(j+1)%12,i*12+(j+1)%12))
 me=bpy.data.meshes.new('Seamless wound rope');me.from_pydata(vs,[],fs);me.materials.append(bpy.data.materials['Manual retrieval | black rope']);o.data=me
 from mathutils import Matrix
 o.matrix_world=Matrix.Identity(4)
audit=json.loads((out/'rear_cleanup_audit.json').read_text());audit['non_manifold']=[]
for o in bpy.context.scene.objects:
 if o.type!='MESH':continue
 bm=bmesh.new();bm.from_mesh(o.data);bad=sum(not e.is_manifold for e in bm.edges);bm.free()
 if bad:audit['non_manifold'].append([o.name,bad])
(out/'rear_cleanup_audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'Kolkata_Tram_V3_8_Clean_Rear_And_Rope.blend'))
