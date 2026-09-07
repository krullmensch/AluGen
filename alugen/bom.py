"""Parts list: collect, format, export and validate."""

import os

import bpy

from . import catalog


def _profile_key(obj):
    p = obj.alugen
    return (float(p.a), float(p.b), p.slot, round(p.length, 1))


def collect(context):
    """Return (profiles, panels, parts) as sorted lists of dicts."""
    profiles = {}
    panels = {}
    parts = {}
    for obj in context.scene.objects:
        p = obj.alugen
        if not p.is_part:
            continue
        if p.kind == 'PANEL':
            pan = p.panel
            key = (p.part_id, round(pan.width, 1), round(pan.depth, 1),
                   round(pan.thickness, 1))
            row = panels.setdefault(key, dict(part_id=p.part_id, name=p.part_name,
                                              width=pan.width, depth=pan.depth,
                                              thickness=pan.thickness,
                                              cutouts=pan.cutouts, qty=0,
                                              note=pan.warning))
            row['qty'] += 1
        elif p.kind == 'PROFILE':
            key = _profile_key(obj)
            row = profiles.setdefault(key, dict(a=key[0], b=key[1], slot=key[2],
                                                length=key[3], qty=0))
            row['qty'] += 1
        else:
            key = p.part_id or p.kind
            row = parts.setdefault(key, dict(part_id=p.part_id, name=p.part_name or p.kind,
                                             kind=p.kind, qty=0, note=p.note))
            row['qty'] += 1

    prof_list = sorted(profiles.values(), key=lambda r: (r['slot'], r['a'], r['b'], -r['length']))
    panel_list = sorted(panels.values(), key=lambda r: (-r['width'], -r['depth']))
    part_list = sorted(parts.values(), key=lambda r: (r['kind'], r['part_id'], r['name']))
    return prof_list, panel_list, part_list


def totals(prof_list, panel_list, part_list):
    return dict(cut_mm=sum(r['length'] * r['qty'] for r in prof_list),
                profile_count=sum(r['qty'] for r in prof_list),
                panel_count=sum(r['qty'] for r in panel_list),
                panel_area=sum(r['width'] * r['depth'] * r['qty'] for r in panel_list) / 1e6,
                part_count=sum(r['qty'] for r in part_list))


def slot_label(slot):
    return catalog.SLOT_SYSTEMS[slot]['label']


def as_text(context):
    prof, panel_rows, parts = collect(context)
    t = totals(prof, panel_rows, parts)
    L = []
    L.append("PARTS LIST - AluGen")
    L.append("File: %s" % (bpy.data.filepath or "(unsaved)"))
    L.append("Material: %s" % catalog.MATERIAL)
    L.append("")
    L.append("CUT LIST")
    L.append("%-5s %-8s %-8s %-9s %-12s" % ("Qty", "A (mm)", "B (mm)", "Slot", "Length (mm)"))
    if not prof:
        L.append("(none)")
    for r in prof:
        L.append("%-5d %-8g %-8g %-9s %-12.1f" %
                 (r['qty'], r['a'], r['b'], slot_label(r['slot']), r['length']))
    L.append("Total cut length: %.0f mm (%.2f m) in %d pieces"
             % (t['cut_mm'], t['cut_mm'] / 1000.0, t['profile_count']))
    L.append("")
    L.append("PANELS")
    if not panel_rows:
        L.append("(none)")
    for r in panel_rows:
        L.append("%-4d x %-28s %.1f x %.1f x %.1f mm%s"
                 % (r['qty'], r['name'].split(" panel")[0], r['width'], r['depth'],
                    r['thickness'],
                    ", %d cut-out(s)" % r['cutouts'] if r['cutouts'] else ""))
        if r['note']:
            L.append("         Note: %s" % r['note'])
    if panel_rows:
        L.append("Panel area: %.3f m2 in %d pieces" % (t['panel_area'], t['panel_count']))
    L.append("")
    L.append("HARDWARE")
    if not parts:
        L.append("(none)")
    for r in parts:
        L.append("%-4d x %-20s %s" % (r['qty'], r['part_id'] or "-", r['name']))
        if r['note']:
            L.append("         Note: %s" % r['note'])
    L.append("")
    L.append("Hardware total: %d pieces" % t['part_count'])
    return "\n".join(L)


