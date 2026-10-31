"""
XR_Museum_: the gallery floor, in the language of the Bihar Museum (Maki + Opolis).

Sequence, the way the real building works: a lobby with backlit teak screen walls and an oval
dish of light in the ceiling, then a tapered sandstone corridor with recessed light slots, then
the hall itself. The hall is a triangle with its three corners cut back into alcoves, one
masterpiece in each, under a big elliptical skylight.

Materials: near-black polished stone floor, Dholpur sandstone ashlar, red travertine, teak.
Light: a raking sun through tall slot windows, the two skylights, warm cove light behind the
teak, and one spot per alcove.

Everything is baked in Cycles to a single lighting atlas, so the page needs no runtime lights
for the room. Names drive gameplay: WALK_* is standable, everything else blocks (see
XR_LOCOMOTION_SPEC.md).

Run:
  Blender -b -P build/build_museum.py -- preview     # Cycles stills to build/preview_*.png
  Blender -b -P build/build_museum.py -- bake        # bake + export docs/models/museum.glb
"""
import bpy, bmesh, math, json, os, sys, random
from mathutils import Vector, Matrix

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else ['preview']
# When this file is exec'd inside a running Blender, a MUSEUM_MODE global set beforehand wins,
# so the geometry can be built and looked at without starting a render.
MODE = globals().get('MUSEUM_MODE', ARGS[0])
ROOT = '/Users/joy/Desktop/VSCODE/XR_Museum_/'
random.seed(7)

# ---------------------------------------------------------------- dimensions (metres)
R        = 14.0        # circumradius of the hall triangle; inradius is R/2 = 7
CHAM     = 4.8         # how far back each corner is cut: also the width of the alcove mouth
ALC_D    = 2.9         # alcove depth, outward from the mouth
H_HALL   = 6.8         # hall ceiling
H_ALC    = 4.2         # alcove soffit
WALL_T   = 0.35
DOOR_W, DOOR_H = 3.4, 3.4

COR_Y0, COR_Y1 = -19.0, -7.0      # corridor runs from the lobby to the hall's south wall
COR_HW0, COR_HW1 = 1.65, 2.40     # half width: it splays open towards the hall
H_COR    = 3.6
COR_LEAN = 9.0                    # degrees the corridor walls lean in at the top

LOB_X, LOB_Y0, LOB_Y1 = 5.2, -26.5, -19.0
H_LOB    = 4.6

SKY_A, SKY_B, SKY_DEPTH = 4.75, 3.25, 1.55    # hall skylight: elliptical dish, semi-axes and rise
LSKY_A, LSKY_B, LSKY_DEPTH = 3.0, 2.0, 1.05   # lobby skylight

CORNERS = [Vector((R * math.cos(math.radians(90 + 120 * i)),
                   R * math.sin(math.radians(90 + 120 * i)), 0)) for i in range(3)]

# ---------------------------------------------------------------- scene reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# Blender block-buffers stdout when it is redirected, so progress goes to a file we can tail.
import time
_T0 = time.time()
_LOG = open(ROOT + 'build/build.log', 'w')


def log(msg):
    _LOG.write('%7.1fs  %s\n' % (time.time() - _T0, msg))
    _LOG.flush()


log('start mode=%s' % MODE)


