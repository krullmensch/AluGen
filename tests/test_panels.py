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

alugen.unregister()
print("\n==== RESULT: %d failures ====" % len(FAIL))
for f_ in FAIL:
    print("  FAIL  " + f_)
if FAIL:
    sys.exit(1)
