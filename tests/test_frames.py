"""Headless tests for the editable frame, mounted hardware and the gizmos.

    blender --background --factory-startup --python tests/test_frames.py
"""

import math
import os
import sys

import bpy
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

MM = 0.001
FAIL = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAIL.append(msg)


import alugen  # noqa: E402
alugen.register()

from alugen import builder, frames, gizmos, mounting  # noqa: E402

C = bpy.context


def reset():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def bounds(objs):
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return lo, hi


def profiles(ctrl):
    return [o for o in frames.members(ctrl) if o.alugen.kind == 'PROFILE']


def lengths(ctrl):
    return sorted(round(o.alugen.length, 1) for o in profiles(ctrl))


def make_frame(x=800.0, y=600.0, z=900.0, levels=0):
    reset()
    s = C.scene.alugen
    s.a, s.b, s.slot = '40', '40', 'N8'
    s.frame_x, s.frame_y, s.frame_z = x, y, z
    s.frame_levels, s.frame_top, s.frame_bottom = levels, True, True
    s.frame_brackets = s.frame_caps = True
    bpy.ops.alugen.build_frame()
    return C.active_object


print("\n=== Frame controller ===")
ctrl = make_frame()
check(frames.is_controller(ctrl), "build_frame returns a frame controller")
check(len(profiles(ctrl)) == 12, "12 profiles for a single level frame (%d)"
      % len(profiles(ctrl)))
check(all(o.parent is not None for o in frames.members(ctrl)),
      "every member is parented into the frame")
check(all(o.alugen.fid == ctrl.alugen.frame.fid for o in frames.members(ctrl)),
      "every member carries the frame id")
lo, hi = bounds(profiles(ctrl))
size = (hi - lo) / MM
check(abs(size.x - 800) < 1e-3 and abs(size.y - 600) < 1e-3 and abs(size.z - 900) < 1e-3,
      "outer size exact: %.3f x %.3f x %.3f mm" % (size.x, size.y, size.z))
check(lengths(ctrl) == [520.0] * 4 + [720.0] * 4 + [900.0] * 4,
      "cut lengths: %s" % sorted(set(lengths(ctrl))))

print("\n=== Move one side, opposite stays ===")
x_lo_before = lo.x
r = bpy.ops.alugen.frame_resize(side='x_max', delta=100.0)
lo2, hi2 = bounds(profiles(ctrl))
size2 = (hi2 - lo2) / MM
check(r == {'FINISHED'}, "frame_resize runs")
check(abs(size2.x - 900) < 1e-3, "X grew by 100 mm: %.3f" % size2.x)
check(abs(lo2.x - x_lo_before) < 1e-6, "the -X side did not move (%.6f mm)"
      % ((lo2.x - x_lo_before) / MM))
check(abs(size2.y - 600) < 1e-3 and abs(size2.z - 900) < 1e-3, "Y and Z unchanged")
check(sorted(set(lengths(ctrl))) == [520.0, 820.0, 900.0],
      "X rails grew to 820 mm, Y rails stayed at 520 mm: %s" % sorted(set(lengths(ctrl))))

bpy.ops.alugen.frame_resize(side='z_max', delta=-200.0)
lo3, hi3 = bounds(profiles(ctrl))
check(abs((hi3 - lo3).z / MM - 700) < 1e-3, "Z shrank to 700 mm")
check(abs(lo3.z - lo2.z) < 1e-6, "the base did not move")
check(sorted(set(lengths(ctrl))) == [520.0, 700.0, 820.0],
      "posts shortened to 700 mm, rails untouched: %s" % sorted(set(lengths(ctrl))))

bpy.ops.alugen.frame_resize(side='y_min', delta=150.0)
lo4, hi4 = bounds(profiles(ctrl))
check(abs((hi4 - lo4).y / MM - 750) < 1e-3, "moving the -Y side outwards grows Y to 750 mm")
check(abs(hi4.y - hi3.y) < 1e-6, "the +Y side stayed")

print("\n=== Frame brackets follow the rails ===")
ctrl = make_frame()
rails = [o for o in profiles(ctrl) if abs(o.alugen.length - 720.0) < 1e-6]
brackets = [o for o in frames.members(ctrl) if o.alugen.kind == 'BRACKET']
check(len(brackets) == 16, "16 frame brackets on a single level frame (%d)" % len(brackets))


def bracket_gap(brk):
    """Smallest distance from a bracket corner to any rail end face."""
    best = 1e9
    for rail in profiles(ctrl):
        start, stop = builder.profile_span(rail)
        axis = builder.profile_axis_world(rail)
        for joint in (start, stop):
            d = abs((brk.matrix_world.translation - joint).dot(axis))
            radial = (brk.matrix_world.translation - joint - axis * (
                (brk.matrix_world.translation - joint).dot(axis))).length
            best = min(best, d + max(0.0, radial - 0.021))
    return best / MM


