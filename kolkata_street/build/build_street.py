"""The Kolkata street  ->  scene/kolkata_street.blend

This is the assembly. It builds nothing that already exists: the tram, the taxi
and the city kit are LINKED in from their own .blend files and placed as
collection instances, so every tram in the street is the one tram, and
re-running build_tram.py and saving updates all of them.

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
    X0=-90.0, X1=150.0,            # the street runs this far along X
    ROAD_HW=7.0,                   # kerb to centreline
    WALK_W=2.4, KERB_H=0.155,
    CAMBER=0.075,
    TRACK_Y=1.90,                  # centre of each track, +/- from the centreline
    GAUGE=1.435,
    RAIL_W=0.070, RAIL_H=0.150,
    SETTS_W=2.60,                  # granite band the track is laid in
    POLE_SPACING=23.0, POLE_Y=7.35,
    WIRE_Z=5.80,                   # trolley wire height above the rail head
    BUILD_Y=9.40,
    WET=0.80,                      # 0 dry, 1 sheet water
)
BUILDINGS = ['KIT_BLDG_A', 'KIT_BLDG_B', 'KIT_BLDG_C', 'KIT_BLDG_D',
             'KIT_BLDG_E', 'KIT_BLDG_F']
FIGURES = ['KIT_FIGURE_%d' % i for i in range(6)]
LINK = not S.has_flag('--append')

MAT = {}


def materials():
    MAT['asphalt'] = T.wet_asphalt('st_asphalt', wetness=ST['WET'], puddle_scale=0.42)
    MAT['setts'] = T.granite_setts('st_setts')
    MAT['rail'] = T.steel('st_rail', rough=0.18, tint=(0.52, 0.51, 0.48))
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
    x0, x1, hw = ST['X0'] - 20, ST['X1'] + 20, ST['ROAD_HW']
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
    return road


def build_track(coll):
    """Two tracks of grooved rail laid flush in a band of granite setts.

    1,435 mm standard gauge -- the Kolkata system started metre gauge and was
    converted from 1900. It is not broad gauge, whatever the Indian main line does.
    """
    parts = []
    x0, x1 = ST['X0'] - 20, ST['X1'] + 20
    for sy in (1, -1):
        cy = sy * ST['TRACK_Y']
        zc = z_road(cy)
        parts.append(M.box((x1 - x0, ST['SETTS_W'], 0.22), ((x0 + x1) / 2, cy,
                           zc - 0.11 + 0.004), name='setts', coll=coll,
                           mat=MAT['setts']))
        for sg in (1, -1):
            ry = cy + sg * ST['GAUGE'] / 2
            # head, flush with the setts, and the groove beside it
            parts.append(M.box((x1 - x0, ST['RAIL_W'], ST['RAIL_H']),
                               ((x0 + x1) / 2, ry, zc - ST['RAIL_H'] / 2 + 0.006),
                               name='rail', coll=coll, mat=MAT['rail']))
            parts.append(M.box((x1 - x0, 0.034, 0.05),
                               ((x0 + x1) / 2, ry + sg * 0.052, zc - 0.022),
                               name='groove', coll=coll, mat=MAT['iron']))
    return M.join(parts, 'SOLID_track', coll)


def build_kerbs_and_walks(coll):
    parts = []
    x0, x1 = ST['X0'] - 20, ST['X1'] + 20
    hw, ww, kh = ST['ROAD_HW'], ST['WALK_W'], ST['KERB_H']
    for sy in (1, -1):
        parts.append(M.box((x1 - x0, 0.30, 0.42), ((x0 + x1) / 2, sy * (hw + 0.15),
                           kh - 0.21), name='kerb', coll=coll, mat=MAT['kerb']))
        parts.append(M.box((x1 - x0, ww, 0.14), ((x0 + x1) / 2,
                           sy * (hw + 0.30 + ww / 2), kh - 0.07), name='walk',
                           coll=coll, mat=MAT['walk']))
        # the strip of dirt between the footpath and the building line
        parts.append(M.box((x1 - x0, ST['BUILD_Y'] - (hw + 0.30 + ww), 0.12),
                           ((x0 + x1) / 2,
                            sy * (hw + 0.30 + ww + (ST['BUILD_Y'] - hw - 0.30 - ww) / 2),
                            kh - 0.06), name='verge', coll=coll, mat=MAT['walk']))
    return M.join(parts, 'WALK_footpath', coll)


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
        'tram_ctc.blend': ['TRAM_CTC'],
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
    """Two trams, taxis, autos and a handcart. Traffic keeps left, so the
    +X-bound stream is on the +Y side and the -X-bound stream on the -Y side."""
    zr = lambda y: z_road(y)

    # the two trams, on their own tracks
    S.instance(kit['TRAM_CTC'], 'TRAM_near', (-2.0, ST['TRACK_Y'], zr(ST['TRACK_Y'])),
               (0, 0, 0), into=coll)
    S.instance(kit['TRAM_CTC'], 'TRAM_far', (62.0, -ST['TRACK_Y'], zr(-ST['TRACK_Y'])),
               (0, 0, math.pi), into=coll)

    # taxis: x, y, heading, so they can be moved one line at a time
    taxis = [(-16.5, 5.05, 0.0), (10.5, 4.60, 0.0), (33.0, 5.30, 0.0),
             (58.0, 4.80, 0.0), (-9.0, -4.70, math.pi), (19.0, -5.20, math.pi),
             (44.0, -4.65, math.pi), (80.0, -5.00, math.pi)]
    for i, (x, y, h) in enumerate(taxis):
        S.instance(kit['AMBASSADOR_TAXI'], 'taxi_%d' % i, (x, y, zr(y)),
                   (0, 0, h + rnd.uniform(-0.03, 0.03)), into=coll)
    for i, (x, y, h) in enumerate([(-24.0, 6.10, 0.0), (26.0, -6.20, math.pi)]):
        S.instance(kit['KIT_AUTO'], 'auto_%d' % i, (x, y, zr(y)), (0, 0, h), into=coll)
    S.instance(kit['KIT_HANDCART'], 'handcart', (-30.0, 6.40, zr(6.4)),
               (0, 0, 0.12), into=coll)


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

    walk_y = ST['ROAD_HW'] + 0.30 + ST['WALK_W'] / 2
    spots = []
    for i in range(34):
        sy = 1 if i % 2 else -1
        spots.append((rnd.uniform(ST['X0'] + 10, ST['X1'] - 20),
                      sy * (walk_y + rnd.uniform(-0.8, 0.8)), ST['KERB_H'],
                      rnd.uniform(0, 6.28)))
    # a few crossing the carriageway, which is what gives the street its scale
    for i in range(7):
        y = rnd.uniform(-6.4, 6.4)
        spots.append((rnd.uniform(-34, 40), y, z_road(y), rnd.uniform(0, 6.28)))
    for i, (x, y, z, h) in enumerate(spots):
        S.instance(kit[rnd.choice(FIGURES)], 'figure_%d' % i, (x, y, z), (0, 0, h),
                   into=coll)


# ===================================================================== weather
def build_sky(fog=True):
    """Overcast monsoon light: a hazy sky, a soft low sun, and a thin uniform fog
    so distance reads as distance. This is the look of the reference paintings --
    almost monochrome, with the tram the only saturated thing in the frame."""
    w = bpy.data.worlds.new('MonsoonSky')
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes['Background']
    sky = nt.nodes.new('ShaderNodeTexSky')
    sky.location = (-300, 0)
    try:
        sky.sky_type = 'NISHITA'
        sky.sun_elevation = math.radians(27)
        sky.sun_rotation = math.radians(118)
        sky.sun_intensity = 0.25          # heavily diffused: it is overcast
        sky.altitude = 10
        sky.air_density = 1.9
        sky.dust_density = 5.0
        sky.ozone_density = 1.4
    except Exception:
        pass
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 0.85
    if fog:
        vs = nt.nodes.new('ShaderNodeVolumeScatter')
        vs.location = (-200, -260)
        vs.inputs['Color'].default_value = (0.74, 0.77, 0.82, 1.0)
        vs.inputs['Density'].default_value = 0.0016
        vs.inputs['Anisotropy'].default_value = 0.35
        out = nt.nodes['World Output']
        nt.links.new(vs.outputs[0], out.inputs['Volume'])
    bpy.context.scene.world = w

    sun = bpy.data.objects.new('SUN_key', bpy.data.lights.new('SUN_key', 'SUN'))
    sun.data.energy = 2.1
    sun.data.angle = math.radians(11.0)   # a big soft source: cloud, not clear sky
    sun.data.color = (1.0, 0.95, 0.88)
    sun.rotation_euler = (math.radians(63), 0, math.radians(118))
    bpy.context.scene.collection.objects.link(sun)
    return w, sun


# ===================================================================== cameras
# Each entry is a real shot. Move them, add to them: that is the whole point of
# the file. `aim` is a point in the street, not a rotation.
SHOTS = [
    dict(name='SHOT_01_tram_nose', loc=(-27.0, 3.30, 1.35), aim=(-4.0, 2.10, 2.05),
         lens=85, fstop=2.8,
         note='Low and long, tram filling the frame, like the first watercolour.'),
    dict(name='SHOT_02_wet_wide', loc=(-19.0, -4.20, 1.62), aim=(16.0, 0.60, 2.40),
         lens=24, fstop=5.6,
         note='Wide, standing in the road, the whole wet street and the reflections.'),
    dict(name='SHOT_03_telephoto_vista', loc=(-46.0, 1.40, 1.55),
         aim=(90.0, 0.20, 3.20), lens=200, fstop=4.0,
         note='Compressed down the street, traffic stacked, the dome closing it.'),
    dict(name='SHOT_04_puddle', loc=(-12.0, 4.90, 0.22), aim=(14.0, 2.60, 2.60),
         lens=35, fstop=4.0,
         note='A hand-span above the road: the reflection is the subject.'),
    dict(name='SHOT_05_balcony', loc=(-21.0, 11.60, 8.40), aim=(8.0, 0.0, 1.20),
         lens=50, fstop=6.3,
         note='From a second-floor balcony, looking down into the traffic.'),
    dict(name='SHOT_06_pavement', loc=(-8.0, 8.30, 1.62), aim=(26.0, 2.00, 2.20),
         lens=35, fstop=3.5,
         note='Pedestrian eye level on the footpath, under the awnings.'),
    dict(name='SHOT_07_under_wires', loc=(4.0, 0.0, 4.60), aim=(70.0, 0.0, 5.60),
         lens=28, fstop=8.0,
         note='Up among the trolley wire and the cable, looking down the line.'),
    dict(name='SHOT_08_taxi_three_quarter', loc=(-20.5, 9.10, 1.15),
         aim=(-9.0, 4.70, 1.00), lens=50, fstop=2.2,
         note='Taxi close in three-quarter, the tram soft behind it.'),
    dict(name='SHOT_09_crossing', loc=(14.0, -7.80, 1.70), aim=(-12.0, 1.80, 2.00),
         lens=50, fstop=4.0,
         note='Looking back up the street from the far kerb, across both tracks.'),
    dict(name='SHOT_10_tram_rear', loc=(26.0, 5.40, 2.90), aim=(-6.0, 1.90, 2.10),
         lens=70, fstop=4.0,
         note='Behind and above the near tram, the street opening out past it.'),
]


def build_cameras(coll):
    cams = [C.camera(s['name'], s['loc'], s['aim'], s['lens'], s['fstop'],
                     coll=coll, note=s['note']) for s in SHOTS]
    # a dolly that runs up the middle of the street, aimed at the near tram
    C.dolly_rig('CAM_DOLLY', [(-60, 0.4, 2.2), (-30, 2.2, 1.9), (0, 3.4, 1.7),
                              (30, 1.2, 2.4), (70, -1.0, 3.0), (110, 0.2, 3.6)],
                (-2.0, 1.9, 2.0), lens=40, frames=250, fstop=5.6, coll=coll)
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
    S.instance(kit['KIT_MOSQUE'], 'mosque', (ST['X1'] + 26, 0.0, 0.0),
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

    S.cycles(samples=int(S.argval('--samples', 160, int)), res=(1920, 1080),
             device='CPU', bounces=6, clamp_indirect=6.0)
    sc = bpy.context.scene
    sc.cycles.volume_step_rate = 8.0
    sc.cycles.volume_max_steps = 128
    sc.render.use_persistent_data = True

    S.log('scene: %s' % S.stats())
    S.save(os.path.join(S.SCENE, 'kolkata_street.blend'))

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