# ---------------------------------------------------------------- materials
def mat(name, color, rough=0.85, metal=0.0, emit=None, emit_str=0.0, backface=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if emit is not None:
        bsdf.inputs['Emission'].default_value = (*emit, 1)
        bsdf.inputs['Emission Strength'].default_value = emit_str
    m.use_backface_culling = backface          # False -> doubleSided in glTF, so walls block from both sides
    return m


def add_noise(m, scale, detail, strength, dark=0.75):
    """Break up a flat colour with a little stone mottling, mixed into Base Color."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    base = bsdf.inputs['Base Color'].default_value[:3]
    tex = nt.nodes.new('ShaderNodeTexNoise')
    tex.inputs['Scale'].default_value = scale
    tex.inputs['Detail'].default_value = detail
    mix = nt.nodes.new('ShaderNodeMixRGB')
    mix.blend_type = 'MIX'
    mix.inputs['Fac'].default_value = strength
    mix.inputs['Color1'].default_value = (*base, 1)
    mix.inputs['Color2'].default_value = (base[0] * dark, base[1] * dark, base[2] * dark, 1)
    nt.links.new(tex.outputs['Fac'], mix.inputs['Fac'])
    nt.links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])
    return mix


def add_bricks(m, scale, mortar, mortar_col, row_h=0.42, brick_w=0.5, offset=0.5, wall=False):
    """Ashlar joints (sandstone) or the floor's tile grid, straight into Base Color.

    The Brick texture lays its pattern out in the X/Y of whatever vector it is given, which is
    right for a floor and useless on a wall (you get stripes). For walls we hand it
    (x + y, z): one horizontal coordinate that advances along a wall running any direction,
    and height as the second axis, so the courses are level whichever way the wall faces.
    """
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    base = bsdf.inputs['Base Color'].default_value[:3]
    coord = nt.nodes.new('ShaderNodeTexCoord')
    src = coord.outputs['Object']
    if wall:
        sep = nt.nodes.new('ShaderNodeSeparateXYZ')
        add = nt.nodes.new('ShaderNodeMath')
        add.operation = 'ADD'
        comb = nt.nodes.new('ShaderNodeCombineXYZ')
        nt.links.new(coord.outputs['Object'], sep.inputs['Vector'])
        nt.links.new(sep.outputs['X'], add.inputs[0])
        nt.links.new(sep.outputs['Y'], add.inputs[1])
        nt.links.new(add.outputs['Value'], comb.inputs['X'])
        nt.links.new(sep.outputs['Z'], comb.inputs['Y'])
        src = comb.outputs['Vector']
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (scale, scale, scale)
    br = nt.nodes.new('ShaderNodeTexBrick')
    br.offset = offset
    br.squash = 1.0
    br.inputs['Color1'].default_value = (*base, 1)
    br.inputs['Color2'].default_value = (base[0] * 0.93, base[1] * 0.93, base[2] * 0.93, 1)
    br.inputs['Mortar'].default_value = (*mortar_col, 1)
    br.inputs['Scale'].default_value = 1.0
    br.inputs['Mortar Size'].default_value = mortar
    br.inputs['Bias'].default_value = 0.0
    br.inputs['Brick Width'].default_value = brick_w
    br.inputs['Row Height'].default_value = row_h
    nt.links.new(src, mp.inputs['Vector'])
    nt.links.new(mp.outputs['Vector'], br.inputs['Vector'])
    nt.links.new(br.outputs['Color'], bsdf.inputs['Base Color'])
    return br


def add_strata(m, scale, strength):
    """Travertine: horizontal bands with a wandering edge."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    base = bsdf.inputs['Base Color'].default_value[:3]
    coord = nt.nodes.new('ShaderNodeTexCoord')
    w = nt.nodes.new('ShaderNodeTexWave')
    w.wave_type = 'BANDS'
    w.bands_direction = 'Z'
    w.inputs['Scale'].default_value = scale
    w.inputs['Distortion'].default_value = 5.0
    w.inputs['Detail'].default_value = 8.0
    w.inputs['Detail Scale'].default_value = 1.6
    mix = nt.nodes.new('ShaderNodeMixRGB')
    mix.inputs['Fac'].default_value = strength
    mix.inputs['Color1'].default_value = (*base, 1)
    mix.inputs['Color2'].default_value = (min(base[0] * 1.45, 1), base[1] * 1.15, base[2] * 0.82, 1)
    nt.links.new(coord.outputs['Object'], w.inputs['Vector'])
    nt.links.new(w.outputs['Fac'], mix.inputs['Fac'])
    nt.links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])


M = {}
M['floor']     = mat('MD_floor', (0.016, 0.016, 0.019), rough=0.07)
add_bricks(M['floor'], 1 / 1.6, 0.010, (0.038, 0.037, 0.035), row_h=1.0, brick_w=1.0, offset=0.0)
M['stone']     = mat('MD_sandstone', (0.430, 0.330, 0.188), rough=0.86)
add_bricks(M['stone'], 1 / 1.15, 0.008, (0.330, 0.255, 0.145), row_h=0.52, brick_w=0.78, offset=0.5, wall=True)
M['stone2']    = mat('MD_sandstone_plain', (0.430, 0.330, 0.188), rough=0.86)
add_noise(M['stone2'], 9, 5, 0.5, 0.86)
M['travertine'] = mat('MD_travertine', (0.355, 0.120, 0.052), rough=0.42)
add_strata(M['travertine'], 26, 1.0)
M['teak']      = mat('MD_teak', (0.098, 0.033, 0.013), rough=0.42)
add_noise(M['teak'], 40, 8, 0.45, 0.6)
M['plaster']   = mat('MD_plaster', (0.80, 0.785, 0.755), rough=0.92)
M['plinth']    = mat('MD_plinth', (0.030, 0.030, 0.033), rough=0.40)
M['brass']     = mat('MD_brass', (0.62, 0.44, 0.14), rough=0.35, metal=0.85)
M['glass']     = mat('MD_glass', (0.75, 0.82, 0.86), rough=0.08)
M['emit_warm'] = mat('MD_emit_warm', (0, 0, 0), emit=(1.0, 0.55, 0.22), emit_str=34.0)
M['emit_cove'] = mat('MD_emit_cove', (0, 0, 0), emit=(1.0, 0.66, 0.34), emit_str=16.0)
M['emit_sky']  = mat('MD_emit_sky', (0, 0, 0), emit=(0.80, 0.88, 1.0), emit_str=26.0)
M['emit_dome'] = mat('MD_emit_dome', (0, 0, 0), emit=(1.0, 0.96, 0.88), emit_str=7.0)
M['emit_slot'] = mat('MD_emit_slot', (0, 0, 0), emit=(1.0, 0.76, 0.46), emit_str=26.0)
M['shell']     = mat('MD_shell', (0.02, 0.02, 0.02), rough=1.0)

log('materials done')

MESHES = []          # everything that will be exported


# ---------------------------------------------------------------- geometry helpers
def finish(ob, m, export=True):
    ob.data.materials.append(m)
    for p in ob.data.polygons:
        p.use_smooth = False
    if export:
        MESHES.append(ob)
    return ob


def box(name, m, c, s, rz=0.0, ry=0.0, export=True):
    """Axis-aligned box of size s centred at c, optionally spun about Z then tipped about its own Y."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(s), verts=bm.verts)
    if ry:
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(ry), 3, 'Y'))
    if rz:
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(rz), 3, 'Z'))
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(c))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return finish(ob, m, export)


def face(name, m, pts, export=True):
    """One flat n-gon. Materials are double sided, so a single face still blocks from both sides."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new(Vector(p)) for p in pts]
    bm.faces.new(vs)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return finish(ob, m, export)


