"""Kolkata street kit  ->  assets/city_kit.blend

Everything in the street that is not a tram or a taxi: the buildings, the shop
fronts, the traction poles, the trees, the tin-roofed stall, the handcart, the
auto-rickshaw, the walk-on figures, and the domed mosque that closes the view.

Each item is its own collection, so build_street.py can link them once and then
instance them as many times as it likes. Nothing here is modelled twice.

The buildings are a generator, not a model. North-Kolkata terraces are a rhythm:
a shop at the bottom, three or four storeys of tall louvred-shutter windows
above, a projecting sun hood over each, cast-iron balconies, a string course at
every floor, a parapet, and water tanks on the roof -- all under lime plaster
that the monsoon has streaked black. `building()` takes the width, the number of
floors and a seed, and plays that rhythm back differently every time.

Run:
    blender -b -P build/build_city_kit.py
    blender -b -P build/build_city_kit.py -- --preview
"""
import bpy, math, os, sys, random
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klib import mesh as M, mat as T, sceneutil as S

S.log_to(os.path.join(S.ROOT, 'build', 'build_city_kit.log'))

MAT = {}

PLASTER_COLOURS = ['#b9ae95', '#a8a persisted', '#9d927c', '#c4b49a', '#8f8a79',
                   '#b0a08a', '#cdbfa4']
PLASTER_COLOURS = ['#b9ae95', '#9d927c', '#c4b49a', '#8f8a79', '#b0a08a', '#cdbfa4']
SHUTTER_COLOURS = ['#2f4f3a', '#3d5a4a', '#6b4a2a', '#4a4030', '#2d3f4f']
SHOP_COLOURS = ['#9c2a1e', '#1f4f6b', '#3a6b2f', '#b5741a', '#5a2d6b']


def materials():
    MAT['plaster'] = [T.plaster('city_plaster%d' % i, T.srgb(c), 0.92, 0.5)
                      for i, c in enumerate(PLASTER_COLOURS)]
    MAT['brick'] = T.brick('city_brick')
    MAT['concrete'] = T.concrete('city_concrete')
    MAT['stone'] = T.base('city_stone', T.srgb('#8c8575'), 0.88)
    MAT['shutter'] = [T.base('city_shutter%d' % i, T.srgb(c), 0.72)
                      for i, c in enumerate(SHUTTER_COLOURS)]
    MAT['shop'] = [T.painted_metal('city_shop%d' % i, T.srgb(c), 0.55, 0.3)
                   for i, c in enumerate(SHOP_COLOURS)]
    MAT['iron'] = T.base('city_iron', T.srgb('#1d1d1f'), 0.62, metal=0.6)
    MAT['rust'] = T.rust('city_rust')
    MAT['tin'] = T.corrugated_tin('city_tin')
    MAT['glass'] = T.dark_glass('city_glass')
    MAT['wood'] = T.teak('city_wood')
    MAT['tarp'] = T.cloth('city_tarp', T.srgb('#1d4a8c'), 0.86)
    MAT['tarp2'] = T.cloth('city_tarp2', T.srgb('#b23a1a'), 0.86)
    MAT['foliage'] = T.foliage('city_foliage')
    MAT['bark'] = T.base('city_bark', T.srgb('#3a332c'), 0.92)
    MAT['steel'] = T.steel('city_steel', 0.5)
    MAT['dark'] = T.base('city_dark', (0.012, 0.012, 0.013), 0.7)
    MAT['white'] = T.base('city_white', T.srgb('#ddd8cc'), 0.8)
    MAT['lamp'] = T.emissive('city_lamp', (1.0, 0.82, 0.52), 18.0)
    MAT['neon'] = T.emissive('city_neon', (1.0, 0.35, 0.18), 9.0)
    MAT['shopglow'] = T.emissive('city_shopglow', (1.0, 0.88, 0.62), 4.0)
    MAT['skin'] = T.base('city_skin', T.srgb('#5a3f2e'), 0.76)
    MAT['cloth'] = [T.cloth('city_cloth%d' % i, T.srgb(c)) for i, c in
                    enumerate(['#d8d2c4', '#8c2f3a', '#2a4a6b', '#c47a1a',
                               '#3a5a3a', '#6b3a6b'])]
    MAT['auto_green'] = T.car_paint('city_auto_green', T.srgb('#1f6b35'), 0.35, dirt=0.4)
    MAT['auto_yellow'] = T.car_paint('city_auto_yellow', T.srgb('#e0a614'), 0.35, dirt=0.4)
    MAT['dome'] = T.base('city_dome', T.srgb('#cfc4ad'), 0.72)
    MAT['dome_trim'] = T.base('city_dome_trim', T.srgb('#8a7a5c'), 0.7)


