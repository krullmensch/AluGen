"""Panels in the 3D viewport sidebar (N panel, tab "AluGen")."""

import bpy

from . import bom, catalog, frames, mounting, panels


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

        col = lay.column(align=True)
        col.prop(s, "show_gizmos", icon='GIZMO')
        sub = col.column(align=True)
        sub.enabled = s.show_gizmos
        sub.prop(s, "gizmo_hardware")


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
        if p.kind == 'FRAME':
            lay.label(text="Frame controller, see the Frame panel", icon='MOD_BUILD')
            return
        if p.kind == 'PANEL':
            pan = p.panel
            col = lay.column(align=True)
            col.prop(pan, "material")
            if pan.material == 'OTHER':
                col.prop(pan, "custom_material")
            col.prop(pan, "thickness")
            col.prop(pan, "mode")
            col.prop(pan, "fit")
            if pan.fit == 'CUSTOM':
                col.prop(pan, "width")
                col.prop(pan, "depth")
            col.prop(pan, "level")
            if pan.level == 'CUSTOM':
                col.prop(pan, "z")
            if pan.mode == 'IN_SLOT':
                col.prop(pan, "slot_engagement")
            col = lay.column(align=True)
            col.prop(pan, "clearance")
            col.prop(pan, "corner_radius")
            col.prop(pan, "notch")
            sub = col.column(align=True)
            sub.enabled = pan.notch
            sub.prop(pan, "notch_clearance")
            box = lay.box().column(align=True)
            box.scale_y = 0.8
            box.label(text="%.1f x %.1f x %.1f mm" % (pan.width, pan.depth, pan.thickness))
            box.label(text="Cut-outs: %d" % pan.cutouts)
            if pan.warning:
                for line in pan.warning.split(" | "):
                    box.label(text=line, icon='ERROR')
            row = lay.row(align=True)
            for n, text in ((0, "No supports"), (1, "1 per post"), (2, "2 per post")):
                op = row.operator("alugen.panel_supports", text=text,
                                  depress=(pan.supports == n))
                op.count = n
            lay.operator("alugen.panel_update", icon='FILE_REFRESH')
            return
        if p.kind == 'PROFILE':
            col = lay.column(align=True)
            row = col.row(align=True)
            row.prop(p, "a")
            row.prop(p, "b")
            col.prop(p, "slot")
            col.prop(p, "length")
            col.prop(p, "origin_mode")
            col.prop(p, "corner_cavity")
            if p.fid:
                col.enabled = False
                lay.label(text="Driven by its frame", icon='INFO')
            sub = lay.column(align=True)
            sub.prop(p, "arc_segs")
            sub.prop(p, "bore_segs")
        else:
            box = lay.box().column(align=True)
            box.label(text=p.part_name or p.kind)
            box.label(text="Part id: %s" % (p.part_id or "-"))
            if p.note:
                box.label(text=p.note, icon='ERROR')
            if p.has_mount:
                host = mounting.host_of(obj)
                col = lay.column(align=True)
                col.label(text="Mounted on %s" % (host.name if host else "-"))
                col.prop(p, "mount_offset")
                col.prop(p, "mount_rotation")
                col.prop(p, "mount_spin")
                col.prop(p, "mount_lateral")
                row = lay.row(align=True)
                row.prop(p, "mount_snap_faces", toggle=True)
                row.prop(p, "mount_snap_spin", toggle=True)


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
        lay.separator()
        col = lay.column(align=True)
        s = context.scene.alugen
        row = col.row(align=True)
        row.prop(s, "panel_material", text="")
        row.prop(s, "panel_thickness", text="")
        col.prop(s, "panel_mode", text="")
        col.prop(s, "panel_fit", text="")
        col.prop(s, "panel_level", text="")
        col.prop(s, "panel_supports")
        op = lay.operator("alugen.add_panel", icon='MESH_PLANE')
        op.material = s.panel_material
        op.mode = s.panel_mode
        op.fit = s.panel_fit
        op.level = s.panel_level
        op.thickness = s.panel_thickness
        op.supports = s.panel_supports


