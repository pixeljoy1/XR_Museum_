"""The Kolkata street  ->  scene/kolkata_street.blend

This is the assembly. It builds nothing that already exists: the taxi and the
city kit are LINKED in from their own .blend files and placed as collection
instances. (The tram is not placed in this scene; assets/tram_ctc.blend still
builds on its own.)

What this file does build is the ground the others stand on:

  * the carriageway, with a camber, two tracks of standard-gauge grooved rail
    laid in a band of granite setts, kerbs and footpaths;
  * the overhead -- traction poles, the 550 V trolley wire over each track, span
    wires, and the thicket of telecom and power cable that is half of what a
    Kolkata street looks like;
  * the weather: an overcast monsoon sky, a wet road, standing water;
  * and the cameras, which are the point of the exercise.

Traffic keeps left, so the +X-bound track and the +X-bound traffic are both on
the +Y side.

Run:
    blender -b -P build/build_street.py                      # assemble and save
    blender -b -P build/build_street.py -- --append          # copy in rather than link
    blender -b -P build/build_street.py -- --append --out scene/_flat.blend
    blender -b -P build/build_street.py -- --preview         # ... and render every shot
    blender -b -P build/build_street.py -- --preview --shot SHOT_02_wet_wide
"""
import bpy, math, os, sys, random
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klib import mesh as M, mat as T, sceneutil as S, cam as C

S.log_to(os.path.join(S.ROOT, 'build', 'build_street.log'))
rnd = random.Random(2026)

# ===================================================================== layout
ST = dict(
    X0=-90.0, X1=150.0,            # the terrace runs this far along X
    X_END=158.0,                   # where the carriageway stops, at the cross street
    MOSQUE_X=166.0,
    ROAD_HW=7.0,                   # kerb to centreline
    WALK_W=2.4, KERB_H=0.155,
    CAMBER=0.075,
    TRACK_Y=1.90,                  # centre of each track, +/- from the centreline
    GAUGE=1.435,
    RAIL_W=0.072, RAIL_H=0.160,
    SETTS_W=2.25,                  # granite band the track is laid in
    POLE_SPACING=23.0, POLE_Y=7.35,
    WIRE_Z=5.80,                   # trolley wire height above the rail head
    BUILD_Y=9.40,
    WET=0.80,                      # 0 dry, 1 sheet water
)
BUILDINGS = ['KIT_BLDG_A', 'KIT_BLDG_B', 'KIT_BLDG_C', 'KIT_BLDG_D',
             'KIT_BLDG_E', 'KIT_BLDG_F']
FIGURES = ['KIT_FIGURE_%d' % i for i in range(8)]
LINK = not S.has_flag('--append')

MAT = {}


def materials():
    MAT['asphalt'] = T.wet_asphalt('st_asphalt', wetness=ST['WET'], puddle_scale=0.16)
    # the track band is the SAME wet material as the road, with the sett joints
    # as bump only -- see wet_asphalt's docstring for why a separate, glossier
    # stone material turns the track into a white stripe down the street
    MAT['setts'] = T.wet_asphalt('st_setts', wetness=ST['WET'] * 0.9,
                                 puddle_scale=0.16,
                                 tint=(0.052, 0.050, 0.047), blocks=True,
                                 block_scale=2.2)
    MAT['rail'] = T.steel('st_rail', rough=0.14, tint=(0.62, 0.61, 0.57))
    MAT['kerb'] = T.base('st_kerb', T.srgb('#6e6a62'), 0.80)
    MAT['walk'] = T.concrete('st_walk', T.srgb('#5f5b54'), 0.86)
    MAT['iron'] = T.base('st_iron', T.srgb('#1d1d1f'), 0.62, metal=0.6)
    MAT['wire'] = T.base('st_wire', (0.020, 0.019, 0.018), 0.55, metal=0.8)
    MAT['copper'] = T.base('st_trolleywire', T.srgb('#6b4a2a'), 0.35, metal=1.0)