# ===================================================================== buildings
def louvre_shutter(w, h, coll, mat, blades=9):
    """A louvred timber shutter: the blades are real, because at street level the
    shadow line across them is most of what makes these facades read."""
    parts = [M.box((w, 0.035, 0.05), (0, 0, h / 2 - 0.025), name='sh_top', coll=coll,
                   mat=mat),
             M.box((w, 0.035, 0.05), (0, 0, -h / 2 + 0.025), name='sh_bot', coll=coll,
                   mat=mat),
             M.box((0.045, 0.035, h), (-w / 2 + 0.022, 0, 0), name='sh_l', coll=coll,
                   mat=mat),
             M.box((0.045, 0.035, h), (w / 2 - 0.022, 0, 0), name='sh_r', coll=coll,
                   mat=mat)]
    inner = h - 0.10
    for i in range(blades):
        z = -inner / 2 + inner * (i + 0.5) / blades
        parts.append(M.box((w - 0.09, 0.030, inner / blades * 0.85), (0, 0, z),
                           (0.42, 0, 0), name='blade%d' % i, coll=coll, mat=mat))
    return parts


def window_bay(x, z, w, h, coll, rnd, wall_y, shutter_mat, open_frac=0.0):
    """One tall window: reveal, sill, louvred shutters, and the sun hood over it."""
    p = []
    p.append(M.box((w + 0.16, 0.10, h + 0.20), (x, wall_y - 0.02, z + 0.02),
                   name='surround', coll=coll, mat=MAT['stone']))
    p.append(M.box((w, 0.10, h), (x, wall_y - 0.075, z), name='reveal', coll=coll,
                   mat=MAT['dark']))
    p.append(M.box((w - 0.04, 0.02, h - 0.04), (x, wall_y - 0.10, z), name='pane',
                   coll=coll, mat=MAT['glass']))
    p.append(M.box((w + 0.26, 0.17, 0.07), (x, wall_y - 0.055, z - h / 2 - 0.035),
                   name='sill', coll=coll, mat=MAT['stone'], bevel=0.015))
    # chhajja: the projecting sun hood
    p.append(M.box((w + 0.34, 0.30, 0.055), (x, wall_y - 0.13, z + h / 2 + 0.13),
                   (0.10, 0, 0), name='chhajja', coll=coll, mat=MAT['concrete']))
    # two leaves, one sometimes swung open
    for sd in (1, -1):
        leaf_w = (w - 0.03) / 2
        ang = sd * open_frac * 1.1
        hx = x + sd * (w / 2 - leaf_w / 2)
        pivot = x + sd * w / 2
        cx = pivot - sd * (leaf_w / 2) * math.cos(ang)
        cy = wall_y - 0.055 - (leaf_w / 2) * math.sin(abs(ang))
        for part in louvre_shutter(leaf_w, h - 0.03, coll, shutter_mat):
            part.rotation_euler = (0, 0, ang)
            part.location = (part.location.x + cx, part.location.y + cy,
                             part.location.z + z)
            p.append(part)
    return p


def iron_railing(w, h, coll, posts=None, z0=0.0):
    """Cast-iron balcony railing: top and bottom rail with turned balusters."""
    p = [M.box((w, 0.035, 0.040), (0, 0, z0 + h - 0.02), name='rail_top', coll=coll,
               mat=MAT['iron']),
         M.box((w, 0.030, 0.030), (0, 0, z0 + 0.02), name='rail_bot', coll=coll,
               mat=MAT['iron'])]
    n = posts or max(3, int(w / 0.14))
    for i in range(n):
        x = -w / 2 + w * (i + 0.5) / n
        p.append(M.cyl(0.013, h - 0.05, (x, 0, z0 + h / 2), name='bal%d' % i,
                       coll=coll, mat=MAT['iron'], seg=8))
    return p


