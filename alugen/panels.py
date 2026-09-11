"""Panels: worktops, shelves and covers made from wood, plastic or sheet metal.

A panel knows the frame it belongs to, so it keeps its size and height when the
frame changes. It cuts itself around any profile that passes through it, and it
can carry support brackets that follow its underside.
"""

import math
import uuid

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from mathutils import Matrix, Vector

from . import builder, catalog, frames, geometry, mounting, props
from .geometry import MM


# --------------------------------------------------------------------------
# Lookup and placement
# --------------------------------------------------------------------------

def is_panel(obj):
    return bool(obj) and obj.alugen.kind == 'PANEL'


def frame_of(obj):
    fid = obj.alugen.fid
    if not fid:
        return None
    for candidate in bpy.data.objects:
        if frames.is_controller(candidate) and candidate.alugen.frame.fid == fid:
            return candidate
    return None


def level_heights(f, level, custom_z):
    """(top of the rails, centre of the rails) at a frame level, in millimetres."""
    a = float(f.a)
    z0, z1 = f.z_min / MM, f.z_max / MM
    Z = z1 - z0
    if level == 'TOP':
        return z1, z1 - a * 0.5, ""
    if level == 'BOTTOM':
        return z0 + a, z0 + a * 0.5, ""
    if level.startswith('MID_'):
        k = int(level.split("_")[1])
        if k > f.levels:
            return z1, z1 - a * 0.5, ("Level %d does not exist, using the top level" % k)
        h = z0 + Z * k / (f.levels + 1.0)
        return h + a * 0.5, h, ""
    return custom_z, custom_z, ""


def panel_plan(obj):
    """Size and height of a panel; sizes in millimetres, height in frame space."""
    p = obj.alugen.panel
    ctrl = frame_of(obj)
    warn = []
    if ctrl is None:
        return dict(width=p.width, depth=p.depth, thickness=p.thickness,
                    centre=(0.0, 0.0), z_bottom=None, warnings=warn)

    f = ctrl.alugen.frame
    a, b = float(f.a), float(f.b)
    x0, x1 = f.x_min / MM, f.x_max / MM
    y0, y1 = f.y_min / MM, f.y_max / MM
    X, Y = x1 - x0, y1 - y0
    c = p.clearance

    top_z, mid_z, note = level_heights(f, p.level, p.z)
    if note:
        warn.append(note)

    if p.mode == 'IN_SLOT':
        spec = geometry.resolve_spec(a, b, f.slot)
        eng = p.slot_engagement or max(0.0, spec['depth'] - 1.0)
        width = X - 2.0 * a - 2.0 * c + 2.0 * eng
        depth = Y - 2.0 * b - 2.0 * c + 2.0 * eng
        z_bottom = mid_z - p.thickness * 0.5
        if p.thickness > spec['opening'] - 0.2:
            warn.append("Panel is %.1f mm thick, the slot opening is %.1f mm"
                        % (p.thickness, spec['opening']))
    else:
        if p.fit == 'OUTER':
            width, depth = X - 2.0 * c, Y - 2.0 * c
        elif p.fit == 'INNER':
            width, depth = X - 2.0 * a - 2.0 * c, Y - 2.0 * b - 2.0 * c
        else:
            width, depth = p.width, p.depth
        z_bottom = top_z if p.mode == 'ON_TOP' else top_z - p.thickness

    return dict(width=max(width, 1.0), depth=max(depth, 1.0), thickness=p.thickness,
                centre=((x0 + x1) * 0.5, (y0 + y1) * 0.5), z_bottom=z_bottom,
                warnings=warn)


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def cut_sources(obj):
    """Profiles that may pass through this panel."""
    ctrl = frame_of(obj)
    if ctrl is not None:
        pool = frames.members(ctrl)
    else:
        pool = [o for o in bpy.context.scene.objects
                if o.alugen.is_part and o.alugen.kind == 'PROFILE']
    return [o for o in pool if o.alugen.is_part and o.alugen.kind == 'PROFILE']


# Guard so a panel update and the conflict pass do not call each other
_RESOLVING = [False]

# A cut-out smaller than this is a rounding sliver where the panel edge and a
# profile meet, not a real notch.
MIN_CUTOUT_AREA = 1.0  # mm2