def z_road(y):
    """Cambered carriageway, flattened across each track so the rails stay level."""
    t = min(1.0, abs(y) / ST['ROAD_HW'])
    z = ST['CAMBER'] * (1.0 - t * t)
    for sy in (1, -1):
        c = sy * ST['TRACK_Y']
        if abs(y - c) < ST['SETTS_W'] / 2:
            tc = min(1.0, abs(c) / ST['ROAD_HW'])
            zc = ST['CAMBER'] * (1.0 - tc * tc)
            k = M.smoothstep(ST['SETTS_W'] / 2 - 0.45, ST['SETTS_W'] / 2,
                             abs(y - c))
            z = M.lerp(zc, z, k)
    return z


# ===================================================================== ground
def build_road(coll):
    """The carriageway as a grid, so the camber, the worn hollows along the rails
    and the dish of standing water at the kerb are real geometry and the puddles
    in the material have somewhere to sit."""
    x0, x1, hw = ST['X0'] - 20, ST['X_END'], ST['ROAD_HW']
    nx, ny = int((x1 - x0) / 1.4), 64
    verts, faces = [], []
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * i / nx
        for j in range(ny + 1):
            y = -hw + 2 * hw * j / ny
            z = z_road(y)
            # worn hollows just outside each running rail, and a dish at the kerb
            for sy in (1, -1):
                for rail in (ST['TRACK_Y'] * sy + ST['GAUGE'] / 2 * sy,
                             ST['TRACK_Y'] * sy - ST['GAUGE'] / 2 * sy):
                    d = abs(y - (rail + 0.34 * sy))
                    if d < 0.40:
                        z -= 0.022 * (1 - d / 0.40)
            z -= 0.030 * M.smoothstep(hw - 2.2, hw - 0.1, abs(y))
            z += 0.012 * math.sin(x * 0.7 + y * 1.9) * math.sin(x * 0.21)
            verts.append((x, y, z))
    for i in range(nx):
        for j in range(ny):
            a = i * (ny + 1) + j
            b = (i + 1) * (ny + 1) + j
            faces.append([a, b, b + 1, a + 1])
    road = M.new_mesh('WALK_road', verts, faces, coll, MAT['asphalt'], smooth=True,
                      auto_angle=20.0)
    # the cross street the terrace runs into, so the view down the road lands on
    # ground rather than on the sky
    # WALK_ so the locomotion module treats it as standable rather than a wall
    M.plane((150, 150), (ST['X_END'] + 60, 0, 0.02), name='WALK_far_ground',
            coll=coll, mat=MAT['asphalt'])
    return road


def build_track(coll):
    """Two tracks of grooved rail laid flush in a band of granite setts.

    1,435 mm standard gauge -- the Kolkata system started metre gauge and was
    converted from 1900. It is not broad gauge, whatever the Indian main line does.
    """
    parts = []
    x0, x1 = ST['X0'] - 20, ST['X_END']
    for sy in (1, -1):
        cy = sy * ST['TRACK_Y']
        zc = z_road(cy)
        parts.append(M.box((x1 - x0, ST['SETTS_W'], 0.22), ((x0 + x1) / 2, cy,
                           zc - 0.11 + 0.004), name='setts', coll=coll,
                           mat=MAT['setts']))
        for sg in (1, -1):
            ry = cy + sg * ST['GAUGE'] / 2
            # head, flush with the setts, and the groove beside it
            # the head stands ~14 mm proud of the setts, which is what makes the
            # two bright steel lines read down a wet street
            parts.append(M.box((x1 - x0, ST['RAIL_W'], ST['RAIL_H']),
                               ((x0 + x1) / 2, ry, zc - ST['RAIL_H'] / 2 + 0.014),
                               name='rail', coll=coll, mat=MAT['rail']))
            parts.append(M.box((x1 - x0, 0.034, 0.05),
                               ((x0 + x1) / 2, ry + sg * 0.052, zc - 0.022),
                               name='groove', coll=coll, mat=MAT['iron']))
    return M.apply_transform(M.join(parts, 'SOLID_track', coll),
                             loc=True, rot=True, scale=True)


