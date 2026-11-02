"""Hindustan Ambassador, Kolkata taxi  ->  assets/ambassador_taxi.blend

Built once, here, and linked into the street scene.

WHAT IS BEING MODELLED
----------------------
The Hindustan Motors Ambassador Mark IV / Classic -- the Morris Oxford Series III
body Hindustan kept building at Uttarpara until 2014, and the car that is the
Kolkata taxi. Published figures it is built to:

  length       4,325 mm
  width        1,662 mm
  height       1,600 mm      (sources vary 1,593-1,600)
  wheelbase    2,464 mm
  ground clr.    155 mm
  wheels       14 in rims, ~165R14, so a 0.62-0.64 m tyre

Sources disagree by a millimetre or two on width and height; SPEC below carries
the figure used so it is easy to change.

The body is not boxes. It is a loft through fourteen cross-sections, each one a
closed Catmull-Rom curve through seven landmarks (underside, widest point,
beltline, tumblehome, roof side, crown). That is what gets the bulbous Morris
shoulder and the domed roof; a box-and-bevel car would read as a generic saloon.
Wheel arches, the glasshouse and the cabin are then cut with booleans.

Taxi fittings: all-over yellow, roof TAXI box, yellow number plates front and
rear, right-hand drive (India drives on the left, so the wheel is on the right,
at -Y in this file's axes).

Axes:  +X forward, +Z up, z = 0 is the road. +Y is the car's LEFT.

Run:
    blender -b -P build/build_ambassador.py
    blender -b -P build/build_ambassador.py -- --preview
"""
import bpy, math, os, sys
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klib import mesh as M, mat as T, sceneutil as S

S.log_to(os.path.join(S.ROOT, 'build', 'build_ambassador.log'))

SPEC = dict(
    LENGTH=4.325, WIDTH=1.662, HEIGHT=1.600, WHEELBASE=2.464, CLEARANCE=0.155,
    WHEEL_D=0.635, TYRE_W=0.185, TRACK=1.300,
    FRONT_AXLE=1.360, REAR_AXLE=-1.104,          # 1.360 + 1.104 = 2.464
    PLATE='WB 04F 0325',
    RINGS=4,                                      # Catmull-Rom samples per landmark span
    STATION_SPANS=3,                              # samples between key stations
)
HALF_L = SPEC['LENGTH'] / 2                       # 2.1625, over bumpers
X_NOSE = HALF_L - 0.088                           # the body's own nose/tail
HW = SPEC['WIDTH'] / 2                            # 0.831
RW = SPEC['WHEEL_D'] / 2

MAT = {}


def materials():
    MAT['paint'] = T.car_paint('amb_yellow', T.srgb('#eaa90f'), rough=0.26,
                               coat=1.0, dirt=0.30)
    MAT['black'] = T.car_paint('amb_black', T.srgb('#101012'), rough=0.35,
                               coat=0.8, dirt=0.35)
    MAT['chrome'] = T.chrome('amb_chrome', rough=0.09)
    MAT['glass'] = T.base('amb_glass', (0.52, 0.57, 0.56), 0.04, 0.0,
                          ior=1.52, transmission=0.90)
    MAT['rubber'] = T.rubber('amb_rubber', rough=0.80)
    MAT['tread'] = T.rubber('amb_tread', rough=0.88, tint=(0.022, 0.022, 0.024))
    MAT['lamp'] = T.emissive('amb_lamp', (1.0, 0.90, 0.68), 14.0)
    MAT['amber'] = T.base('amb_amber', T.srgb('#e08b10'), 0.18, coat=0.9)
    MAT['red'] = T.base('amb_red', T.srgb('#a8120c'), 0.22, coat=0.9)
    MAT['plate'] = T.base('amb_plate', T.srgb('#e8bb16'), 0.45)
    MAT['plate_ink'] = T.base('amb_plate_ink', (0.008, 0.008, 0.008), 0.55)
    MAT['trim'] = T.base('amb_trim', (0.015, 0.015, 0.016), 0.70)
    MAT['seat'] = T.base('amb_seat', T.srgb('#ded7c4'), 0.60, sheen=0.4)
    MAT['dash'] = T.base('amb_dash', T.srgb('#2a2622'), 0.62)
    MAT['steel'] = T.steel('amb_steel', rough=0.45)