def wall(name, m, p0, p1, z0, z1, t=WALL_T, out=1.0):
    """A wall whose INNER face runs from p0 to p1; it is given thickness towards `out`."""
    p0, p1 = Vector(p0), Vector(p1)
    d = (p1 - p0)
    L = d.length
    d.normalize()
    n = Vector((-d.y, d.x, 0)) * out          # left of the direction of travel
    c = (p0 + p1) / 2 + n * (t / 2)
    c.z = (z0 + z1) / 2
    return box(name, m, c, (L, t, z1 - z0), rz=math.degrees(math.atan2(d.y, d.x)))


def ring(name, m, outer, inner, export=True):
    """Bridge two closed loops of the same length: the ceiling with its skylight hole cut out."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vo = [bm.verts.new(Vector(p)) for p in outer]
    vi = [bm.verts.new(Vector(p)) for p in inner]
    n = len(outer)
    for i in range(n):
        bm.faces.new((vo[i], vo[(i + 1) % n], vi[(i + 1) % n], vi[i]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return finish(ob, m, export)


def resample(pts, n):
    """Walk a closed polygon and return n points spaced equally along its perimeter."""
    segs = [(Vector(pts[i]), Vector(pts[(i + 1) % len(pts)])) for i in range(len(pts))]
    total = sum((b - a).length for a, b in segs)
    out, step, acc, si = [], total / n, 0.0, 0
    for i in range(n):
        t = i * step
        while si < len(segs) - 1 and acc + (segs[si][1] - segs[si][0]).length < t:
            acc += (segs[si][1] - segs[si][0]).length
            si += 1
        a, b = segs[si]
        k = (t - acc) / max((b - a).length, 1e-6)
        out.append(a + (b - a) * k)
    return out


def ceiling_with_hole(name, m, poly, z, cx, cy, a, b, n=96):
    """A ceiling slab with an elliptical hole: the two loops are matched by polar angle about the
    hole's centre, not by arc length, or the bridge comes out twisted and seals the skylight."""
    outer = resample([(p[0], p[1], z) for p in poly], n)
    inner = [Vector((cx + a * math.cos(t), cy + b * math.sin(t), z))
             for t in [math.atan2(p.y - cy, p.x - cx) for p in outer]]
    return ring(name, m, outer, inner)