def cutouts_for(obj, width, depth, thickness, world=None):
    """Notch outlines in panel space for every profile passing through it.

    world is the panel matrix to measure against. It has to be passed in while a
    panel is being placed, because Blender only refreshes matrix_world on the
    next depsgraph update and the stale one would put the notches elsewhere.
    """
    p = obj.alugen.panel
    if not p.notch:
        return []
    outline = [(-width * 0.5, -depth * 0.5), (width * 0.5, -depth * 0.5),
               (width * 0.5, depth * 0.5), (-width * 0.5, depth * 0.5)]
    inv = (world if world is not None else obj.matrix_world).inverted()
    holes = []
    for src in cut_sources(obj):
        pts = [(inv @ (src.matrix_world @ Vector(c))) / MM for c in src.bound_box]
        zs = [q.z for q in pts]
        overlap = min(max(zs), thickness) - max(min(zs), 0.0)
        if overlap <= 0.01:
            continue
        hull = geometry.convex_hull([(q.x, q.y) for q in pts])
        if len(hull) < 3:
            continue
        grown = geometry.offset_convex(hull, p.notch_clearance)
        clipped = geometry.clip_to_convex(grown, outline)
        if len(clipped) < 3 or geometry.polygon_area(clipped) < MIN_CUTOUT_AREA:
            continue
        holes.append(geometry.orient(clipped, ccw=False))
    return holes


def panel_material(key):
    label, _thick, color = catalog.panel_material(key)
    name = "AluGen Panel %s" % label
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Roughness"].default_value = 0.6
            if color[3] < 0.9:
                bsdf.inputs["Alpha"].default_value = color[3]
                mat.blend_method = 'BLEND' if hasattr(mat, "blend_method") else mat.blend_method
        mat.diffuse_color = color
    return mat


def update_panel(obj, context=None):
    """Recompute size, height, cut-outs and supports of a panel."""
    if not is_panel(obj):
        return []
    context = context or bpy.context
    p = obj.alugen.panel
    plan = panel_plan(obj)
    warnings = list(plan['warnings'])

    ctrl = frame_of(obj)
    world = obj.matrix_world.copy()
    if ctrl is not None and plan['z_bottom'] is not None:
        cx, cy = plan['centre']
        basis = Matrix.Translation(Vector((cx * MM, cy * MM, plan['z_bottom'] * MM)))
        with props.busy():
            obj.parent = ctrl
            obj.matrix_parent_inverse = Matrix.Identity(4)
            obj.matrix_basis = basis
        world = ctrl.matrix_world @ basis
        if p.fit != 'CUSTOM' or p.mode == 'IN_SLOT':
            with props.busy():
                p.width, p.depth = plan['width'], plan['depth']

    width, depth, thickness = plan['width'], plan['depth'], plan['thickness']
    # The cut-outs are measured against the profiles around the panel, so their
    # world matrices have to be current: Blender only refreshes those on the
    # next depsgraph update, and a frame resize moves them right before this.
    try:
        context.view_layer.update()
    except (AttributeError, RuntimeError):
        pass
    holes = cutouts_for(obj, width, depth, thickness, world)
    outer = geometry.rounded_rect(0.0, 0.0, width, depth, p.corner_radius, segs=4)
    verts, faces = geometry.extrude_section([outer] + holes, 0.0, thickness)
    geometry.write_mesh(obj.data, verts, faces)
    mat = panel_material(p.material)
    obj.data.materials.clear()
    obj.data.materials.append(mat)

    pid, label = catalog.panel_part(p.material, p.custom_material, width, depth,
                                    thickness, len(holes))
    with props.busy():
        p.cutouts = len(holes)
        obj.alugen.part_id = pid
        obj.alugen.part_name = label
        obj.name = "Panel %.0fx%.0fx%.0f" % (width, depth, thickness)
        obj.data.name = obj.name

    if not p.notch:
        blocked = cutouts_for_check(obj, width, depth, thickness, world)
        if blocked:
            warnings.append("%d profile(s) run through the panel without a cut-out"
                            % blocked)

    warnings += sync_supports(obj, context)
    if ctrl is not None and ctrl.alugen.frame.bracket_avoid_panels and not _RESOLVING[0]:
        _RESOLVING[0] = True
        try:
            warnings += resolve_bracket_conflicts(ctrl, None, context)
        finally:
            _RESOLVING[0] = False
    with props.busy():
        p.warning = " | ".join(warnings)
        obj.alugen.note = p.warning
    return warnings


def cutouts_for_check(obj, width, depth, thickness, world=None):
    """How many profiles would need a cut-out, ignoring the notch switch."""
    p = obj.alugen.panel
    with props.busy():
        was, p.notch = p.notch, True
    try:
        return len(cutouts_for(obj, width, depth, thickness, world))
    finally:
        with props.busy():
            p.notch = was