# ===================================================================== body
# x, z_bot, hw_bot, z_max, hw_max, z_belt, hw_belt, z_green, hw_green,
#    z_roof, hw_roof, z_top
KEY = [
    (+2.0745, 0.44, 0.58, 0.62, 0.670, 0.80, 0.645, 0.86, 0.52, 0.90, 0.32, 0.93),
    (+2.0300, 0.37, 0.66, 0.64, 0.745, 0.85, 0.710, 0.91, 0.580, 0.95, 0.37, 0.99),
    (+1.8000, 0.30, 0.71, 0.66, 0.800, 0.92, 0.755, 0.98, 0.615, 1.02, 0.39, 1.055),
    (+1.4500, 0.27, 0.745, 0.68, 0.822, 0.975, 0.780, 1.035, 0.635, 1.075, 0.41, 1.105),
    (+1.0500, 0.26, 0.750, 0.66, 0.822, 1.000, 0.780, 1.060, 0.620, 1.100, 0.40, 1.130),
    (+0.5800, 0.26, 0.750, 0.66, 0.822, 1.020, 0.780, 1.105, 0.690, 1.200, 0.52, 1.255),
    (+0.4000, 0.26, 0.750, 0.66, 0.822, 1.030, 0.780, 1.230, 0.715, 1.440, 0.585, 1.490),
    (+0.2000, 0.26, 0.750, 0.66, 0.822, 1.040, 0.780, 1.300, 0.730, 1.545, 0.635, 1.585),
    (-0.3000, 0.26, 0.750, 0.66, 0.822, 1.050, 0.780, 1.320, 0.740, 1.560, 0.655, 1.600),
    (-0.9500, 0.26, 0.748, 0.66, 0.830, 1.050, 0.778, 1.305, 0.722, 1.538, 0.618, 1.578),
    (-1.2500, 0.27, 0.740, 0.66, 0.825, 1.040, 0.772, 1.180, 0.680, 1.320, 0.520, 1.360),
    (-1.5500, 0.28, 0.730, 0.66, 0.815, 1.020, 0.765, 1.060, 0.660, 1.100, 0.450, 1.130),
    (-1.9500, 0.33, 0.680, 0.64, 0.780, 0.980, 0.720, 1.020, 0.580, 1.055, 0.380, 1.080),
    (-2.0745, 0.43, 0.545, 0.62, 0.630, 0.920, 0.590, 0.960, 0.470, 0.995, 0.295, 1.020),
]


