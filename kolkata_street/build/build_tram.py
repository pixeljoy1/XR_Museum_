"""Kolkata (CTC) articulated tram car  ->  assets/tram_ctc.blend

Built once, here, and linked into the street scene. Re-running this file and
re-saving updates every tram in the street, because the street links rather
than copies.

WHAT IS BEING MODELLED, and why these numbers
---------------------------------------------
The car is the classic Calcutta Tramways articulated six-axle single-deck tram --
the type the Nonapukur workshop, Burn Standard and Jessop & Co built, and the
type in all four reference images. Checked facts it is built to:

  gauge              1,435 mm standard gauge.  (The system started metre gauge and
                     was converted to standard from 1900. It is NOT broad gauge --
                     that is the Indian main line, not the tram.)
  overall length     57 ft = 17.37 m   )  preserved car No. 204, Heritage
  width              7 ft  =  2.134 m  )  Transport Museum, Gurugram
  weight             18 t              )
  power              550 V DC from overhead line, rails as return
  collector          trolley pole, on the leading (first class) coach
  ends               single ended -- routes turn on terminal loops, so there is a
                     driving cab at one end only
  bodies             two, permanently articulated, riding on three two-axle
                     trucks: one under each outer end and a shared truck under
                     the joint (that is what "six-axle articulated" means)
  classes            first class leads, second class trails, with a partition
  motorman           screened by coarse weldmesh, not glass -- the single most
                     recognisable detail of the front end
  seating            54-61 depending on the source

Dimensions that no public source gives (window heights, pillar widths, roof
radius, truck wheelbase) are drawn off the reference photographs against the
known 2.134 m width and 17.37 m length, and are collected in SPEC below so they
are easy to argue with.

Axes:  +X is forward (the nose).  +Z is up.  z = 0 is the top of the rail, so the
car can be dropped straight onto track at any height.

Run:
    blender -b -P build/build_tram.py                 # build and save the .blend
    blender -b -P build/build_tram.py -- --preview    # ... and render a turntable sheet
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klib import mesh as M, mat as T, sceneutil as S

S.log_to(os.path.join(S.ROOT, 'build', 'build_tram.log'))

# ===================================================================== SPEC
SPEC = dict(
    L_TOTAL=17.37, WIDTH=2.134, GAUGE=1.435,
    BODY_L=8.45, GAP=0.47,                 # 8.45 + 0.47 + 8.45 = 17.37
    Z_PAN=0.455,                           # underside of the body (underfloor pan)
    Z_FLOOR=0.78,                          # saloon floor above rail head
    Z_SILL=1.58, Z_HEAD=2.48,              # window opening, bottom and top (0.90 tall)
    Z_SHOULDER=2.72,                       # where the side stops being vertical
    Z_ROOF=3.285,                          # roof apex; the roof is an ellipse quarter
    WALL=0.055,
    HALF_W=1.067,
    PILLAR=0.10, BAY=0.84,                 # window pillar width, target window width
    DOOR_W=0.90, Z_DOOR_TOP=2.30,
    Z_STEP=0.42, STEP_OUT=0.13,
    FACET_X=0.56, FACET_Y=0.60,          # cab-corner chamfer: depth, half width of the flat front
    WHEEL_D=0.66, WHEELBASE=1.60,
    TRUCK_X=6.30,                          # outer truck centres, +/- from car centre
    POLE_LEN=5.0, POLE_RISE=24.0,          # trolley pole length and angle above horizontal
    ROUTE='5', DEST='ESPLANADE', FLEET='660',
)
HALF_L = SPEC['L_TOTAL'] / 2                       # 8.685
BODY_IN = SPEC['GAP'] / 2                          # inner face of each body, +/- 0.235
BODY_OUT = BODY_IN + SPEC['BODY_L']                # 8.685 == HALF_L
assert abs(BODY_OUT - HALF_L) < 1e-9, 'body lengths do not add up to L_TOTAL'

# ===================================================================== livery
# Taken off the reference paintings: CTC vermillion with a cream band, grey roof,
# near-black underframe, and the yellow advertisement panels along the skirt.
LIVERY = dict(
    body=T.srgb('#c2370f'),      # CTC vermillion
    cream=T.srgb('#efe2c4'),
    roof=T.srgb('#8e9094'),
    under=T.srgb('#2b2b2d'),
    truck=T.srgb('#3a3a3d'),
    advert=T.srgb('#f2c413'),
    advert2=T.srgb('#c8102e'),
    dash=T.srgb('#f0ece0'),
    interior=T.srgb('#c7c0ad'),
    seat=T.srgb('#7a4a24'),
)

MAT = {}


def materials():
    MAT['body'] = T.car_paint('tram_body', LIVERY['body'], rough=0.38, coat=0.55, dirt=0.16)
    MAT['cream'] = T.car_paint('tram_cream', LIVERY['cream'], rough=0.46, coat=0.4, dirt=0.30)
    MAT['roof'] = T.painted_metal('tram_roof', LIVERY['roof'], rough=0.75, dirt=0.6)
    MAT['under'] = T.painted_metal('tram_under', LIVERY['under'], rough=0.8, dirt=0.7)
    MAT['truck'] = T.painted_metal('tram_truck', LIVERY['truck'], rough=0.74, dirt=0.55)
    MAT['steel'] = T.steel('tram_steel', rough=0.38)
    MAT['wheel'] = T.steel('tram_wheel', rough=0.32, tint=(0.30, 0.30, 0.31))
    MAT['chrome'] = T.chrome('tram_chrome', rough=0.14)
    MAT['rubber'] = T.rubber('tram_rubber')
    MAT['glass'] = T.base('tram_glass', (0.55, 0.60, 0.58), 0.05, 0.0,
                          ior=1.52, transmission=0.90)
    MAT['lamp'] = T.emissive('tram_lamp', (1.0, 0.86, 0.58), 26.0)
    MAT['dest'] = T.emissive('tram_dest', (1.0, 0.93, 0.74), 3.0)
    MAT['advert'] = T.painted_metal('tram_advert', LIVERY['advert'], 0.5, dirt=0.4)
    MAT['advert2'] = T.painted_metal('tram_advert2', LIVERY['advert2'], 0.5, dirt=0.4)
    MAT['dash'] = T.car_paint('tram_dash', LIVERY['dash'], rough=0.5, coat=0.3, dirt=0.5)
    MAT['interior'] = T.base('tram_interior', LIVERY['interior'], 0.85)
    MAT['seat'] = T.teak('tram_seat', LIVERY['seat'], 0.6)
    MAT['black'] = T.base('tram_black', (0.012, 0.012, 0.013), 0.6)
    MAT['white'] = T.base('tram_white', T.srgb('#f4f2ee'), 0.5)


# ===================================================================== sections
ROOF_STEPS = 9


def roof_arc(a, b, z0, steps=ROOF_STEPS):
    """Quarter ellipse from (a, z0) to (0, z0 + b): the roof curve."""
    out = []
    for i in range(steps + 1):
        t = (math.pi / 2) * i / steps
        out.append((a * math.cos(t), z0 + b * math.sin(t)))
    return out


def outer_section():
    """Half the body cross-section, bottom centre round to top centre, y >= 0.

    Elevation, bottom to top:  underfloor pan 0.455 | skirt (advertisement panels)
    | window sill 1.58 | glass 0.90 high | cantrail band 2.48-2.72 | roof arc to 3.285.
    That division is read off the reference photographs against the known 2.134 m width.
    """
    sp = SPEC
    half = [(0.0, sp['Z_PAN']), (0.86, sp['Z_PAN']), (0.955, 0.545), (1.035, 0.70),
            (sp['HALF_W'], 1.05), (sp['HALF_W'], sp['Z_SHOULDER'])]
    half += roof_arc(sp['HALF_W'], sp['Z_ROOF'] - sp['Z_SHOULDER'], sp['Z_SHOULDER'])[1:]
    return M.mirror_half_ring([Vector((0.0, y, z)) for y, z in half], axis=1)


def inner_section():
    """The saloon cavity: the same shell inset by WALL, floor upward."""
    sp, w = SPEC, SPEC['WALL']
    half = [(0.0, sp['Z_FLOOR']), (sp['HALF_W'] - w, sp['Z_FLOOR']),
            (sp['HALF_W'] - w, sp['Z_SHOULDER'])]
    half += roof_arc(sp['HALF_W'] - w, sp['Z_ROOF'] - sp['Z_SHOULDER'] - w,
                     sp['Z_SHOULDER'])[1:]
    return M.mirror_half_ring([Vector((0.0, y, z)) for y, z in half], axis=1)


def roof_cap_profile(t=0.016):
    """A thin curved shell lying on the roof arc, so the roof can be grey without
    a flat box poking through the curve. Outer arc out, inner arc back."""
    sp = SPEC
    a, b, z0 = sp['HALF_W'], sp['Z_ROOF'] - sp['Z_SHOULDER'], sp['Z_SHOULDER']
    outer = roof_arc(a + t, b + t, z0)
    inner = roof_arc(a, b, z0)
    pts = [(y, z) for y, z in outer]
    pts += [(-y, z) for y, z in reversed(outer)][1:]
    pts += [(-y, z) for y, z in inner][1:]
    pts += [(y, z) for y, z in reversed(inner)][1:-1]
    return [Vector((0.0, y, z)) for y, z in pts]


def bay_layout(x0, x1, pillar, target_bay):
    """Fit a whole number of equal window bays between x0 and x1.
    Returns [(xa, xb), ...] openings, with a pillar at each end and between."""
    span = x1 - x0
    n = max(1, int(round((span - pillar) / (target_bay + pillar))))
    bay = (span - (n + 1) * pillar) / n
    out = []
    x = x0 + pillar
    for _ in range(n):
        out.append((x, x + bay))
        x += bay + pillar
    return out


# ===================================================================== body shell
def facet_cutters(xn, coll):
    """Two wedges that chamfer the front corners into a faceted cab bay.

    The Kolkata cab front is not a flat slab: it steps back through angled corner
    panels, so the windscreen is a three-pane bay (centre plus two raked corners).
    Each cutter is a big box lying on the line from the nose corner (xn, +/-0.62)
    out to the full body width at xn - FACET_X.
    """
    fx, y1 = SPEC['FACET_X'], SPEC['FACET_Y']
    out = []
    for sd in (1, -1):
        d = Vector((-fx, sd * (SPEC['HALF_W'] - y1))).normalized()
        n = Vector((d.y, -d.x)) * sd                       # outward
        mid = Vector((xn - fx / 2, sd * (y1 + SPEC['HALF_W']) / 2))
        c = mid + n * 1.6
        out.append(M.box((4.0, 3.2, 7.0), (c.x, c.y, 1.6),
                         (0, 0, math.atan2(d.y, d.x)), name='facet%d' % sd, coll=coll))
    return out


def build_body(which, coll):
    """`which` is 'front' (first class, with the cab) or 'rear' (second class)."""
    sp = SPEC
    front = which == 'front'
    x_in = BODY_IN if front else -BODY_IN           # the articulation end
    x_out = BODY_OUT if front else -BODY_OUT        # the nose, or the tail
    sgn = 1.0 if front else -1.0
    lo, hi = min(x_in, x_out), max(x_in, x_out)
    parts = []

    # --- shell: a constant section extruded the length of the body, then hollowed
    sec = [Vector((lo, p.y, p.z)) for p in outer_section()]
    shell = M.extrude_profile(sec, (hi - lo, 0, 0), 'body_%s' % which, coll,
                              MAT['body'], smooth=False)
    cav = [Vector((lo + sp['WALL'], p.y, p.z)) for p in inner_section()]
    cavity = M.extrude_profile(cav, (hi - lo - 2 * sp['WALL'], 0, 0), 'cavity', coll)
    M.boolean(shell, cavity, 'DIFFERENCE')

    # --- grey roof cap, following the same ellipse as the section
    capsec = [Vector((lo + 0.005, p.y, p.z)) for p in roof_cap_profile()]
    roofcap = M.extrude_profile(capsec, (hi - lo - 0.01, 0, 0), 'roofskin_%s' % which,
                                coll, MAT['roof'], smooth=True, auto_angle=30.0)

    # --- chamfer the cab corners. Everything that wraps the body -- shell, roof
    # cap, cantrail band, waist rail -- has to take the same cut, or it overhangs.
    def facet_cut(target):
        if not front:
            return target
        for cut in facet_cutters(x_out, coll):
            M.boolean(target, cut, 'DIFFERENCE')
        return target

    facet_cut(shell)
    facet_cut(roofcap)

    # --- doorways. Three per side across the pair, as on the SLT/articulated cars:
    # one behind the cab on the leading body, one each side of the articulation on
    # the trailing body. Open doorways, no leaves -- passengers board from the road.
    if front:
        doors = [(x_out - 3.30 - sp['DOOR_W'], x_out - 3.30)]
    else:
        doors = [(x_in - 1.00 - sp['DOOR_W'], x_in - 1.00),
                 (x_out + 0.95, x_out + 0.95 + sp['DOOR_W'])]
    for i, (a, b) in enumerate(doors):
        c = M.box((b - a, 3.0, sp['Z_DOOR_TOP'] - sp['Z_FLOOR']),
                  ((a + b) / 2, 0, (sp['Z_FLOOR'] + sp['Z_DOOR_TOP']) / 2),
                  name='doorcut%d' % i, coll=coll)
        M.boolean(shell, c, 'DIFFERENCE')

    # --- window bays in the runs of wall between the doorways
    spans = []
    if front:
        spans.append((x_out - 3.05, x_out - 0.72))          # motorman's bay (weldmesh)
        spans.append((x_in + 0.12, doors[0][0] - 0.06))     # first class saloon
        mesh_span = spans[0]
    else:
        spans.append((doors[1][1] + 0.06, doors[0][0] - 0.06))
        mesh_span = None
    windows, pillars = [], []
    for a, b in spans:
        lo_s, hi_s = min(a, b), max(a, b)
        bays = bay_layout(lo_s, hi_s, sp['PILLAR'], sp['BAY'])
        windows.extend(bays)
        edges = [lo_s] + [v for bay in bays for v in bay] + [hi_s]
        pillars.extend((edges[i], edges[i + 1]) for i in range(0, len(edges) - 1, 2))
    for i, (a, b) in enumerate(windows):
        c = M.box((b - a, 3.0, sp['Z_HEAD'] - sp['Z_SILL']),
                  ((a + b) / 2, 0, (sp['Z_SILL'] + sp['Z_HEAD']) / 2),
                  name='wincut%d' % i, coll=coll)
        M.boolean(shell, c, 'DIFFERENCE')

    # --- the windscreen bay: one cut opens the flat front and both raked facets
    if front:
        c = M.box((sp['FACET_X'] + 0.30, 2.6, sp['Z_HEAD'] - sp['Z_SILL']),
                  (x_out - sp['FACET_X'] / 2 + 0.14, 0,
                   (sp['Z_SILL'] + sp['Z_HEAD']) / 2),
                  name='wscut', coll=coll)
        M.boolean(shell, c, 'DIFFERENCE')

    M.weld(shell)
    M.shade_flat(shell)
    parts.append(shell)
    parts.append(roofcap)

    # --- glazing: a pane in every window
    for i, (a, b) in enumerate(windows):
        if mesh_span and mesh_span[0] - 0.01 <= a <= mesh_span[1] + 0.01:
            continue                                   # motorman's bay is weldmesh
        for sd in (1, -1):
            parts.append(M.box((b - a, 0.008, sp['Z_HEAD'] - sp['Z_SILL'] - 0.01),
                               ((a + b) / 2, sd * (sp['HALF_W'] - 0.028),
                                (sp['Z_SILL'] + sp['Z_HEAD']) / 2),
                               name='pane%d_%d' % (i, sd), coll=coll, mat=MAT['glass']))

    # --- weldmesh over the motorman's openings
    if front:
        for a, b in windows:
            if mesh_span[0] - 0.01 <= a <= mesh_span[1] + 0.01:
                for sd in (1, -1):
                    g = M.grid_bars(b - a - 0.02, sp['Z_HEAD'] - sp['Z_SILL'] - 0.02,
                                    0.058, 0.005, 'weldmesh', coll, MAT['black'],
                                    depth=0.012)
                    M.place(g, ((a + b) / 2, sd * (sp['HALF_W'] - 0.025),
                                (sp['Z_SILL'] + sp['Z_HEAD']) / 2))
                    parts.append(g)

    # --- cream pillars between the windows, the waist rail and the cantrail band.
    # This is the CTC look in the reference paintings: a vermillion skirt, a cream
    # window band carried on cream pillars, cream again above the heads, grey roof.
    for i, (a, b) in enumerate(pillars):
        if b - a < 0.02:
            continue
        for sd in (1, -1):
            parts.append(M.box((b - a, 0.016, sp['Z_HEAD'] - sp['Z_SILL'] + 0.02),
                               ((a + b) / 2, sd * (sp['HALF_W'] + 0.002),
                                (sp['Z_SILL'] + sp['Z_HEAD']) / 2),
                               name='pillar%s%d_%d' % (which, i, sd), coll=coll,
                               mat=MAT['cream']))
    waist = M.box((abs(hi - lo) - 0.02, 2 * sp['HALF_W'] + 0.010, 0.055),
                  ((lo + hi) / 2, 0, sp['Z_SILL'] - 0.028),
                  name='waist_%s' % which, coll=coll, mat=MAT['cream'])
    for a, b in doors:
        dc = M.box((b - a, 3.0, 0.3), ((a + b) / 2, 0, sp['Z_SILL'] - 0.028),
                   name='waistdoorcut', coll=coll)
        M.boolean(waist, dc, 'DIFFERENCE')
    parts.append(facet_cut(waist))
    band = M.box((abs(hi - lo) - 0.02, 2 * sp['HALF_W'] + 0.008,
                  sp['Z_SHOULDER'] - sp['Z_HEAD']),
                 ((lo + hi) / 2, 0, (sp['Z_HEAD'] + sp['Z_SHOULDER']) / 2),
                 name='band_%s' % which, coll=coll, mat=MAT['cream'])
    parts.append(facet_cut(band))

    # --- advertisement panels along the skirt, the way every CTC car carries them.
    # They sit proud of the body side, not inside it.
    adv_mat = MAT['advert'] if front else MAT['advert2']
    a0, a1 = (lo + 0.55, hi - 4.6) if front else (lo + 1.6, hi - 1.7)
    if a1 - a0 > 1.0:
        for sd in (1, -1):
            parts.append(M.box((a1 - a0, 0.014, 0.40), ((a0 + a1) / 2,
                               sd * (sp['HALF_W'] + 0.006), 1.14),
                               name='advert_%s%d' % (which, sd), coll=coll, mat=adv_mat))

    # --- underframe: solebars, battery and resistor boxes
    for sd in (1, -1):
        parts.append(M.box((abs(hi - lo) - 0.10, 0.08, 0.20),
                           ((lo + hi) / 2, sd * 0.92, 0.40),
                           name='solebar%s%d' % (which, sd), coll=coll, mat=MAT['under']))
    parts.append(M.box((1.5, 1.1, 0.34), ((lo + hi) / 2 + sgn * 1.4, 0.0, 0.33),
                       name='under_box_%s' % which, coll=coll, mat=MAT['under']))
    parts.append(M.box((0.9, 0.7, 0.28), ((lo + hi) / 2 - sgn * 1.9, -0.35, 0.33),
                       name='under_box2_%s' % which, coll=coll, mat=MAT['under']))

    # --- roof ventilators
    nvent = 4
    for i in range(nvent):
        t = (i + 0.5) / nvent
        x = lo + (hi - lo) * t
        parts.append(M.box((0.42, 0.30, 0.055), (x, 0, sp['Z_ROOF'] + 0.028),
                           name='vent%s%d' % (which, i), coll=coll, mat=MAT['roof'],
                           bevel=0.012))

    # --- doorway furniture: steps, grab poles, a handrail each side
    for a, b in doors:
        for sd in (1, -1):
            parts.append(M.box((b - a + 0.12, sp['STEP_OUT'], 0.045),
                               ((a + b) / 2, sd * (sp['HALF_W'] + sp['STEP_OUT'] / 2 - 0.02),
                                sp['Z_STEP']), name='step', coll=coll, mat=MAT['under']))
            for xx in (a - 0.03, b + 0.03):
                parts.append(M.cyl(0.021, sp['Z_DOOR_TOP'] - sp['Z_STEP'],
                                   (xx, sd * (sp['HALF_W'] - 0.05),
                                    (sp['Z_STEP'] + sp['Z_DOOR_TOP']) / 2),
                                   name='grab', coll=coll, mat=MAT['chrome'], seg=10))
    return parts, shell, windows, doors


# ===================================================================== interior
def build_interior(coll):
    sp = SPEC
    parts = []
    parts.append(M.box((sp['L_TOTAL'] - 0.6, 2 * (sp['HALF_W'] - sp['WALL']) - 0.01, 0.04),
                       (0, 0, sp['Z_FLOOR'] - 0.02), name='floor', coll=coll,
                       mat=MAT['black']))
    parts.append(M.box((sp['L_TOTAL'] - 0.6, 2 * (sp['HALF_W'] - sp['WALL']) - 0.02, 0.02),
                       (0, 0, 3.15), name='ceiling', coll=coll, mat=MAT['interior']))

    # transverse bench seats, 2 + 2 either side of a centre aisle
    def bench(x, s, mat):
        base = M.box((0.46, 0.80, 0.06), (x, s * 0.60, 1.17), name='seatpan',
                     coll=coll, mat=mat)
        back = M.box((0.07, 0.80, 0.44), (x - 0.20, s * 0.60, 1.42), name='seatback',
                     coll=coll, mat=mat)
        legs = [M.cyl(0.016, 0.37, (x + dx, s * (0.60 + dy), 0.985), name='seatleg',
                      coll=coll, mat=MAT['steel'], seg=8)
                for dx in (-0.15, 0.15) for dy in (-0.3, 0.3)]
        return [base, back] + legs

    for x in [x for x in [2.0, 2.75, 3.5, 4.25, 5.0, 5.75, 6.5]]:
        for s in (1, -1):
            parts.extend(bench(x, s, MAT['seat']))
    for x in [-1.3, -2.05, -2.8, -3.55, -4.3, -5.05, -5.8, -6.55]:
        for s in (1, -1):
            parts.extend(bench(x, s, MAT['seat']))

    # grab poles down the aisle, and the longitudinal handrail
    for x in [i * 1.5 for i in range(-5, 6)]:
        parts.append(M.cyl(0.019, 3.15 - sp['Z_FLOOR'], (x, 0, (sp['Z_FLOOR'] + 3.15) / 2),
                           name='pole', coll=coll, mat=MAT['chrome'], seg=10))
    for s in (1, -1):
        parts.append(M.cyl(0.018, sp['L_TOTAL'] - 2.2, (0, s * 0.62, 2.92),
                           rot=(0, math.pi / 2, 0), name='rail', coll=coll,
                           mat=MAT['chrome'], seg=10))

    # the class partition, at the articulation
    for s in (1, -1):
        parts.append(M.box((0.05, 0.62, 1.55), (0.0, s * 0.74, 1.56),
                           name='partition', coll=coll, mat=MAT['interior']))

    # motorman's position: controller pedestal, brake standard, a stool
    xn = BODY_OUT
    parts.append(M.cyl(0.14, 0.70, (xn - 0.58, -0.42, 1.13), name='controller',
                       coll=coll, mat=MAT['black'], seg=16))
    parts.append(M.cyl(0.17, 0.05, (xn - 0.58, -0.42, 1.50), name='ctrl_top',
                       coll=coll, mat=MAT['steel'], seg=16))
    parts.append(M.cyl(0.018, 0.34, (xn - 0.58, -0.42, 1.67), name='ctrl_handle',
                       coll=coll, mat=MAT['steel'], seg=10))
    parts.append(M.cyl(0.028, 1.00, (xn - 0.58, 0.46, 1.28), name='brake_std',
                       coll=coll, mat=MAT['steel'], seg=12))
    parts.append(M.tube(0.17, 0.145, 0.03, (xn - 0.58, 0.46, 1.78), (0, 0, 0),
                        name='brake_wheel', coll=coll, mat=MAT['black'], seg=20))
    parts.append(M.box((0.34, 0.34, 0.05), (xn - 1.05, 0.0, 1.10), name='stool',
                       coll=coll, mat=MAT['seat']))
    return parts


# ===================================================================== trucks
def build_truck(x_centre, coll, name):
    """A two-axle tram truck: side frames with journal boxes, two wheelsets,
    a motor case and the brake gear, reduced to what reads from street level."""
    sp = SPEC
    half_g = sp['GAUGE'] / 2 + 0.035          # wheel centre plane, outside the rail head
    r = sp['WHEEL_D'] / 2
    wb = sp['WHEELBASE']
    parts = []
    for s in (1, -1):
        parts.append(M.box((wb + 0.95, 0.075, 0.26), (x_centre, s * (half_g + 0.10), 0.47),
                           name=name + '_frame', coll=coll, mat=MAT['truck'], bevel=0.02))
        for dx in (-wb / 2, wb / 2):
            parts.append(M.box((0.26, 0.17, 0.30), (x_centre + dx, s * (half_g + 0.13), r),
                               name=name + '_jbox', coll=coll, mat=MAT['truck'],
                               bevel=0.015))
            # helical springs over each journal
            parts.append(M.cyl(0.055, 0.17, (x_centre + dx, s * (half_g + 0.13), r + 0.24),
                               name=name + '_spring', coll=coll, mat=MAT['steel'], seg=10))
    for dx in (-wb / 2, wb / 2):
        # axle
        parts.append(M.cyl(0.048, 2 * half_g + 0.10, (x_centre + dx, 0, r),
                           rot=(math.pi / 2, 0, 0), name=name + '_axle', coll=coll,
                           mat=MAT['steel'], seg=12))
        for s in (1, -1):
            # tyre, flange and hub -- the flange sits inboard, against the rail
            parts.append(M.cyl(r, 0.075, (x_centre + dx, s * half_g, r),
                               rot=(math.pi / 2, 0, 0), name=name + '_tyre', coll=coll,
                               mat=MAT['wheel'], seg=36))
            parts.append(M.cyl(r + 0.026, 0.016,
                               (x_centre + dx, s * (half_g - 0.045), r),
                               rot=(math.pi / 2, 0, 0), name=name + '_flange', coll=coll,
                               mat=MAT['wheel'], seg=36))
            parts.append(M.cyl(0.13, 0.085, (x_centre + dx, s * half_g, r),
                               rot=(math.pi / 2, 0, 0), name=name + '_hub', coll=coll,
                               mat=MAT['truck'], seg=16))
    # traction motor slung between the axles, and the gear case
    parts.append(M.cyl(0.21, 0.62, (x_centre, 0.30, r + 0.02), rot=(math.pi / 2, 0, 0),
                       name=name + '_motor', coll=coll, mat=MAT['truck'], seg=20))
    parts.append(M.box((0.40, 0.30, 0.34), (x_centre + wb / 2, 0.38, r + 0.02),
                       name=name + '_gearcase', coll=coll, mat=MAT['truck'], bevel=0.03))
    # brake shoes
    for dx in (-wb / 2, wb / 2):
        for s in (1, -1):
            parts.append(M.box((0.05, 0.08, 0.16),
                               (x_centre + dx - 0.30 * (1 if dx > 0 else -1),
                                s * half_g, r + 0.02),
                               name=name + '_shoe', coll=coll, mat=MAT['steel']))
    # sand boxes and the lifeguard tray under the outer ends
    parts.append(M.box((0.24, 0.22, 0.26), (x_centre - wb / 2 - 0.42, 0.55, 0.52),
                       name=name + '_sand', coll=coll, mat=MAT['truck'], bevel=0.02))
    return parts


# ===================================================================== front end
def build_front(coll):
    """The cab end.

    Modelled on the classic tram cab the reference points at: a faceted bay with a
    three-pane windscreen, the route number painted large on the dash, one big
    round headlight centred below it, a destination board carried on brackets
    above the roof, and marker lamps at the front roof corners. The Kolkata
    additions are the weldmesh over the motorman's side openings (done in
    build_body) and the slatted apron and lifeguard tray at the rail.
    """
    sp = SPEC
    xn, fx, fy = BODY_OUT, sp['FACET_X'], sp['FACET_Y']
    parts = []

    # --- windscreen glazing: flat centre pane plus a raked pane in each facet
    parts.append(M.box((0.012, 2 * fy - 0.14, sp['Z_HEAD'] - sp['Z_SILL'] - 0.01),
                       (xn - 0.028, 0, (sp['Z_SILL'] + sp['Z_HEAD']) / 2),
                       name='windscreen_c', coll=coll, mat=MAT['glass']))
    for sd in (1, -1):
        d = Vector((-fx, sd * (sp['HALF_W'] - fy)))
        ln = d.length
        mid = Vector((xn - fx / 2, sd * (fy + sp['HALF_W']) / 2)) - d.normalized() * 0.0
        inset = d.normalized().orthogonal().normalized()
        parts.append(M.box((ln - 0.10, 0.012, sp['Z_HEAD'] - sp['Z_SILL'] - 0.01),
                           (mid.x, mid.y - sd * 0.022,
                            (sp['Z_SILL'] + sp['Z_HEAD']) / 2),
                           (0, 0, math.atan2(d.y, d.x)),
                           name='windscreen_%d' % sd, coll=coll, mat=MAT['glass']))
        # corner pillar between the centre pane and the raked pane
        parts.append(M.box((0.10, 0.10, sp['Z_HEAD'] - sp['Z_SILL'] + 0.04),
                           (xn - 0.045, sd * (fy - 0.035),
                            (sp['Z_SILL'] + sp['Z_HEAD']) / 2),
                           name='ws_pillar%d' % sd, coll=coll, mat=MAT['body']))
    # centre division of the windscreen
    parts.append(M.box((0.09, 0.075, sp['Z_HEAD'] - sp['Z_SILL'] + 0.04),
                       (xn - 0.04, 0, (sp['Z_SILL'] + sp['Z_HEAD']) / 2),
                       name='ws_mullion', coll=coll, mat=MAT['body']))

    # --- the dash: the route number large in cream, one big headlight below it
    rt = M.text_solid(sp['ROUTE'], 0.26, 0.006, 'routenum', coll, MAT['cream'])
    M.place(rt, (xn + 0.018, 0, 1.36), (math.pi / 2, 0, math.pi / 2))
    parts.append(rt)
    parts.append(M.cyl(0.155, 0.17, (xn - 0.02, 0, 1.00), rot=(0, math.pi / 2, 0),
                       name='hl_can', coll=coll, mat=MAT['black'], seg=28))
    parts.append(M.tube(0.158, 0.130, 0.05, (xn + 0.072, 0, 1.00), (0, math.pi / 2, 0),
                        name='hl_rim', coll=coll, mat=MAT['chrome'], seg=28))
    parts.append(M.cyl(0.132, 0.02, (xn + 0.070, 0, 1.00), rot=(0, math.pi / 2, 0),
                       name='hl_lens', coll=coll, mat=MAT['lamp'], seg=28))
    # fleet number small, on the waist rail
    fn = M.text_solid(sp['FLEET'], 0.085, 0.003, 'fleetnum', coll, MAT['cream'])
    M.place(fn, (xn + 0.016, 0.44, 1.66), (math.pi / 2, 0, math.pi / 2))
    parts.append(fn)

    # --- destination board on brackets over the roof, reading forwards
    bz = sp['Z_ROOF'] + 0.33
    for sd in (1, -1):
        parts.append(M.box((0.035, 0.035, 0.40), (xn - 0.72, sd * 0.42,
                           sp['Z_ROOF'] - 0.02), name='destbrk%d' % sd, coll=coll,
                           mat=MAT['steel']))
    parts.append(M.box((0.055, 1.62, 0.30), (xn - 0.72, 0, bz), name='destboard',
                       coll=coll, mat=MAT['black'], bevel=0.012))
    parts.append(M.box((0.014, 1.54, 0.24), (xn - 0.69, 0, bz), name='destface',
                       coll=coll, mat=MAT['dest']))
    t = M.text_solid(sp['DEST'], 0.135, 0.004, 'desttext', coll, MAT['black'])
    M.place(t, (xn - 0.681, 0, bz - 0.008), (math.pi / 2, 0, math.pi / 2))
    parts.append(t)

    # --- marker lamps at the front roof corners
    for sd in (1, -1):
        parts.append(M.cyl(0.062, 0.14, (xn - 0.20, sd * 0.50, sp['Z_ROOF'] + 0.02),
                           name='roofmarker%d' % sd, coll=coll, mat=MAT['black'], seg=14))
        parts.append(M.cyl(0.050, 0.03, (xn - 0.20, sd * 0.50, sp['Z_ROOF'] + 0.10),
                           name='roofmarkerlens%d' % sd, coll=coll, mat=MAT['lamp'],
                           seg=14))

    # --- the apron and lifeguard: a slatted guard raked down toward the rail with a
    # tray close to the ground. Every Kolkata car has one and it dominates the
    # lower front in the reference images.
    gate_z, gate_h, rake = 0.265, 0.40, -0.28
    parts.append(M.box((0.05, 1.30, gate_h), (xn + 0.085, 0, gate_z), (0, rake, 0),
                       name='lifeguard_gate', coll=coll, mat=MAT['body']))
    for i in range(11):
        y = -0.56 + 1.12 * i / 10
        parts.append(M.box((0.035, 0.030, gate_h - 0.04),
                           (xn + 0.118, y, gate_z + 0.006), (0, rake, 0),
                           name='slat%d' % i, coll=coll, mat=MAT['black']))
    parts.append(M.box((0.26, 1.28, 0.030), (xn + 0.195, 0, 0.085), name='lifeguard',
                       coll=coll, mat=MAT['under'], bevel=0.009))
    parts.append(M.box((0.09, 1.34, 0.11), (xn + 0.035, 0, 0.50), name='bufferbeam',
                       coll=coll, mat=MAT['under'], bevel=0.022))
    parts.append(M.cyl(0.030, 1.22, (xn + 0.062, 0, 0.56), rot=(math.pi / 2, 0, 0),
                       name='fenderbar', coll=coll, mat=MAT['steel'], seg=12))
    # wiper on the centre pane
    parts.append(M.cyl(0.012, 0.50, (xn + 0.005, 0.26, 1.70), rot=(0, 0.5, 0),
                       name='wiper', coll=coll, mat=MAT['black'], seg=8))
    return parts


def build_tail(coll):
    """The trailing end: no cab, a rear window, a tail lamp and the draw gear."""
    sp = SPEC
    xt = -BODY_OUT
    parts = []
    c = M.box((0.60, 1.30, 0.84), (xt + 0.10, 0, 2.03), name='rearcut', coll=coll)
    parts.append(('CUT', c))
    parts.append(M.box((0.012, 1.24, 0.80), (xt + 0.035, 0, 2.03), name='rearglass',
                       coll=coll, mat=MAT['glass']))
    parts.append(M.box((0.05, 1.96, 0.42), (xt - 0.018, 0, 1.30), name='tailpanel',
                       coll=coll, mat=MAT['body']))
    for s in (1, -1):
        parts.append(M.cyl(0.055, 0.06, (xt - 0.05, s * 0.78, 1.18),
                           rot=(0, math.pi / 2, 0), name='taillamp', coll=coll,
                           mat=MAT['chrome'], seg=14))
        parts.append(M.cyl(0.042, 0.016, (xt - 0.085, s * 0.78, 1.18),
                           rot=(0, math.pi / 2, 0), name='taillens', coll=coll,
                           mat=T.emissive('tram_taillight', (1.0, 0.07, 0.03), 9.0),
                           seg=14))
    parts.append(M.box((0.10, 1.98, 0.12), (xt - 0.06, 0, 0.60), name='rearbeam',
                       coll=coll, mat=MAT['under'], bevel=0.025))
    parts.append(M.box((0.28, 1.86, 0.035), (xt - 0.19, 0, 0.115), name='rear_lifeguard',
                       coll=coll, mat=MAT['under'], bevel=0.01))
    fn = M.text_solid(SPEC['FLEET'], 0.085, 0.003, 'fleetnum_r', coll, MAT['white'])
    M.place(fn, (xt - 0.05, -0.62, 1.30), (math.pi / 2, 0, -math.pi / 2))
    parts.append(fn)
    return parts


# ===================================================================== trolley pole
def build_trolley(coll):
    """Trolley pole on the leading body, swept back over the car, sprung at the base.
    It collects from a single 550 V trolley wire -- a pantograph would be wrong here."""
    sp = SPEC
    base_x, base_z = BODY_OUT - 2.0, sp['Z_ROOF'] + 0.03
    parts = []
    parts.append(M.box((0.60, 0.46, 0.05), (base_x, 0, base_z), name='trolley_plate',
                       coll=coll, mat=MAT['roof'], bevel=0.015))
    parts.append(M.cyl(0.085, 0.24, (base_x, 0, base_z + 0.14), name='trolley_base',
                       coll=coll, mat=MAT['black'], seg=16))
    # the pole itself, swept backwards and up
    a = math.radians(sp['POLE_RISE'])
    L = sp['POLE_LEN']
    p0 = Vector((base_x, 0, base_z + 0.26))
    p1 = p0 + Vector((-L * math.cos(a), 0, L * math.sin(a)))
    pole = M.capsule_rod(p0, p1, 0.030, 10, 'trolley_pole', coll, MAT['steel'])
    parts.append(pole)
    # harp and trolley wheel at the tip
    for s in (1, -1):
        parts.append(M.box((0.16, 0.012, 0.10),
                           (p1.x + 0.07, s * 0.045, p1.z + 0.05),
                           rot=(0, -a, 0), name='harp', coll=coll, mat=MAT['steel']))
    parts.append(M.cyl(0.055, 0.035, (p1.x + 0.13, 0, p1.z + 0.085),
                       rot=(math.pi / 2, 0, 0), name='trolley_wheel', coll=coll,
                       mat=MAT['chrome'], seg=18))
    # tension springs at the base and the retrieval rope back along the roof
    parts.append(M.cyl(0.028, 0.30, (base_x - 0.22, 0.17, base_z + 0.20),
                       rot=(0, -a + math.pi / 2, 0), name='pole_spring', coll=coll,
                       mat=MAT['steel'], seg=10))
    rope_end = Vector((BODY_OUT - 7.6, 0.0, sp['Z_ROOF'] + 0.08))
    parts.append(M.capsule_rod(p1 + Vector((0.10, 0, 0.02)), rope_end, 0.006, 6,
                               'trolley_rope', coll, MAT['black']))
    return parts


# ===================================================================== bellows
def build_bellows(coll):
    """The concertina between the two bodies, over the shared articulation truck."""
    sp = SPEC
    rings = []
    n = 9
    for i in range(n + 1):
        t = i / n
        x = -BODY_IN + sp['GAP'] * t
        pinch = 0.055 if i % 2 else 0.0
        w = 2 * (sp['HALF_W'] - 0.085) - 2 * pinch
        h = (sp['Z_SHOULDER'] - 0.04) - sp['Z_FLOOR'] - 2 * pinch
        prof = M.rounded_rect_profile(w, h, 0.12, 3)
        cz = (sp['Z_FLOOR'] + sp['Z_SHOULDER'] - 0.04) / 2
        rings.append([Vector((x, p.y, p.z + cz)) for p in prof])
    ob = M.loft(rings, False, False, 'bellows', coll, MAT['black'], smooth=False)
    M.solidify(ob, 0.02)
    gang = M.box((sp['GAP'] + 0.1, 1.5, 0.05), (0, 0, sp['Z_FLOOR'] - 0.02),
                 name='gangway', coll=coll, mat=MAT['black'])
    return [ob, gang]


# ===================================================================== assemble
def main():
    S.reset('TramBuild')
    materials()
    coll = S.coll('TRAM_CTC')
    scratch = S.coll('_scratch')

    S.log('front body')
    fparts, fshell, fwin, fdoor = build_body('front', scratch)
    S.log('rear body')
    rparts, rshell, rwin, rdoor = build_body('rear', scratch)

    # cut the rear window into the trailing body before anything is joined
    tail = build_tail(scratch)
    tail_parts = []
    for item in tail:
        if isinstance(item, tuple) and item[0] == 'CUT':
            M.boolean(rshell, item[1], 'DIFFERENCE')
        else:
            tail_parts.append(item)

    S.log('trucks, interior, ends, trolley, bellows')
    parts = list(fparts) + list(rparts) + tail_parts
    parts += build_front(scratch)
    parts += build_interior(scratch)
    parts += build_bellows(scratch)
    parts += build_trolley(scratch)
    for i, x in enumerate((SPEC['TRUCK_X'], 0.0, -SPEC['TRUCK_X'])):
        parts += build_truck(x, scratch, 'truck%d' % i)

    body = M.join([p for p in parts if p is not None], 'TramCTC', coll)
    # The join target keeps its own object transform, and parts[0] is not at the
    # origin, so bake it down: a linked asset must have local space == world space
    # and its origin on the road under the centre of the vehicle.
    M.apply_transform(body, loc=True, rot=True, scale=True)
    M.shade_smooth(body, 28.0)
    body.location = (0, 0, 0)

    # tidy: nothing should be left in the scratch collection
    for ob in list(scratch.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.context.scene.collection.children.unlink(scratch)
    bpy.data.collections.remove(scratch)

    mn, mx = M.dims(body)
    S.log('tram bounds  L=%.3f (body %.3f)  W=%.3f (body %.3f)  H=%.3f incl. pole' %
          (mx.x - mn.x, SPEC['L_TOTAL'], mx.y - mn.y, SPEC['WIDTH'], mx.z - mn.z))
    S.log('tris=%d  materials=%d' % (M.tri_count(body), len(body.data.materials)))

    out = os.path.join(S.ASSETS, 'tram_ctc.blend')
    S.save(out)

    if S.has_flag('--preview'):
        preview(body)


def preview(body):
    """Orthographic elevations plus one three-quarter view.

    Orthographic, because the point of a model preview is to check proportions
    against the reference, and perspective makes that impossible to judge.
    A short length of standard-gauge track is laid so the wheels can be checked
    sitting on the rail head rather than floating or sunk.
    """
    import mathutils
    sc = S.cycles(samples=64, res=(1600, 900), device='CPU', bounces=4)
    sc.world = bpy.data.worlds.new('w')
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.58, 0.63, 0.70, 1)
    bg.inputs[1].default_value = 2.2
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
    sun.data.energy = 2.6
    sun.data.angle = math.radians(3.0)
    sun.rotation_euler = (math.radians(46), 0, math.radians(118))
    sc.collection.objects.link(sun)

    road = T.base('prev_road', (0.045, 0.045, 0.048), 0.75)
    M.plane((80, 40), (0, 0, -0.14), name='gnd', mat=road)
    railmat = T.steel('prev_rail', 0.22, (0.50, 0.49, 0.47))
    for sdy in (1, -1):
        y = sdy * (SPEC['GAUGE'] / 2 + 0.035)
        M.box((60, 0.070, 0.14), (0, y, -0.07), name='rail', mat=railmat)

    mn, mx = M.dims(body)
    ctr = (mn + mx) / 2
    span = max(mx.x - mn.x, mx.z - mn.z) * 1.08

    cam_data = bpy.data.cameras.new('cam')
    cam = bpy.data.objects.new('cam', cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    shots = [
        ('elev_side',  'ORTHO', (ctr.x, -40, ctr.z), (ctr.x, 0, ctr.z), span),
        ('elev_front', 'ORTHO', (40, 0, ctr.z), (0, 0, ctr.z), 6.0),
        ('elev_rear',  'ORTHO', (-40, 0, ctr.z), (0, 0, ctr.z), 6.0),
        ('plan',       'ORTHO', (ctr.x, 0, 40), (ctr.x, 0, 0), span),
        ('3q',         'PERSP', (19.0, -15.0, 5.2), (-0.5, 0, 1.6), 55),
        ('3q_rear',    'PERSP', (-17.0, 12.0, 4.4), (1.0, 0, 1.6), 55),
        ('nose',       'PERSP', (14.5, -3.4, 1.35), (6.0, 0.4, 1.6), 50),
    ]
    for name, kind, loc, aim, val in shots:
        cam_data.type = kind
        if kind == 'ORTHO':
            cam_data.ortho_scale = val
        else:
            cam_data.lens = val
        cam.location = loc
        d = mathutils.Vector(aim) - mathutils.Vector(loc)
        up = 'Y' if name != 'plan' else 'Y'
        cam.rotation_euler = d.to_track_quat('-Z', up).to_euler()
        sc.render.filepath = os.path.join(S.RENDERS, 'tram_%s.png' % name)
        S.log('render %s' % name)
        bpy.ops.render.render(write_still=True)


main()