def as_csv(context):
    prof, panel_rows, parts = collect(context)
    t = totals(prof, panel_rows, parts)
    rows = ["Group,Qty,A (mm),B (mm),Slot,Length (mm),Part id,Description,Note"]
    for r in prof:
        rows.append("Profile,%d,%g,%g,%s,%.1f,,\"%s\"," %
                    (r['qty'], r['a'], r['b'], slot_label(r['slot']), r['length'],
                     "Extrusion I-type %s" % catalog.MATERIAL))
    for r in panel_rows:
        rows.append("Panel,%d,%.1f,%.1f,%.1f mm thick,,%s,\"%s\",\"%s\"" %
                    (r['qty'], r['width'], r['depth'], r['thickness'], r['part_id'],
                     r['name'].replace('"', "'"), r['note'].replace('"', "'")))
    for r in parts:
        rows.append("Hardware,%d,,,,,%s,\"%s\",\"%s\"" %
                    (r['qty'], r['part_id'], r['name'].replace('"', "'"),
                     r['note'].replace('"', "'")))
    rows.append("")
    rows.append("Total,%d,,,,%.1f,,Cut length total," % (t['profile_count'], t['cut_mm']))
    return "\n".join(rows)


def check_scene(context):
    """Sanity check; returns a list of findings."""
    issues = []
    for obj in context.scene.objects:
        p = obj.alugen
        if not p.is_part:
            continue
        s = obj.scale
        if max(abs(s.x - 1.0), abs(s.y - 1.0), abs(s.z - 1.0)) > 1e-4:
            issues.append("%s: object is scaled (%.3f/%.3f/%.3f), dimensions are wrong. "
                          "Apply or reset the scale." % (obj.name, s.x, s.y, s.z))
        if p.kind == 'PROFILE':
            if p.length < catalog.LEN_MIN - 1e-6:
                issues.append("%s: length %.1f mm is below the %.0f mm minimum"
                              % (obj.name, p.length, catalog.LEN_MIN))
            if p.length > catalog.LEN_MAX + 1e-6:
                issues.append("%s: length %.1f mm is above the %.0f mm maximum"
                              % (obj.name, p.length, catalog.LEN_MAX))
            a, b = float(p.a), float(p.b)
            if p.slot == 'N5' and max(a, b) > 20.0:
                issues.append("%s: slot 5 on %gx%g is unusual, check slot 8"
                              % (obj.name, a, b))
            if p.slot == 'N8' and max(a, b) <= 20.0:
                issues.append("%s: slot 8 on %gx%g is unusual, check slot 5"
                              % (obj.name, a, b))
            if abs(p.length - round(p.length, 1)) > 1e-6:
                issues.append("%s: length %.4f mm, round it to 0.1 mm" % (obj.name, p.length))
        elif p.kind == 'PANEL':
            pan = p.panel
            if pan.thickness <= 0.0:
                issues.append("%s: panel thickness is not set" % obj.name)
            if pan.warning:
                issues.append("%s: %s" % (obj.name, pan.warning))
        elif p.note:
            issues.append("%s: %s" % (obj.name, p.note))
    return issues


class ALUGEN_OT_parts_export(bpy.types.Operator):
    bl_idname = "alugen.parts_export"
    bl_label = "Export parts list"
    bl_description = "Write the parts list as CSV and TXT"
    bl_options = {'REGISTER'}

    def execute(self, context):
        path = bpy.path.abspath(context.scene.alugen.bom_path)
        if not path:
            self.report({'ERROR'}, "No file path set")
            return {'CANCELLED'}
        base, ext = os.path.splitext(path)
        if ext.lower() != ".csv":
            base = path
        folder = os.path.dirname(base)
        if folder and not os.path.isdir(folder):
            self.report({'ERROR'}, "Folder does not exist: %s" % folder)
            return {'CANCELLED'}
        try:
            with open(base + ".csv", "w", encoding="utf-8-sig", newline="") as f:
                f.write(as_csv(context))
            with open(base + ".txt", "w", encoding="utf-8") as f:
                f.write(as_text(context))
        except OSError as exc:
            self.report({'ERROR'}, "Could not write file: %s" % exc)
            return {'CANCELLED'}
        self.report({'INFO'}, "Saved: %s.csv and %s.txt" % (base, base))
        return {'FINISHED'}


class ALUGEN_OT_parts_clipboard(bpy.types.Operator):
    bl_idname = "alugen.parts_clipboard"
    bl_label = "Copy parts list"
    bl_description = "Copy the parts list to the clipboard"
    bl_options = {'REGISTER'}

    def execute(self, context):
        context.window_manager.clipboard = as_text(context)
        self.report({'INFO'}, "Parts list copied")
        return {'FINISHED'}


class ALUGEN_OT_parts_text(bpy.types.Operator):
    bl_idname = "alugen.parts_text"
    bl_label = "Parts list as text block"
    bl_description = "Write the parts list into a Blender text block"
    bl_options = {'REGISTER'}

    def execute(self, context):
        name = "AluGen Parts List"
        txt = bpy.data.texts.get(name) or bpy.data.texts.new(name)
        txt.clear()
        txt.write(as_text(context))
        self.report({'INFO'}, "Text block '%s' updated" % name)
        return {'FINISHED'}


CLASSES = (ALUGEN_OT_parts_export, ALUGEN_OT_parts_clipboard, ALUGEN_OT_parts_text)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