worst_before = max(bracket_gap(b) for b in brackets)
bpy.ops.alugen.frame_resize(side='x_max', delta=250.0)
brackets = [o for o in frames.members(ctrl) if o.alugen.kind == 'BRACKET']
worst_after = max(bracket_gap(b) for b in brackets)
check(worst_before < 1e-3 and worst_after < 1e-3,
      "brackets sit on the rail ends before (%.4f mm) and after the resize (%.4f mm)"
      % (worst_before, worst_after))

# 110 mm wide leaves 30 mm X rails: long enough to order, too short for a bracket
bpy.ops.alugen.frame_resize(side='x_max', delta=-940.0)
short = [o for o in profiles(ctrl) if abs(o.alugen.length - 30.0) < 1e-6]
brackets = [o for o in frames.members(ctrl) if o.alugen.kind == 'BRACKET']
check(len(short) == 4 and len(brackets) == 8,
      "rails too short for a bracket lose it: %d short rails, %d brackets left"
      % (len(short), len(brackets)))
check("too short for a bracket" in ctrl.alugen.frame.warning,
      "and the frame reports it: %r" % ctrl.alugen.frame.warning)

# The box cannot collapse past the profiles themselves
bpy.ops.alugen.frame_resize(side='x_max', delta=-200.0)
check(abs(ctrl.alugen.frame.size_x - 80.0) < 1e-3,
      "shrinking past the posts is clamped at %.1f mm" % ctrl.alugen.frame.size_x)
check(len(profiles(ctrl)) == 8,
      "the vanished X rails are removed (%d profiles left)" % len(profiles(ctrl)))
check("below the" in ctrl.alugen.frame.warning,
      "and that is reported too: %r" % ctrl.alugen.frame.warning)
ctrl = make_frame()

print("\n=== Frame follows its controller ===")
before = bounds(profiles(ctrl))[0]
ctrl.location = ctrl.location + Vector((1.0, 0.0, 0.0))
C.view_layer.update()
after = bounds(profiles(ctrl))[0]
check(abs((after - before).x - 1.0) < 1e-6, "moving the controller moves every member")
ctrl.location = ctrl.location - Vector((1.0, 0.0, 0.0))
C.view_layer.update()

print("\n=== Layout changes ===")
ctrl = make_frame(levels=1)
check(len(profiles(ctrl)) == 16, "one intermediate level adds four rails (%d)"
      % len(profiles(ctrl)))
ctrl.alugen.frame.levels = 2
check(len(profiles(ctrl)) == 20, "raising the level count adds rails (%d)"
      % len(profiles(ctrl)))
ctrl.alugen.frame.levels = 0
check(len(profiles(ctrl)) == 12, "lowering it removes them again (%d)"
      % len(profiles(ctrl)))
ctrl.alugen.frame.caps = False
caps = [o for o in frames.members(ctrl) if o.alugen.kind == 'CAP']
check(not caps, "turning caps off removes them (%d left)" % len(caps))
ctrl.alugen.frame.caps = True
caps = [o for o in bpy.data.objects if o.alugen.kind == 'CAP']
check(len(caps) == 8, "turning caps back on restores 8 caps (%d)" % len(caps))

print("\n=== Brackets keep their place ===")
ctrl = make_frame(x=800.0, y=600.0, z=900.0)
rail = sorted((o for o in profiles(ctrl) if abs(o.alugen.length - 720.0) < 1e-6),
              key=lambda o: o.name)[0]
for o in C.selected_objects:
    o.select_set(False)
rail.select_set(True)
C.view_layer.objects.active = rail
bpy.ops.alugen.add_bracket_on_profile(offset=650.0, rotation=90.0, spin=0.0)
free = [o for o in bpy.data.objects if o.alugen.has_mount][-1]
check(abs(free.alugen.mount_offset - 650.0) < 1e-6,
      "bracket placed at 650 mm on a 720 mm rail")

C.view_layer.objects.active = ctrl
bpy.ops.alugen.frame_resize(side='x_max', delta=-200.0)
host = mounting.host_of(free)
check(host is rail and abs(rail.alugen.length - 520.0) < 1e-6,
      "rail shortened to %.1f mm" % rail.alugen.length)
lo_r, hi_r = mounting.extent_on_host(free, rail)
check(lo_r > -1e-3 and hi_r < rail.alugen.length + 1e-3,
      "bracket stays on the rail (%.1f .. %.1f of %.1f mm)"
      % (lo_r, hi_r, rail.alugen.length))