# --------------------------------------------------------------------------
# Support brackets
# --------------------------------------------------------------------------

def supports_of(obj):
    pid = obj.alugen.panel.pid
    return [o for o in bpy.data.objects if o.alugen.support_pid and
            o.alugen.support_pid == pid]


def sync_supports(obj, context=None):
    """Place, move or remove the brackets that carry a panel."""
    context = context or bpy.context
    p = obj.alugen.panel
    existing = supports_of(obj)
    ctrl = frame_of(obj)
    if ctrl is None or p.supports == 0:
        for o in existing:
            bpy.data.objects.remove(o, do_unlink=True)
        return []

    f = ctrl.alugen.frame
    a, b = float(f.a), float(f.b)
    grid = min(a, b)
    plan = panel_plan(obj)
    z_bottom = plan['z_bottom']
    posts = [o for o in frames.members(ctrl)
             if o.alugen.role == frames.ROLE_POST and o.alugen.kind == 'PROFILE']
    x0, x1 = f.x_min / MM, f.x_max / MM
    y0, y1 = f.y_min / MM, f.y_max / MM
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5

    wanted = []
    for post in posts:
        loc = post.matrix_basis.translation / MM
        inward_x = -1.0 if loc.x > cx else 1.0
        inward_y = -1.0 if loc.y > cy else 1.0
        faces = [0.0 if inward_x > 0 else math.pi]
        if p.supports > 1:
            faces.append(math.pi * 0.5 if inward_y > 0 else -math.pi * 0.5)
        for rot in faces:
            wanted.append((post, rot))

    warnings = []
    for i, (post, rot) in enumerate(wanted):
        offset = z_bottom - post.matrix_basis.translation.z / MM
        if i < len(existing):
            brk = existing[i]
        else:
            verts, faces_ = geometry.bracket_mesh(grid, f.slot)
            brk = builder.new_object(context, "Bracket %s %g" % (f.slot, grid),
                                     verts, faces_, 'ALU')
            part_id, label, common = catalog.bracket_part(grid, f.slot)
            with props.busy():
                brk.alugen.is_part = True
                brk.alugen.kind = 'BRACKET'
                brk.alugen.part_id = part_id
                brk.alugen.part_name = label
                brk.alugen.note = "" if common else "Uncommon grid size, check availability"
                brk.alugen.support_pid = p.pid
                brk.alugen.fid = f.fid
        if brk.parent is not post:
            with props.busy():
                brk.parent = post
                brk.matrix_parent_inverse = Matrix.Identity(4)
        # The mounted leg runs down the post so the free leg carries the panel
        mounting.store_mount(brk, offset, rot, math.pi, 0.0, True, True, 'AUTO')
        note = mounting.fit_offset(brk, post)
        if note:
            warnings.append("Support bracket %s" % note)

    for extra in existing[len(wanted):]:
        bpy.data.objects.remove(extra, do_unlink=True)
    return warnings


# --------------------------------------------------------------------------
# Creation
# --------------------------------------------------------------------------

def create_panel(context, ctrl, material='PLYWOOD', mode='ON_TOP', fit='OUTER',
                 level='TOP', thickness=None, supports=0, location=(0.0, 0.0, 0.0)):
    label, default_t, _color = catalog.panel_material(material)
    me = bpy.data.meshes.new("Panel")
    obj = bpy.data.objects.new("Panel", me)
    builder.get_collection(context).objects.link(obj)
    obj.data.materials.append(panel_material(material))

    with props.busy():
        o = obj.alugen
        o.is_part = True
        o.kind = 'PANEL'
        p = o.panel
        p.pid = uuid.uuid4().hex
        p.material = material
        p.thickness = thickness if thickness else default_t
        p.mode = mode
        p.fit = fit if mode != 'IN_SLOT' else 'INNER'
        p.level = level
        p.supports = supports
        if ctrl is not None:
            o.fid = ctrl.alugen.frame.fid
        else:
            obj.matrix_world = Matrix.Translation(Vector(location) * MM)
    del label
    update_panel(obj, context)
    return obj


