"""Geometry primitives. Everything returns a Blender object; nothing is subject-specific.

The house style of this project: build every part as its own small object with a single
material, then `join()` the parts at the end. Per-face material assignment is avoided
entirely -- joining turns each part's material into a slot, which is both easier to get
right and easier to re-colour later.
"""
import bpy, bmesh, math
from mathutils import Vector, Matrix, Euler

TAU = math.pi * 2


# ------------------------------------------------------------------ low level
def new_mesh(name, verts, faces, coll=None, mat=None, smooth=False, auto_angle=40.0):
    """Build a mesh object from raw vert/face lists and link it into `coll`."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [list(f) for f in faces])
    me.validate(verbose=False)
    me.update()
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    if mat:
        ob.data.materials.append(mat)
    recalc_normals(ob)
    if smooth:
        shade_smooth(ob, auto_angle)
    return ob


def recalc_normals(ob):
    """Make the normals consistent and, for a closed solid, outward.

    recalc_face_normals alone only makes them *consistent*; on a lofted tube with
    n-gon caps it can settle on the inward solution. An inward solid silently
    inverts every later boolean -- a DIFFERENCE then eats the model instead of the
    cutter -- so the signed volume is checked and the mesh flipped if it is
    negative.
    """
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    try:
        if bm.calc_volume(signed=True) < 0.0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
    except Exception:
        pass
    bm.to_mesh(ob.data)
    bm.free()


def is_closed(ob):
    """True if every edge has exactly two faces -- i.e. the mesh is a watertight
    solid and safe to use with the exact boolean solver."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    ok = all(len(e.link_faces) == 2 for e in bm.edges)
    bm.free()
    return ok


def shade_smooth(ob, angle_deg=40.0):
    """Smooth shading limited by an angle.

    Blender 4.1 removed mesh.use_auto_smooth and replaced it with a 'Smooth by Angle'
    geometry-nodes modifier, so this has to branch on version.
    """
    for p in ob.data.polygons:
        p.use_smooth = True
    if hasattr(ob.data, 'use_auto_smooth'):          # <= 4.0
        ob.data.use_auto_smooth = True
        ob.data.auto_smooth_angle = math.radians(angle_deg)
    else:                                            # >= 4.1
        prev = set(bpy.data.objects)
        try:
            with bpy.context.temp_override(object=ob, active_object=ob,
                                           selected_objects=[ob],
                                           selected_editable_objects=[ob]):
                bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle_deg))
        except Exception:
            pass
        del prev
    return ob


def shade_flat(ob):
    for p in ob.data.polygons:
        p.use_smooth = False
    return ob


def join(objs, name=None, coll=None):
    """Join a list of objects into the first one. Materials become slots."""
    objs = [o for o in objs if o is not None]
    if not objs:
        return None
    if len(objs) == 1:
        if name:
            objs[0].name = objs[0].data.name = name
        return objs[0]
    target = objs[0]
    with bpy.context.temp_override(active_object=target, selected_editable_objects=objs,
                                   selected_objects=objs, object=target):
        bpy.ops.object.join()
    if name:
        target.name = target.data.name = name
    if coll is not None:
        move_to(target, coll)
    return target


def move_to(ob, coll):
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
    return ob


def delete(*objs):
    for ob in objs:
        if ob and ob.name in bpy.data.objects:
            bpy.data.objects.remove(ob, do_unlink=True)


def apply_transform(ob, loc=False, rot=True, scale=True):
    with bpy.context.temp_override(active_object=ob, selected_editable_objects=[ob],
                                   object=ob):
        bpy.ops.object.transform_apply(location=loc, rotation=rot, scale=scale)
    return ob