check(free.alugen.mount_offset < 650.0, "bracket offset was pulled back to %.1f mm"
      % free.alugen.mount_offset)
check("moved by" in free.alugen.note, "the move is reported: %r" % free.alugen.note)

print("\n=== Warning when a part cannot fit ===")
reset()
s = C.scene.alugen
s.a, s.b, s.slot, s.length, s.axis, s.at_cursor = '40', '40', 'N8', 300.0, 'Z', False
bpy.ops.alugen.add_profile()
post = C.active_object
bpy.ops.alugen.add_bracket_on_profile(offset=100.0, rotation=0.0)
brk = [o for o in bpy.data.objects if o.alugen.has_mount][-1]
post.alugen.length = 30.0
check("does not fit" in brk.alugen.note,
      "shrinking below the bracket footprint warns: %r" % brk.alugen.note)
post.alugen.length = 300.0
check(brk.alugen.note == "", "growing the profile again clears the warning")

print("\n=== Fast length rebuild matches a full rebuild ===")
reset()
bpy.ops.alugen.add_profile()
prof = C.active_object
prof.alugen.length = 400.0
fast = [tuple(v.co) for v in prof.data.vertices]
builder.rebuild_profile(prof, allow_fast=False)
full = [tuple(v.co) for v in prof.data.vertices]
worst = max((Vector(a) - Vector(b)).length for a, b in zip(fast, full)) if fast else 1.0
check(len(fast) == len(full) and worst < 1e-9,
      "fast path is identical (%d verts, max deviation %.2e)" % (len(fast), worst))

print("\n=== Gizmos ===")
reset()
bpy.ops.alugen.add_profile()
prof = C.active_object
check(gizmos.ALUGEN_GGT_profile.poll(C), "length gizmo shows on a standalone profile")
check(not gizmos.ALUGEN_GGT_frame.poll(C), "frame gizmo stays hidden there")
prof.alugen.length_bu = 0.25
check(abs(prof.alugen.length - 250.0) < 1e-6,
      "dragging the length handle sets %.1f mm" % prof.alugen.length)

bpy.ops.alugen.add_bracket_on_profile(offset=100.0, rotation=0.0)
brk = [o for o in bpy.data.objects if o.alugen.has_mount][-1]
for o in C.selected_objects:
    o.select_set(False)
brk.select_set(True)
C.view_layer.objects.active = brk
check(gizmos.ALUGEN_GGT_mount.poll(C), "hardware gizmos show on a mounted bracket")
brk.alugen.mount_offset_bu = 0.05
check(abs(brk.alugen.mount_offset - 50.0) < 1e-6, "offset handle sets 50 mm")
corner_before = brk.matrix_world.translation.copy()
brk.alugen.mount_spin = math.radians(90.0)
check((brk.matrix_world.translation - corner_before).length < 1e-6,
      "spin dial keeps the corner in place")

ctrl = make_frame()
member = profiles(ctrl)[0]
for o in C.selected_objects:
    o.select_set(False)
member.select_set(True)
C.view_layer.objects.active = member
check(gizmos.ALUGEN_GGT_frame.poll(C), "frame gizmos show when a member is selected")
check(not gizmos.ALUGEN_GGT_profile.poll(C),
      "the length handle is hidden on frame members")
f = ctrl.alugen.frame
before_x = f.size_x
f.x_max = f.x_max + 0.05
check(abs(f.size_x - (before_x + 50.0)) < 1e-3,
      "dragging the +X face handle grows the frame to %.1f mm" % f.size_x)
C.scene.alugen.show_gizmos = False
check(not gizmos.ALUGEN_GGT_frame.poll(C), "gizmos can be switched off")
C.scene.alugen.show_gizmos = True

print("\n=== Parts list ===")
from alugen import bom  # noqa: E402
ctrl = make_frame(levels=1)
pl, pan, pa = bom.collect(C)
t = bom.totals(pl, pan, pa)
check(t['profile_count'] == 16, "parts list counts 16 profiles (%d)" % t['profile_count'])
check(all(r['part_id'] for r in pa), "every hardware row has a part id")
check(not any(o.alugen.is_part for o in bpy.data.objects if o.alugen.kind == 'FRAME'),
      "the controller itself is not a part")
issues = bom.check_scene(C)
check(len(issues) == 0, "validation is clean (%d)" % len(issues))
for i in issues[:5]:
    print("    ! " + i)

alugen.unregister()
print("\n==== RESULT: %d failures ====" % len(FAIL))
for f_ in FAIL:
    print("  FAIL  " + f_)
if FAIL:
    sys.exit(1)
