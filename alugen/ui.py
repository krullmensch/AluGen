"""Panels in the 3D viewport sidebar (N panel, tab "AluGen")."""

import bpy

from . import bom, catalog


class _Base:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "AluGen"


class ALUGEN_PT_new(_Base, bpy.types.Panel):
    bl_label = "Add profile"
    bl_idname = "ALUGEN_PT_new"

    def draw(self, context):
        s = context.scene.alugen
        lay = self.layout
        lay.operator("alugen.setup_scene", icon='SETTINGS')
        col = lay.column(align=True)
        row = col.row(align=True)
        row.prop(s, "a")
        row.prop(s, "b")
        col.prop(s, "slot")
        col.prop(s, "length")
        row = col.row(align=True)
        row.prop(s, "axis", expand=True)
        col.prop(s, "origin_mode")
        col.prop(s, "corner_cavity")
        col.prop(s, "at_cursor")
        lay.operator("alugen.add_profile", icon='ADD')
        lay.operator("alugen.array", icon='MOD_ARRAY')

        info = lay.box().column(align=True)
        info.scale_y = 0.8
        info.label(text="Cut range %.0f - %.0f mm" % (catalog.LEN_MIN, catalog.LEN_MAX))


class ALUGEN_PT_edit(_Base, bpy.types.Panel):
    bl_label = "Edit selection"
    bl_idname = "ALUGEN_PT_edit"

    def draw(self, context):
        lay = self.layout
        obj = context.active_object
        if obj is None or not obj.alugen.is_part:
            lay.label(text="No AluGen part selected", icon='INFO')
            return
        p = obj.alugen
        if p.kind == 'PROFILE':
            col = lay.column(align=True)
            row = col.row(align=True)
            row.prop(p, "a")
            row.prop(p, "b")
            col.prop(p, "slot")
            col.prop(p, "length")
            col.prop(p, "origin_mode")
            col.prop(p, "corner_cavity")
            sub = lay.column(align=True)
            sub.prop(p, "arc_segs")
            sub.prop(p, "bore_segs")
        else:
            box = lay.box().column(align=True)
            box.label(text=p.part_name or p.kind)
            box.label(text="Part id: %s" % (p.part_id or "-"))
            if p.note:
                box.label(text=p.note, icon='ERROR')


class ALUGEN_PT_connect(_Base, bpy.types.Panel):
    bl_label = "Join"
    bl_idname = "ALUGEN_PT_connect"

    def draw(self, context):
        lay = self.layout
        lay.label(text="Last selected is active and moves")
        lay.operator("alugen.snap_end", icon='SNAP_ON')
        lay.operator("alugen.attach", text="Perpendicular on face",
                     icon='EMPTY_ARROWS').mode = 'PERP'
        lay.operator("alugen.attach", text="Parallel to face",
                     icon='MOD_ARRAY').mode = 'PARALLEL'
        lay.operator("alugen.fit_length", icon='DRIVER_DISTANCE')


class ALUGEN_PT_parts(_Base, bpy.types.Panel):
    bl_label = "Hardware"
    bl_idname = "ALUGEN_PT_parts"

    def draw(self, context):
        lay = self.layout
        lay.operator("alugen.add_caps", icon='MESH_PLANE')
        lay.operator("alugen.add_bracket", icon='MOD_BEVEL')
        lay.operator("alugen.add_bracket_on_profile", icon='EMPTY_AXIS')
        lay.operator("alugen.add_tnut", icon='MESH_CUBE')
        lay.operator("alugen.add_connector", icon='LINKED')


class ALUGEN_PT_frame(_Base, bpy.types.Panel):
    bl_label = "Frame generator"
    bl_idname = "ALUGEN_PT_frame"

    def draw(self, context):
        s = context.scene.alugen
        lay = self.layout
        col = lay.column(align=True)
        col.prop(s, "frame_x")
        col.prop(s, "frame_y")
        col.prop(s, "frame_z")
        col = lay.column(align=True)
        col.prop(s, "frame_bottom")
        col.prop(s, "frame_top")
        col.prop(s, "frame_levels")
        col.prop(s, "frame_brackets")
        col.prop(s, "frame_caps")
        lay.label(text="Profile: %s x %s, %s"
                       % (s.a, s.b, catalog.SLOT_SYSTEMS[s.slot]['label']))
        a, b = float(s.a), float(s.b)
        n_lvl = (1 if s.frame_bottom else 0) + (1 if s.frame_top else 0) + s.frame_levels
        box = lay.box().column(align=True)
        box.scale_y = 0.8
        box.label(text="Cut list:")
        box.label(text="4 x post     %.1f mm" % s.frame_z)
        box.label(text="%d x X rail   %.1f mm" % (2 * n_lvl, s.frame_x - 2 * a))
        box.label(text="%d x Y rail   %.1f mm" % (2 * n_lvl, s.frame_y - 2 * b))
        lay.operator("alugen.build_frame", icon='MESH_CUBE')


class ALUGEN_PT_bom(_Base, bpy.types.Panel):
    bl_label = "Parts list"
    bl_idname = "ALUGEN_PT_bom"

    def draw(self, context):
        lay = self.layout
        prof, parts = bom.collect(context)
        t = bom.totals(prof, parts)
        box = lay.box().column(align=True)
        box.scale_y = 0.8
        if not prof:
            box.label(text="No profiles in the scene yet")
        for r in prof:
            box.label(text="%d x  %gx%g %s   L = %.1f mm"
                           % (r['qty'], r['a'], r['b'], bom.slot_label(r['slot']), r['length']))
        if prof:
            box.label(text="Total cut length: %.2f m" % (t['cut_mm'] / 1000.0))
        if parts:
            box2 = lay.box().column(align=True)
            box2.scale_y = 0.8
            for r in parts:
                box2.label(text="%d x  %s" % (r['qty'], r['part_id'] or r['name'][:28]))
            box2.label(text="Hardware: %d pieces" % t['part_count'])
        lay.prop(context.scene.alugen, "bom_path")
        row = lay.row(align=True)
        row.operator("alugen.parts_export", icon='EXPORT')
        row.operator("alugen.parts_clipboard", text="", icon='COPYDOWN')
        lay.operator("alugen.parts_text", icon='TEXT')
        lay.operator("alugen.check", icon='CHECKMARK')


CLASSES = (ALUGEN_PT_new, ALUGEN_PT_edit, ALUGEN_PT_connect,
           ALUGEN_PT_parts, ALUGEN_PT_frame, ALUGEN_PT_bom)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
