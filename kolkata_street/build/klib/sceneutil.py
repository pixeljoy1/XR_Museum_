"""Scene plumbing: reset, collections, render settings, saving, library linking.

Paths are all derived from this file's own location, so the project can be cloned
anywhere (the old XR_Museum_ build hardcoded a Mac path; this one does not).
"""
import bpy, os, sys, math, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../build
ROOT = os.path.dirname(HERE)                                          # project root
ASSETS = os.path.join(ROOT, 'assets')
SCENE = os.path.join(ROOT, 'scene')
RENDERS = os.path.join(ROOT, 'renders')
for d in (ASSETS, SCENE, RENDERS):
    os.makedirs(d, exist_ok=True)

_T0 = time.time()
_LOG = None


def log_to(path):
    """Blender block-buffers stdout when it is redirected, so a headless run is only
    watchable through a file. Every build writes one."""
    global _LOG
    _LOG = open(path, 'w')


def log(msg):
    line = '%7.1fs  %s' % (time.time() - _T0, msg)
    print(line)
    sys.stdout.flush()
    if _LOG:
        _LOG.write(line + '\n')
        _LOG.flush()


def args(default=None):
    """Everything after `--` on the Blender command line."""
    if '--' in sys.argv:
        return sys.argv[sys.argv.index('--') + 1:]
    return list(default or [])


def argval(flag, default=None, cast=str):
    a = args()
    if flag in a:
        i = a.index(flag)
        if i + 1 < len(a):
            return cast(a[i + 1])
    return default


def has_flag(flag):
    return flag in args()


# ------------------------------------------------------------------ scene
def reset(name='Scene', unit_scale=1.0):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.name = name
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = unit_scale
    sc.unit_settings.length_unit = 'METERS'
    return sc


def coll(name, parent=None):
    """Get or make a collection, linked under `parent` (scene collection by default)."""
    if name in bpy.data.collections:
        c = bpy.data.collections[name]
    else:
        c = bpy.data.collections.new(name)
    p = parent or bpy.context.scene.collection
    if c.name not in [x.name for x in p.children]:
        try:
            p.children.link(c)
        except RuntimeError:
            pass
    return c


def cycles(samples=128, denoise=True, res=(1920, 1080), pct=100, device='CPU',
           bounces=6, transparent=False, film_exposure=1.0, clamp_indirect=8.0):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = device
    sc.cycles.samples = samples
    sc.cycles.preview_samples = max(16, samples // 8)
    sc.cycles.use_denoising = denoise
    sc.cycles.max_bounces = bounces
    sc.cycles.diffuse_bounces = min(3, bounces)
    sc.cycles.glossy_bounces = min(3, bounces)   # a wet road is a mirror: these
                                                 # are the expensive ones
    sc.cycles.transmission_bounces = bounces
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.sample_clamp_indirect = clamp_indirect
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = pct
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = 'PNG'
    # AgX on 4.x, Filmic on 3.x -- both roll highlights off instead of clipping them,
    # which matters for a wet street full of specular hits.
    for vt in ('AgX', 'Filmic', 'Standard'):
        try:
            sc.view_settings.view_transform = vt
            break
        except TypeError:
            continue
    sc.view_settings.look = 'None'
    sc.view_settings.exposure = 0.0
    if hasattr(sc.cycles, 'film_exposure'):
        sc.cycles.film_exposure = film_exposure
    return sc


def eevee(samples=64, res=(1920, 1080)):
    sc = bpy.context.scene
    for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    ee = sc.eevee
    for attr, val in (('taa_render_samples', samples), ('use_gtao', True),
                      ('use_ssr', True), ('use_ssr_refraction', True),
                      ('use_bloom', True), ('use_raytracing', True)):
        if hasattr(ee, attr):
            setattr(ee, attr, val)
    sc.render.resolution_x, sc.render.resolution_y = res
    return sc


def purge():
    """Drop orphaned datablocks. Builds that create and delete thousands of small
    objects leave the mesh datablocks behind, which bloats the .blend."""
    for _ in range(4):
        n = 0
        for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                     bpy.data.objects, bpy.data.images, bpy.data.node_groups):
            for d in list(coll):
                if d.users == 0:
                    coll.remove(d)
                    n += 1
        if not n:
            break


def save(path):
    purge()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True,
                                relative_remap=True)
    log('saved %s  (%.1f MB)' % (path, os.path.getsize(path) / 1e6))
    return path


# ------------------------------------------------------------------ linking
def link_collection(blend_path, coll_name, link=True):
    """Bring a collection in from another .blend.

    link=True  -> a library link: the geometry lives in exactly one file and every
                  placement in the street is an instance of it. This is what makes
                  'model it once' literally true, and it means re-running
                  build_tram.py updates every tram in the street.
    link=False -> append a real copy (use when you want the scene self-contained).
    """
    blend_path = os.path.abspath(blend_path)
    if not os.path.exists(blend_path):
        raise FileNotFoundError('%s is missing -- build it first' % blend_path)
    inner = os.path.join(blend_path, 'Collection', coll_name)
    directory = os.path.join(blend_path, 'Collection') + os.sep
    before = set(bpy.data.collections.keys())
    bpy.ops.wm.link(filepath=inner, filename=coll_name, directory=directory,
                    link=link, instance_collections=False, autoselect=False)
    new = set(bpy.data.collections.keys()) - before
    found = None
    for n in new:
        c = bpy.data.collections[n]
        if c.name.split('.')[0] == coll_name:
            found = c
            break
    if found is None and coll_name in bpy.data.collections:
        found = bpy.data.collections[coll_name]
    if found is None:
        raise RuntimeError('could not link %s from %s' % (coll_name, blend_path))
    unlink_everywhere(found)
    log('linked %s from %s' % (coll_name, os.path.basename(blend_path)))
    return found


def unlink_everywhere(c):
    """Take a collection out of the scene hierarchy without unloading it.

    wm.link puts the linked collection into the active collection, so its objects
    render at their authored positions -- at the origin -- *as well as* at every
    instance of it. That puts a second copy of every asset in a heap in the middle
    of the street. An instance empty keeps its reference to the collection
    whether or not the collection is in the hierarchy, so dropping it here is
    exactly right.
    """
    for parent in [bpy.context.scene.collection] + list(bpy.data.collections):
        try:
            if c.name in [ch.name for ch in parent.children]:
                parent.children.unlink(c)
        except (RuntimeError, ReferenceError):
            pass
    return c


def instance(src_coll, name, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1),
             into=None):
    """An empty that draws a whole collection. Cheap: the mesh data is shared."""
    ob = bpy.data.objects.new(name, None)
    ob.instance_type = 'COLLECTION'
    ob.instance_collection = src_coll
    ob.empty_display_size = 0.4
    ob.location = loc
    ob.rotation_euler = rot
    ob.scale = scale
    (into or bpy.context.scene.collection).objects.link(ob)
    return ob


def stats():
    tris = 0
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            tris += sum(len(p.vertices) - 2 for p in ob.data.polygons)
    return {'objects': len(bpy.data.objects), 'meshes': len(bpy.data.meshes),
            'tris': tris, 'materials': len(bpy.data.materials)}