def update_panels_of_frame(ctrl, context=None):
    """Called after a frame changed: keep its panels in step."""
    fid = ctrl.alugen.frame.fid
    warnings = []
    for obj in list(bpy.data.objects):
        if is_panel(obj) and obj.alugen.fid == fid:
            warnings += ["%s: %s" % (obj.name, w) for w in update_panel(obj, context)]
    return warnings


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class ALUGEN_OT_add_panel(bpy.types.Operator):
    bl_idname = "alugen.add_panel"
    bl_label = "Add panel"
    bl_description = ("Add a worktop, shelf or cover panel. With a frame selected it "
                      "takes its size and height from the frame and cuts itself around "
                      "any profile that passes through it")
    bl_options = {'REGISTER', 'UNDO'}

    material: EnumProperty(name="Material", items=props.MATERIAL_ITEMS, default='PLYWOOD')
    mode: EnumProperty(name="Sits", items=props.PANEL_MODE_ITEMS, default='ON_TOP')
    fit: EnumProperty(name="Size", items=props.PANEL_FIT_ITEMS, default='OUTER')
    level: EnumProperty(name="Level", items=props.PANEL_LEVEL_ITEMS, default='TOP')
    thickness: FloatProperty(name="Thickness (mm)", default=0.0, min=0.0, max=200.0,
                             description="0 uses the default thickness of the material")
    supports: IntProperty(name="Support brackets per post", default=1, min=0, max=2)
    at_cursor: BoolProperty(name="At 3D cursor", default=True,
                            description="Only used when no frame is selected")

    def execute(self, context):
        ctrl = frames.controller_for(context.active_object)
        loc = (0.0, 0.0, 0.0)
        if ctrl is None and self.at_cursor:
            c = context.scene.cursor.location
            loc = (c.x / MM, c.y / MM, c.z / MM)
        obj = create_panel(context, ctrl, self.material, self.mode, self.fit,
                           self.level, self.thickness or None,
                           self.supports if ctrl is not None else 0, loc)
        for w in obj.alugen.panel.warning.split(" | "):
            if w:
                self.report({'WARNING'}, w)
        builder.select_only(context, obj)
        p = obj.alugen.panel
        self.report({'INFO'}, "Panel %.1f x %.1f x %.1f mm, %d cut-out(s)"
                    % (p.width, p.depth, p.thickness, p.cutouts))
        return {'FINISHED'}


class ALUGEN_OT_panel_update(bpy.types.Operator):
    bl_idname = "alugen.panel_update"
    bl_label = "Update panel"
    bl_description = "Recompute size, height, cut-outs and support brackets"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return is_panel(context.active_object)

    def execute(self, context):
        warnings = update_panel(context.active_object, context)
        for w in warnings:
            self.report({'WARNING'}, w)
        p = context.active_object.alugen.panel
        self.report({'INFO'}, "Panel %.1f x %.1f x %.1f mm, %d cut-out(s)"
                    % (p.width, p.depth, p.thickness, p.cutouts))
        return {'FINISHED'}


class ALUGEN_OT_panel_supports(bpy.types.Operator):
    bl_idname = "alugen.panel_supports"
    bl_label = "Support brackets"
    bl_description = "Add, move or remove the brackets that carry the panel"
    bl_options = {'REGISTER', 'UNDO'}

    count: IntProperty(name="Brackets per post", default=1, min=0, max=2)

    @classmethod
    def poll(cls, context):
        return is_panel(context.active_object) and frame_of(context.active_object)

    def execute(self, context):
        obj = context.active_object
        with props.busy():
            obj.alugen.panel.supports = self.count
        warnings = update_panel(obj, context)
        for w in warnings:
            self.report({'WARNING'}, w)
        self.report({'INFO'}, "%d support bracket(s)" % len(supports_of(obj)))
        return {'FINISHED'}


CLASSES = (ALUGEN_OT_add_panel, ALUGEN_OT_panel_update, ALUGEN_OT_panel_supports)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


# --------------------------------------------------------------------------
# Keeping hardware out of a panel
# --------------------------------------------------------------------------

# A part overlapping a panel by less than this is touching it, not blocking it.
BLOCK_AREA = 4.0      # mm2 of shared footprint
BLOCK_DEPTH = 0.05    # mm of shared thickness


def panels_of_frame(ctrl):
    fid = ctrl.alugen.frame.fid
    return [o for o in ctrl.children if is_panel(o) and o.alugen.fid == fid]


