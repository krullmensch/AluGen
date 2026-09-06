"""Render the documentation images.

    blender --background --factory-startup --python scripts/make_docs_images.py
"""

import math
import os
import sys

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "docs", "images")
sys.path.insert(0, REPO)

import alugen  # noqa: E402
alugen.register()
from alugen import builder  # noqa: E402

C = bpy.context
MM = 0.001
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()


def render(name, ortho, loc, rot, res, flat=False):
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    C.scene.collection.objects.link(cam)
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = ortho
    cam.location = loc
    cam.rotation_euler = rot
    C.scene.camera = cam
    r = C.scene.render
    r.engine = 'BLENDER_WORKBENCH'
    r.resolution_x, r.resolution_y = res
    r.filepath = os.path.join(OUT, name)
    r.image_settings.file_format = 'PNG'
    sh = C.scene.display.shading
    if flat:
        sh.light = 'FLAT'
        sh.color_type = 'SINGLE'
        sh.single_color = (0.16, 0.17, 0.19)
        sh.show_cavity = False
    else:
        sh.light = 'STUDIO'
        sh.color_type = 'OBJECT'
        sh.show_cavity = True
    sh.show_object_outline = True
    C.scene.display.render_aa = '16'
    for o in C.scene.objects:
        if o.alugen.kind == 'BRACKET':
            o.color = (0.85, 0.55, 0.15, 1)
        elif o.alugen.kind == 'CAP':
            o.color = (0.09, 0.09, 0.10, 1)
        elif o.alugen.kind in {'TNUT', 'SCREW', 'CONNECTOR'}:
            o.color = (0.25, 0.45, 0.85, 1)
        elif o.alugen.is_part:
            o.color = (0.72, 0.73, 0.75, 1)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


# 1) cross sections
for (x, a, b, slot, cav) in [(-60, 20, 20, 'N5', False), (-10, 30, 30, 'N8', False),
                             (50, 40, 40, 'N8', True), (130, 40, 80, 'N8', True)]:
    builder.create_profile(C, a, b, slot, 20, 'Z', 'CENTER', cav, (x * MM, 0, 0))
render("cross-sections.png", 0.26, (0.035, 0, 0.2), (0, 0, 0), (1400, 520), flat=True)

# 2) full frame
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
s = C.scene.alugen
s.a, s.b, s.slot = '40', '40', 'N8'
s.frame_x, s.frame_y, s.frame_z = 800.0, 600.0, 900.0
s.frame_levels, s.frame_top, s.frame_bottom = 1, True, True
s.frame_brackets = s.frame_caps = True
bpy.ops.alugen.build_frame()
render("frame.png", 1.9, (1.42, -1.69, 1.62), (math.radians(62), 0, math.radians(40)), (1200, 900))

# 3) corner detail
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
s.frame_x, s.frame_y, s.frame_z = 400.0, 300.0, 400.0
s.frame_levels = 0
bpy.ops.alugen.build_frame()
post = [o for o in C.scene.objects
        if o.alugen.kind == 'PROFILE' and abs(o.alugen.length - 400) < 1e-6][0]
for o in C.selected_objects:
    o.select_set(False)
post.select_set(True)
C.view_layer.objects.active = post
bpy.ops.alugen.add_tnut(face='X-', offset=200.0)
bpy.ops.alugen.add_connector(kind='BUTT', offset=250.0, face='X-')
render("joint-detail.png", 0.30, (0.55, -0.55, 0.62),
       (math.radians(58), 0, math.radians(45)), (1200, 900))

# 4) brackets placed freely on posts, carrying a panel
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
X, Y, Z, A = 400.0, 300.0, 400.0, 40.0
s.frame_x, s.frame_y, s.frame_z = X, Y, Z
s.frame_levels, s.frame_top, s.frame_bottom = 0, False, True
bpy.ops.alugen.build_frame()

panel_t = 18.0
corner_z = Z - panel_t
posts = [o for o in C.scene.objects
         if o.alugen.kind == 'PROFILE' and abs(o.alugen.length - Z) < 1e-6]
for post in posts:
    for o in C.selected_objects:
        o.select_set(False)
    post.select_set(True)
    C.view_layer.objects.active = post
    inward = 180.0 if post.matrix_world.translation.x > 0 else 0.0
    bpy.ops.alugen.add_bracket_on_profile(offset=corner_z, rotation=inward, spin=180.0)

bpy.ops.mesh.primitive_cube_add(size=2.0)
panel = C.active_object
panel.name = "Panel (not an AluGen part)"
panel.scale = ((X * 0.5 - A) * MM, (Y * 0.5 - A) * MM, panel_t * 0.5 * MM)
panel.location = (0.0, 0.0, (corner_z + panel_t * 0.5) * MM)
panel.color = (0.55, 0.36, 0.18, 1.0)
render("free-brackets.png", 0.95, (0.75, -0.85, 0.72),
       (math.radians(66), 0, math.radians(41)), (1200, 900))


# 5) the same bracket spun in place on one face
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
s.a, s.b, s.slot, s.length, s.axis = '40', '40', 'N8', 420.0, 'Z'
s.at_cursor = False
bpy.ops.alugen.add_profile()
column = C.active_object
for i, sp in enumerate((0.0, 90.0, 180.0, 270.0)):
    for o in C.selected_objects:
        o.select_set(False)
    column.select_set(True)
    C.view_layer.objects.active = column
    bpy.ops.alugen.add_bracket_on_profile(offset=60.0 + i * 100.0, rotation=0.0, spin=sp)
render("bracket-spin.png", 0.55, (0.63, -0.43, 0.46),
       (math.radians(72), 0, math.radians(56)), (900, 1000))

print("IMAGES DONE")
