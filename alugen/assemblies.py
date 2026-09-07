"""Assembly generators. The frame itself lives in frames.py and stays editable."""

import bpy
from bpy.props import BoolProperty

from . import frames
from .geometry import MM


class ALUGEN_OT_build_frame(bpy.types.Operator):
    bl_idname = "alugen.build_frame"
    bl_label = "Build frame"
    bl_description = ("Build a cuboid frame with exact outer dimensions: posts, rails, "
                      "brackets and end caps. The frame stays editable afterwards")
    bl_options = {'REGISTER', 'UNDO'}

    at_cursor: BoolProperty(name="At 3D cursor", default=False)

    def execute(self, context):
        s = context.scene.alugen
        a, b = float(s.a), float(s.b)
        origin = (0.0, 0.0, 0.0)
        if self.at_cursor:
            c = context.scene.cursor.location
            origin = (c.x / MM, c.y / MM, c.z / MM)
        ctrl = frames.create_frame(context, s.frame_x, s.frame_y, s.frame_z, a, b, s.slot,
                                   s.frame_levels, s.frame_top, s.frame_bottom,
                                   s.frame_brackets, s.frame_caps, origin, s.corner_cavity)
        for w in ctrl.alugen.frame.warning.split(" | "):
            if w:
                self.report({'WARNING'}, w)
        for o in context.selected_objects:
            o.select_set(False)
        ctrl.select_set(True)
        context.view_layer.objects.active = ctrl
        members = frames.members(ctrl)
        profiles = [o for o in members if o.alugen.kind == 'PROFILE']
        self.report({'INFO'}, "Frame: %d profiles, %d parts in total"
                    % (len(profiles), len(members)))
        return {'FINISHED'}


CLASSES = (ALUGEN_OT_build_frame,)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