def dome(name, m, cx, cy, a, b, z, rise, n=64, rings=7):
    """A shallow elliptical dish set above a hole in the ceiling: the building's one soft gesture."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    loops = []
    for r in range(rings + 1):
        t = r / rings
        k = math.cos(t * math.pi / 2)                     # radius falls off as a cosine: a true dish
        zz = z + math.sin(t * math.pi / 2) * rise
        if r == rings:
            loops.append([bm.verts.new((cx, cy, zz))])
        else:
            loops.append([bm.verts.new((cx + a * k * math.cos(2 * math.pi * i / n),
                                        cy + b * k * math.sin(2 * math.pi * i / n), zz)) for i in range(n)])
    for r in range(rings):
        lo, hi = loops[r], loops[r + 1]
        if len(hi) == 1:
            for i in range(n):
                bm.faces.new((lo[i], lo[(i + 1) % n], hi[0]))
        else:
            for i in range(n):
                bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return finish(ob, m)


# ---------------------------------------------------------------- the hall plan
def chamfer_points():
    """IN_i and OUT_i: where each corner is cut back. IN_i -> OUT_i is the alcove mouth."""
    P = []
    for i in range(3):
        c = CORNERS[i]
        prev = (CORNERS[(i - 1) % 3] - c).normalized()
        nxt = (CORNERS[(i + 1) % 3] - c).normalized()
        P.append((c + prev * CHAM, c + nxt * CHAM))
    return P


CH = chamfer_points()
HALL = []                                   # the hall outline, counter-clockwise
for i in range(3):
    HALL += [CH[i][0], CH[i][1]]

ALCOVE = []                                 # centre, outward normal, and the frame of each alcove
for i in range(3):
    a, b = CH[i]
    mid = (a + b) / 2
    nrm = CORNERS[i].normalized()
    ALCOVE.append(dict(i=i, mouth=(a, b), mid=mid, n=nrm,
                       tan=Vector((-nrm.y, nrm.x, 0)),
                       back=mid + nrm * ALC_D))


# ---------------------------------------------------------------- floors
face('WALK_floor_hall', M['floor'], [(p.x, p.y, 0) for p in HALL])
for A in ALCOVE:
    a, b = A['mouth']
    n = A['n'] * ALC_D
    face('WALK_floor_alcove%d' % A['i'], M['floor'],
         [(a.x, a.y, 0), (b.x, b.y, 0), (b.x + n.x, b.y + n.y, 0), (a.x + n.x, a.y + n.y, 0)])

log('hall floors done')

face('WALK_floor_corridor', M['floor'],
     [(-COR_HW0, COR_Y0, 0), (COR_HW0, COR_Y0, 0), (COR_HW1, COR_Y1, 0), (-COR_HW1, COR_Y1, 0)])
face('WALK_floor_lobby', M['floor'],
     [(-LOB_X, LOB_Y0, 0), (LOB_X, LOB_Y0, 0), (LOB_X, LOB_Y1, 0), (-LOB_X, LOB_Y1, 0)])


# ---------------------------------------------------------------- hall walls
# edge 0: OUT_0 -> IN_1   (north-west)  red travertine
# edge 1: OUT_1 -> IN_2   (south)       sandstone with the tall slot windows and the doorway
# edge 2: OUT_2 -> IN_0   (north-east)  backlit teak screen
EDGES = [(CH[i][1], CH[(i + 1) % 3][0]) for i in range(3)]

# -- edge 0: travertine, with a clerestory band left open above it
p0, p1 = EDGES[0]
wall('SOLID_wall_travertine', M['travertine'], p0, p1, 0, 5.5)
wall('SOLID_wall_trav_head', M['stone2'], p0, p1, 6.25, H_HALL)
d = (p1 - p0).normalized()
nn = Vector((-d.y, d.x, 0))
for k in range(1, 7):                                           # mullions in the clerestory
    c = p0 + d * ((p1 - p0).length * k / 7) + nn * (WALL_T / 2)
    box('SOLID_mullion_%d' % k, M['stone2'], (c.x, c.y, 5.875), (0.12, WALL_T, 0.75),
        rz=math.degrees(math.atan2(d.y, d.x)))
box('SOLID_clere_sky', M['emit_sky'],
    ((p0.x + p1.x) / 2 + nn.x * 0.9, (p0.y + p1.y) / 2 + nn.y * 0.9, 5.875),
    ((p1 - p0).length, 0.06, 0.75), rz=math.degrees(math.atan2(d.y, d.x)))

# -- edge 1: the south wall. Doorway in the middle, two tall slot windows either side.
p0, p1 = EDGES[1]
d = (p1 - p0).normalized()
L = (p1 - p0).length
nn = Vector((-d.y, d.x, 0))
SLOTS = [0.17, 0.27, 0.73, 0.83]                                # fractions along the wall
cuts = []
for s in SLOTS:
    cuts.append((s - 0.016, s + 0.016))
cuts.append((0.5 - DOOR_W / 2 / L, 0.5 + DOOR_W / 2 / L))
cuts.sort()
seg_start = 0.0
for j, (c0, c1) in enumerate(cuts):
    if c0 > seg_start:
        wall('SOLID_wall_south_%d' % j, M['stone'], p0 + d * (seg_start * L), p0 + d * (c0 * L), 0, H_HALL)
    seg_start = c1
wall('SOLID_wall_south_end', M['stone'], p0 + d * (seg_start * L), p1, 0, H_HALL)
# over the doorway, and the daylight behind each slot
wall('SOLID_wall_south_lintel', M['stone'],
     p0 + d * ((0.5 - DOOR_W / 2 / L) * L), p0 + d * ((0.5 + DOOR_W / 2 / L) * L), DOOR_H, H_HALL)
for s in SLOTS:
    c = p0 + d * (s * L) + nn * 0.70
    box('SOLID_slotlight_%.2f' % s, M['emit_sky'], (c.x, c.y, 2.6), (0.5, 0.06, 5.0),
        rz=math.degrees(math.atan2(d.y, d.x)))
    for z0, z1 in [(0.0, 0.18), (5.0, 5.3)]:                    # slot sills and heads
        cc = p0 + d * (s * L) + nn * (WALL_T / 2)
        box('SOLID_slotcap_%.2f_%.0f' % (s, z0), M['stone'], (cc.x, cc.y, (z0 + z1) / 2),
            (0.34, WALL_T, z1 - z0), rz=math.degrees(math.atan2(d.y, d.x)))

log('walls 0,1 done')

# -- edge 2: the teak screen. Short blocks of varying depth, backlit (the lobby wall of image 1).
p0, p1 = EDGES[2]
d = (p1 - p0).normalized()
L = (p1 - p0).length
nn = Vector((-d.y, d.x, 0))
wall('SOLID_wall_screen_back', M['stone2'], p0, p1, 0, H_HALL, t=0.12)
box('SOLID_screen_glow', M['emit_warm'],
    ((p0.x + p1.x) / 2 + nn.x * 0.10, (p0.y + p1.y) / 2 + nn.y * 0.10, H_HALL / 2),
    (L, 0.03, H_HALL - 0.2), rz=math.degrees(math.atan2(d.y, d.x)))
rzw = math.degrees(math.atan2(d.y, d.x))
ncol = int(L / 0.145)
for c in range(ncol):
    x = (c + 0.5) * L / ncol
    z = 0.0
    while z < H_HALL - 0.1:
        h = random.uniform(0.35, 1.5)
        if z + h > H_HALL - 0.1:
            h = H_HALL - 0.1 - z
        if random.random() < 0.88 and h > 0.12:
            dep = random.uniform(0.09, 0.30)
            cc = p0 + d * x + nn * (dep / 2 - 0.02)
            box('SOLID_slat_%d_%d' % (c, int(z * 10)), M['teak'],
                (cc.x, cc.y, z + h / 2), (0.088, dep, h * 0.97), rz=rzw)
        z += h + random.uniform(0.04, 0.14)

log('teak screen done')

# -- alcoves: sandstone box, a cove slot each side, a soffit, and a spot above the plinth
for A in ALCOVE:
    a, b = A['mouth']
    n, t = A['n'], A['tan']
    ab = a + n * ALC_D
    bb = b + n * ALC_D
    wall('SOLID_alc%d_back' % A['i'], M['stone'], bb, ab, 0, H_ALC)
    wall('SOLID_alc%d_side0' % A['i'], M['stone2'], a, ab, 0, H_ALC)
    wall('SOLID_alc%d_side1' % A['i'], M['stone2'], bb, b, 0, H_ALC)
    face('SOLID_alc%d_soffit' % A['i'], M['plaster'],
         [(a.x, a.y, H_ALC), (ab.x, ab.y, H_ALC), (bb.x, bb.y, H_ALC), (b.x, b.y, H_ALC)])
    # the wall above the alcove mouth, back up to the hall ceiling
    wall('SOLID_alc%d_head' % A['i'], M['stone2'], a, b, H_ALC, H_HALL, out=-1.0)
    # warm cove slots washing the back wall
    for s in (-1, 1):
        c = A['mid'] + n * (ALC_D - 0.12) + t * (s * (CHAM / 2 - 0.22))
        box('SOLID_alc%d_cove%d' % (A['i'], s), M['emit_cove'], (c.x, c.y, H_ALC / 2),
            (0.07, 0.07, H_ALC - 0.5), rz=math.degrees(math.atan2(t.y, t.x)))

# -- hall ceiling: a ring from the hall outline to the skylight ellipse, plus the dish above
ceiling_with_hole('SOLID_ceiling_hall', M['plaster'], [(p.x, p.y) for p in HALL],
                  H_HALL, 0, 0, SKY_A, SKY_B, n=96)
dome('SOLID_skylight_hall', M['emit_dome'], 0, 0, SKY_A, SKY_B, H_HALL, SKY_DEPTH)


log('hall ceiling done')

# ---------------------------------------------------------------- corridor (image 3)
# Walls lean in at the top and splay open towards the hall; recessed light slots in a diagonal rhythm.
for s in (-1, 1):
    p0 = Vector((s * COR_HW0, COR_Y0, 0))
    p1 = Vector((s * COR_HW1, COR_Y1, 0))
    d = (p1 - p0).normalized()
    L = (p1 - p0).length
    rz = math.degrees(math.atan2(d.y, d.x))
    nn = Vector((-d.y, d.x, 0)) * s
    lean = math.radians(COR_LEAN)
    # the leaning face, as one slab tipped about its own long axis
    c = (p0 + p1) / 2 - nn * (WALL_T / 2)
    hmid = H_COR / 2
    cc = c + nn * (-math.sin(lean) * hmid)
    ob = box('SOLID_cor_wall%d' % s, M['stone'], (cc.x, cc.y, hmid), (L, WALL_T, H_COR / math.cos(lean)))
    # tip it about its own length so the top leans in over the walker (the splayed section of image 3)
    pivot = Vector((cc.x, cc.y, hmid))
    ob.data.transform(Matrix.Translation(-pivot))
    ob.data.transform(Matrix.Rotation(-lean * s, 4, 'Y'))
    ob.data.transform(Matrix.Translation(pivot))
    # light slots: two rows, each column stepped so the pattern reads diagonally
    nslot = 7
    for k in range(nslot):
        f = (k + 0.5) / nslot
        base = p0 + d * (f * L)
        for row, zc in enumerate((1.05, 2.25)):
            zz = zc + (k % 2) * 0.16
            off = -math.sin(lean) * zz
            cpt = base + nn * (off + 0.03)
            box('SOLID_cor_slot%d_%d_%d' % (s, k, row), M['emit_slot'],
                (cpt.x, cpt.y, zz), (0.10, 0.05, 0.84), rz=rz)
    box('SOLID_cor_fascia%d' % s, M['stone2'],
        ((p0.x + p1.x) / 2 - nn.x * 0.1, (p0.y + p1.y) / 2 - nn.y * 0.1, H_COR + 0.1),
        (L, 0.5, 0.2), rz=rz)

face('SOLID_cor_ceiling', M['plaster'],
     [(-COR_HW0, COR_Y0, H_COR), (COR_HW0, COR_Y0, H_COR), (COR_HW1, COR_Y1, H_COR), (-COR_HW1, COR_Y1, H_COR)])
# the lit sandstone end wall you see down the corridor (image 3) is the hall's south wall beyond the door


log('corridor done')

# ---------------------------------------------------------------- lobby (image 1)
LW = [((-LOB_X, LOB_Y0), (-LOB_X, LOB_Y1)), ((LOB_X, LOB_Y1), (LOB_X, LOB_Y0))]
for li, (a, b) in enumerate(LW):
    a = Vector((a[0], a[1], 0))
    b = Vector((b[0], b[1], 0))
    d = (b - a).normalized()
    L = (b - a).length
    rz = math.degrees(math.atan2(d.y, d.x))
    nn = Vector((-d.y, d.x, 0))
    wall('SOLID_lob_back%d' % li, M['stone2'], a, b, 0, H_LOB, t=0.12)
    box('SOLID_lob_glow%d' % li, M['emit_warm'],
        ((a.x + b.x) / 2 + nn.x * 0.10, (a.y + b.y) / 2 + nn.y * 0.10, H_LOB / 2 + 0.3),
        (L, 0.03, H_LOB - 1.0), rz=rz)
    ncol = int(L / 0.145)
    for c in range(ncol):
        x = (c + 0.5) * L / ncol
        z = 0.9
        while z < H_LOB - 0.1:
            h = random.uniform(0.3, 1.2)
            if z + h > H_LOB - 0.1:
                h = H_LOB - 0.1 - z
            if random.random() < 0.88 and h > 0.12:
                dep = random.uniform(0.08, 0.26)
                cc = a + d * x + nn * (dep / 2 - 0.02)
                box('SOLID_lobslat_%d_%d_%d' % (li, c, int(z * 10)), M['teak'],
                    (cc.x, cc.y, z + h / 2), (0.088, dep, h * 0.97), rz=rz)
            z += h + random.uniform(0.04, 0.14)
    box('SOLID_lob_dado%d' % li, M['stone'],
        ((a.x + b.x) / 2 + nn.x * 0.06, (a.y + b.y) / 2 + nn.y * 0.06, 0.45), (L, 0.12, 0.9), rz=rz)

# lobby end wall with the entrance doors (shut: this is where you came in)
wall('SOLID_lob_front', M['stone'], (-LOB_X, LOB_Y0, 0), (LOB_X, LOB_Y0, 0), 0, H_LOB, out=1.0)
for s in (-1, 1):
    box('SOLID_lob_door%d' % s, M['teak'], (s * 0.85, LOB_Y0 + 0.2, 1.35), (1.5, 0.1, 2.7))
    box('SOLID_lob_handle%d' % s, M['brass'], (s * 0.85 + s * 0.6, LOB_Y0 + 0.27, 1.25), (0.05, 0.05, 1.0))
# the wall between lobby and corridor, with the corridor mouth left open
for s in (-1, 1):
    wall('SOLID_lob_back_%d' % s, M['stone'],
         (s * COR_HW0, LOB_Y1, 0), (s * LOB_X, LOB_Y1, 0), 0, H_LOB, out=s)
box('SOLID_lob_lintel', M['stone'], (0, LOB_Y1 + WALL_T / 2, (H_COR + H_LOB) / 2),
    (COR_HW0 * 2, WALL_T, H_LOB - H_COR))

ceiling_with_hole('SOLID_ceiling_lobby', M['plaster'],
                  [(-LOB_X, LOB_Y0), (LOB_X, LOB_Y0), (LOB_X, LOB_Y1), (-LOB_X, LOB_Y1)],
                  H_LOB, 0, (LOB_Y0 + LOB_Y1) / 2, LSKY_A, LSKY_B, n=64)
dome('SOLID_skylight_lobby', M['emit_dome'], 0, (LOB_Y0 + LOB_Y1) / 2, LSKY_A, LSKY_B, H_LOB, LSKY_DEPTH)

# the travertine reception block of image 1
box('SOLID_reception', M['travertine'], (-3.6, LOB_Y0 + 2.4, 0.53), (2.6, 1.0, 1.06))
box('SOLID_reception_top', M['plinth'], (-3.6, LOB_Y0 + 2.4, 1.075), (2.68, 1.08, 0.03))


log('lobby done (objects=%d)' % len(MESHES))

# ---------------------------------------------------------------- plinths and furniture
PLINTH = {}
SPEC = [(0, 'nefertiti', 1.05, 0.70), (1, 'caesar', 0.95, 0.80), (2, 'rocket', 0.20, 2.40)]
for idx, key, ph, pw in SPEC:
    A = ALCOVE[idx]
    c = A['mid'] + A['n'] * (ALC_D * 0.42)
    rz = math.degrees(math.atan2(A['n'].y, A['n'].x)) + 90
    box('SOLID_plinth_%s' % key, M['plinth'], (c.x, c.y, ph / 2), (pw, pw * (1.6 if key == 'rocket' else 1.0), ph), rz=rz)
    box('SOLID_plinth_%s_cap' % key, M['plinth'],
        (c.x, c.y, ph + 0.012), (pw + 0.06, pw * (1.6 if key == 'rocket' else 1.0) + 0.06, 0.024), rz=rz)
    PLINTH[key] = dict(x=round(c.x, 3), y=round(c.y, 3), top=round(ph + 0.024, 3),
                       yaw=round(math.degrees(math.atan2(A['n'].y, A['n'].x)), 2))

for i, (bx, by, brz) in enumerate([(-4.2, 0.6, 20), (4.4, 0.2, -20), (0, -4.6, 0)]):
    box('SOLID_bench%d' % i, M['plinth'], (bx, by, 0.21), (2.2, 0.5, 0.42), rz=brz)
    box('SOLID_bench%d_top' % i, M['teak'], (bx, by, 0.435), (2.24, 0.54, 0.05), rz=brz)


log('plinths done')

# ---------------------------------------------------------------- lighting (Cycles)
def light(name, kind, loc, energy, color=(1, 1, 1), size=1.0, rot=(0, 0, 0), spot=None):
    d = bpy.data.lights.new(name, kind)
    d.energy = energy
    d.color = color
    if kind == 'AREA':
        d.size = size
    elif kind == 'SUN':
        d.angle = math.radians(1.5)
    elif kind == 'SPOT':
        d.spot_size = math.radians(spot[0])
        d.spot_blend = spot[1]
        d.shadow_soft_size = 0.12
    ob = bpy.data.objects.new(name, d)
    ob.location = loc
    ob.rotation_euler = rot
    bpy.context.collection.objects.link(ob)
    return ob


# A light-tight shell around the whole building. Without it the world leaks a flat blue fill in
# through the clerestory and over the walls, and the contrast the real building lives on is gone.
# It is never exported: it exists so the bake only sees the light we designed.
box('SHELL_roof', M['shell'], (0, -6, 24.0), (90, 120, 0.5), export=False)
box('SHELL_floor', M['shell'], (0, -6, -0.6), (90, 120, 0.5), export=False)
for sx, sy, sz in [(-34, -6, 0), (34, -6, 0), (0, -48, 0), (0, 36, 0)]:
    box('SHELL_w_%d_%d' % (sx, sy), M['shell'], (sx, sy, 11),
        (0.5 if sx else 90, 120 if sx else 0.5, 24), export=False)

# the sun rakes in low through the south slot windows: the parallelograms of image 4
light('SUN', 'SUN', (0, -30, 20), 7.0, (1.0, 0.93, 0.78),
      rot=(math.radians(62), 0, math.radians(16)))
# daylight dropping onto each skylight dish
light('SKY_hall', 'AREA', (0, 0, H_HALL + SKY_DEPTH + 0.8), 2600, (0.92, 0.96, 1.0), size=6.5,
      rot=(math.radians(180), 0, 0))
light('SKY_lobby', 'AREA', (0, (LOB_Y0 + LOB_Y1) / 2, H_LOB + LSKY_DEPTH + 0.7), 700,
      (0.92, 0.96, 1.0), size=4.0, rot=(math.radians(180), 0, 0))
# one tight warm spot per alcove, from the soffit edge onto the piece
for idx, key, ph, pw in SPEC:
    A = ALCOVE[idx]
    tgt = Vector((PLINTH[key]['x'], PLINTH[key]['y'], ph + (1.2 if key == 'rocket' else 0.45)))
    src = A['mid'] + A['n'] * 0.30 + Vector((0, 0, H_ALC - 0.12))
    ob = light('SPOT_%s' % key, 'SPOT', src, 1500, (1.0, 0.84, 0.63), spot=(38, 0.35))
    ob.rotation_euler = (tgt - src).to_track_quat('-Z', 'Y').to_euler()
    # a second, softer spot from the front so the face of the piece is not left in its own shadow
    src2 = A['mid'] - A['n'] * 2.6 + Vector((0, 0, H_HALL - 1.4))
    ob = light('SPOT_%s_front' % key, 'SPOT', src2, 420, (1.0, 0.88, 0.72), spot=(26, 0.6))
    ob.rotation_euler = (tgt - src2).to_track_quat('-Z', 'Y').to_euler()

# a grazing wash down the travertine wall, the way the real galleries light their stone
p0, p1 = EDGES[0]
for k in range(5):
    c = p0 + (p1 - p0) * ((k + 0.5) / 5)
    nrm = Vector((-(p1 - p0).normalized().y, (p1 - p0).normalized().x, 0))
    src = c - nrm * 0.9 + Vector((0, 0, H_HALL - 0.5))
    ob = light('WASH_%d' % k, 'SPOT', src, 320, (1.0, 0.90, 0.78), spot=(70, 0.9))
    ob.rotation_euler = ((c + Vector((0, 0, 2.0))) - src).to_track_quat('-Z', 'Y').to_euler()

world = bpy.data.worlds.new('W')
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (0.012, 0.016, 0.026, 1)
bg.inputs['Strength'].default_value = 1.0


log('lights done')

# ---------------------------------------------------------------- the artworks (bake only)
ART = []
for key in ('caesar', 'nefertiti', 'rocket'):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=ROOT + 'docs/models/%s.glb' % key)
    new = [o for o in bpy.context.scene.objects if o not in before]
    p = PLINTH[key]
    for o in new:
        if o.parent is None:
            o.rotation_euler.z = math.radians(p['yaw'] - 90)
            o.location = (p['x'], p['y'], p['top'])
    ART += new

log('artworks imported')

# ---------------------------------------------------------------- render / bake
scene.render.engine = 'CYCLES'
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for dv in prefs.devices:
        dv.use = True
    scene.cycles.device = 'GPU'
except Exception as e:
    print('GPU unavailable, using CPU:', e)
scene.cycles.use_denoising = True
scene.view_settings.view_transform = 'Filmic'
scene.view_settings.look = 'High Contrast'
scene.view_settings.exposure = 0.0

EYE = 1.62
CAMS = [
    ('lobby',    (0, LOB_Y0 + 1.6, EYE), (math.radians(84), 0, 0)),
    ('corridor', (0, -16.5, EYE), (math.radians(86), 0, 0)),
    ('arrival',  (0, -6.0, EYE), (math.radians(80), 0, 0)),
    ('hall',     (0, -4.0, EYE), (math.radians(84), 0, math.radians(-118))),
    ('dome',     (0, -3.0, EYE), (math.radians(136), 0, 0)),
    ('plan',     (0, -11.0, 46.0), (0, 0, 0)),
    ('cor2',     (0, -11.0, EYE), (math.radians(96), 0, math.radians(180))),
    ('nefertiti', (ALCOVE[0]['mid'].x, ALCOVE[0]['mid'].y - 5.0, EYE), (math.radians(88), 0, 0)),
    ('caesar',   (ALCOVE[1]['mid'].x + 4.3, ALCOVE[1]['mid'].y + 2.5, EYE), (math.radians(88), 0, math.radians(119))),
    ('rocket',   (ALCOVE[2]['mid'].x - 4.3, ALCOVE[2]['mid'].y + 2.5, EYE), (math.radians(88), 0, math.radians(-119))),
]

if MODE == 'preview':
    cam = bpy.data.objects.new('CAM', bpy.data.cameras.new('CAM'))
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 20
    cam.data.clip_end = 300
    scene.cycles.samples = int(ARGS[1]) if len(ARGS) > 1 else 48
    scene.render.resolution_x, scene.render.resolution_y = 960, 540
    only = ARGS[2] if len(ARGS) > 2 else None
    for name, loc, rot in CAMS:
        if only and only != name:
            continue
        cam.location = loc
        cam.rotation_euler = rot
        scene.render.filepath = ROOT + 'build/preview_%s.png' % name
        log('rendering ' + name)
        bpy.ops.render.render(write_still=True)
        log('rendered ' + name)
    json.dump(PLINTH, open(ROOT + 'build/plinths.json', 'w'), indent=1)
    print('PREVIEW DONE')

elif MODE == 'bake':
    # Join the ~1200 pieces into a dozen groups first. Unwrapping and baking that many separate
    # objects crashes Blender, and the page wants a handful of meshes anyway: the collision
    # raycasts skip a whole group by its bounding box, which is what keeps the frame rate up.
    def group_of(name):
        if name.startswith('WALK_'):
            return 'WALK_floors'
        if name.startswith(('SOLID_slat_', 'SOLID_wall_screen', 'SOLID_screen_glow')):
            return 'SOLID_screen'
        if name.startswith(('SOLID_lobslat', 'SOLID_lob_glow', 'SOLID_lob_back0',
                            'SOLID_lob_back1', 'SOLID_lob_dado')):
            return 'SOLID_lobbyscreen'
        for i in '012':
            if name.startswith('SOLID_alc%s_' % i):
                return 'SOLID_alcove%s' % i
        if name.startswith('SOLID_cor_'):
            return 'SOLID_corridor'
        if name.startswith(('SOLID_lob_', 'SOLID_reception')):
            return 'SOLID_lobby'
        if name.startswith(('SOLID_ceiling', 'SOLID_skylight')):
            return 'SOLID_ceiling'
        if name.startswith(('SOLID_plinth', 'SOLID_bench')):
            return 'SOLID_furniture'
        return 'SOLID_hall'

    groups = {}
    for ob in MESHES:
        groups.setdefault(group_of(ob.name), []).append(ob)
    joined = []
    for gname, obs in groups.items():
        bpy.ops.object.select_all(action='DESELECT')
        for o in obs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = obs[0]
        if len(obs) > 1:
            bpy.ops.object.join()
        ob = bpy.context.view_layer.objects.active
        ob.name = gname
        joined.append(ob)
    MESHES = joined
    log('joined into %d groups: %s' % (len(MESHES), ', '.join(sorted(groups))))

    # Each group is unwrapped and baked on its own into its own lighting atlas.
    # (bpy.ops.uv.pack_islands crashes Blender 3.6 in background mode, and unwrapping every
    # group together in one multi-object edit goes the same way, so we never do either.)
    BIG = {'WALK_floors', 'SOLID_hall', 'SOLID_screen', 'SOLID_ceiling', 'SOLID_lobbyscreen'}
    scene.cycles.samples = 200
    scene.cycles.bake_type = 'COMBINED'
    scene.render.bake.margin = 8
    scene.render.bake.use_clear = True
    scene.render.image_settings.file_format = 'JPEG'
    scene.render.image_settings.quality = 90

    images = {}
    for ob in MESHES:
        res = 2048 if ob.name in BIG else 1024
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.012)
        bpy.ops.object.mode_set(mode='OBJECT')

        img = bpy.data.images.new('BAKE_' + ob.name, res, res, float_buffer=True)
        images[ob.name] = img
        # the bake writes into whichever image node is active, so every material this group
        # uses gets its own copy pointed at this group's image
        for slot in ob.material_slots:
            if not slot.material:
                continue
            slot.material = slot.material.copy()
            nt = slot.material.node_tree
            tx = nt.nodes.new('ShaderNodeTexImage')
            tx.image = img
            nt.nodes.active = tx
            for n in nt.nodes:
                n.select = (n == tx)
        log('unwrapped %s (%d faces, %d px), baking' % (ob.name, len(ob.data.polygons), res))
        bpy.ops.object.bake(type='COMBINED')
        log('baked %s' % ob.name)

    # Save through the view transform so the page gets the tone-mapped picture, then re-import it:
    # the exported material is pure emission, so the page needs no lights for the room at all.
    for ob in MESHES:
        path = ROOT + 'build/bake_%s.jpg' % ob.name
        images[ob.name].save_render(path, scene=scene)
        baked = bpy.data.images.load(path)
        m2 = bpy.data.materials.new('Baked_' + ob.name)
        m2.use_nodes = True
        nt = m2.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = baked
        bsdf.inputs['Base Color'].default_value = (0, 0, 0, 1)
        bsdf.inputs['Roughness'].default_value = 1.0
        bsdf.inputs['Emission Strength'].default_value = 1.0
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Emission'])
        nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        m2.use_backface_culling = False
        ob.data.materials.clear()
        ob.data.materials.append(m2)

    for o in list(bpy.context.scene.objects):
        if o not in MESHES:
            bpy.data.objects.remove(o, do_unlink=True)

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=ROOT + 'docs/models/museum.glb', export_format='GLB',
                              use_selection=True, export_apply=True, export_yup=True,
                              export_cameras=False, export_lights=False,
                              export_image_format='JPEG', export_jpeg_quality=90,
                              export_normals=False)
    json.dump(PLINTH, open(ROOT + 'build/plinths.json', 'w'), indent=1)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in MESHES)
    print('BAKE DONE objects=%d tris=%d' % (len(MESHES), tris))
