"""Material factory. Everything is procedural -- no image files, so the .blend files
are self-contained and the scene opens the same on any machine.

Socket names moved between Blender 3.x and 4.x (Clearcoat -> Coat Weight,
Emission -> Emission Color, Transmission -> Transmission Weight, ...), so every
Principled input is written through `_set`, which tries the alternatives in turn.
"""
import bpy, math

# 4.x name first, then the 3.x name.
ALIASES = {
    'coat':        ('Coat Weight', 'Clearcoat'),
    'coat_rough':  ('Coat Roughness', 'Clearcoat Roughness'),
    'emission':    ('Emission Color', 'Emission'),
    'emit_str':    ('Emission Strength',),
    'transmission': ('Transmission Weight', 'Transmission'),
    'specular':    ('Specular IOR Level', 'Specular'),
    'sheen':       ('Sheen Weight', 'Sheen'),
    'base':        ('Base Color',),
    'metallic':    ('Metallic',),
    'roughness':   ('Roughness',),
    'ior':         ('IOR',),
    'alpha':       ('Alpha',),
    'normal':      ('Normal',),
}


def _set(bsdf, key, value):
    for n in ALIASES.get(key, (key,)):
        if n in bsdf.inputs:
            s = bsdf.inputs[n]
            if hasattr(s.default_value, '__len__') and not hasattr(value, '__len__'):
                s.default_value = (value, value, value, 1.0)
            elif hasattr(s.default_value, '__len__') and len(value) == 3:
                s.default_value = (*value, 1.0)
            else:
                s.default_value = value
            return s
    return None


def _socket(bsdf, key):
    for n in ALIASES.get(key, (key,)):
        if n in bsdf.inputs:
            return bsdf.inputs[n]
    return None


def _new(name):
    if name in bpy.data.materials:
        return bpy.data.materials[name], None, None
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    return m, nt, bsdf


def base(name, color=(0.5, 0.5, 0.5), rough=0.6, metal=0.0, coat=0.0, ior=1.45,
         emit=None, emit_str=0.0, alpha=1.0, transmission=0.0, sheen=0.0,
         coat_rough=0.05):
    """A plain Principled material. Returns the existing one if the name is taken,
    so builds are idempotent and a re-run does not pile up duplicates."""
    m, nt, bsdf = _new(name)
    if nt is None:
        return m
    _set(bsdf, 'base', color)
    _set(bsdf, 'roughness', rough)
    _set(bsdf, 'metallic', metal)
    _set(bsdf, 'coat', coat)
    _set(bsdf, 'coat_rough', coat_rough)
    _set(bsdf, 'ior', ior)
    _set(bsdf, 'alpha', alpha)
    _set(bsdf, 'transmission', transmission)
    _set(bsdf, 'sheen', sheen)
    if emit is not None:
        _set(bsdf, 'emission', emit)
        _set(bsdf, 'emit_str', emit_str)
    if alpha < 1.0 or transmission > 0.0:
        m.blend_method = 'BLEND'
        if hasattr(m, 'shadow_method'):
            m.shadow_method = 'HASHED'
    return m


def bsdf_of(m):
    return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


# ------------------------------------------------------------------ node helpers
def _noise(nt, scale=5.0, detail=6.0, rough=0.5, distortion=0.0, loc=(-900, 0)):
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.location = loc
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    if 'Roughness' in n.inputs:
        n.inputs['Roughness'].default_value = rough
    n.inputs['Distortion'].default_value = distortion
    return n


def _ramp(nt, stops, loc=(-700, 0), interp='LINEAR'):
    n = nt.nodes.new('ShaderNodeValToRGB')
    n.location = loc
    n.color_ramp.interpolation = interp
    els = n.color_ramp.elements
    while len(els) > 1:
        els.remove(els[-1])
    for i, (pos, col) in enumerate(stops):
        e = els[0] if i == 0 else els.new(pos)
        e.position = pos
        e.color = (*col, 1.0) if len(col) == 3 else col
    return n