class ALUGEN_PT_frame_edit(_Base, bpy.types.Panel):
    bl_label = "Frame"
    bl_idname = "ALUGEN_PT_frame_edit"

    @classmethod
    def poll(cls, context):
        return frames.controller_for(context.active_object) is not None

    def draw(self, context):
        lay = self.layout
        ctrl = frames.controller_for(context.active_object)
        f = ctrl.alugen.frame
        lay.label(text=ctrl.name, icon='MOD_BUILD')

        col = lay.column(align=True)
        col.prop(f, "size_x", text="Width X (mm)")
        col.prop(f, "size_y", text="Depth Y (mm)")
        col.prop(f, "size_z", text="Height Z (mm)")

        box = lay.box().column(align=True)
        box.scale_y = 0.9
        box.label(text="Move one side, opposite stays:")
        for label, side in (("X", "x"), ("Y", "y"), ("Z", "z")):
            row = box.row(align=True)
            row.label(text=label)
            for suffix, text in (("_min", "min"), ("_max", "max")):
                sub = row.row(align=True)
                for delta, icon in ((-10.0, 'REMOVE'), (10.0, 'ADD')):
                    op = sub.operator("alugen.frame_resize", text="", icon=icon)
                    op.side = side + suffix
                    op.delta = delta

        col = lay.column(align=True)
        row = col.row(align=True)
        row.prop(f, "a")
        row.prop(f, "b")
        col.prop(f, "slot")
        col.prop(f, "levels")
        row = col.row(align=True)
        row.prop(f, "bottom", toggle=True)
        row.prop(f, "top", toggle=True)
        row = col.row(align=True)
        row.prop(f, "brackets", toggle=True)
        row.prop(f, "caps", toggle=True)

        a, b = float(f.a), float(f.b)
        cut = lay.box().column(align=True)
        cut.scale_y = 0.8
        cut.label(text="Cut list:")
        cut.label(text="4 x post     %.1f mm" % f.size_z)
        n_lvl = (1 if f.bottom else 0) + (1 if f.top else 0) + f.levels
        cut.label(text="%d x X rail   %.1f mm" % (2 * n_lvl, f.size_x - 2 * a))
        cut.label(text="%d x Y rail   %.1f mm" % (2 * n_lvl, f.size_y - 2 * b))

        if f.warning:
            warn = lay.box().column(align=True)
            warn.scale_y = 0.8
            for line in f.warning.split(" | "):
                warn.label(text=line, icon='ERROR')

        row = lay.row(align=True)
        row.operator("alugen.frame_update", icon='FILE_REFRESH')
        row.operator("alugen.frame_select", text="", icon='RESTRICT_SELECT_OFF')


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
        prof, panel_rows, parts = bom.collect(context)
        t = bom.totals(prof, panel_rows, parts)
        box = lay.box().column(align=True)
        box.scale_y = 0.8
        if not prof:
            box.label(text="No profiles in the scene yet")
        for r in prof:
            box.label(text="%d x  %gx%g %s   L = %.1f mm"
                           % (r['qty'], r['a'], r['b'], bom.slot_label(r['slot']), r['length']))
        if prof:
            box.label(text="Total cut length: %.2f m" % (t['cut_mm'] / 1000.0))
        if panel_rows:
            boxp = lay.box().column(align=True)
            boxp.scale_y = 0.8
            for r in panel_rows:
                boxp.label(text="%d x  %.0f x %.0f x %.0f mm%s"
                                % (r['qty'], r['width'], r['depth'], r['thickness'],
                                   "  (%d cut-outs)" % r['cutouts'] if r['cutouts'] else ""))
            boxp.label(text="Panel area: %.3f m2" % t['panel_area'])
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


CLASSES = (ALUGEN_PT_new, ALUGEN_PT_edit, ALUGEN_PT_connect, ALUGEN_PT_parts,
           ALUGEN_PT_frame_edit, ALUGEN_PT_frame, ALUGEN_PT_bom)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