def place(ob, loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    ob.location = loc
    ob.rotation_euler = rot
    if scale:
        ob.scale = scale if hasattr(scale, '__len__') else (scale,) * 3
    return ob


# ------------------------------------------------------------------ curves
def catmull_rom(pts, samples_per_span=8, closed=False, tension=0.0):
    """Sample a Catmull-Rom spline through `pts` (tuples of any dimension)."""
    n = len(pts)
    if n < 2:
        return list(pts)
    P = [Vector(p) for p in pts]
    if closed:
        idx = lambda i: P[i % n]
    else:
        ext = [P[0] + (P[0] - P[1])] + P + [P[-1] + (P[-1] - P[-2])]
        idx = lambda i: ext[max(0, min(len(ext) - 1, i + 1))]
    out = []
    spans = n if closed else n - 1
    a = 0.5 * (1.0 - tension)
    for i in range(spans):
        p0, p1, p2, p3 = idx(i - 1), idx(i), idx(i + 1), idx(i + 2)
        for s in range(samples_per_span):
            t = s / samples_per_span
            t2, t3 = t * t, t * t * t
            out.append(p1 + a * ((p2 - p0) * t
                                 + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                                 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1])
    return out


def smoothstep(a, b, t):
    t = min(1.0, max(0.0, (t - a) / (b - a))) if b != a else (0.0 if t < a else 1.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


# ------------------------------------------------------------------ lofting
def mirror_half_ring(half, axis=1):
    """half: points from one centre-line vertex round to the other, with coord[axis] >= 0.
    Returns a closed ring: the half, then its mirror image coming back, ends not doubled."""
    ring = [Vector(p) for p in half]
    back = []
    for p in reversed(ring[1:-1]):
        q = p.copy()
        q[axis] = -q[axis]
        back.append(q)
    return ring + back


def loft(rings, cap_start=True, cap_end=True, name='loft', coll=None, mat=None,
         smooth=True, auto_angle=35.0, closed_rings=True):
    """Skin a list of equal-length rings into a tube. Rings run along the body."""
    n = len(rings[0])
    assert all(len(r) == n for r in rings), 'loft rings must all be the same length'
    verts, faces = [], []
    for r in rings:
        verts.extend(Vector(p) for p in r)
    span = n if closed_rings else n - 1
    for i in range(len(rings) - 1):
        a, b = i * n, (i + 1) * n
        for j in range(span):
            k = (j + 1) % n
            faces.append([a + j, a + k, b + k, b + j])
    if cap_start:
        faces.append(list(range(n - 1, -1, -1)))
    if cap_end:
        o = (len(rings) - 1) * n
        faces.append(list(range(o, o + n)))
    return new_mesh(name, verts, faces, coll, mat, smooth, auto_angle)


def extrude_profile(poly, vec, name='extr', coll=None, mat=None, smooth=False,
                    auto_angle=35.0):
    """Extrude a closed planar polygon along a vector into a solid."""
    v = Vector(vec)
    a = [Vector(p) for p in poly]
    b = [p + v for p in a]
    n = len(a)
    verts = a + b
    faces = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    return new_mesh(name, verts, faces, coll, mat, smooth, auto_angle)


def revolve(profile, segments=32, axis='Z', sweep=TAU, name='rev', coll=None, mat=None,
            smooth=True, auto_angle=35.0, cap=True):
    """Spin a 2-D profile of (radius, height) pairs about an axis."""
    rings = []
    closed = abs(sweep - TAU) < 1e-6
    steps = segments if closed else segments + 1
    for i in range(steps):
        a = sweep * (i / segments)
        ca, sa = math.cos(a), math.sin(a)
        ring = []
        for r, h in profile:
            if axis == 'Z':
                ring.append(Vector((r * ca, r * sa, h)))
            elif axis == 'X':
                ring.append(Vector((h, r * ca, r * sa)))
            else:
                ring.append(Vector((r * ca, h, r * sa)))
        rings.append(ring)
    n = len(profile)
    verts, faces = [], []
    for r in rings:
        verts.extend(r)
    for i in range(len(rings) if closed else len(rings) - 1):
        a, b = i * n, ((i + 1) % len(rings)) * n
        for j in range(n - 1):
            faces.append([a + j, a + j + 1, b + j + 1, b + j])
    if cap and closed:
        # close the two ends of the profile with a fan, if they are off the axis
        if abs(profile[0][0]) > 1e-6:
            faces.append([i * n for i in range(len(rings))][::-1])
        if abs(profile[-1][0]) > 1e-6:
            faces.append([i * n + (n - 1) for i in range(len(rings))])
    return new_mesh(name, verts, faces, coll, mat, smooth, auto_angle)


# ------------------------------------------------------------------ primitives
def box(size=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0), name='box', coll=None, mat=None,
        bevel=0.0, bevel_seg=2, smooth=False):
    sx, sy, sz = (s / 2 for s in size)
    verts = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
             (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
             [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    ob = new_mesh(name, verts, faces, coll, mat)
    if bevel > 0:
        bevel_edges(ob, bevel, bevel_seg)
    if smooth:
        shade_smooth(ob)
    place(ob, loc, rot)
    return ob


def plane(size=(1, 1), loc=(0, 0, 0), rot=(0, 0, 0), name='plane', coll=None, mat=None,
          subdiv=0):
    sx, sy = size[0] / 2, size[1] / 2
    ob = new_mesh(name, [(-sx, -sy, 0), (sx, -sy, 0), (sx, sy, 0), (-sx, sy, 0)],
                  [[0, 1, 2, 3]], coll, mat)
    if subdiv:
        subdivide(ob, subdiv)
    place(ob, loc, rot)
    return ob


def cyl(r=0.5, h=1.0, loc=(0, 0, 0), rot=(0, 0, 0), name='cyl', coll=None, mat=None,
        seg=24, axis='Z', caps=True, smooth=True, r_top=None):
    r_top = r if r_top is None else r_top
    rings = []
    for z, rr in ((-h / 2, r), (h / 2, r_top)):
        ring = []
        for i in range(seg):
            a = TAU * i / seg
            p = Vector((rr * math.cos(a), rr * math.sin(a), z))
            if axis == 'X':
                p = Vector((p.z, p.x, p.y))
            elif axis == 'Y':
                p = Vector((p.x, p.z, p.y))
            ring.append(p)
        rings.append(ring)
    ob = loft(rings, caps, caps, name, coll, mat, smooth, 50.0)
    place(ob, loc, rot)
    return ob


def tube(r_out=0.5, r_in=0.4, h=1.0, loc=(0, 0, 0), rot=(0, 0, 0), name='tube',
         coll=None, mat=None, seg=24, axis='Z', smooth=True):
    """A hollow cylinder, built as a revolve of a rectangle."""
    prof = [(r_in, -h / 2), (r_out, -h / 2), (r_out, h / 2), (r_in, h / 2), (r_in, -h / 2)]
    ob = revolve(prof, seg, 'Z', TAU, name, coll, mat, smooth, 50.0, cap=False)
    if axis == 'X':
        ob.rotation_euler = (0, math.pi / 2, 0)
        apply_transform(ob)
    elif axis == 'Y':
        ob.rotation_euler = (math.pi / 2, 0, 0)
        apply_transform(ob)
    place(ob, loc, rot)
    return ob


def sphere(r=0.5, loc=(0, 0, 0), name='sph', coll=None, mat=None, seg=24, rings=12,
           squash=1.0, hemi=False):
    prof = []
    steps = rings
    for i in range(steps + 1):
        a = (math.pi / 2 if hemi else math.pi) * i / steps - (0 if hemi else math.pi / 2)
        prof.append((r * math.cos(a), r * math.sin(a) * squash))
    ob = revolve(prof, seg, 'Z', TAU, name, coll, mat, True, 60.0, cap=False)
    place(ob, loc)
    return ob


def capsule_rod(p0, p1, r, seg=12, name='rod', coll=None, mat=None, smooth=True):
    """A cylinder between two points in space."""
    a, b = Vector(p0), Vector(p1)
    d = b - a
    ob = cyl(r, d.length, name=name, coll=coll, mat=mat, seg=seg, smooth=smooth)
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = d.to_track_quat('Z', 'Y')
    ob.location = (a + b) / 2
    return ob


# ------------------------------------------------------------------ modifiers
def bevel_edges(ob, width=0.01, segments=2, angle=50.0, clamp=True):
    m = ob.modifiers.new('bev', 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = clamp
    m.harden_normals = False
    apply_mods(ob)
    return ob


def solidify(ob, thickness=0.01, offset=-1.0):
    m = ob.modifiers.new('sol', 'SOLIDIFY')
    m.thickness = thickness
    m.offset = offset
    apply_mods(ob)
    return ob


def subdivide(ob, cuts=1, simple=False):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts,
                              use_grid_fill=True,
                              smooth=0.0 if simple else 0.0)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def apply_mods(ob):
    with bpy.context.temp_override(object=ob, active_object=ob,
                                   selected_editable_objects=[ob]):
        for m in list(ob.modifiers):
            try:
                bpy.ops.object.modifier_apply(modifier=m.name)
            except RuntimeError:
                ob.modifiers.remove(m)
    return ob


def boolean(target, cutter, op='DIFFERENCE', solver='EXACT', remove_cutter=True):
    m = target.modifiers.new('bool', 'BOOLEAN')
    m.operation = op
    m.object = cutter
    m.solver = solver
    try:
        with bpy.context.temp_override(object=target, active_object=target,
                                       selected_editable_objects=[target]):
            bpy.ops.object.modifier_apply(modifier=m.name)
    except RuntimeError:
        target.modifiers.remove(m)
    if remove_cutter:
        delete(cutter)
    return target


def weld(ob, dist=1e-4):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=dist)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def dims(ob):
    """World-space bounding box (min, max) as Vectors."""
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def text_solid(body, size=0.2, extrude=0.004, name='txt', coll=None, mat=None,
               align_x='CENTER', align_y='CENTER', spacing=1.0, bevel=0.0):
    """A string as real geometry, using Blender's bundled font.

    Used for route numbers, number plates and shop boards. Latin and digits only --
    the bundled font has no Bengali glyphs, so Bengali signage in this project is
    painted panels rather than text.
    """
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align_x
    cu.align_y = align_y
    cu.space_character = spacing
    if bevel:
        cu.bevel_depth = bevel
    tmp = bpy.data.objects.new(name + '_curve', cu)
    target = coll or bpy.context.scene.collection
    target.objects.link(tmp)
    # Evaluate the font curve into a mesh directly rather than going through
    # bpy.ops.object.convert, whose poll needs a selection context that does not
    # exist in a -b run.
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    me.name = name
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    ob = bpy.data.objects.new(name, me)
    target.objects.link(ob)
    if mat:
        ob.data.materials.clear()
        ob.data.materials.append(mat)
    return ob


def grid_bars(w, h, pitch=0.055, bar=0.004, name='mesh_grid', coll=None, mat=None,
              depth=None):
    """A weldmesh panel in the XZ plane, centred on the origin, facing +Y.

    Kolkata trams screen the motorman's openings with coarse square weldmesh
    rather than glass, and it is the single most recognisable detail of the front
    end, so it is built as real bars rather than faked with a texture.
    """
    depth = depth or bar
    parts = []
    nv = max(2, int(round(w / pitch)) + 1)
    nh = max(2, int(round(h / pitch)) + 1)
    for i in range(nv):
        x = -w / 2 + w * i / (nv - 1)
        parts.append(box((bar, depth, h), (x, 0, 0), name='%s_v%d' % (name, i),
                         coll=coll, mat=mat))
    for i in range(nh):
        z = -h / 2 + h * i / (nh - 1)
        parts.append(box((w, depth * 0.9, bar), (0, 0, z), name='%s_h%d' % (name, i),
                         coll=coll, mat=mat))
    return join(parts, name, coll)


def rounded_rect_profile(w, h, r, samples=4):
    """Closed polygon in the YZ plane (x = 0): a rectangle with rounded corners."""
    hw, hh = w / 2, h / 2
    r = min(r, hw, hh)
    pts = []
    for cy, cz, a0 in ((hw - r, -(hh - r), -math.pi / 2), (hw - r, hh - r, 0.0),
                       (-(hw - r), hh - r, math.pi / 2), (-(hw - r), -(hh - r), math.pi)):
        for i in range(samples + 1):
            a = a0 + (math.pi / 2) * i / samples
            pts.append(Vector((0.0, cy + r * math.cos(a), cz + r * math.sin(a))))
    return pts


def tube_along(points, r=0.01, seg=6, name='tube_path', coll=None, mat=None,
               smooth=True):
    """A round tube swept along a polyline, with a fixed up-vector frame.

    Used for every wire in the scene. A fixed frame twists on a path that turns
    sharply, but overhead wires are nearly straight, so it is both adequate and
    far cheaper than parallel transport.
    """
    P = [Vector(p) for p in points]
    rings = []
    for i, p in enumerate(P):
        if i == 0:
            t = (P[1] - P[0])
        elif i == len(P) - 1:
            t = (P[-1] - P[-2])
        else:
            t = (P[i + 1] - P[i - 1])
        t.normalize()
        up = Vector((0, 0, 1))
        if abs(t.dot(up)) > 0.98:
            up = Vector((0, 1, 0))
        u = t.cross(up).normalized()
        v = t.cross(u).normalized()
        rings.append([p + u * (r * math.cos(TAU * k / seg))
                      + v * (r * math.sin(TAU * k / seg)) for k in range(seg)])
    return loft(rings, True, True, name, coll, mat, smooth, 60.0)


def sag_points(p0, p1, sag, steps=10):
    """A parabolic sag between two points -- close enough to a catenary for a wire
    and much cheaper to evaluate."""
    a, b = Vector(p0), Vector(p1)
    out = []
    for i in range(steps + 1):
        t = i / steps
        p = a.lerp(b, t)
        p.z -= 4.0 * sag * t * (1.0 - t)
        out.append(p)
    return out


def sag_wire(p0, p1, sag=0.25, r=0.008, name='wire', coll=None, mat=None, steps=10,
             seg=5):
    return tube_along(sag_points(p0, p1, sag, steps), r, seg, name, coll, mat)