def _mapping(nt, scale=(1, 1, 1), loc=(-1100, 0), coord='Object'):
    """A scaled texture coordinate.

    coord='World' uses the Geometry node's Position, which is world space in
    metres. That is the only coordinate that is continuous ACROSS objects:
    'Generated' is normalised to each object's own bounding box, so two
    neighbouring surfaces with the same material get completely different
    patterns, and 'Object' shifts with each object's origin.
    """
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.location = loc
    mp.inputs['Scale'].default_value = scale
    if coord == 'World':
        tc = nt.nodes.new('ShaderNodeNewGeometry')
        tc.location = (loc[0] - 200, loc[1])
        nt.links.new(tc.outputs['Position'], mp.inputs['Vector'])
    else:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        tc.location = (loc[0] - 200, loc[1])
        nt.links.new(tc.outputs[coord], mp.inputs['Vector'])
    return tc, mp


def _mix_rgb(nt, fac_node, fac_out, a, b, loc=(-450, 0)):
    """Mix two colours. ShaderNodeMix in 4.x, ShaderNodeMixRGB in 3.x."""
    try:
        n = nt.nodes.new('ShaderNodeMix')
        n.data_type = 'RGBA'
        n.location = loc
        n.inputs[0].default_value = 0.5
        if fac_node is not None:
            nt.links.new(fac_node.outputs[fac_out], n.inputs[0])
        n.inputs[6].default_value = (*a, 1.0) if len(a) == 3 else a
        n.inputs[7].default_value = (*b, 1.0) if len(b) == 3 else b
        return n, n.outputs[2]
    except RuntimeError:
        n = nt.nodes.new('ShaderNodeMixRGB')
        n.location = loc
        if fac_node is not None:
            nt.links.new(fac_node.outputs[fac_out], n.inputs['Fac'])
        n.inputs['Color1'].default_value = (*a, 1.0) if len(a) == 3 else a
        n.inputs['Color2'].default_value = (*b, 1.0) if len(b) == 3 else b
        return n, n.outputs['Color']


def _mix_float(nt, fac_node, fac_out, a, b, loc=(-450, -200)):
    try:
        n = nt.nodes.new('ShaderNodeMix')
        n.data_type = 'FLOAT'
        n.location = loc
        if fac_node is not None:
            nt.links.new(fac_node.outputs[fac_out], n.inputs[0])
        n.inputs[2].default_value = a
        n.inputs[3].default_value = b
        return n, n.outputs[0]
    except RuntimeError:
        n = nt.nodes.new('ShaderNodeMixRGB')
        n.location = loc
        if fac_node is not None:
            nt.links.new(fac_node.outputs[fac_out], n.inputs['Fac'])
        n.inputs['Color1'].default_value = (a, a, a, 1)
        n.inputs['Color2'].default_value = (b, b, b, 1)
        return n, n.outputs['Color']


def _bump(nt, bsdf, height_node, height_out, strength=0.2, distance=0.01, loc=(-250, -400)):
    b = nt.nodes.new('ShaderNodeBump')
    b.location = loc
    b.inputs['Strength'].default_value = strength
    b.inputs['Distance'].default_value = distance
    nt.links.new(height_node.outputs[height_out], b.inputs['Height'])
    nt.links.new(b.outputs['Normal'], _socket(bsdf, 'normal'))
    return b