def build_kerbs_and_walks(coll):
    parts = []
    x0, x1 = ST['X0'] - 20, ST['X_END']
    hw, ww, kh = ST['ROAD_HW'], ST['WALK_W'], ST['KERB_H']
    for sy in (1, -1):
        parts.append(M.box((x1 - x0, 0.30, 0.42), ((x0 + x1) / 2, sy * (hw + 0.15),
                           kh - 0.21), name='kerb', coll=coll, mat=MAT['kerb']))
        parts.append(M.box((x1 - x0, ww, 0.14), ((x0 + x1) / 2,
                           sy * (hw + 0.30 + ww / 2), kh - 0.07), name='walk',
                           coll=coll, mat=MAT['walk']))
        # the strip between the footpath and the building line. BUILD_Y can be
        # inside the footpath, which would give the box a negative width and turn
        # it inside out, so it is only built when there is actually a gap.
        gap = ST['BUILD_Y'] - (hw + 0.30 + ww)
        if gap > 0.05:
            parts.append(M.box((x1 - x0, gap, 0.12),
                               ((x0 + x1) / 2, sy * (hw + 0.30 + ww + gap / 2),
                                kh - 0.06), name='verge', coll=coll, mat=MAT['walk']))
    return M.apply_transform(M.join(parts, 'WALK_footpath', coll),
                             loc=True, rot=True, scale=True)


# ===================================================================== overhead
def build_overhead(coll, poles):
    """Trolley wire over each track, span wires across, and the mess of telecom
    and power cable strung pole to pole that is half of what the street looks like."""
    parts = []
    x0, x1 = ST['X0'], ST['X1']
    wz = ST['WIRE_Z']
    # the two trolley wires, running the length, with a slight sag between poles
    for sy in (1, -1):
        cy = sy * ST['TRACK_Y']
        pts = []
        xs = [x for x in poles]
        for a, b in zip(xs, xs[1:]):
            pts += M.sag_points((a, cy, wz), (b, cy, wz), 0.10, 5)[:-1]
        pts.append((xs[-1], cy, wz))
        parts.append(M.tube_along(pts, 0.012, 5, 'trolleywire', coll, MAT['copper']))
    # span wires across the street, pole to pole, carrying the trolley wires
    for x in poles:
        parts.append(M.sag_wire((-ST['POLE_Y'], 0, 0), (ST['POLE_Y'], 0, 0), 0, 0.009,
                                'spanwire', coll, MAT['wire'], steps=1, seg=4))
        parts[-1].rotation_euler = (0, 0, math.pi / 2)
        parts[-1].location = (x, 0, wz + 0.62)
        for sy in (1, -1):
            parts.append(M.sag_wire((x, sy * ST['TRACK_Y'], wz + 0.60),
                                    (x, sy * ST['TRACK_Y'], wz), 0, 0.007, 'dropper',
                                    coll, MAT['wire'], steps=1, seg=4))
    # telecom and power: several runs at different heights, sagging hard
    for a, b in zip(poles, poles[1:]):
        for sy in (1, -1):
            py = sy * ST['POLE_Y']
            for k in range(rnd.randint(3, 6)):
                z = 6.4 + k * 0.38 + rnd.uniform(-0.12, 0.12)
                yy = py - sy * rnd.uniform(0.0, 0.5)
                parts.append(M.sag_wire((a, yy, z), (b, yy + rnd.uniform(-0.2, 0.2), z),
                                        rnd.uniform(0.35, 0.95), 0.010, 'cable', coll,
                                        MAT['wire'], steps=8, seg=4))
        # a couple of crossings
        if rnd.random() < 0.6:
            xm = (a + b) / 2
            z = rnd.uniform(6.6, 7.8)
            parts.append(M.sag_wire((xm, -ST['POLE_Y'], z), (xm, ST['POLE_Y'], z),
                                    rnd.uniform(0.5, 1.1), 0.010, 'crosscable', coll,
                                    MAT['wire'], steps=8, seg=4))
    return M.join(parts, 'overhead', coll)