def building(name, width, floors, depth=9.0, seed=1, ground_h=3.9, floor_h=3.25,
             balcony_floors=None, arcade=False):
    """One terrace block: wall, shop at the bottom, floors of windows, parapet."""
    rnd = random.Random(seed)
    coll = S.coll(name)
    plaster = rnd.choice(MAT['plaster'])
    shutter = rnd.choice(MAT['shutter'])
    shop_col = rnd.choice(MAT['shop'])
    H = ground_h + floors * floor_h
    parapet_h = rnd.uniform(0.85, 1.35)
    p = []

    # --- the mass. The facade plane is y = 0; the building runs back to +y.
    p.append(M.box((width, depth, H), (0, depth / 2, H / 2), name='mass', coll=coll,
                   mat=plaster))
    p.append(M.box((width + 0.30, depth, parapet_h), (0, depth / 2 - 0.1,
                   H + parapet_h / 2), name='parapet', coll=coll, mat=plaster))
    p.append(M.box((width + 0.44, 0.45, 0.22), (0, -0.14, H + 0.11), name='cornice',
                   coll=coll, mat=MAT['concrete'], bevel=0.03))
    p.append(M.box((width + 0.36, 0.30, 0.10), (0, -0.09, H + parapet_h - 0.05),
                   name='coping', coll=coll, mat=MAT['stone'], bevel=0.02))

    # --- shop front at street level
    bays = max(1, int(round(width / rnd.uniform(3.1, 4.2))))
    bw = width / bays
    for b in range(bays):
        cx = -width / 2 + bw * (b + 0.5)
        op_w, op_h = bw - 0.55, ground_h - 1.05
        p.append(M.box((op_w, 0.70, op_h), (cx, 0.33, op_h / 2 + 0.12), name='shopbox',
                       coll=coll, mat=MAT['dark']))
        if rnd.random() < 0.55:          # roller shutter down
            p.append(M.box((op_w, 0.06, op_h), (cx, -0.02, op_h / 2 + 0.12),
                           name='roller', coll=coll, mat=shop_col))
            for i in range(int(op_h / 0.11)):
                p.append(M.box((op_w, 0.015, 0.012), (cx, -0.052,
                               0.14 + i * 0.11), name='rollerrib', coll=coll,
                               mat=MAT['dark']))
        else:                             # open, lit, with goods stacked
            p.append(M.box((op_w - 0.1, 0.02, op_h - 0.2),
                           (cx, 0.60, op_h / 2 + 0.12), name='shopglow', coll=coll,
                           mat=MAT['shopglow']))
            for i in range(rnd.randint(3, 6)):
                p.append(M.box((rnd.uniform(0.2, 0.5), rnd.uniform(0.2, 0.4),
                                rnd.uniform(0.25, 0.7)),
                               (cx + rnd.uniform(-op_w / 3, op_w / 3),
                                rnd.uniform(0.25, 0.55), rnd.uniform(0.3, 0.9)),
                               name='goods', coll=coll,
                               mat=rnd.choice(MAT['cloth'])))
        # signboard over the opening
        p.append(M.box((bw - 0.2, 0.09, 0.62), (cx, -0.06, ground_h - 0.60),
                       name='signboard', coll=coll, mat=rnd.choice(MAT['shop'])))
        if rnd.random() < 0.5:
            p.append(M.box((bw - 0.5, 0.03, 0.10), (cx, -0.12, ground_h - 0.60),
                           name='signtext', coll=coll, mat=MAT['white']))
        # awning or tarpaulin
        if rnd.random() < 0.55:
            p.append(M.box((bw - 0.3, 1.25, 0.04), (cx, -0.60, ground_h - 1.25),
                           (0.30, 0, 0), name='awning', coll=coll,
                           mat=rnd.choice([MAT['tarp'], MAT['tarp2'], MAT['tin']])))
            for sx in (-1, 1):
                p.append(M.cyl(0.018, 1.15, (cx + sx * (bw / 2 - 0.25), -1.05,
                               ground_h / 2 - 0.2), name='awnpost', coll=coll,
                               mat=MAT['steel'], seg=8))
        # pilaster between shops
        p.append(M.box((0.34, 0.22, ground_h), (cx - bw / 2, -0.05, ground_h / 2),
                       name='pilaster', coll=coll, mat=MAT['stone']))
    p.append(M.box((width + 0.3, 0.25, 0.26), (0, -0.07, ground_h + 0.05),
                   name='stringcourse', coll=coll, mat=MAT['stone'], bevel=0.025))

    # --- upper floors
    wbays = max(2, int(round(width / rnd.uniform(1.9, 2.5))))
    ww = min(1.25, width / wbays - 0.55)
    wh = floor_h - 1.25
    bal = balcony_floors if balcony_floors is not None else \
        sorted(rnd.sample(range(floors), k=min(floors, rnd.randint(0, 2))))
    for f in range(floors):
        z0 = ground_h + f * floor_h
        zc = z0 + wh / 2 + 0.55
        for b in range(wbays):
            cx = -width / 2 + width * (b + 0.5) / wbays
            p += window_bay(cx, zc, ww, wh, coll, rnd, 0.0, shutter,
                            open_frac=rnd.choice([0, 0, 0, 0.55, 0.9]))
        # string course at every floor
        p.append(M.box((width + 0.22, 0.20, 0.16), (0, -0.05, z0 + 0.10),
                       name='band', coll=coll, mat=MAT['stone'], bevel=0.02))
        # a balcony on some floors, the full width or just the centre bays
        if f in bal:
            bwid = width * rnd.choice([0.42, 0.62, 0.95])
            p.append(M.box((bwid, 1.05, 0.14), (0, -0.50, z0 + 0.52), name='balslab',
                           coll=coll, mat=MAT['concrete'], bevel=0.02))
            for part in iron_railing(bwid, 0.98, coll, z0=z0 + 0.59):
                part.location.y += -1.0
                p.append(part)
            for sx in (-1, 1):
                p.append(M.box((0.16, 0.9, 0.18), (sx * (bwid / 2 - 0.1), -0.45,
                               z0 + 0.40), (0.35, 0, 0), name='bracket', coll=coll,
                               mat=MAT['stone']))
        # electric meter boxes, air conditioners and cable runs
        if rnd.random() < 0.45:
            cx = rnd.uniform(-width / 2 + 1, width / 2 - 1)
            p.append(M.box((0.62, 0.45, 0.48), (cx, -0.24, z0 + 1.1), name='ac',
                           coll=coll, mat=MAT['white']))
            p.append(M.box((0.56, 0.06, 0.40), (cx, -0.47, z0 + 1.1), name='acgrille',
                           coll=coll, mat=MAT['dark']))

    # --- roof clutter: water tanks, a stair head, antennas, a washing line
    for i in range(rnd.randint(1, 3)):
        tx = rnd.uniform(-width / 2 + 1, width / 2 - 1)
        ty = rnd.uniform(1.2, depth - 1.5)
        p.append(M.cyl(rnd.uniform(0.38, 0.55), rnd.uniform(0.9, 1.3), (tx, ty,
                       H + 0.6), name='tank', coll=coll, mat=MAT['white'], seg=16))
    p.append(M.box((2.1, 2.3, 2.5), (rnd.uniform(-width / 4, width / 4), depth * 0.6,
                   H + 1.25), name='stairhead', coll=coll, mat=plaster))
    for i in range(rnd.randint(1, 3)):
        ax = rnd.uniform(-width / 2 + 0.8, width / 2 - 0.8)
        p.append(M.cyl(0.020, rnd.uniform(1.6, 2.8), (ax, rnd.uniform(0.6, 2.5),
                       H + 1.6), name='antenna', coll=coll, mat=MAT['steel'], seg=6))

    ob = M.join(p, name, coll)
    M.move_to(ob, coll)
    S.log('%s: %.1f m wide, %d floors, %.1f m tall, %d tris'
          % (name, width, floors, H + parapet_h, M.tri_count(ob)))
    return coll


