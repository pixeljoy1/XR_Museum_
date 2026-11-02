"""Render shots from the saved street scene, without rebuilding it.

    blender -b scene/kolkata_street.blend -P build/render.py -- --list
    blender -b scene/kolkata_street.blend -P build/render.py -- --all --samples 256
    blender -b scene/kolkata_street.blend -P build/render.py -- --shot SHOT_03_telephoto_vista
    blender -b scene/kolkata_street.blend -P build/render.py -- --dolly 1,60,120,180,250
    blender -b scene/kolkata_street.blend -P build/render.py -- --all --draft

--draft drops to 32 samples at half resolution, which is the setting to use while
you are moving cameras around. The full-quality pass is what --samples is for.
"""
import bpy, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klib import sceneutil as S

S.log_to(os.path.join(S.ROOT, 'build', 'render.log'))


def cameras():
    return sorted([o for o in bpy.data.objects if o.type == 'CAMERA'],
                  key=lambda o: o.name)


def main():
    sc = bpy.context.scene
    cams = cameras()
    if S.has_flag('--list') or not S.args():
        print('\ncameras in %s\n' % bpy.data.filepath)
        for c in cams:
            note = c.get('note', '')
            print('  %-28s %4.0f mm   %s' % (c.name, c.data.lens, note))
        print('\nframes %d-%d (the CAM_DOLLY move)\n' % (sc.frame_start, sc.frame_end))
        return

    if S.has_flag('--draft'):
        sc.cycles.samples = 32
        sc.render.resolution_percentage = 50
    samples = S.argval('--samples', None, int)
    if samples:
        sc.cycles.samples = samples
    pct = S.argval('--res', None, int)
    if pct:
        sc.render.resolution_percentage = pct
    out = S.argval('--out', S.RENDERS)
    os.makedirs(out, exist_ok=True)

    dolly = S.argval('--dolly', None)
    if dolly:
        cam = bpy.data.objects.get('CAM_DOLLY')
        if cam is None:
            print('no CAM_DOLLY in this scene')
            return
        sc.camera = cam
        for f in [int(v) for v in dolly.split(',')]:
            sc.frame_set(f)
            sc.render.filepath = os.path.join(out, 'DOLLY_%04d.png' % f)
            S.log('render dolly frame %d' % f)
            bpy.ops.render.render(write_still=True)
        return

    want = S.argval('--shot', None)
    targets = cams if S.has_flag('--all') else \
        [c for c in cams if c.name == want] if want else [sc.camera]
    if not targets or targets == [None]:
        print('nothing to render: pass --all, or --shot <name> (see --list)')
        return
    for c in targets:
        if c.name == 'CAM_DOLLY':
            continue
        sc.camera = c
        sc.render.filepath = os.path.join(out, '%s.png' % c.name)
        S.log('render %s (%.0f mm, %d samples)' % (c.name, c.data.lens,
                                                   sc.cycles.samples))
        bpy.ops.render.render(write_still=True)


main()
