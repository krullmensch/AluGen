"""Headless tests for panels: fit, height, cut-outs and support brackets.

    blender --background --factory-startup --python tests/test_panels.py
"""

import math
import os
import sys

import bmesh
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

from alugen import bom, frames, panels  # noqa: E402

C = bpy.context


def reset():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def make_frame(x=800.0, y=600.0, z=900.0, levels=0):
    reset()
    s = C.scene.alugen
    s.a, s.b, s.slot = '40', '40', 'N8'
    s.frame_x, s.frame_y, s.frame_z = x, y, z
    s.frame_levels, s.frame_top, s.frame_bottom = levels, True, True
    s.frame_brackets = s.frame_caps = True
    bpy.ops.alugen.build_frame()
    return C.active_object


def volume(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    v = bm.calc_volume(signed=True)
    open_edges = len([e for e in bm.edges if len(e.link_faces) != 2])
    bm.free()
    return v / MM ** 3, open_edges


def world_z(obj):
    return obj.matrix_world.translation.z / MM


print("\n=== Panel on top of a shelf level, cut around the posts ===")
ctrl = make_frame(levels=1)
bpy.ops.alugen.add_panel(material='PLYWOOD', mode='ON_TOP', fit='OUTER',
                         level='MID_1', supports=0)
panel = C.active_object
p = panel.alugen.panel
a = 40.0
c, nc = p.clearance, p.notch_clearance
check(panels.is_panel(panel), "add_panel creates a panel part")
check(abs(p.width - (800.0 - 2 * c)) < 1e-3 and abs(p.depth - (600.0 - 2 * c)) < 1e-3,
      "outer fit sizes it to %.1f x %.1f mm" % (p.width, p.depth))
check(p.cutouts == 4, "four posts pass through it, %d cut-outs" % p.cutouts)

notch = (a + nc - c) ** 2
expect_area = p.width * p.depth - 4 * notch
vol, open_edges = volume(panel)
check(open_edges == 0, "panel mesh is watertight")
check(abs(vol / p.thickness - expect_area) < 1.0,
      "area matches outline minus cut-outs: %.1f mm2, expected %.1f mm2"
      % (vol / p.thickness, expect_area))

f = ctrl.alugen.frame
mid_top = (f.z_min / MM) + (f.z_max - f.z_min) / MM * 0.5 + a * 0.5
check(abs(world_z(panel) - mid_top) < 1e-3,
      "it rests on top of the mid rails at %.1f mm" % world_z(panel))

posts = [o for o in frames.members(ctrl) if o.alugen.role == frames.ROLE_POST]
inside = 0
for post in posts:
    inv = post.matrix_world.inverted()
    for v in panel.data.vertices:
        q = inv @ (panel.matrix_world @ v.co) / MM
        if abs(q.x) < a * 0.5 - 1e-6 and abs(q.y) < a * 0.5 - 1e-6:
            inside += 1
check(inside == 0, "no panel vertex sits inside a post (%d)" % inside)

print("\n=== The panel follows the frame ===")
C.view_layer.objects.active = ctrl
bpy.ops.alugen.frame_resize(side='x_max', delta=100.0)
C.view_layer.update()
check(abs(p.width - (900.0 - 2 * c)) < 1e-3,
      "growing the frame grows the panel to %.1f mm" % p.width)
check(p.cutouts == 4, "still four cut-outs after the resize (%d)" % p.cutouts)
vol, _ = volume(panel)
check(abs(vol / p.thickness - (p.width * p.depth - 4 * notch)) < 1.0,
      "and the area follows: %.1f mm2" % (vol / p.thickness))

print("\n=== Inset panel with support brackets ===")
ctrl = make_frame()
bpy.ops.alugen.add_panel(material='MDF', mode='INSET', fit='INNER',
                         level='TOP', supports=1)
panel = C.active_object
p = panel.alugen.panel
C.view_layer.update()
f = ctrl.alugen.frame
top = f.z_max / MM
check(abs(world_z(panel) + p.thickness - top) < 1e-3,
      "inset: the panel top is flush with the frame at %.1f mm"
      % (world_z(panel) + p.thickness))
check(abs(p.width - (800.0 - 2 * 40.0 - 2 * c)) < 1e-3,
      "inner fit drops it between the rails: %.1f mm" % p.width)
check(p.cutouts == 0, "no cut-outs needed between the rails (%d)" % p.cutouts)

sup = panels.supports_of(panel)
check(len(sup) == 4, "one support bracket per post (%d)" % len(sup))
tops = []
for brk in sup:
    zs = [(brk.matrix_world @ Vector(cor)).z / MM for cor in brk.bound_box]
    tops.append(max(zs))
check(max(abs(t - world_z(panel)) for t in tops) < 1e-3,
      "every bracket ends at the panel underside (%.3f mm off)"
      % max(abs(t - world_z(panel)) for t in tops))
check(all(b.parent in posts or b.parent.alugen.role == frames.ROLE_POST for b in sup),
      "supports are mounted on the posts")

print("\n=== A thicker panel moves its supports down ===")
before = min(tops)
was = p.thickness
p.thickness = 30.0
C.view_layer.update()
sup = panels.supports_of(panel)
after = max((brk.matrix_world @ Vector(cor)).z / MM
            for brk in sup for cor in brk.bound_box)
check(abs(world_z(panel) + 30.0 - top) < 1e-3,
      "the top stays flush after the thickness change")
check(abs((before - after) - (30.0 - was)) < 1e-3,
      "the brackets dropped by %.1f mm, expected %.1f mm" % (before - after, 30.0 - was))
check(abs(after - world_z(panel)) < 1e-3, "and still meet the underside")

bpy.ops.alugen.panel_supports(count=2)
check(len(panels.supports_of(panel)) == 8, "two per post gives 8 brackets (%d)"
      % len(panels.supports_of(panel)))
bpy.ops.alugen.panel_supports(count=0)
check(len(panels.supports_of(panel)) == 0, "and zero removes them again")

print("\n=== Panel in the slot ===")
ctrl = make_frame()
bpy.ops.alugen.add_panel(material='ACRYLIC', mode='IN_SLOT', level='BOTTOM', supports=0)
panel = C.active_object
p = panel.alugen.panel
C.view_layer.update()
spec_depth = 10.5
inner = 800.0 - 2 * 40.0 - 2 * p.clearance
check(abs(p.width - (inner + 2 * (spec_depth - 1.0))) < 0.2,
      "it reaches into the slot: %.1f mm wide, inner clear is %.1f mm" % (p.width, inner))
rail_centre = (f.z_min / MM) + 40.0 * 0.5
check(abs(world_z(panel) + p.thickness * 0.5 - rail_centre) < 1e-3,
      "and sits on the slot centre line at %.1f mm"
      % (world_z(panel) + p.thickness * 0.5))
p.thickness = 18.0
check("slot opening" in p.warning, "too thick for the slot is reported: %r" % p.warning)

print("\n=== Cut-outs can be switched off, with a warning ===")
ctrl = make_frame(levels=1)
bpy.ops.alugen.add_panel(material='PLYWOOD', mode='ON_TOP', fit='OUTER',
                         level='MID_1', supports=0)
panel = C.active_object
p = panel.alugen.panel
p.notch = False
check(p.cutouts == 0 and "without a cut-out" in p.warning,
      "switching cut-outs off warns: %r" % p.warning)
p.notch = True
check(p.cutouts == 4 and p.warning == "", "switching them back on clears it")

print("\n=== Free panel without a frame ===")
reset()
s = C.scene.alugen
s.a, s.b, s.slot, s.length, s.axis, s.at_cursor = '40', '40', 'N8', 500.0, 'Z', False
bpy.ops.alugen.add_profile()
bpy.ops.alugen.add_panel(material='ALU_SHEET', fit='CUSTOM', supports=0, at_cursor=False)
panel = C.active_object
p = panel.alugen.panel
with_frame = frames.controller_for(panel)
check(with_frame is None, "a free panel has no frame")
p.width, p.depth, p.z = 300.0, 300.0, 0.0
panel.matrix_world.translation = Vector((0.0, 0.0, 0.2))
bpy.ops.alugen.panel_update()
C.view_layer.update()
check(p.cutouts == 1, "the profile it sits on is cut out (%d)" % p.cutouts)
vol, open_edges = volume(panel)
check(open_edges == 0, "free panel mesh is watertight")

print("\n=== Parts list ===")
ctrl = make_frame(levels=1)
bpy.ops.alugen.add_panel(material='PLYWOOD', mode='ON_TOP', fit='OUTER',
                         level='MID_1', supports=1)
bpy.ops.alugen.add_panel(material='MDF', mode='INSET', fit='INNER',
                         level='TOP', supports=0)
prof, panel_rows, parts = bom.collect(C)
t = bom.totals(prof, panel_rows, parts)
print(bom.as_text(C))
check(t['panel_count'] == 2, "two panels in the list (%d)" % t['panel_count'])
check(t['panel_area'] > 0.5, "panel area %.3f m2" % t['panel_area'])
check(any("Plywood" in r['name'] for r in panel_rows), "material is named in the list")
check(any("cut-out" in r['name'] for r in panel_rows), "cut-outs are noted in the list")
csv = bom.as_csv(C)
check("Panel," in csv, "CSV has a panel group")
issues = bom.check_scene(C)
check(len(issues) == 0, "validation is clean (%d)" % len(issues))
for i in issues[:5]:
    print("    ! " + i)

from alugen import frames as _frames  # noqa: E402


def rail_brackets(ctrl):
    return [o for o in _frames.members(ctrl) if o.alugen.kind == 'BRACKET']


def facing_up(brk):
    """True when the mounting face of the bracket points up."""
    return (brk.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).z > 0.5


print("\n=== A panel pushes the corner brackets out of the way ===")
ctrl = make_frame(levels=1)
before = rail_brackets(ctrl)
mid_up = [b for b in before
          if facing_up(b) and abs(b.matrix_world.translation.z / MM - 450.0) < 25.0]
check(len(mid_up) == 8, "the mid level starts with 8 brackets facing up (%d)" % len(mid_up))

bpy.ops.alugen.add_panel(material='PLYWOOD', mode='ON_TOP', fit='OUTER',
                         level='MID_1', supports=0)
panel = C.active_object
C.view_layer.update()
after = rail_brackets(ctrl)
mid = [b for b in after if abs(b.matrix_world.translation.z / MM - 450.0) < 45.0]
check(len(after) == len(before), "no bracket was lost (%d)" % len(after))
check(all(not facing_up(b) for b in mid),
      "every mid bracket now sits under its rail (%d of %d still up)"
      % (sum(1 for b in mid if facing_up(b)), len(mid)))
worst = max(panels.blocked_area(b, panel) for b in after)
check(worst < panels.BLOCK_AREA,
      "no bracket runs into the panel any more (worst %.2f mm2)" % worst)

print("\n=== Squeezed from both sides the bracket is dropped ===")
# A second panel just below the level: it does not reach the rail, so it has no
# cut-out there and the bracket that moved down runs straight into it.
bpy.ops.alugen.add_panel(material='MDF', mode='ON_TOP', fit='OUTER', level='CUSTOM',
                         thickness=30.0, supports=0)
under = C.active_object
under.alugen.panel.z = 380.0
C.view_layer.update()
left = rail_brackets(ctrl)
check(len(left) < len(after), "brackets with no room were removed (%d left of %d)"
      % (len(left), len(after)))
check("was removed" in ctrl.alugen.frame.warning or
      any("removed" in o.alugen.panel.warning for o in panels.panels_of_frame(ctrl)),
      "and it is reported")
bpy.data.objects.remove(under, do_unlink=True)
C.view_layer.objects.active = ctrl
bpy.ops.alugen.frame_update()
check(len(rail_brackets(ctrl)) == len(before),
      "removing that panel brings the brackets back (%d)" % len(rail_brackets(ctrl)))

print("\n=== A bracket placed by hand moves to the other face ===")
ctrl = make_frame(levels=1)
mid_z = 450.0  # frame is 900 tall with one intermediate level
rails_mid = sorted((o for o in _frames.members(ctrl)
                    if o.alugen.role == _frames.ROLE_RAIL and o.alugen.kind == 'PROFILE'),
                   key=lambda o: abs(o.matrix_world.translation.z / MM - mid_z))
check(bool(rails_mid) and abs(rails_mid[0].matrix_world.translation.z / MM - mid_z) < 1.0,
      "found a rail at the intermediate level")
rail = rails_mid[0]
for o in C.selected_objects:
    o.select_set(False)
rail.select_set(True)
C.view_layer.objects.active = rail
bpy.ops.alugen.add_bracket_on_profile(offset=300.0, rotation=0.0, spin=0.0)
manual = [o for o in C.scene.objects
          if o.alugen.has_mount and not o.alugen.support_pid and o.parent is rail][-1]
# Which rotation points at the sky depends on whether this is an X or a Y rail
for deg in (0.0, 90.0, 180.0, 270.0):
    manual.alugen.mount_rotation = math.radians(deg)
    C.view_layer.update()
    if facing_up(manual):
        break
rot_before = manual.alugen.mount_rotation
check(facing_up(manual), "it starts on the upper face of the rail")

for o in C.selected_objects:
    o.select_set(False)
ctrl.select_set(True)
C.view_layer.objects.active = ctrl
bpy.ops.alugen.add_panel(material='PLYWOOD', mode='ON_TOP', fit='OUTER',
                         level='MID_1', supports=0)
panel = C.active_object
C.view_layer.update()
check(manual.name in bpy.data.objects, "a hand placed bracket is never deleted")
check(not facing_up(manual), "it moved to the underside of the rail")
check(abs(abs(manual.alugen.mount_rotation - rot_before) - math.pi) < 1e-6,
      "by half a turn around the profile axis")
check(panels.blocked_area(manual, panel) < panels.BLOCK_AREA,
      "and it is clear of the panel (%.2f mm2)" % panels.blocked_area(manual, panel))

print("\n=== The check can be switched off ===")
ctrl = make_frame(levels=1)
ctrl.alugen.frame.bracket_avoid_panels = False
bpy.ops.alugen.add_panel(material='PLYWOOD', mode='ON_TOP', fit='OUTER',
                         level='MID_1', supports=0)
panel = C.active_object
C.view_layer.update()
mid = [b for b in rail_brackets(ctrl)
       if abs(b.matrix_world.translation.z / MM - 450.0) < 45.0]
check(any(facing_up(b) for b in mid), "with the option off the brackets stay put")

alugen.unregister()
print("\n==== RESULT: %d failures ====" % len(FAIL))
for f_ in FAIL:
    print("  FAIL  " + f_)
if FAIL:
    sys.exit(1)