# ===================================================================== street kit
def traction_pole(name='KIT_TRAMPOLE', height=8.4, arm=3.3):
    """Tram traction pole: a tapered tube on a cast base, with a bracket arm that
    carries the 550 V trolley wire out over the track, and a street-light arm."""
    coll = S.coll(name)
    p = [M.cyl(0.14, 0.55, (0, 0, 0.27), name='base', coll=coll, mat=MAT['iron'],
               seg=16, r_top=0.11),
         M.cyl(0.095, height, (0, 0, height / 2 + 0.5), name='shaft', coll=coll,
               mat=MAT['iron'], seg=14, r_top=0.055),
         M.cyl(0.115, 0.10, (0, 0, 2.0), name='collar', coll=coll, mat=MAT['iron'],
               seg=14)]
    # bracket arm out over the track, with a tie rod back to the pole
    ztop = height * 0.80
    p.append(M.capsule_rod((0, 0, ztop), (0, -arm, ztop), 0.040, 10, 'arm', coll,
                           MAT['iron']))
    p.append(M.capsule_rod((0, 0, ztop + 1.25), (0, -arm + 0.35, ztop), 0.022, 8,
                           'tie', coll, MAT['iron']))
    p.append(M.cyl(0.05, 0.22, (0, -arm + 0.05, ztop - 0.14), name='insulator',
                   coll=coll, mat=MAT['white'], seg=12))
    # street light on a swan neck
    p.append(M.capsule_rod((0, 0, height + 0.35), (0, -1.5, height + 0.75), 0.030, 8,
                           'lampatarm', coll, MAT['iron']))
    p.append(M.box((0.46, 0.70, 0.16), (0, -1.62, height + 0.70), (0.12, 0, 0),
                   name='lamphead', coll=coll, mat=MAT['steel'], bevel=0.04))
    p.append(M.box((0.36, 0.56, 0.03), (0, -1.64, height + 0.62), (0.12, 0, 0),
                   name='lamplens', coll=coll, mat=MAT['lamp']))
    M.join(p, name, coll)
    return coll


