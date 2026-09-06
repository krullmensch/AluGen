"""Headless test suite for the AluGen add-on.

Run with:
    blender --background --factory-startup --python tests/test_alugen.py
"""

import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

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

C = bpy.context
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

from alugen import builder, geometry, bom  # noqa: E402


def mesh_stats(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    nonmani = [e for e in bm.edges if len(e.link_faces) != 2]
    zero = [f for f in bm.faces if f.calc_area() < 1e-14]
    vol = bm.calc_volume(signed=True)
    bm.free()
    return len(nonmani), len(zero), vol


def seg_int(p1, p2, p3, p4):
    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2 = cr(p3, p4, p1), cr(p3, p4, p2)
    d3, d4 = cr(p1, p2, p3), cr(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


print("\n=== Cross-section is self-intersection free ===")
for (a, b, slot) in [(20, 20, 'N5'), (20, 40, 'N5'), (30, 30, 'N8'), (40, 40, 'N8'),
                     (40, 80, 'N8'), (80, 80, 'N8'), (20, 20, 'N8'), (30, 60, 'N8'),
                     (80, 40, 'N8')]:
    spec = geometry.resolve_spec(a, b, slot)
    outer, _holes = geometry.profile_section(spec, True, 5, 24)
    n = len(outer)
    bad = 0
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if seg_int(outer[i], outer[(i + 1) % n], outer[j], outer[(j + 1) % n]):
                bad += 1
    check(bad == 0, "%gx%g %s: clean contour (%d points, depth %.2f, chamber %.2f)"
          % (a, b, slot, n, spec['depth'], spec['chamber_w']))

print("\n=== Profile meshes ===")
for (a, b, slot, L, cav) in [(20, 20, 'N5', 300, False), (30, 30, 'N8', 450, False),
                             (40, 40, 'N8', 500, True), (40, 80, 'N8', 1000, True),
                             (20, 40, 'N5', 250, False), (80, 80, 'N8', 600, True)]:
    o = builder.create_profile(C, a, b, slot, L, 'Z', 'START', cav, (0, 0, 0))
    nm, zf, vol = mesh_stats(o)
    d = o.dimensions
    dims_ok = (abs(d.x - a * MM) < 1e-6 and abs(d.y - b * MM) < 1e-6
               and abs(d.z - L * MM) < 1e-6)
    check(nm == 0, "%gx%g %s: watertight (%d open edges)" % (a, b, slot, nm))
    check(zf == 0, "%gx%g %s: no zero-area faces" % (a, b, slot))
    check(vol > 0, "%gx%g %s: normals point outwards, %.1f mm2 section"
          % (a, b, slot, (vol / MM ** 3) / L))
    check(dims_ok, "%gx%g %s: exact outer size (%.4f/%.4f/%.4f mm)"
          % (a, b, slot, d.x / MM, d.y / MM, d.z / MM))
    bpy.data.objects.remove(o, do_unlink=True)

print("\n=== Hardware meshes ===")
for name, fn in (("End cap 40x40", lambda: geometry.end_cap_mesh(40, 40, 'N8')),
                 ("Bracket 40", lambda: geometry.bracket_mesh(40, 'N8')),
                 ("Bracket 20", lambda: geometry.bracket_mesh(20, 'N5')),
                 ("T-slot nut N8", lambda: geometry.tnut_mesh('N8')),
                 ("Screw N8", lambda: geometry.screw_mesh('N8', 25)),
                 ("Bar connector N8", lambda: geometry.bar_connector_mesh('N8')),
                 ("Cube connector", lambda: geometry.cube_connector_mesh(40))):
    v, f = fn()
    o = builder.new_object(C, name, v, f, 'ALU')
    _nm, zf, vol = mesh_stats(o)
    check(zf == 0 and vol > 0, "%s: %d verts, volume %.0f mm3" % (name, len(v), vol / MM ** 3))
    bpy.data.objects.remove(o, do_unlink=True)

print("\n=== Operators ===")
bpy.ops.alugen.setup_scene()
check(C.scene.unit_settings.length_unit == 'MILLIMETERS', "units set to millimetres")

s = C.scene.alugen
s.a, s.b, s.slot, s.length, s.axis = '40', '40', 'N8', 600.0, 'Z'
bpy.ops.alugen.add_profile()
post = C.active_object
check(post.alugen.kind == 'PROFILE' and abs(post.alugen.length - 600) < 1e-6,
      "add_profile: %s" % post.name)

s.axis, s.length = 'X', 400.0
bpy.ops.alugen.add_profile()
rail = C.active_object
post.select_set(True)
C.view_layer.objects.active = rail
r = bpy.ops.alugen.attach(mode='PERP', face='X+', offset=100.0)
st, _sp = builder.profile_span(rail)
check(r == {'FINISHED'} and abs(st.x - 0.020) < 1e-6 and abs(st.z - 0.100) < 1e-6,
      "attach perpendicular lands exactly (x=%.4f mm, z=%.4f mm)" % (st.x / MM, st.z / MM))

r = bpy.ops.alugen.add_bracket(variant=0)
br = [o for o in C.scene.objects if o.alugen.kind == 'BRACKET']
check(r == {'FINISHED'} and len(br) == 1 and br[0].alugen.part_id == 'BRACKET-N8-40',
      "add_bracket: %s" % (br[0].alugen.part_id if br else "-"))

rail.select_set(True)
post.select_set(False)
C.view_layer.objects.active = rail
bpy.ops.alugen.add_caps(ends='BOTH')
caps = [o for o in C.scene.objects if o.alugen.kind == 'CAP']
check(len(caps) == 2 and caps[0].alugen.part_id == 'CAP-N8-40x40',
      "end caps: %d, id %s" % (len(caps), caps[0].alugen.part_id if caps else "-"))

old = [tuple(c.matrix_world.translation) for c in caps]
rail.alugen.length = 500.0
C.view_layer.update()
check(old != [tuple(c.matrix_world.translation) for c in caps],
      "caps follow a length change")
check(abs(max(rail.dimensions) - 0.5) < 1e-6,
      "length rebuild is live: %.3f mm" % (max(rail.dimensions) / MM))

check(bpy.ops.alugen.add_tnut(face='Y+', offset=120.0) == {'FINISHED'}, "add_tnut")
check(bpy.ops.alugen.add_connector(kind='BAR', offset=50.0, face='Y-') == {'FINISHED'},
      "add_connector bar")
check(bpy.ops.alugen.add_connector(kind='BUTT', offset=10.0, face='X+') == {'FINISHED'},
      "add_connector butt joint")

for o in C.selected_objects:
    o.select_set(False)
rail.select_set(True)
C.view_layer.objects.active = rail
check(bpy.ops.alugen.array(count=2, spacing=150.0, direction='Z') == {'FINISHED'}, "array")

for o in C.selected_objects:
    o.select_set(False)
s.axis, s.length = 'X', 300.0
bpy.ops.alugen.add_profile()
p2 = C.active_object
rail.select_set(True)
p2.select_set(True)
C.view_layer.objects.active = p2
r = bpy.ops.alugen.snap_end(target_end='END')
st2, _ = builder.profile_span(p2)
_, rs = builder.profile_span(rail)
check(r == {'FINISHED'} and (st2 - rs).length < 1e-6,
      "snap_end meets the end face (deviation %.6f mm)" % ((st2 - rs).length / MM))

def aabb_early(o):
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
    return lo, hi


def overlap_early(A, B, tol=1e-5):
    v = 1.0
    for i in range(3):
        d = min(A[1][i], B[1][i]) - max(A[0][i], B[0][i]) - tol
        if d <= 0:
            return 0.0
        v *= d
    return v


def gap_early(A, B):
    return max(max(B[0][i] - A[1][i], A[0][i] - B[1][i]) for i in range(3))


print("\n=== Bracket on a single profile ===")
for o in list(C.scene.objects):
    bpy.data.objects.remove(o, do_unlink=True)
s.a, s.b, s.slot, s.length, s.axis = '40', '40', 'N8', 600.0, 'Z'
s.at_cursor = False
bpy.ops.alugen.add_profile()
solo = C.active_object

cases = [(0.0, 0.0, Vector((0.020, 0.0, 0.100))),
         (90.0, 0.0, Vector((0.0, 0.020, 0.100))),
         (180.0, 180.0, Vector((-0.020, 0.0, 0.100))),
         (270.0, 90.0, Vector((0.0, -0.020, 0.100)))]
for rot, spin, expect in cases:
    r = bpy.ops.alugen.add_bracket_on_profile(offset=100.0, rotation=rot, spin=spin)
    obj = [o for o in C.scene.objects if o.alugen.kind == 'BRACKET'][-1]
    d = (obj.matrix_world.translation - expect).length
    check(r == {'FINISHED'} and d < 1e-6,
          "free bracket at face %.0f deg, spin %.0f deg: corner off by %.6f mm"
          % (rot, spin, d / MM))

check(C.active_object is solo, "the profile stays active after placing a bracket")
r = bpy.ops.alugen.add_bracket_on_profile(offset=250.0, rotation=45.0, snap_faces=False)
free = [o for o in C.scene.objects if o.alugen.kind == 'BRACKET'][-1]
_r = geometry.resolve_spec(40, 40, 'N8')['corner_r']
_d45 = ((20 - _r) * 2 ** -0.5 * 2 + _r) * MM
expect45 = Vector((_d45 * 2 ** -0.5, _d45 * 2 ** -0.5, 0.25))
check(r == {'FINISHED'} and (free.matrix_world.translation - expect45).length < 1e-6,
      "free bracket at 45 deg sits on the profile corner")
check(free.parent is solo, "free bracket is parented to the profile")
check(free.alugen.part_id == 'BRACKET-N8-40', "free bracket part id: %s" % free.alugen.part_id)

r = bpy.ops.alugen.add_bracket_on_profile(offset=900.0)
check(r == {'FINISHED'}, "offset beyond the profile length still runs and warns")

# Spin turns the bracket in place: the corner stays, the mounted leg turns.
n_face = Vector((1.0, 0.0, 0.0))
axis_w = Vector((0.0, 0.0, 1.0))
corner_expect = Vector((0.020, 0.0, 0.300))
for spin in (0.0, 90.0, 180.0, 270.0, 37.5):
    snap = abs(spin % 90.0) < 1e-9
    r = bpy.ops.alugen.add_bracket_on_profile(offset=300.0, rotation=0.0, spin=spin,
                                              snap_spin=snap)
    obj = [o for o in C.scene.objects if o.alugen.kind == 'BRACKET'][-1]
    leg = (obj.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
    want = (Matrix.Rotation(math.radians(spin), 4, n_face).to_3x3() @ axis_w).normalized()
    mount = (obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    check(r == {'FINISHED'} and (leg - want).length < 1e-6,
          "spin %.1f deg turns the mounted leg (off by %.6f)" % (spin, (leg - want).length))
    check((obj.matrix_world.translation - corner_expect).length < 1e-6,
          "spin %.1f deg leaves the corner in place" % spin)
    check((mount - n_face).length < 1e-6,
          "spin %.1f deg keeps the bracket flat on the face" % spin)

r = bpy.ops.alugen.add_bracket_on_profile(offset=300.0, rotation=0.0, spin=44.0,
                                          snap_spin=True)
obj = [o for o in C.scene.objects if o.alugen.kind == 'BRACKET'][-1]
leg = (obj.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
check((leg - axis_w).length < 1e-6, "snap_spin rounds 44 deg down to 0 deg")
bpy.data.objects.remove(obj, do_unlink=True)

free_brs = [o for o in C.scene.objects if o.alugen.kind == 'BRACKET']


def rounded_box_sdf(x, y, ha, hb, r):
    qx, qy = abs(x) - (ha - r), abs(y) - (hb - r)
    outside = (max(qx, 0.0) ** 2 + max(qy, 0.0) ** 2) ** 0.5
    return outside + min(max(qx, qy), 0.0) - r


inv = solo.matrix_world.inverted()
worst = 1e9
for o in free_brs:
    for v in o.data.vertices:
        p = inv @ (o.matrix_world @ v.co)
        worst = min(worst, rounded_box_sdf(p.x / MM, p.y / MM, 20.0, 20.0, _r))
check(len(free_brs) == 11, "11 free brackets placed (%d)" % len(free_brs))
check(worst > -1e-4, "no free bracket vertex sits inside the profile hull "
                     "(closest %.4f mm)" % worst)
check(abs(worst) < 1e-4, "brackets sit flush on the surface (gap %.4f mm)" % worst)

_pl, _pa = bom.collect(C)
check(any(r["part_id"] == "BRACKET-N8-40" and r["qty"] == 11 for r in _pa),
            "parts list counts all 11 free brackets")


print("\n=== Frame ===")
for o in list(C.scene.objects):
    bpy.data.objects.remove(o, do_unlink=True)
s.a, s.b, s.slot = '40', '40', 'N8'
s.frame_x, s.frame_y, s.frame_z = 800.0, 600.0, 900.0
s.frame_levels, s.frame_top, s.frame_bottom = 1, True, True
s.frame_brackets = s.frame_caps = True
check(bpy.ops.alugen.build_frame() == {'FINISHED'}, "build_frame")
profs = [o for o in C.scene.objects if o.alugen.kind == 'PROFILE']
brs = [o for o in C.scene.objects if o.alugen.kind == 'BRACKET']
cps = [o for o in C.scene.objects if o.alugen.kind == 'CAP']
check(len(profs) == 16, "profiles: %d (expected 16)" % len(profs))
check(len(brs) == 24, "brackets: %d (expected 24)" % len(brs))
check(len(cps) == 8, "end caps: %d (expected 8)" % len(cps))

mn = Vector((1e9,) * 3)
mx = Vector((-1e9,) * 3)
for o in profs:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], w[i])
            mx[i] = max(mx[i], w[i])
size = (mx - mn) / MM
check(abs(size.x - 800) < 1e-3 and abs(size.y - 600) < 1e-3 and abs(size.z - 900) < 1e-3,
      "outer frame size exact: %.3f x %.3f x %.3f mm" % (size.x, size.y, size.z))
check(sorted(set(round(o.alugen.length, 2) for o in profs)) == [520.0, 720.0, 900.0],
      "cut lengths: %s" % sorted(set(round(o.alugen.length, 2) for o in profs)))


aabb, overlap, gap = aabb_early, overlap_early, gap_early
boxes = {o.name: aabb(o) for o in profs + brs}
pen = sum(1 for b in brs if any(overlap(boxes[b.name], boxes[p.name]) > 1e-12 for p in profs))
loose = sum(1 for b in brs
            if sum(1 for p in profs if gap(boxes[b.name], boxes[p.name]) < 1e-6) < 2)
check(pen == 0, "no bracket intersects a profile")
check(loose == 0, "every bracket touches two profiles")
prof_pen = sum(1 for i, p in enumerate(profs) for q in profs[i + 1:]
               if overlap(boxes[p.name], boxes[q.name]) > 1e-12)
check(prof_pen == 0, "no profile intersects another profile")

print("\n=== Parts list ===")
pl, pa = bom.collect(C)
t = bom.totals(pl, pa)
print(bom.as_text(C))
check(t['profile_count'] == 16, "parts list counts 16 profiles")
check(t['part_count'] == 32, "parts list counts 32 hardware items")
out = os.path.join(REPO, "tests", "_tmp_parts")
C.scene.alugen.bom_path = out + ".csv"
check(bpy.ops.alugen.parts_export() == {'FINISHED'} and os.path.exists(out + ".csv"),
      "CSV export")
for ext in (".csv", ".txt"):
    if os.path.exists(out + ext):
        os.remove(out + ext)
issues = bom.check_scene(C)
check(len(issues) == 0, "validation reports no issues (%d)" % len(issues))
for i in issues[:10]:
    print("    ! " + i)

print("\n=== unregister ===")
alugen.unregister()
print("  PASS  unregister")

print("\n==== RESULT: %d failures ====" % len(FAIL))
for f in FAIL:
    print("  FAIL  " + f)
if FAIL:
    sys.exit(1)