def cr_scalar(vals, spans):
    """Catmull-Rom through a list of floats, indexed by position. Used to blow the
    fourteen key stations up into a smooth run of forty."""
    n = len(vals)
    ext = [2 * vals[0] - vals[1]] + list(vals) + [2 * vals[-1] - vals[-2]]
    out = []
    for i in range(n - 1):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for s in range(spans):
            t = s / spans
            t2, t3 = t * t, t * t * t
            out.append(0.5 * (2 * p1 + (p2 - p0) * t
                              + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(vals[-1])
    return out


def section_ring(x, z_bot, hw_bot, z_max, hw_max, z_belt, hw_belt, z_green, hw_green,
                 z_roof, hw_roof, z_top):
    """One closed cross-section.

    The landmarks are mirrored and the spline is run closed, which is what keeps
    the roof crown and the underside smooth across the centre line -- a half
    section splined on its own creases there.
    """
    lm = [(0.0, z_bot), (hw_bot, z_bot + 0.012), (hw_max, z_max), (hw_belt, z_belt),
          (hw_green, z_green), (hw_roof, z_roof), (0.0, z_top)]
    full = lm + [(-y, z) for y, z in reversed(lm[1:-1])]
    pts = M.catmull_rom([Vector((0.0, y, z)) for y, z in full],
                        SPEC['RINGS'], closed=True)
    return [Vector((x, p.y, p.z)) for p in pts]


WALL = 0.045          # body skin thickness


STATIONS = []           # filled by build_shell, read by hw_at


def stations():
    if not STATIONS:
        cols = list(zip(*KEY))
        STATIONS.extend(zip(*[cr_scalar(c, SPEC['STATION_SPANS']) for c in cols]))
    return STATIONS


def hw_at(x, z, bias=0.004):
    """Half-width of the body at a point on its flank.

    Every strip of trim -- waist moulding, shut lines, handles, mirrors, the side
    glass -- has to sit ON the surface. The body tumbles in above the beltline by
    about 150 mm, so a trim strip placed at a constant y either floats in the air
    or disappears inside the car. This walks the landmark polyline of the two
    stations either side of x and interpolates, which is close enough to the
    splined surface for trim once `bias` pushes it just proud.
    """
    st = stations()
    xs = [t[0] for t in st]
    if x >= xs[0]:
        i, f = 0, 0.0
    elif x <= xs[-1]:
        i, f = len(st) - 2, 1.0
    else:
        i = max(j for j in range(len(st) - 1) if xs[j] >= x)
        f = (xs[i] - x) / (xs[i] - xs[i + 1])

    def y_of(t):
        (_, z_bot, hw_bot, z_max, hw_max, z_belt, hw_belt, z_green, hw_green,
         z_roof, hw_roof, z_top) = t
        pts = [(0.0, z_bot), (hw_bot, z_bot + 0.012), (hw_max, z_max),
               (hw_belt, z_belt), (hw_green, z_green), (hw_roof, z_roof),
               (0.0, z_top)]
        if z <= pts[0][1]:
            return pts[0][0]
        for a, b in zip(pts, pts[1:]):
            if a[1] <= z <= b[1]:
                u = 0.0 if b[1] == a[1] else (z - a[1]) / (b[1] - a[1])
                return a[0] + (b[0] - a[0]) * u
        return pts[-1][0]

    return M.lerp(y_of(st[i]), y_of(st[i + 1]), f) + bias


def build_shell(coll):
    rings = [section_ring(*vals) for vals in stations()]
    return M.loft(rings, True, True, 'AmbassadorBody', coll, MAT['paint'],
                  smooth=True, auto_angle=46.0)


def build_inner_shell(coll):
    """The same loft, inset by WALL, used to hollow the body.

    This matters more than it looks. A window cutter driven into a *solid* body
    only buries a void inside it; the surface never opens and the mesh stops
    being a clean solid, after which every later boolean misbehaves. Hollowing
    first means each window cutter breaks through a skin, which is what a window
    actually is.
    """
    w = WALL
    rings = []
    for (x, z_bot, hw_bot, z_max, hw_max, z_belt, hw_belt, z_green, hw_green,
         z_roof, hw_roof, z_top) in stations():
        xi = math.copysign(min(abs(x), X_NOSE - w), x)       # pull the end caps in
        rings.append(section_ring(xi, z_bot + w, max(0.05, hw_bot - w), z_max,
                                  max(0.05, hw_max - w), z_belt,
                                  max(0.05, hw_belt - w), z_green,
                                  max(0.05, hw_green - w), z_roof - w * 0.4,
                                  max(0.05, hw_roof - w), z_top - w))
    return M.loft(rings, True, True, 'AmbassadorCavity', coll, smooth=False)


def cut_arches(body, coll):
    """Wheel arches, cut from each side separately so the car does not end up with
    a tunnel through it, plus a dark liner hugging the cut."""
    liners = []
    for ax in (SPEC['FRONT_AXLE'], SPEC['REAR_AXLE']):
        for sd in (1, -1):
            c = M.cyl(0.405, 0.60, (ax, sd * 0.72, RW + 0.025), (math.pi / 2, 0, 0),
                      name='archcut', coll=coll, seg=28)
            M.boolean(body, c, 'DIFFERENCE')
            liners.append(M.tube(0.399, 0.380, 0.42, (ax, sd * 0.61, RW + 0.025),
                                 (math.pi / 2, 0, 0), name='archliner', coll=coll,
                                 mat=MAT['trim'], seg=28))
            liners.append(M.cyl(0.398, 0.02, (ax, sd * 0.410, RW + 0.025),
                                (math.pi / 2, 0, 0), name='archback', coll=coll,
                                mat=MAT['trim'], seg=28))
    return liners


GLASS = dict(
    # (x0, x1, z0, z1) side apertures, in the car's own frame
    front_door=(+0.14, -0.44, 1.075, 1.455),
    rear_door=(-0.54, -1.03, 1.075, 1.435),
)
# (cowl point, roof point) in the XZ plane, for the two raked screens
WINDSCREEN = ((0.555, 1.090), (0.215, 1.525))
REARSCREEN = ((-1.320, 1.070), (-0.990, 1.520))


def raked_slab(p0, p1, width, inset, thickness=0.26):
    """Centre, size and Y-rotation of a slab lying across a raked screen."""
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dz)
    beta = math.atan2(dx, dz)
    centre = ((p0[0] + p1[0]) / 2, 0.0, (p0[1] + p1[1]) / 2)
    return centre, (thickness, width, max(0.05, L - inset)), (0, beta, 0)


def cut_glasshouse(body, coll):
    """Side windows cut straight through, and the two raked screens cut normal to
    their own plane. The body is already hollow, so each of these opens a hole."""
    glass = []
    for name, (x0, x1, z0, z1) in GLASS.items():
        c = M.box((abs(x1 - x0), 2.4, z1 - z0), ((x0 + x1) / 2, 0, (z0 + z1) / 2),
                  name='sidecut_' + name, coll=coll)
        M.boolean(body, c, 'DIFFERENCE')
        cx = (x0 + x1) / 2
        yb, yt = hw_at(cx, z0, -0.018), hw_at(cx, z1, -0.018)
        tilt = math.atan2(yb - yt, z1 - z0)
        for sd in (1, -1):
            glass.append(M.box((abs(x1 - x0) - 0.012, 0.006, z1 - z0 - 0.012),
                               (cx, sd * (yb + yt) / 2, (z0 + z1) / 2),
                               (sd * tilt, 0, 0),
                               name='glass_%s%d' % (name, sd), coll=coll,
                               mat=MAT['glass']))
    for nm, (p0, p1), w in (('windscreen', WINDSCREEN, 1.32),
                            ('rearscreen', REARSCREEN, 1.20)):
        ctr, size, rot = raked_slab(p0, p1, w, 0.09)
        M.boolean(body, M.box(size, ctr, rot, name=nm + 'cut', coll=coll),
                  'DIFFERENCE')
        gctr, gsize, grot = raked_slab(p0, p1, w - 0.05, 0.14, thickness=0.010)
        glass.append(M.box(gsize, gctr, grot, name=nm, coll=coll, mat=MAT['glass']))
    return glass


# ===================================================================== details
def build_front_end(coll):
    p = []
    xf = X_NOSE
    # grille: a recessed black box with horizontal chrome bars and a chrome surround
    p.append(M.box((0.07, 0.92, 0.33), (xf - 0.045, 0, 0.745), name='grille_back',
                   coll=coll, mat=MAT['trim']))
    for i in range(7):
        z = 0.605 + 0.28 * i / 6
        p.append(M.box((0.055, 0.88, 0.022), (xf - 0.012, 0, z), name='gbar%d' % i,
                       coll=coll, mat=MAT['chrome']))
    p.append(M.box((0.05, 0.05, 0.34), (xf - 0.010, 0, 0.745), name='gcentre',
                   coll=coll, mat=MAT['chrome']))
    for sd in (1, -1):
        p.append(M.box((0.05, 0.045, 0.36), (xf - 0.012, sd * 0.465, 0.745),
                       name='gedge%d' % sd, coll=coll, mat=MAT['chrome']))
    p.append(M.box((0.05, 0.96, 0.045), (xf - 0.012, 0, 0.925), name='gtop',
                   coll=coll, mat=MAT['chrome']))

    # headlights set into the wings, with chrome rims
    for sd in (1, -1):
        p.append(M.cyl(0.098, 0.12, (xf - 0.045, sd * 0.545, 0.860),
                       (0, math.pi / 2, 0), name='hl_can%d' % sd, coll=coll,
                       mat=MAT['trim'], seg=24))
        p.append(M.tube(0.102, 0.080, 0.045, (xf + 0.022, sd * 0.545, 0.860),
                        (0, math.pi / 2, 0), name='hl_rim%d' % sd, coll=coll,
                        mat=MAT['chrome'], seg=24))
        p.append(M.cyl(0.082, 0.018, (xf + 0.012, sd * 0.545, 0.860),
                       (0, math.pi / 2, 0), name='hl_lens%d' % sd, coll=coll,
                       mat=MAT['lamp'], seg=24))
        # indicator / side lamp below
        p.append(M.cyl(0.040, 0.05, (xf + 0.005, sd * 0.565, 0.668),
                       (0, math.pi / 2, 0), name='ind%d' % sd, coll=coll,
                       mat=MAT['amber'], seg=16))

    # bumper: three segments so it wraps, with two over-riders
    bx = HALF_L - 0.0500
    p.append(M.box((0.085, 1.10, 0.105), (bx, 0, 0.545), name='bumper_c',
                   coll=coll, mat=MAT['chrome'], bevel=0.028, bevel_seg=3))
    for sd in (1, -1):
        p.append(M.box((0.085, 0.42, 0.105), (bx - 0.060, sd * 0.70, 0.545),
                       (0, 0, sd * 0.42), name='bumper_e%d' % sd, coll=coll,
                       mat=MAT['chrome'], bevel=0.026, bevel_seg=3))
        p.append(M.box((0.10, 0.075, 0.23), (bx - 0.005, sd * 0.235, 0.600),
                       name='override%d' % sd, coll=coll, mat=MAT['chrome'],
                       bevel=0.022, bevel_seg=2))
    # bonnet ornament
    p.append(M.box((0.16, 0.035, 0.030), (xf - 0.13, 0, 0.955), (0, -0.12, 0),
                   name='bonnet_badge', coll=coll, mat=MAT['chrome'], bevel=0.008))
    # number plate
    p += plate(xf + 0.030, 0.400, 0, coll, face=1)
    # wipers
    for sd in (1, -1):
        p.append(M.cyl(0.010, 0.44, (0.55, sd * 0.26, 1.085), (0, 0.9, sd * 0.25),
                       name='wiper%d' % sd, coll=coll, mat=MAT['trim'], seg=8))
    return p


def build_rear_end(coll):
    p = []
    xr = -X_NOSE
    bx = -HALF_L + 0.0500
    p.append(M.box((0.085, 1.06, 0.105), (bx, 0, 0.605), name='rbumper_c',
                   coll=coll, mat=MAT['chrome'], bevel=0.028, bevel_seg=3))
    for sd in (1, -1):
        p.append(M.box((0.085, 0.38, 0.105), (bx + 0.060, sd * 0.665, 0.605),
                       (0, 0, -sd * 0.42), name='rbumper_e%d' % sd, coll=coll,
                       mat=MAT['chrome'], bevel=0.026, bevel_seg=3))
        # upright tail lamps
        p.append(M.box((0.055, 0.085, 0.175), (xr + 0.015, sd * 0.515, 0.845),
                       name='taillamp%d' % sd, coll=coll, mat=MAT['red'],
                       bevel=0.016, bevel_seg=2))
        p.append(M.box((0.030, 0.085, 0.055), (xr + 0.020, sd * 0.515, 0.735),
                       name='reverse%d' % sd, coll=coll, mat=MAT['chrome'],
                       bevel=0.010))
    p.append(M.box((0.05, 0.42, 0.035), (xr + 0.012, 0, 0.985), name='rbadge',
                   coll=coll, mat=MAT['chrome']))
    p += plate(xr - 0.012, 0.700, math.pi, coll, face=-1)
    # exhaust
    p.append(M.cyl(0.026, 0.18, (xr + 0.02, 0.40, 0.345), (0, math.pi / 2, 0),
                   name='exhaust', coll=coll, mat=MAT['steel'], seg=12))
    # mudflaps behind the rear wheels
    for sd in (1, -1):
        p.append(M.box((0.014, 0.17, 0.20), (SPEC['REAR_AXLE'] - 0.42, sd * 0.655, 0.16),
                       name='mudflap%d' % sd, coll=coll, mat=MAT['rubber']))
    return p


def plate(x, z, yaw, coll, face=1):
    """Indian commercial plate: black on yellow."""
    p = [M.box((0.012, 0.50, 0.135), (x, 0, z), (0, 0, yaw), name='plate',
               coll=coll, mat=MAT['plate'])]
    t = M.text_solid(SPEC['PLATE'], 0.078, 0.003, 'platetext', coll, MAT['plate_ink'],
                     spacing=0.92)
    M.place(t, (x + face * 0.010, 0, z - 0.004),
            (math.pi / 2, 0, math.pi / 2 if face > 0 else -math.pi / 2))
    p.append(t)
    return p


def build_sides(coll):
    """Waist moulding, door shut lines, handles, window surrounds and the wing
    mirrors -- all placed with hw_at so they lie on the flank rather than near it."""
    p = []
    for sd in (1, -1):
        # waist moulding, segmented so it follows the curve of the flank
        zc = 0.985
        segs = [(-1.68, -1.10), (-1.05, -0.56), (-0.51, 0.10), (0.15, 0.80),
                (0.85, 1.42)]
        for x0, x1 in segs:
            cx = (x0 + x1) / 2
            p.append(M.box((x1 - x0, 0.016, 0.020), (cx, sd * hw_at(cx, zc), zc),
                           name='waiststrip', coll=coll, mat=MAT['chrome']))
        # door shut lines
        for x in (0.145, -0.495, -1.055):
            z0, z1 = 0.46, 1.045
            yb, yt = hw_at(x, z0), hw_at(x, z1)
            p.append(M.box((0.010, 0.014, z1 - z0),
                           (x, sd * (yb + yt) / 2, (z0 + z1) / 2),
                           (sd * math.atan2(yb - yt, z1 - z0), 0, 0),
                           name='shutline', coll=coll, mat=MAT['trim']))
        # door handles
        for x in (-0.09, -0.73):
            p.append(M.box((0.13, 0.032, 0.030), (x, sd * hw_at(x, 1.030) + sd * 0.012,
                                                  1.030),
                           name='handle', coll=coll, mat=MAT['chrome'], bevel=0.009))
        # chrome surrounds on the window apertures, on the glass plane
        for (x0, x1, z0, z1) in GLASS.values():
            cx, w = (x0 + x1) / 2, abs(x1 - x0)
            for z, h in ((z1, 0.020), (z0, 0.024)):
                p.append(M.box((w, 0.018, h), (cx, sd * hw_at(cx, z, -0.006), z),
                               name='winsurround', coll=coll, mat=MAT['chrome']))
        # wing mirror, on its stalk
        my = hw_at(1.08, 1.12)
        p.append(M.cyl(0.011, 0.13, (1.08, sd * (my + 0.055), 1.165), (sd * 0.5, 0, 0),
                       name='mirrorstem', coll=coll, mat=MAT['chrome'], seg=8))
        p.append(M.cyl(0.052, 0.022, (1.08, sd * (my + 0.115), 1.225),
                       (0, math.pi / 2, 0), name='mirror', coll=coll,
                       mat=MAT['chrome'], seg=16))
        # sill below the doors
        p.append(M.box((2.26, 0.07, 0.055), (-0.10, sd * hw_at(-0.10, 0.33) - sd * 0.02,
                                             0.315),
                       name='sill', coll=coll, mat=MAT['trim'], bevel=0.013))
    return p


def build_wheel(x, sd, coll, steer=0.0):
    """Tyre revolved from a rounded profile, steel rim, chrome hubcap."""
    y = sd * SPEC['TRACK'] / 2
    tw = SPEC['TYRE_W'] / 2
    prof = [(0.215, -tw + 0.01), (0.255, -tw), (0.300, -tw + 0.018),
            (RW, -tw + 0.055), (RW, tw - 0.055), (0.300, tw - 0.018),
            (0.255, tw), (0.215, tw - 0.01)]
    tyre = M.revolve(prof, 36, 'Y', M.TAU, 'tyre', coll, MAT['tread'], True, 50.0,
                     cap=False)
    rim = M.cyl(0.218, SPEC['TYRE_W'] - 0.05, (0, 0, 0), (math.pi / 2, 0, 0),
                name='rim', coll=coll, mat=MAT['steel'], seg=28)
    cap_ = M.sphere(0.145, (0, 0, 0), name='hubcap', coll=coll, mat=MAT['chrome'],
                    seg=24, rings=6, squash=0.42, hemi=True)
    cap_.rotation_euler = (math.pi / 2 * (-sd), 0, 0)
    cap_.location = (0, sd * (tw - 0.045), 0)
    M.apply_transform(cap_, loc=True)
    w = M.join([tyre, rim, cap_], 'wheel_%.2f_%d' % (x, sd), coll)
    M.place(w, (x, y, RW), (0, 0, steer))
    return w


def build_interior(coll):
    p = []
    p.append(M.box((2.10, 1.42, 0.03), (-0.35, 0, 0.545), name='cabfloor', coll=coll,
                   mat=MAT['dash']))
    # dashboard and parcel shelf
    p.append(M.box((0.20, 1.40, 0.20), (0.565, 0, 1.055), name='dash', coll=coll,
                   mat=MAT['dash'], bevel=0.05, bevel_seg=2))
    # right-hand drive: India drives on the left, so the wheel is at -Y
    p.append(M.cyl(0.028, 0.30, (0.44, -0.33, 1.08), (0, 1.05, 0), name='column',
                   coll=coll, mat=MAT['dash'], seg=10))
    p.append(M.tube(0.185, 0.160, 0.022, (0.325, -0.33, 1.195), (0, 1.05, 0),
                    name='steering', coll=coll, mat=MAT['trim'], seg=26))
    # taxi meter on the dash, driver's side
    p.append(M.box((0.11, 0.09, 0.13), (0.50, -0.10, 1.215), name='meter', coll=coll,
                   mat=MAT['trim'], bevel=0.015))
    # front and rear bench seats, loose white covers as Kolkata taxis run
    for x, bx in ((0.06, -0.14), (-0.86, -1.06)):
        p.append(M.box((0.50, 1.32, 0.16), (x, 0, 0.705), name='seatbase', coll=coll,
                       mat=MAT['seat'], bevel=0.05, bevel_seg=2))
        p.append(M.box((0.14, 1.32, 0.50), (bx, 0, 0.995), (0, -0.12, 0),
                       name='seatback', coll=coll, mat=MAT['seat'], bevel=0.05,
                       bevel_seg=2))
    p.append(M.box((0.42, 1.30, 0.03), (-1.34, 0, 1.055), name='parcelshelf',
                   coll=coll, mat=MAT['dash']))
    # bulkheads: the body is a hollow shell, so without these you see straight up
    # the bonnet and into the boot through the glass
    p.append(M.box((0.05, 1.46, 0.62), (0.655, 0, 0.86), name='bulkhead_f', coll=coll,
                   mat=MAT['dash']))
    p.append(M.box((0.05, 1.46, 0.60), (-1.40, 0, 0.85), name='bulkhead_r', coll=coll,
                   mat=MAT['dash']))
    return p


def build_taxi_kit(coll):
    """Roof TAXI box and the black roof band."""
    p = []
    p.append(M.box((0.44, 0.185, 0.145), (0.10, 0, 1.675), name='taxibox', coll=coll,
                   mat=MAT['black'], bevel=0.022, bevel_seg=2))
    for sd in (1, -1):
        p.append(M.box((0.40, 0.012, 0.105), (0.10, sd * 0.094, 1.675),
                       name='taxiface%d' % sd, coll=coll,
                       mat=T.emissive('amb_taxi_sign', T.srgb('#ffd24a'), 4.0)))
        t = M.text_solid('TAXI', 0.075, 0.003, 'taxitext', coll, MAT['black'],
                         spacing=1.05)
        M.place(t, (0.10, sd * 0.102, 1.672),
                (math.pi / 2, 0, math.pi if sd > 0 else 0))
        p.append(t)
    for sd in (1, -1):
        p.append(M.cyl(0.016, 0.085, (0.10, sd * 0.07, 1.598), name='taxileg',
                       coll=coll, mat=MAT['steel'], seg=8))
    return p


# ===================================================================== assemble
def main():
    S.reset('AmbassadorBuild')
    materials()
    coll = S.coll('AMBASSADOR_TAXI')
    scratch = S.coll('_scratch')

    def chk(stage):
        """Log the body's envelope and whether it is still a closed solid.

        Not debug leftovers. A boolean that goes wrong here does not raise --
        it quietly returns a fragment, or eats the car, and the failure only
        shows up in a render twenty minutes later. closed= going False is the
        earliest signal.
        """
        mn, mx = M.dims(body)
        S.log('%-12s closed=%-5s  x %6.3f..%6.3f  y %6.3f..%6.3f  z %6.3f..%6.3f'
              % (stage, M.is_closed(body), mn.x, mx.x, mn.y, mx.y, mn.z, mx.z))

    S.log('shell')
    body = build_shell(scratch)
    chk('shell')
    M.boolean(body, build_inner_shell(scratch), 'DIFFERENCE')
    chk('hollow')
    parts = cut_arches(body, scratch)
    chk('arches')
    parts += cut_glasshouse(body, scratch)
    chk('glasshouse')
    M.weld(body)
    M.shade_smooth(body, 46.0)
    parts.append(body)

    S.log('details')
    parts += build_front_end(scratch)
    parts += build_rear_end(scratch)
    parts += build_sides(scratch)
    parts += build_interior(scratch)
    parts += build_taxi_kit(scratch)
    for x, steer in ((SPEC['FRONT_AXLE'], 0.0), (SPEC['REAR_AXLE'], 0.0)):
        for sd in (1, -1):
            parts.append(build_wheel(x, sd, scratch, steer))

    bmn, bmx = M.dims(body)
    car = M.join([p for p in parts if p is not None], 'AmbassadorTaxi', coll)
    # The join target keeps its own object transform, and parts[0] is not at the
    # origin, so bake it down: a linked asset must have local space == world space
    # and its origin on the road under the centre of the vehicle.
    M.apply_transform(car, loc=True, rot=True, scale=True)
    M.shade_smooth(car, 44.0)

    for ob in list(scratch.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.context.scene.collection.children.unlink(scratch)
    bpy.data.collections.remove(scratch)

    S.log('body only      L=%.3f  W=%.3f  roof %.3f above the road   '
          '(spec %.3f / %.3f / %.3f)'
          % (bmx.x - bmn.x, bmx.y - bmn.y, bmx.z,
             SPEC['LENGTH'], SPEC['WIDTH'], SPEC['HEIGHT']))
    mn, mx = M.dims(car)
    S.log('with fittings  L=%.3f over bumpers  W=%.3f over mirrors  H=%.3f over the '
          'TAXI box' % (mx.x - mn.x, mx.y - mn.y, mx.z - mn.z))
    S.log('tris=%d  materials=%d' % (M.tri_count(car), len(car.data.materials)))
    S.save(os.path.join(S.ASSETS, 'ambassador_taxi.blend'))

    if S.has_flag('--preview'):
        preview(car)


def preview(car):
    import mathutils
    sc = S.cycles(samples=64, res=(1600, 900), device='CPU', bounces=4)
    sc.world = bpy.data.worlds.new('w')
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.58, 0.63, 0.70, 1)
    bg.inputs[1].default_value = 2.2
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
    sun.data.energy = 2.8
    sun.data.angle = math.radians(3.0)
    sun.rotation_euler = (math.radians(48), 0, math.radians(125))
    sc.collection.objects.link(sun)
    M.plane((40, 40), (0, 0, 0), name='gnd',
            mat=T.base('prev_road', (0.045, 0.045, 0.048), 0.72))

    cam_data = bpy.data.cameras.new('cam')
    cam = bpy.data.objects.new('cam', cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    shots = [('elev_side', 'ORTHO', (0, -20, 0.80), (0, 0, 0.80), 5.0),
             ('elev_front', 'ORTHO', (20, 0, 0.80), (0, 0, 0.80), 2.6),
             ('elev_rear', 'ORTHO', (-20, 0, 0.80), (0, 0, 0.80), 2.6),
             ('plan', 'ORTHO', (0, 0, 20), (0, 0, 0), 5.0),
             ('3q', 'PERSP', (5.4, -4.4, 1.95), (-0.2, 0, 0.78), 60),
             ('3q_rear', 'PERSP', (-5.0, 3.9, 1.80), (0.2, 0, 0.78), 60)]
    for name, kind, loc, aim, val in shots:
        cam_data.type = kind
        if kind == 'ORTHO':
            cam_data.ortho_scale = val
        else:
            cam_data.lens = val
        cam.location = loc
        d = mathutils.Vector(aim) - mathutils.Vector(loc)
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(S.RENDERS, 'amb_%s.png' % name)
        S.log('render %s' % name)
        bpy.ops.render.render(write_still=True)


main()