def tin_shed(name='KIT_SHED', w=2.6, d=2.0, h=2.3):
    """The tin-roofed roadside stall of the first reference image: a tea stall or
    a cobbler's kiosk, leaning against whatever is behind it."""
    coll = S.coll(name)
    rnd = random.Random(21)
    p = []
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        p.append(M.box((0.08, 0.08, h), (sx * w / 2, sy * d / 2, h / 2), name='post',
                       coll=coll, mat=MAT['wood']))
    p.append(M.box((w + 0.45, d + 0.45, 0.05), (0, 0.05, h + 0.13), (0.14, 0, 0),
                   name='roof', coll=coll, mat=MAT['tin']))
    p.append(M.box((w, 0.06, h - 0.1), (0, d / 2, (h - 0.1) / 2), name='back',
                   coll=coll, mat=MAT['tin']))
    for sx in (-1, 1):
        p.append(M.box((0.06, d, h - 0.1), (sx * w / 2, 0, (h - 0.1) / 2),
                       name='side', coll=coll, mat=MAT['tin']))
    p.append(M.box((w - 0.2, 0.5, 0.08), (0, -d / 2 + 0.3, 0.95), name='counter',
                   coll=coll, mat=MAT['wood']))
    for i in range(6):
        p.append(M.box((0.16, 0.16, 0.22), (-w / 2 + 0.3 + i * 0.36, -d / 2 + 0.3,
                       1.10), name='jar', coll=coll, mat=MAT['glass']))
    p.append(M.box((w - 0.3, 0.05, 0.34), (0, -d / 2 - 0.04, h - 0.25), name='board',
                   coll=coll, mat=rnd.choice(MAT['shop'])))
    p.append(M.cyl(0.04, 0.12, (w / 2 - 0.4, -d / 2 + 0.1, h - 0.35), name='bulb',
                   coll=coll, mat=MAT['lamp'], seg=10))
    M.join(p, name, coll)
    return coll


def hoarding(name='KIT_HOARDING', w=4.2, h=2.6, legs=3.4):
    coll = S.coll(name)
    p = [M.box((w, 0.12, h), (0, 0, legs + h / 2), name='panel', coll=coll,
               mat=MAT['white']),
         M.box((w - 0.2, 0.03, h - 0.2), (0, -0.08, legs + h / 2), name='print',
               coll=coll, mat=random.Random(5).choice(MAT['shop']))]
    for sx in (-1, 1):
        p.append(M.box((0.10, 0.10, legs + h), (sx * (w / 2 - 0.3), 0,
                       (legs + h) / 2), name='leg', coll=coll, mat=MAT['steel']))
        p.append(M.capsule_rod((sx * (w / 2 - 0.3), 0, legs + h * 0.6),
                               (sx * (w / 2 - 0.3), 1.1, legs * 0.35), 0.030, 6,
                               'brace', coll, MAT['steel']))
    M.join(p, name, coll)
    return coll