# ===================================================================== assembly
def link_kit():
    """Link every asset collection once. Nothing is duplicated: the street holds
    instances, and the geometry stays in the three asset files."""
    blends = {
        'tram_v3.blend': ['TRAM_V3'],
        'ambassador_taxi.blend': ['AMBASSADOR_TAXI'],
        'city_kit.blend': BUILDINGS + ['KIT_TRAMPOLE', 'KIT_SHED', 'KIT_HOARDING',
                                       'KIT_TREE_BIG', 'KIT_TREE_SMALL',
                                       'KIT_HANDCART', 'KIT_AUTO', 'KIT_MOSQUE']
                          + FIGURES,
    }
    out = {}
    for fn, names in blends.items():
        path = os.path.join(S.ASSETS, fn)
        for n in names:
            out[n] = S.link_collection(path, n, link=LINK)
    return out


def place_buildings(kit, coll):
    """Two terraces, built up block by block with no gaps, each block a different
    kit building so the rhythm does not repeat."""
    for sy in (1, -1):
        x = ST['X0']
        i = 0
        while x < ST['X1']:
            name = BUILDINGS[(i + (0 if sy > 0 else 3)) % len(BUILDINGS)]
            src = kit[name]
            w = max(ob.dimensions.x for ob in src.objects) if src.objects else 10.0
            S.instance(src, 'bldg_%s_%d' % ('N' if sy > 0 else 'S', i),
                       (x + w / 2, sy * ST['BUILD_Y'], 0.0),
                       (0, 0, 0 if sy > 0 else math.pi), into=coll)
            x += w + 0.02
            i += 1


def place_overhead_poles(kit, coll):
    poles = []
    x = ST['X0'] + 6
    while x < ST['X1']:
        poles.append(x)
        for sy in (1, -1):
            S.instance(kit['KIT_TRAMPOLE'], 'pole_%d_%d' % (len(poles), sy),
                       (x, sy * ST['POLE_Y'], ST['KERB_H']),
                       (0, 0, 0 if sy > 0 else math.pi), into=coll)
        x += ST['POLE_SPACING']
    return poles


def place_traffic(kit, coll):
    """One tram, one taxi, two autos and a handcart, all parked: the street is a
    still set. Traffic keeps left, so a vehicle heading -X sits on the -Y side.

    The tram is the supplied V3.10 model (assets/tram_v3.blend, built from the
    1:87 source by build_tram_v3.py). Its driver's cab is at -X, so with no
    rotation it faces down the street towards a camera standing at negative X.
    The old tram (assets/tram_ctc.blend) still builds on its own and is not placed."""
    zr = lambda y: z_road(y)

    # origin on the wheel contact, so it sits on the rail head: the head stands
    # 14 mm proud of the setts (see build_track)
    S.instance(kit['TRAM_V3'], 'TRAM_v3', (7.0, -ST['TRACK_Y'], zr(-ST['TRACK_Y']) + 0.014),
               (0, 0, 0), into=coll)

    # the one taxi: on the -Y side heading -X, so a camera down the street at
    # negative X sees it head-on
    taxis = [(-14.0, -5.00, math.pi)]
    for i, (x, y, h) in enumerate(taxis):
        S.instance(kit['AMBASSADOR_TAXI'], 'taxi_%d' % i, (x, y, zr(y)),
                   (0, 0, h + rnd.uniform(-0.03, 0.03)), into=coll)
    for i, (x, y, h) in enumerate([(-30.0, -6.20, math.pi), (22.0, 6.10, 0.0)]):
        S.instance(kit['KIT_AUTO'], 'auto_%d' % i, (x, y, zr(y)), (0, 0, h), into=coll)
    S.instance(kit['KIT_HANDCART'], 'handcart', (-36.0, -6.35, zr(-6.35)),
               (0, 0, math.pi + 0.12), into=coll)


