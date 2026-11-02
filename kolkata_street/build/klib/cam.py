"""Cameras.

The point of this project is to be able to move the camera and get a different
picture out of the same street, so the cameras are first-class: a named table of
shots, each with a real lens, a real aperture and a real focus distance, plus a
dolly rig on a path for moves.
"""
import bpy, math
from mathutils import Vector


def look_at(ob, loc, aim, roll=0.0):
    ob.location = loc
    d = Vector(aim) - Vector(loc)
    q = d.to_track_quat('-Z', 'Y')
    e = q.to_euler()
    if roll:
        ob.rotation_mode = 'QUATERNION'
        ob.rotation_quaternion = q
        ob.rotation_mode = 'XYZ'
        e = ob.rotation_euler.copy()
    ob.rotation_euler = e
    return ob


def camera(name, loc, aim, lens=50.0, fstop=None, focus=None, sensor=36.0,
           shift=(0.0, 0.0), clip=(0.05, 2000.0), coll=None, note=''):
    """One shot. `fstop` None means everything sharp; a number turns on depth of
    field, focused on `focus` metres or on the aim point if that is None."""
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = sensor
    cd.shift_x, cd.shift_y = shift
    cd.clip_start, cd.clip_end = clip
    if fstop:
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.focus_distance = focus or (Vector(aim) - Vector(loc)).length
    ob = bpy.data.objects.new(name, cd)
    (coll or bpy.context.scene.collection).objects.link(ob)
    look_at(ob, loc, aim)
    ob['note'] = note
    ob['aim'] = list(aim)
    return ob


def path_curve(name, points, coll=None):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('NURBS')
    sp.points.add(len(points) - 1)
    for i, p in enumerate(points):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
    sp.use_endpoint_u = True
    sp.order_u = 4
    cu.path_duration = 250
    cu.use_path = True
    ob = bpy.data.objects.new(name, cu)
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def dolly_rig(name, points, target_loc, lens=40.0, frames=250, fstop=None,
              coll=None):
    """A camera that slides along a path while aiming at a target empty.

    Scrub the timeline to move the shot; drag the target empty to re-aim it.
    This is the knob to turn when you want a perspective the fixed shots do not
    give you.
    """
    scene = bpy.context.scene
    curve = path_curve(name + '_PATH', points, coll)
    tgt = bpy.data.objects.new(name + '_TARGET', None)
    tgt.empty_display_type = 'SPHERE'
    tgt.empty_display_size = 0.6
    tgt.location = target_loc
    (coll or scene.collection).objects.link(tgt)

    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start, cd.clip_end = 0.05, 2000.0
    if fstop:
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.focus_object = tgt
    cam = bpy.data.objects.new(name, cd)
    (coll or scene.collection).objects.link(cam)

    c = cam.constraints.new('FOLLOW_PATH')
    c.target = curve
    c.use_curve_follow = False
    t = cam.constraints.new('TRACK_TO')
    t.target = tgt
    t.track_axis = 'TRACK_NEGATIVE_Z'
    t.up_axis = 'UP_Y'

    curve.data.eval_time = 0
    curve.data.keyframe_insert('eval_time', frame=1)
    curve.data.eval_time = frames
    curve.data.keyframe_insert('eval_time', frame=frames)
    if curve.data.animation_data and curve.data.animation_data.action:
        for fc in curve.data.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'
    scene.frame_start, scene.frame_end = 1, frames
    return cam, curve, tgt
