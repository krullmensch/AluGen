"""Build the example scene shipped in examples/.

    blender --background --factory-startup --python scripts/make_example.py
"""

import os
import sys

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import alugen  # noqa: E402
alugen.register()
from alugen import bom  # noqa: E402

C = bpy.context
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.alugen.setup_scene()

s = C.scene.alugen
s.a, s.b, s.slot = '40', '40', 'N8'
s.frame_x, s.frame_y, s.frame_z = 800.0, 600.0, 900.0
s.frame_levels, s.frame_top, s.frame_bottom = 1, True, True
s.frame_brackets = s.frame_caps = True
bpy.ops.alugen.build_frame()
ctrl = C.active_object
bpy.ops.alugen.add_panel(material='MDF', mode='INSET', fit='INNER', level='TOP',
                         supports=1)
for o in C.selected_objects:
    o.select_set(False)
ctrl.select_set(True)
C.view_layer.objects.active = ctrl
bpy.ops.alugen.add_panel(material='PLYWOOD', mode='ON_TOP', fit='OUTER', level='MID_1',
                         supports=0)
s.length = 400.0
s.bom_path = "//parts_list.csv"

txt = bpy.data.texts.get("AluGen Parts List") or bpy.data.texts.new("AluGen Parts List")
txt.clear()
txt.write(bom.as_text(C))

out = os.path.join(REPO, "examples", "frame_800x600x900.blend")
bpy.ops.wm.save_as_mainfile(filepath=out)
print("SAVED", out, len(C.scene.objects), "objects")