def place_street_life(kit, coll):
    """Trees, stalls, hoardings and the walk-ons."""
    for x, sy, which in [(-14.0, -1, 'KIT_TREE_BIG'), (41.0, 1, 'KIT_TREE_SMALL'),
                         (96.0, -1, 'KIT_TREE_BIG'), (-46.0, 1, 'KIT_TREE_SMALL')]:
        S.instance(kit[which], 'tree_%d' % int(x),
                   (x, sy * (ST['ROAD_HW'] + 1.3), ST['KERB_H']),
                   (0, 0, rnd.uniform(0, 6.28)), into=coll)
    for x, sy in [(5.0, -1), (-33.0, 1), (52.0, 1), (72.0, -1)]:
        S.instance(kit['KIT_SHED'], 'shed_%d' % int(x),
                   (x, sy * (ST['BUILD_Y'] - 1.3), ST['KERB_H']),
                   (0, 0, 0 if sy > 0 else math.pi), into=coll)
    for x, sy, z in [(23.0, 1, 0.0), (-40.0, -1, 0.0)]:
        S.instance(kit['KIT_HOARDING'], 'hoard_%d' % int(x),
                   (x, sy * (ST['BUILD_Y'] - 0.6), ST['KERB_H'] + z),
                   (0, 0, 0 if sy > 0 else math.pi), into=coll)

    # The crowd is kept deliberately thin. Each figure is five draw calls in the
    # browser once per placement, and a stylised walk-on earns its keep as a
    # silhouette in the middle distance, not as a mob.
    walk_y = ST['ROAD_HW'] + 0.30 + ST['WALK_W'] / 2
    spots = []
    for i in range(20):
        sy = 1 if i % 2 else -1
        spots.append((rnd.uniform(ST['X0'] + 10, ST['X1'] - 20),
                      sy * (walk_y + rnd.uniform(-0.8, 0.8)), ST['KERB_H'],
                      rnd.uniform(0, 6.28)))
    # a few crossing the carriageway, which is what gives the street its scale.
    # Kept away from the near end, because a stylised figure does not stand up to
    # being eight metres from a 50 mm lens.
    for i in range(5):
        y = rnd.uniform(-6.4, 6.4)
        spots.append((rnd.uniform(18, 72), y, z_road(y), rnd.uniform(0, 6.28)))
    for i, (x, y, z, h) in enumerate(spots):
        S.instance(kit[rnd.choice(FIGURES)], 'figure_%d' % i, (x, y, z), (0, 0, h),
                   into=coll)


# ===================================================================== weather
def build_sky(fog=True):
    """Overcast monsoon light, and depth haze done in the compositor.

    The haze is deliberately NOT a world volume. A world volume in Cycles is
    unbounded, so light from a sun -- which is infinitely far away -- is
    extinguished over an infinite path and the whole scene renders black. The mist
    pass gives the same aerial perspective for nothing, with no volume noise, and
    it can be dialled after the render instead of before it.

    This is the look of the reference paintings: almost monochrome, the distance
    going grey, and the tram the only saturated thing in the frame.
    """
    sc = bpy.context.scene
    w = bpy.data.worlds.new('MonsoonSky')
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes['Background']
    sky = nt.nodes.new('ShaderNodeTexSky')
    sky.location = (-300, 0)
    try:
        sky.sky_type = 'NISHITA'
        sky.sun_elevation = math.radians(34)
        sky.sun_rotation = math.radians(118)
        sky.sun_intensity = 0.35          # heavily diffused: it is overcast
        sky.altitude = 10
        sky.air_density = 1.35
        sky.dust_density = 2.6
        sky.ozone_density = 1.2
    except Exception:
        pass
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 1.45
    sc.world = w

    sun = bpy.data.objects.new('SUN_key', bpy.data.lights.new('SUN_key', 'SUN'))
    sun.data.energy = 3.4
    sun.data.angle = math.radians(14.0)   # a big soft source: cloud, not clear sky
    sun.data.color = (1.0, 0.96, 0.90)
    sun.rotation_euler = (math.radians(56), 0, math.radians(118))
    sc.collection.objects.link(sun)

    if fog:
        add_mist_haze(sc, start=30.0, depth=420.0,
                      colour=(0.70, 0.73, 0.79), strength=0.72)
    return w, sun