def mottle(m, scale=6.0, strength=0.12, detail=8.0, dark=0.72, bump=0.0,
           coord='Object'):
    """Break a flat colour with large-scale blotching -- plaster, stone, paintwork."""
    nt = m.node_tree
    bsdf = bsdf_of(m)
    sock = _socket(bsdf, 'base')
    col = tuple(sock.default_value[:3])
    tc, mp = _mapping(nt, (scale, scale, scale), (-1100, 300), coord)
    n = _noise(nt, 1.0, detail, 0.55, 0.0, (-900, 300))
    nt.links.new(mp.outputs['Vector'], n.inputs['Vector'])
    r = _ramp(nt, [(0.5 - strength, (0, 0, 0)), (0.5 + strength, (1, 1, 1))], (-700, 300))
    nt.links.new(n.outputs['Fac'], r.inputs['Fac'])
    dc = tuple(c * dark for c in col)
    mix, out = _mix_rgb(nt, r, 'Color', dc, col, (-450, 300))
    nt.links.new(out, sock)
    if bump:
        _bump(nt, bsdf, n, 'Fac', bump, 0.02)
    return m


# ------------------------------------------------------------------ the library
def car_paint(name, color, rough=0.28, flake=0.0, coat=1.0, dirt=0.0):
    """Body paint: a clearcoat over a slightly rough base, optionally dusted down.
    `dirt` lifts roughness and greys the colour, which is what every vehicle in a
    Kolkata street actually looks like."""
    m, nt, bsdf = _new(name)
    if nt is None:
        return m
    c = tuple(color)
    if dirt:
        c = tuple(ch * (1 - 0.35 * dirt) + 0.11 * dirt for ch in c)
    _set(bsdf, 'base', c)
    _set(bsdf, 'roughness', rough + 0.35 * dirt)
    _set(bsdf, 'metallic', 0.0)
    _set(bsdf, 'coat', coat * (1 - 0.5 * dirt))
    _set(bsdf, 'coat_rough', 0.03 + 0.25 * dirt)
    if flake:
        _set(bsdf, 'metallic', flake)
    if dirt:
        mottle(m, 2.5, 0.10, 6.0, 0.82, bump=0.05)
    return m


def chrome(name='chrome', rough=0.06, tint=(0.85, 0.86, 0.88)):
    return base(name, tint, rough, 1.0)


def steel(name='steel', rough=0.4, tint=(0.56, 0.57, 0.58)):
    return base(name, tint, rough, 1.0)


def rust(name='rust'):
    m = base(name, (0.26, 0.11, 0.05), 0.85, 0.35)
    mottle(m, 9.0, 0.16, 10.0, 0.55, bump=0.35)
    return m


def rubber(name='rubber', rough=0.75, tint=(0.016, 0.016, 0.018)):
    return base(name, tint, rough, 0.0)


def glass(name='glass', tint=(0.62, 0.68, 0.70), rough=0.02, transmission=0.92):
    m = base(name, tint, rough, 0.0, ior=1.52, transmission=transmission)
    return m


def dark_glass(name='glass_dark', tint=(0.05, 0.06, 0.07), rough=0.12):
    """Cheap window glass for buildings and distant vehicles: opaque, dark,
    glossy. Costs nothing to render and reads correctly at street distance."""
    return base(name, tint, rough, 0.0, coat=0.7, coat_rough=0.03)


def emissive(name, color=(1.0, 0.93, 0.78), strength=12.0):
    m, nt, bsdf = _new(name)
    if nt is None:
        return m
    _set(bsdf, 'base', (0, 0, 0))
    _set(bsdf, 'roughness', 0.3)
    _set(bsdf, 'emission', color)
    _set(bsdf, 'emit_str', strength)
    return m


def painted_metal(name, color, rough=0.45, dirt=0.25):
    m = base(name, color, rough, 0.0, coat=0.3, coat_rough=0.18)
    if dirt:
        mottle(m, 4.0, 0.12, 7.0, 1.0 - 0.3 * dirt, bump=0.08)
    return m