def tree(name='KIT_TREE', seed=3, height=9.0, spread=7.0):
    """A rain tree / banyan: a short heavy trunk, a few forks, and the canopy as
    overlapping squashed spheres. Painterly rather than botanical -- it reads as
    foliage in silhouette, which is all the references ask of it."""
    coll = S.coll(name)
    rnd = random.Random(seed)
    p = [M.cyl(0.52, height * 0.40, (0, 0, height * 0.20), name='trunk', coll=coll,
               mat=MAT['bark'], seg=14, r_top=0.33)]
    # buttress roots
    for i in range(6):
        a = i * math.pi / 3 + rnd.uniform(-0.2, 0.2)
        p.append(M.capsule_rod((0, 0, 0.9),
                               (0.75 * math.cos(a), 0.75 * math.sin(a), 0.0),
                               0.13, 6, 'root', coll, MAT['bark']))
    tips = []
    for i in range(5):
        a = i * 2 * math.pi / 5 + rnd.uniform(-0.3, 0.3)
        r = spread * rnd.uniform(0.32, 0.48)
        tip = Vector((r * math.cos(a), r * math.sin(a), height * rnd.uniform(0.72, 0.95)))
        p.append(M.capsule_rod((0, 0, height * 0.38), tip, 0.15, 7, 'branch', coll,
                               MAT['bark']))
        tips.append(tip)
        for j in range(2):
            t2 = tip + Vector((rnd.uniform(-1.4, 1.4), rnd.uniform(-1.4, 1.4),
                               rnd.uniform(0.3, 1.1)))
            p.append(M.capsule_rod(tip, t2, 0.075, 5, 'twig', coll, MAT['bark']))
            tips.append(t2)
    for t in tips:
        for k in range(3):
            c = t + Vector((rnd.uniform(-1.5, 1.5), rnd.uniform(-1.5, 1.5),
                            rnd.uniform(-0.5, 1.0)))
            p.append(M.sphere(rnd.uniform(1.0, 1.9), (c.x, c.y, c.z), name='leaf',
                              coll=coll, mat=MAT['foliage'], seg=12, rings=6,
                              squash=rnd.uniform(0.5, 0.75)))
    ob = M.join(p, name, coll)
    S.log('%s: %d tris' % (name, M.tri_count(ob)))
    return coll


def handcart(name='KIT_HANDCART'):
    """A thela: the flat four-wheeled handcart that is everywhere in north Kolkata."""
    coll = S.coll(name)
    rnd = random.Random(11)
    p = [M.box((2.2, 1.15, 0.09), (0, 0, 0.70), name='deck', coll=coll,
               mat=MAT['wood'])]
    for sx in (-1, 1):
        p.append(M.box((2.2, 0.06, 0.22), (0, sx * 0.57, 0.84), name='sideboard',
                       coll=coll, mat=MAT['wood']))
    for ax in (0.72, -0.72):
        for sy in (-1, 1):
            p.append(M.cyl(0.29, 0.07, (ax, sy * 0.52, 0.29), (math.pi / 2, 0, 0),
                           name='wheel', coll=coll, mat=MAT['dark'], seg=20))
            p.append(M.cyl(0.07, 0.085, (ax, sy * 0.52, 0.29), (math.pi / 2, 0, 0),
                           name='hub', coll=coll, mat=MAT['steel'], seg=12))
    p.append(M.box((0.9, 0.07, 0.07), (1.55, 0, 0.78), (0, 0.18, 0), name='handle',
                   coll=coll, mat=MAT['wood']))
    for i in range(rnd.randint(3, 6)):
        p.append(M.box((rnd.uniform(0.3, 0.6), rnd.uniform(0.3, 0.7),
                        rnd.uniform(0.2, 0.45)),
                       (rnd.uniform(-0.8, 0.8), rnd.uniform(-0.3, 0.3),
                        0.9 + rnd.uniform(0, 0.3)), name='sack', coll=coll,
                       mat=rnd.choice(MAT['cloth'])))
    M.join(p, name, coll)
    return coll