def add_mist_haze(sc, start=18.0, depth=190.0, colour=(0.76, 0.79, 0.84),
                  strength=0.9):
    """Mix a flat haze colour over the render by the mist pass.

    start/depth are metres: nothing nearer than `start` is touched, and by
    `start + depth` the haze is at full `strength`. Tune them in the compositor
    without re-rendering the beauty pass.
    """
    vl = sc.view_layers[0]
    vl.use_pass_mist = True
    sc.world.mist_settings.use_mist = True
    sc.world.mist_settings.start = start
    sc.world.mist_settings.depth = depth
    sc.world.mist_settings.falloff = 'LINEAR'
    sc.world.mist_settings.intensity = 0.0

    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new('CompositorNodeRLayers')
    rl.location = (-500, 0)
    haze = nt.nodes.new('CompositorNodeRGB')
    haze.location = (-500, -260)
    haze.outputs[0].default_value = (*colour, 1.0)
    mul = nt.nodes.new('CompositorNodeMath')
    mul.operation = 'MULTIPLY'
    mul.location = (-280, -120)
    mul.inputs[1].default_value = strength
    mix = nt.nodes.new('CompositorNodeMixRGB')
    mix.blend_type = 'MIX'
    mix.location = (-60, 0)
    comp = nt.nodes.new('CompositorNodeComposite')
    comp.location = (200, 0)
    vw = nt.nodes.new('CompositorNodeViewer')
    vw.location = (200, -200)
    nt.links.new(rl.outputs['Image'], mix.inputs[1])
    nt.links.new(haze.outputs[0], mix.inputs[2])
    if 'Mist' in rl.outputs:
        nt.links.new(rl.outputs['Mist'], mul.inputs[0])
        nt.links.new(mul.outputs[0], mix.inputs[0])
    else:
        mix.inputs[0].default_value = 0.0
    nt.links.new(mix.outputs[0], comp.inputs['Image'])
    nt.links.new(mix.outputs[0], vw.inputs['Image'])
    return nt


# ===================================================================== cameras
# Each entry is a real shot. Move them, add to them: that is the whole point of
# the file. `aim` is a point in the street, not a rotation.
SHOTS = [
    # an auto and a handcart are parked at x = -30 and -36 on the -Y side, so the
    # camera stands well back and a lane inboard of them
    dict(name='SHOT_01_taxi_head_on', loc=(-42.0, -2.60, 1.25), aim=(-14.0, -5.00, 0.95),
         lens=85, fstop=2.8,
         note='Low and long, the taxi facing you down the wet street.'),
    dict(name='SHOT_02_wet_wide', loc=(-16.0, 3.20, 1.60), aim=(16.0, -1.00, 2.30),
         lens=24, fstop=5.6,
         note='Wide, standing in the road, the whole wet street and the reflections.'),
    dict(name='SHOT_03_telephoto_vista', loc=(-44.0, 0.60, 1.60),
         aim=(120.0, -0.10, 9.00), lens=200, fstop=4.0,
         note='Compressed down the street, traffic stacked, the dome closing it.'),
    dict(name='SHOT_04_puddle', loc=(-11.0, -4.40, 0.22), aim=(13.0, -2.00, 2.40),
         lens=35, fstop=4.0,
         note='A hand-span above the road: the reflection is the subject.'),
    dict(name='SHOT_05_balcony', loc=(-18.0, -8.90, 8.20), aim=(10.0, 0.00, 1.00),
         lens=50, fstop=6.3,
         note='From a second-floor balcony, looking down into the traffic.'),
    dict(name='SHOT_06_pavement', loc=(-6.0, -8.40, 1.62), aim=(26.0, -2.50, 2.20),
         lens=35, fstop=3.5,
         note='Pedestrian eye level on the footpath, under the awnings.'),
    dict(name='SHOT_07_under_wires', loc=(-10.0, 0.00, 4.90), aim=(80.0, 0.00, 5.70),
         lens=28, fstop=8.0,
         note='Up among the trolley wire and the cable, looking down the line.'),
    dict(name='SHOT_08_taxi_three_quarter', loc=(-24.0, -7.90, 1.10),
         aim=(-14.5, -5.00, 0.95), lens=50, fstop=2.2,
         note='Taxi close in three-quarter, the street soft behind it.'),
    # Poles stand every 23 m from x = -84, so x = 8 and x = 31 are occupied.
    # Standing at 10 put one straight down the middle of the frame.
    dict(name='SHOT_09_crossing', loc=(19.5, 7.85, 1.70), aim=(-14.0, -2.00, 2.00),
         lens=50, fstop=4.0,
         note='Looking back up the street from the far kerb, across both tracks.'),
    # the tram stands at x = 7 with its cab at x = -0.9. The page uses an 80 degree
    # field of view where this lens gives about 54, so the camera stands close (4 m
    # off the nose) to read the lattice, the headlamp and the Route 25 board in both
    dict(name='SHOT_11_tram_cab', loc=(-5.2, 0.6, 1.30), aim=(-0.9, -1.9, 1.75),
         lens=35, fstop=4.0,
         note='The tram cab close: wire lattice, headlamp, the Route 25 board.'),
    dict(name='SHOT_10_far_end', loc=(100.0, 4.50, 2.20), aim=(20.0, -1.00, 3.00),
         lens=35, fstop=5.6,
         note='From the mosque end, the whole terrace running away down the street.'),
]