def plaster(name, color=(0.72, 0.69, 0.62), rough=0.9, grime=0.45):
    """Lime-washed colonial plaster, streaked by the monsoon. The streaking is a
    noise stretched hard in Z so it runs down the wall."""
    m, nt, bsdf = _new(name)
    if nt is None:
        return m
    _set(bsdf, 'base', color)
    _set(bsdf, 'roughness', rough)
    tc, mp = _mapping(nt, (6.0, 6.0, 0.35), (-1100, 300), 'Object')
    n = _noise(nt, 1.0, 9.0, 0.6, 0.4, (-900, 300))
    nt.links.new(mp.outputs['Vector'], n.inputs['Vector'])
    r = _ramp(nt, [(0.34, (0, 0, 0)), (0.62, (1, 1, 1))], (-700, 300))
    nt.links.new(n.outputs['Fac'], r.inputs['Fac'])
    dirty = tuple(c * (1.0 - 0.52 * grime) * 0.86 for c in color)
    mix, out = _mix_rgb(nt, r, 'Color', dirty, color, (-450, 300))
    nt.links.new(out, _socket(bsdf, 'base'))
    fine = _noise(nt, 55.0, 6.0, 0.5, 0.0, (-900, -300))
    _bump(nt, bsdf, fine, 'Fac', 0.22, 0.004)
    return m


def brick(name='brick', color=(0.33, 0.15, 0.10), mortar=(0.62, 0.60, 0.56),
          scale=(14.0, 14.0, 44.0)):
    """Courses from a stretched brick texture, mortar lines bumped in."""
    m, nt, bsdf = _new(name)
    if nt is None:
        return m
    tc, mp = _mapping(nt, scale, (-1100, 300), 'Object')
    b = nt.nodes.new('ShaderNodeTexBrick')
    b.location = (-900, 300)
    b.inputs['Color1'].default_value = (*color, 1)
    b.inputs['Color2'].default_value = (*[c * 0.82 for c in color], 1)
    b.inputs['Mortar'].default_value = (*mortar, 1)
    b.inputs['Scale'].default_value = 1.0
    b.inputs['Mortar Size'].default_value = 0.022
    b.inputs['Bias'].default_value = 0.0
    b.inputs['Brick Width'].default_value = 0.5
    b.inputs['Row Height'].default_value = 0.17
    nt.links.new(mp.outputs['Vector'], b.inputs['Vector'])
    nt.links.new(b.outputs['Color'], _socket(bsdf, 'base'))
    _set(bsdf, 'roughness', 0.92)
    _bump(nt, bsdf, b, 'Fac', 0.5, 0.008)
    return m