def blocked_area(obj, panel):
    """How much of obj sits inside the material of panel, in square millimetres.

    Measured in the panel's own space: the part has to share thickness with the
    panel and cover ground that was not cut away anyway.
    """
    p = panel.alugen.panel
    plan = panel_plan(panel)
    width, depth, thickness = plan['width'], plan['depth'], p.thickness
    inv = panel.matrix_world.inverted()
    pts = [(inv @ (obj.matrix_world @ Vector(c))) / MM for c in obj.bound_box]
    zs = [q.z for q in pts]
    if min(max(zs), thickness) - max(min(zs), 0.0) <= BLOCK_DEPTH:
        return 0.0
    hull = geometry.convex_hull([(q.x, q.y) for q in pts])
    if len(hull) < 3:
        return 0.0
    outline = [(-width * 0.5, -depth * 0.5), (width * 0.5, -depth * 0.5),
               (width * 0.5, depth * 0.5), (-width * 0.5, depth * 0.5)]
    inside = geometry.clip_to_convex(hull, outline)
    if len(inside) < 3:
        return 0.0
    area = geometry.polygon_area(inside)
    for notch in cutouts_for(panel, width, depth, thickness, panel.matrix_world):
        cut = geometry.clip_to_convex(hull, notch)
        if len(cut) >= 3:
            area -= geometry.polygon_area(cut)
    return max(0.0, area)


def blocking_panels(obj, panel_list):
    return [pan for pan in panel_list
            if obj.alugen.support_pid != pan.alugen.panel.pid
            and blocked_area(obj, pan) > BLOCK_AREA]


def bracket_map(ctrl):
    """Rebuild {(role, index): (object, layout spec)} for the frame brackets."""
    _posts, _rails, brackets, _warn = frames.layout(ctrl.alugen.frame)
    specs = {(s['role'], s['i']): s for s in brackets}
    found = {}
    for obj in frames.members(ctrl):
        key = (obj.alugen.role, obj.alugen.role_i)
        if obj.alugen.kind == 'BRACKET' and key in specs:
            found[key] = (obj, specs[key])
    return found


def resolve_bracket_conflicts(ctrl, placed_brackets=None, context=None):
    """Move brackets out of the panels of a frame.

    A generated corner bracket is flipped to the other side of its rail and
    dropped if it still does not fit. A bracket the user placed by hand is spun
    to the other side of its mounting face and otherwise only reported, because
    it is not ours to delete.
    """
    context = context or bpy.context
    panel_list = panels_of_frame(ctrl)
    if not panel_list:
        return []
    if placed_brackets is None:
        placed_brackets = bracket_map(ctrl)
    try:
        context.view_layer.update()
    except (AttributeError, RuntimeError):
        pass

    infos = []
    warnings = []
    for key, (obj, spec) in list(placed_brackets.items()):
        if obj.name not in bpy.data.objects:
            continue
        hit = blocking_panels(obj, panel_list)
        if not hit:
            continue
        # Same joint, other side of the rail
        joint = Vector(spec['joint'])
        n_a = -Vector(spec['n_a'])
        corner = joint + n_a * (spec['face_dim'] * 0.5)
        obj.matrix_basis = mounting.basis_matrix(corner * MM, n_a, Vector(spec['n_b']))
        try:
            context.view_layer.update()
        except (AttributeError, RuntimeError):
            pass
        if blocking_panels(obj, panel_list):
            warnings.append("%s had no room next to %s and was removed"
                            % (obj.name, hit[0].name))
            bpy.data.objects.remove(obj, do_unlink=True)
            placed_brackets.pop(key, None)
        else:
            infos.append("%s moved to the other side of its rail, %s was in the way"
                         % (obj.name, hit[0].name))

    # Hardware the user mounted on a profile of this frame
    mounted = [(child, host) for host in frames.members(ctrl)
               if host.alugen.kind == 'PROFILE'
               for child in host.children
               if child.alugen.has_mount and not child.alugen.support_pid]
    for obj, host in mounted:
        p = obj.alugen
        hit = blocking_panels(obj, panel_list)
        if not hit:
            continue
        # Half a turn around the profile axis puts it on the opposite face,
        # which is the underside when it was sitting on top of a rail.
        with props.busy():
            p.mount_rotation = p.mount_rotation + math.pi
        mounting.apply_mount(obj, host)
        try:
            context.view_layer.update()
        except (AttributeError, RuntimeError):
            pass
        if blocking_panels(obj, panel_list):
            with props.busy():
                p.mount_rotation = p.mount_rotation - math.pi
            mounting.apply_mount(obj, host)
            note = "%s runs into %s, move it by hand" % (obj.name, hit[0].name)
            with props.busy():
                p.note = note
            warnings.append(note)
        else:
            infos.append("%s moved to the opposite face of %s, %s was in the way"
                         % (obj.name, host.name, hit[0].name))
    for line in infos:
        print("[AluGen] " + line)
    return warnings