def build_cameras(coll):
    cams = [C.camera(s['name'], s['loc'], s['aim'], s['lens'], s['fstop'],
                     coll=coll, note=s['note']) for s in SHOTS]
    # a dolly that runs up the middle of the street, aimed at the taxi
    C.dolly_rig('CAM_DOLLY', [(-60, 0.4, 2.2), (-34, 3.0, 1.8), (-8, 4.2, 1.6),
                              (22, 2.0, 2.4), (62, -0.6, 3.0), (108, 0.2, 3.6)],
                (-14.0, -5.0, 1.0), lens=40, frames=250, fstop=5.6, coll=coll)
    bpy.context.scene.camera = cams[0]
    return cams


# ===================================================================== main
def main():
    S.reset('KolkataStreet')
    materials()
    ground = S.coll('GROUND')
    city = S.coll('CITY')
    traffic = S.coll('TRAFFIC')
    life = S.coll('STREET_LIFE')
    over = S.coll('OVERHEAD')
    cams = S.coll('CAMERAS')

    S.log('linking assets (%s)' % ('link' if LINK else 'append'))
    kit = link_kit()

    S.log('ground')
    build_road(ground)
    build_track(ground)
    build_kerbs_and_walks(ground)

    S.log('city')
    place_buildings(kit, city)
    S.instance(kit['KIT_MOSQUE'], 'mosque', (ST['MOSQUE_X'], 0.0, 0.0),
               (0, 0, -math.pi / 2), into=city)
    # the cross street behind it, so the vista is closed on both sides of the dome
    for sy, nm in ((1, 'KIT_BLDG_C'), (-1, 'KIT_BLDG_F')):
        S.instance(kit[nm], 'endblock_%d' % sy, (ST['MOSQUE_X'] + 11.0, sy * 20.0, 0.0),
                   (0, 0, -math.pi / 2), into=city)

    S.log('overhead')
    poles = place_overhead_poles(kit, over)
    build_overhead(over, poles)

    S.log('traffic and street life')
    place_traffic(kit, traffic)
    place_street_life(kit, life)

    S.log('sky and cameras')
    build_sky(fog=not S.has_flag('--nofog'))
    build_cameras(cams)

    # Four bounces, not six. The whole carriageway is a near-mirror when it is
    # wet, so every extra glossy bounce is paid for over most of the frame --
    # and by bounce four the contribution is invisible against the haze.
    S.cycles(samples=int(S.argval('--samples', 96, int)), res=(1920, 1080),
             device='CPU', bounces=4, clamp_indirect=4.0)
    sc = bpy.context.scene
    sc.render.use_persistent_data = True

    S.log('scene: %s' % S.stats())
    S.save(S.argval('--out', os.path.join(S.SCENE, 'kolkata_street.blend')))

    if S.has_flag('--preview'):
        only = S.argval('--shot', None)
        render_shots(only)


def render_shots(only=None):
    sc = bpy.context.scene
    for s in SHOTS:
        if only and s['name'] != only:
            continue
        sc.camera = bpy.data.objects[s['name']]
        sc.render.filepath = os.path.join(S.RENDERS, '%s.png' % s['name'])
        S.log('render %s  -- %s' % (s['name'], s['note']))
        bpy.ops.render.render(write_still=True)


main()