def wet_asphalt(name='asphalt_wet', wetness=0.75, puddle_scale=0.55,
                tint=(0.040, 0.040, 0.043), blocks=False, block_scale=5.5):
    """The single most important material in the scene.

    Dry asphalt is near-black and rough. Where a puddle sits, roughness collapses
    to a mirror and the surface darkens -- that is what makes the reference
    paintings read as monsoon Kolkata. The puddle mask is one big noise, hard
    ramped, so puddles are irregular connected pools rather than dots.
    `wetness` 0 = dry road, 1 = sheet water everywhere.

    `blocks` adds a stone-sett joint pattern as bump only, for the band the tram
    rails are laid in. It has to be the same material as the road, not a separate
    glossier one: at grazing incidence Fresnel reflectance goes to 1 whatever the
    base colour, so a shinier band turns into a sheet of white sky and reads as a
    pavement running down the middle of the carriageway. Same wetness, same
    puddles, joints in the bump -- and then the rails are the only bright lines,
    which is what the reference photographs show.
    """
    m, nt, bsdf = _new(name)
    if nt is None:
        return m
    tc, mp = _mapping(nt, (1.0, 1.0, 1.0), (-1400, 300), 'World')
    pud = _noise(nt, puddle_scale, 4.0, 0.52, 0.9, (-1200, 300))
    nt.links.new(mp.outputs['Vector'], pud.inputs['Vector'])
    thresh = 0.56 - 0.20 * wetness
    mask = _ramp(nt, [(thresh, (0, 0, 0)), (thresh + 0.10, (1, 1, 1))], (-1000, 300))
    nt.links.new(pud.outputs['Fac'], mask.inputs['Fac'])

    grain = _noise(nt, 11.0, 8.0, 0.6, 0.0, (-1200, -100))
    nt.links.new(mp.outputs['Vector'], grain.inputs['Vector'])
    gramp = _ramp(nt, [(0.38, (0, 0, 0)), (0.66, (1, 1, 1))], (-1000, -100))
    nt.links.new(grain.outputs['Fac'], gramp.inputs['Fac'])
    dry_col = tuple(c * 2.3 for c in tint)
    dryn, dry_out = _mix_rgb(nt, gramp, 'Color', tint, dry_col, (-800, -100))

    wet_col = tuple(c * 0.52 for c in tint)
    colmix, col_out = _mix_rgb(nt, mask, 'Color', (0, 0, 0), wet_col, (-600, 100))
    nt.links.new(dry_out, colmix.inputs[6] if colmix.bl_idname == 'ShaderNodeMix'
                 else colmix.inputs['Color1'])
    nt.links.new(col_out, _socket(bsdf, 'base'))

    rmix, r_out = _mix_float(nt, mask, 'Color', 0.0, 0.0, (-600, -300))
    # dry side: rough, modulated by grain; wet side: near mirror
    rdry, rdry_out = _mix_float(nt, gramp, 'Color', 0.88, 0.62, (-800, -400))
    nt.links.new(rdry_out, rmix.inputs[2] if rmix.bl_idname == 'ShaderNodeMix'
                 else rmix.inputs['Color1'])
    if rmix.bl_idname == 'ShaderNodeMix':
        rmix.inputs[3].default_value = 0.035
    else:
        rmix.inputs['Color2'].default_value = (0.035,) * 3 + (1,)
    nt.links.new(r_out, _socket(bsdf, 'roughness'))

    # coarse aggregate bump on the dry parts only, plus faint ripples on the wet
    ripple = _noise(nt, 26.0, 3.0, 0.5, 0.0, (-1200, -500))
    nt.links.new(mp.outputs['Vector'], ripple.inputs['Vector'])
    bmix, b_out = _mix_float(nt, mask, 'Color', 0.0, 0.0, (-600, -560))
    nt.links.new(gramp.outputs['Color'], bmix.inputs[2] if bmix.bl_idname == 'ShaderNodeMix'
                 else bmix.inputs['Color1'])
    nt.links.new(ripple.outputs['Fac'], bmix.inputs[3] if bmix.bl_idname == 'ShaderNodeMix'
                 else bmix.inputs['Color2'])
    height_out = b_out
    if blocks:
        tc2, mp2 = _mapping(nt, (block_scale,) * 3, (-1400, -760), 'World')
        br = nt.nodes.new('ShaderNodeTexBrick')
        br.location = (-1200, -760)
        br.inputs['Scale'].default_value = 1.0
        br.inputs['Mortar Size'].default_value = 0.030
        br.inputs['Brick Width'].default_value = 0.55
        br.inputs['Row Height'].default_value = 0.42
        nt.links.new(mp2.outputs['Vector'], br.inputs['Vector'])
        jmix, jout = _mix_float(nt, None, None, 0.0, 0.0, (-900, -760))
        is_mix = jmix.bl_idname == 'ShaderNodeMix'
        nt.links.new(b_out, jmix.inputs[2] if is_mix else jmix.inputs['Color1'])
        nt.links.new(br.outputs['Fac'],
                     jmix.inputs[3] if is_mix else jmix.inputs['Color2'])
        (jmix.inputs[0] if is_mix else jmix.inputs['Fac']).default_value = 0.70
        height_out = jout
    bump = nt.nodes.new('ShaderNodeBump')
    bump.location = (-300, -500)
    bump.inputs['Strength'].default_value = 0.55 if blocks else 0.30
    bump.inputs['Distance'].default_value = 0.010 if blocks else 0.006
    nt.links.new(height_out, bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], _socket(bsdf, 'normal'))
    _set(bsdf, 'specular', 0.5)
    return m