def autorickshaw(name='KIT_AUTO'):
    """Kolkata's green-and-yellow three-wheeler, reduced to its silhouette."""
    coll = S.coll(name)
    p = [M.box((2.35, 1.30, 0.80), (0, 0, 0.72), name='tub', coll=coll,
               mat=MAT['auto_green'], bevel=0.22, bevel_seg=3),
         M.box((1.65, 1.26, 0.70), (-0.30, 0, 1.46), name='cabin', coll=coll,
               mat=MAT['auto_yellow'], bevel=0.26, bevel_seg=3),
         M.box((1.50, 1.12, 0.06), (-0.30, 0, 1.80), name='canopy', coll=coll,
               mat=MAT['auto_yellow'], bevel=0.14, bevel_seg=2),
         M.box((0.10, 1.00, 0.44), (0.80, 0, 1.30), (0, -0.35, 0), name='screen',
               coll=coll, mat=MAT['glass']),
         M.cyl(0.26, 0.11, (1.05, 0, 0.26), (math.pi / 2, 0, 0), name='frontwheel',
               coll=coll, mat=MAT['dark'], seg=20),
         M.cyl(0.19, 0.13, (1.05, 0, 0.78), (0, math.pi / 2, 0), name='fork',
               coll=coll, mat=MAT['steel'], seg=10),
         M.cyl(0.095, 0.08, (1.18, 0, 0.92), (0, math.pi / 2, 0), name='headlamp',
               coll=coll, mat=MAT['lamp'], seg=16)]
    for sy in (-1, 1):
        p.append(M.cyl(0.27, 0.13, (-0.62, sy * 0.62, 0.27), (math.pi / 2, 0, 0),
                       name='rearwheel', coll=coll, mat=MAT['dark'], seg=20))
    p.append(M.box((1.1, 1.16, 0.04), (-0.30, 0, 0.98), name='seat', coll=coll,
                   mat=MAT['dark']))
    M.join(p, name, coll)
    return coll


def figure(name='KIT_FIGURE', seed=1, umbrella=False, walking=True):
    """A walk-on. Stylised on purpose: at the distances these are used, a correct
    silhouette and a block of sari or shirt colour do more than a detailed mesh,
    and they stay cheap enough to scatter by the dozen."""
    coll = S.coll(name)
    rnd = random.Random(seed)
    h = rnd.uniform(1.58, 1.80)
    cloth = rnd.choice(MAT['cloth'])
    cloth2 = rnd.choice(MAT['cloth'])
    stride = 0.30 if walking else 0.08
    p = [M.box((0.22, 0.34, h * 0.30), (0, 0, h * 0.70), name='torso', coll=coll,
               mat=cloth, bevel=0.07, bevel_seg=2),
         M.sphere(h * 0.072, (0, 0, h * 0.93), name='head', coll=coll,
                  mat=MAT['skin'], seg=14, rings=8),
         M.cyl(0.055, h * 0.10, (0, 0, h * 0.86), name='neck', coll=coll,
               mat=MAT['skin'], seg=8)]
    for i, sy in enumerate((-1, 1)):
        a = stride * (1 if i == 0 else -1)
        p.append(M.cyl(0.062, h * 0.46, (a * 0.18, sy * 0.095, h * 0.26),
                       (0, -a * 0.6, 0), name='leg%d' % i, coll=coll, mat=cloth2,
                       seg=8))
        p.append(M.cyl(0.050, h * 0.40, (-a * 0.16, sy * 0.215, h * 0.66),
                       (0, a * 0.5, 0), name='arm%d' % i, coll=coll, mat=MAT['skin'],
                       seg=8))
        p.append(M.box((0.21, 0.09, 0.055), (a * 0.30, sy * 0.095, 0.028),
                       name='foot%d' % i, coll=coll, mat=MAT['dark']))
    if umbrella:
        p.append(M.cyl(0.013, 0.95, (-0.14, 0.24, h * 0.80), name='umbshaft',
                       coll=coll, mat=MAT['dark'], seg=8))
        p.append(M.sphere(0.56, (-0.14, 0.24, h * 1.14), name='umbcanopy', coll=coll,
                          mat=rnd.choice(MAT['cloth']), seg=16, rings=5, squash=0.42,
                          hemi=True))
    M.join(p, name, coll)
    return coll


def mosque(name='KIT_MOSQUE', w=17.0, d=13.0, body_h=13.0, minaret_h=30.0):
    """The domed mosque that closes the view down the street, in the manner of the
    Nakhoda Masjid: a red mass with arched openings, a ribbed onion dome on a
    drum, and a pair of tall minarets with balconies."""
    coll = S.coll(name)
    p = [M.box((w, d, body_h), (0, 0, body_h / 2), name='mass', coll=coll,
               mat=MAT['dome_trim']),
         M.box((w + 0.9, d + 0.9, 0.5), (0, 0, body_h + 0.25), name='cornice',
               coll=coll, mat=MAT['dome'], bevel=0.08)]
    # arched openings across the front
    for i in range(5):
        x = -w / 2 + w * (i + 0.5) / 5
        p.append(M.box((w / 5 - 1.0, 0.9, 5.4), (x, -d / 2 + 0.3, 3.0), name='arch',
                       coll=coll, mat=MAT['dark']))
        p.append(M.cyl((w / 5 - 1.0) / 2, 0.9, (x, -d / 2 + 0.3, 5.7),
                       (math.pi / 2, 0, 0), name='archtop', coll=coll,
                       mat=MAT['dark'], seg=18))
        p.append(M.box((0.7, 1.1, body_h), (x - (w / 5) / 2, -d / 2 + 0.2,
                       body_h / 2), name='pier', coll=coll, mat=MAT['dome']))
    # drum and ribbed onion dome
    p.append(M.cyl(4.6, 2.6, (0, 0, body_h + 1.8), name='drum', coll=coll,
                   mat=MAT['dome'], seg=28))
    prof = []
    for i in range(15):
        t = i / 14
        a = t * math.pi * 0.92
        prof.append((4.5 * math.sin(a) * (1.0 + 0.22 * math.sin(t * math.pi)),
                     body_h + 3.1 + 6.4 * (1 - math.cos(a)) / 2))
    prof.append((0.0, body_h + 9.9))
    p.append(M.revolve(prof, 32, 'Z', M.TAU, 'dome', coll, MAT['dome'], True, 40.0,
                       cap=False))
    p.append(M.cyl(0.22, 1.9, (0, 0, body_h + 10.6), name='finial', coll=coll,
                   mat=MAT['dome_trim'], seg=10))
    # minarets
    for sx in (-1, 1):
        bx = sx * (w / 2 - 1.3)
        p.append(M.cyl(1.25, minaret_h, (bx, 0, minaret_h / 2), name='minaret',
                       coll=coll, mat=MAT['dome'], seg=22, r_top=0.95))
        for zb in (minaret_h * 0.55, minaret_h * 0.86):
            p.append(M.cyl(1.70, 0.30, (bx, 0, zb), name='balcony', coll=coll,
                           mat=MAT['dome_trim'], seg=22))
            p.append(M.tube(1.68, 1.58, 0.85, (bx, 0, zb + 0.55), name='balrail',
                            coll=coll, mat=MAT['dome_trim'], seg=22))
        p.append(M.cyl(1.05, 1.5, (bx, 0, minaret_h + 0.75), name='mincap',
                       coll=coll, mat=MAT['dome'], seg=18))
        p.append(M.sphere(1.15, (bx, 0, minaret_h + 2.1), name='mindome', coll=coll,
                          mat=MAT['dome'], seg=18, rings=8, squash=1.25, hemi=True))
        p.append(M.cyl(0.14, 1.3, (bx, 0, minaret_h + 3.4), name='minfinial',
                       coll=coll, mat=MAT['dome_trim'], seg=8))
    ob = M.join(p, name, coll)
    S.log('%s: %d tris' % (name, M.tri_count(ob)))
    return coll


# ===================================================================== assemble
def main():
    S.reset('CityKit')
    materials()
    root = bpy.context.scene.collection

    S.log('buildings')
    building('KIT_BLDG_A', 11.5, 3, depth=10.0, seed=101)
    building('KIT_BLDG_B', 8.2, 4, depth=9.0, seed=202)
    building('KIT_BLDG_C', 14.0, 3, depth=11.0, seed=303, ground_h=4.3)
    building('KIT_BLDG_D', 6.6, 4, depth=8.0, seed=404, floor_h=3.0)
    building('KIT_BLDG_E', 10.0, 2, depth=9.5, seed=505, ground_h=4.0, floor_h=3.6)
    building('KIT_BLDG_F', 12.8, 5, depth=10.5, seed=606, floor_h=3.1)

    S.log('street furniture and props')
    traction_pole()
    tin_shed()
    hoarding()
    tree('KIT_TREE_BIG', seed=3, height=10.5, spread=8.5)
    tree('KIT_TREE_SMALL', seed=9, height=6.5, spread=5.0)
    handcart()
    autorickshaw()
    mosque()
    for i in range(6):
        figure('KIT_FIGURE_%d' % i, seed=40 + i, umbrella=(i % 3 == 0),
               walking=(i % 2 == 0))

    # keep the file tidy: every item lives in its own collection, nothing loose
    for ob in list(root.objects):
        bpy.data.objects.remove(ob, do_unlink=True)

    S.log('kit: %s' % S.stats())
    S.save(os.path.join(S.ASSETS, 'city_kit.blend'))


main()