def concrete(name='concrete', color=(0.52, 0.51, 0.49), rough=0.88):
    m = base(name, color, rough)
    mottle(m, 7.0, 0.14, 9.0, 0.78, bump=0.25)
    return m


def teak(name='teak', color=(0.20, 0.098, 0.045), rough=0.55):
    m, nt, bsdf = _new(name)
    if nt is None:
        return m
    tc, mp = _mapping(nt, (2.0, 2.0, 30.0), (-1100, 300), 'Object')
    n = _noise(nt, 1.0, 10.0, 0.6, 1.2, (-900, 300))
    nt.links.new(mp.outputs['Vector'], n.inputs['Vector'])
    r = _ramp(nt, [(0.36, [c * 0.55 for c in color]), (0.64, color)], (-700, 300))
    nt.links.new(n.outputs['Fac'], r.inputs['Fac'])
    nt.links.new(r.outputs['Color'], _socket(bsdf, 'base'))
    _set(bsdf, 'roughness', rough)
    _bump(nt, bsdf, n, 'Fac', 0.12, 0.003)
    return m


def corrugated_tin(name='tin', color=(0.38, 0.36, 0.33), rusty=0.5):
    m, nt, bsdf = _new(name)
    if nt is None:
        return m
    _set(bsdf, 'base', color)
    _set(bsdf, 'roughness', 0.62)
    _set(bsdf, 'metallic', 0.75)
    tc, mp = _mapping(nt, (13.0, 1.0, 1.0), (-1100, 0), 'Object')
    w = nt.nodes.new('ShaderNodeTexWave')
    w.location = (-900, 0)
    w.wave_type = 'BANDS'
    w.bands_direction = 'X'
    w.wave_profile = 'SIN'
    w.inputs['Scale'].default_value = 1.0
    nt.links.new(mp.outputs['Vector'], w.inputs['Vector'])
    _bump(nt, bsdf, w, 'Fac', 0.85, 0.02)
    if rusty:
        rn = _noise(nt, 11.0, 9.0, 0.6, 0.0, (-900, 400))
        rr = _ramp(nt, [(0.52 - 0.12 * rusty, (0, 0, 0)), (0.70, (1, 1, 1))], (-700, 400))
        nt.links.new(rn.outputs['Fac'], rr.inputs['Fac'])
        mx, out = _mix_rgb(nt, rr, 'Color', (0.26, 0.11, 0.05), color, (-450, 400))
        nt.links.new(out, _socket(bsdf, 'base'))
        rm, rout = _mix_float(nt, rr, 'Color', 0.92, 0.62, (-450, 150))
        nt.links.new(rout, _socket(bsdf, 'roughness'))
    return m


def foliage(name='foliage', color=(0.030, 0.062, 0.016)):
    """Leaf material.

    Deliberately NO sheen. Principled's sheen lobe is a bright white rim; on the
    big smooth spheres a procedural canopy is made of, it covers the whole
    surface and the tree renders as a pale grey blob instead of foliage. The
    depth comes from mottling the base colour hard instead.
    """
    m, nt, bsdf = _new(name)
    if nt is None:
        return m
    _set(bsdf, 'base', color)
    _set(bsdf, 'roughness', 0.78)
    _set(bsdf, 'sheen', 0.0)
    _set(bsdf, 'specular', 0.25)
    mottle(m, 9.0, 0.26, 10.0, 0.38, bump=0.5)
    return m


def cloth(name, color, rough=0.82):
    return base(name, color, rough, 0.0, sheen=0.55)


def srgb(hexstr):
    """'#e2541a' -> linear RGB, which is what Base Color wants.

    Colours picked off a photograph or a paint chart are sRGB; feeding them
    straight into Base Color is the commonest reason a build comes out washed out.
    """
    h = hexstr.lstrip('#')
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)
