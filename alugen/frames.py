"""Frames as editable assemblies.

A frame is a controller object (an empty) that stores the frame as a box in its
own local space, plus the profiles, brackets and caps that make it up. Changing
one face of the box updates every member: rails get a new cut length, posts move
and the hardware on them is re-fitted.
"""

import uuid

import bpy
from bpy.props import BoolProperty
from mathutils import Matrix, Vector

from . import builder, catalog, mounting, props
from .geometry import MM

ROLE_POST = 'POST'
ROLE_RAIL = 'RAIL'
ROLE_BRACKET = 'BRACKET'

CORNERS = ((-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0))


# --------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------

def is_controller(obj):
    return bool(obj) and obj.alugen.kind == 'FRAME' and obj.alugen.frame.fid != ""


def controller_for(obj):
    """The frame controller for a controller, a member or a mounted part."""
    if obj is None:
        return None
    if is_controller(obj):
        return obj
    fid = obj.alugen.fid
    if not fid and obj.parent is not None:
        fid = obj.parent.alugen.fid
    if not fid:
        return None
    for candidate in bpy.data.objects:
        if is_controller(candidate) and candidate.alugen.frame.fid == fid:
            return candidate
    return None


def members(ctrl, scene=None):
    fid = ctrl.alugen.frame.fid
    pool = scene.objects if scene else bpy.data.objects
    return [o for o in pool if o.alugen.fid == fid and o is not ctrl]


def frame_size(f):
    return ((f.x_max - f.x_min) / MM, (f.y_max - f.y_min) / MM,
            (f.z_max - f.z_min) / MM)


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

def layout(f):
    """Plan every member of the frame in controller local space (millimetres)."""
    a, b = float(f.a), float(f.b)
    x0, x1 = f.x_min / MM, f.x_max / MM
    y0, y1 = f.y_min / MM, f.y_max / MM
    z0, z1 = f.z_min / MM, f.z_max / MM
    X, Y, Z = x1 - x0, y1 - y0, z1 - z0

    posts = []
    rails = []
    warnings = []

    if Z >= catalog.LEN_MIN:
        for i, (sx, sy) in enumerate(CORNERS):
            px = (x0 + a * 0.5) if sx < 0 else (x1 - a * 0.5)
            py = (y0 + b * 0.5) if sy < 0 else (y1 - b * 0.5)
            posts.append(dict(role=ROLE_POST, i=i, length=round(Z, 1),
                              loc=(px, py, z0), axis='Z'))
    else:
        warnings.append("Post would be %.1f mm, below the %.0f mm minimum"
                        % (Z, catalog.LEN_MIN))

    len_x = round(X - 2.0 * a, 1)
    len_y = round(Y - 2.0 * b, 1)

    levels = []
    if f.bottom:
        levels.append(('BOTTOM', z0 + a * 0.5, z0 + b * 0.5))
    if f.top:
        levels.append(('TOP', z1 - a * 0.5, z1 - b * 0.5))
    for k in range(f.levels):
        h = z0 + Z * (k + 1.0) / (f.levels + 1.0)
        levels.append(('MID', h, h))

    for li, (kind, zx, zy) in enumerate(levels):
        n_face = (0.0, 0.0, -1.0 if kind == 'TOP' else 1.0)
        if len_x >= catalog.LEN_MIN:
            for j, sy in enumerate((-1.0, 1.0)):
                py = (y0 + b * 0.5) if sy < 0 else (y1 - b * 0.5)
                rails.append(dict(role=ROLE_RAIL, i=li * 4 + j, length=len_x,
                                  loc=(x0 + a, py, zx), axis='X',
                                  n_face=n_face, face_dim=a))
        elif li == 0:
            warnings.append("X rail would be %.1f mm, below the %.0f mm minimum"
                            % (len_x, catalog.LEN_MIN))
        if len_y >= catalog.LEN_MIN:
            for j, sx in enumerate((-1.0, 1.0)):
                px = (x0 + a * 0.5) if sx < 0 else (x1 - a * 0.5)
                rails.append(dict(role=ROLE_RAIL, i=li * 4 + 2 + j, length=len_y,
                                  loc=(px, y0 + b, zy), axis='Y',
                                  n_face=n_face, face_dim=b))
        elif li == 0:
            warnings.append("Y rail would be %.1f mm, below the %.0f mm minimum"
                            % (len_y, catalog.LEN_MIN))

    brackets = []
    grid = min(a, b)
    if f.brackets:
        for rail in rails:
            if rail['length'] < grid + 2.0:
                warnings.append("Rail %.0f mm is too short for a bracket" % rail['length'])
                continue
            axis_dir = {'X': Vector((1.0, 0.0, 0.0)), 'Y': Vector((0.0, 1.0, 0.0)),
                        'Z': Vector((0.0, 0.0, 1.0))}[rail['axis']]
            start = Vector(rail['loc'])
            stop = start + axis_dir * rail['length']
            n_face = Vector(rail['n_face'])
            for e, (joint, n_b) in enumerate(((start, axis_dir), (stop, -axis_dir))):
                brackets.append(dict(role=ROLE_BRACKET, i=rail['i'] * 2 + e,
                                     corner=tuple(joint + n_face * (rail['face_dim'] * 0.5)),
                                     n_a=tuple(n_face), n_b=tuple(n_b), grid=grid))

    if abs(a - b) > 1e-6:
        warnings.append("A and B differ: brackets sit in the middle of the face, "
                        "which may not be a slot on multi-cell profiles")
    return posts, rails, brackets, warnings


# --------------------------------------------------------------------------
# Build and update
# --------------------------------------------------------------------------

def _local_profile_matrix(spec):
    loc = Vector(spec['loc']) * MM
    return Matrix.Translation(loc) @ builder.AXIS_MATRIX[spec['axis']]


def _attach(obj, ctrl, matrix, role, index):
    obj.parent = ctrl
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = matrix
    with props.busy():
        obj.alugen.fid = ctrl.alugen.frame.fid
        obj.alugen.role = role
        obj.alugen.role_i = index


def _remove(obj):
    for child in list(obj.children):
        _remove(child)
    bpy.data.objects.remove(obj, do_unlink=True)


def create_frame(context, x, y, z, a, b, slot, levels=0, top=True, bottom=True,
                 brackets=True, caps=True, origin=(0.0, 0.0, 0.0), cavity=False):
    """Create a frame controller and all of its members. Sizes in millimetres."""
    ctrl = bpy.data.objects.new("AluGen Frame", None)
    ctrl.empty_display_type = 'PLAIN_AXES'
    ctrl.empty_display_size = max(x, y, z) * MM * 0.15
    builder.get_collection(context).objects.link(ctrl)
    ctrl.matrix_world = Matrix.Translation(Vector(origin) * MM)

    with props.busy():
        p = ctrl.alugen
        p.kind = 'FRAME'
        p.is_part = False
        f = p.frame
        f.fid = uuid.uuid4().hex
        f.x_min, f.x_max = -x * 0.5 * MM, x * 0.5 * MM
        f.y_min, f.y_max = -y * 0.5 * MM, y * 0.5 * MM
        f.z_min, f.z_max = 0.0, z * MM
        f.a, f.b, f.slot = str(int(a)), str(int(b)), slot
        f.levels, f.top, f.bottom = levels, top, bottom
        f.brackets, f.caps = brackets, caps
        f.corner_cavity = cavity

    update_frame(ctrl)
    return ctrl


def update_frame(ctrl, rebuild_members=True, context=None):
    """Recompute every member of the frame. Returns a list of warnings."""
    context = context or bpy.context
    f = ctrl.alugen.frame
    a, b = float(f.a), float(f.b)
    posts, rails, brackets, warnings = layout(f)

    existing = {}
    for obj in members(ctrl):
        if obj.alugen.role:
            existing[(obj.alugen.role, obj.alugen.role_i)] = obj

    kept = set()
    profiles = []

    for spec in posts + rails:
        key = (spec['role'], spec['i'])
        obj = existing.get(key)
        if obj is None or obj.alugen.kind != 'PROFILE':
            obj = builder.create_profile(context, a, b, f.slot, spec['length'],
                                         spec['axis'], 'START', f.corner_cavity)
        else:
            with props.busy():
                obj.alugen.a = str(int(a))
                obj.alugen.b = str(int(b))
                obj.alugen.slot = f.slot
                obj.alugen.length = spec['length']
                obj.alugen.corner_cavity = f.corner_cavity
                obj.alugen.origin_mode = 'START'
            builder.rebuild_profile(obj)
        _attach(obj, ctrl, _local_profile_matrix(spec), spec['role'], spec['i'])
        kept.add(key)
        profiles.append((obj, spec))

    for spec in brackets:
        key = (spec['role'], spec['i'])
        obj = existing.get(key)
        if obj is None or obj.alugen.kind != 'BRACKET':
            obj = builder.add_bracket(context, spec['grid'], f.slot,
                                      Vector((0.0, 0.0, 0.0)),
                                      Vector((0.0, 0.0, 1.0)), Vector((0.0, 1.0, 0.0)))
        matrix = mounting.basis_matrix(Vector(spec['corner']) * MM,
                                       Vector(spec['n_a']), Vector(spec['n_b']))
        _attach(obj, ctrl, matrix, spec['role'], spec['i'])
        kept.add(key)

    for key, obj in existing.items():
        if key not in kept:
            _remove(obj)

    # End caps on the post ends
    for obj, spec in profiles:
        if spec['role'] != ROLE_POST:
            continue
        have = {c.alugen.attach_end: c for c in obj.children
                if c.alugen.is_part and c.alugen.kind == 'CAP'}
        if f.caps:
            for end in ('START', 'END'):
                if end not in have:
                    cap = builder.add_end_cap(context, obj, end)
                    with props.busy():
                        cap.alugen.fid = f.fid
        else:
            for cap in have.values():
                _remove(cap)

    # Re-fit mounted hardware and caps on every member
    for obj, _spec in profiles:
        for note in mounting.refit_children(obj):
            warnings.append(note)

    with props.busy():
        f.warning = " | ".join(warnings)
    return warnings


def face_changed(ctrl, side):
    if not is_controller(ctrl):
        return
    f = ctrl.alugen.frame
    # Keep the box valid: a face may not pass the opposite one
    lo_name, hi_name = side[0] + "_min", side[0] + "_max"
    lo, hi = getattr(f, lo_name), getattr(f, hi_name)
    a, b = float(f.a), float(f.b)
    thin = 2.0 * (a if side[0] == 'x' else b if side[0] == 'y' else a) * MM
    with props.busy():
        if hi - lo < thin:
            if side.endswith("max"):
                setattr(f, hi_name, lo + thin)
            else:
                setattr(f, lo_name, hi - thin)
        # Quantise to 0.1 mm so cut lengths stay orderable
        for name in (lo_name, hi_name):
            setattr(f, name, round(getattr(f, name) / MM, 1) * MM)
    update_frame(ctrl)


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class ALUGEN_OT_frame_update(bpy.types.Operator):
    bl_idname = "alugen.frame_update"
    bl_label = "Update frame"
    bl_description = "Recompute every profile, bracket and cap of the selected frame"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return controller_for(context.active_object) is not None

    def execute(self, context):
        ctrl = controller_for(context.active_object)
        warnings = update_frame(ctrl, context=context)
        for w in warnings:
            self.report({'WARNING'}, w)
        self.report({'INFO'}, "Frame updated: %d members" % len(members(ctrl)))
        return {'FINISHED'}


class ALUGEN_OT_frame_select(bpy.types.Operator):
    bl_idname = "alugen.frame_select"
    bl_label = "Select frame controller"
    bl_description = "Make the frame controller of the active part the active object"
    bl_options = {'REGISTER', 'UNDO'}

    select_members: BoolProperty(name="Select members too", default=False)

    @classmethod
    def poll(cls, context):
        return controller_for(context.active_object) is not None

    def execute(self, context):
        ctrl = controller_for(context.active_object)
        for o in context.selected_objects:
            o.select_set(False)
        if self.select_members:
            for o in members(ctrl):
                o.select_set(True)
        ctrl.select_set(True)
        context.view_layer.objects.active = ctrl
        return {'FINISHED'}


class ALUGEN_OT_frame_resize(bpy.types.Operator):
    bl_idname = "alugen.frame_resize"
    bl_label = "Move frame side"
    bl_description = "Move one side of the frame by a given distance; the opposite side stays"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(
        name="Side", default='x_max',
        items=[('x_min', "-X", ""), ('x_max', "+X", ""), ('y_min', "-Y", ""),
               ('y_max', "+Y", ""), ('z_min', "-Z", ""), ('z_max', "+Z", "")])
    delta: bpy.props.FloatProperty(
        name="Distance (mm)", default=50.0, precision=1,
        description="Positive moves the side outwards")

    @classmethod
    def poll(cls, context):
        return controller_for(context.active_object) is not None

    def execute(self, context):
        ctrl = controller_for(context.active_object)
        f = ctrl.alugen.frame
        sign = 1.0 if self.side.endswith("max") else -1.0
        with props.busy():
            setattr(f, self.side, getattr(f, self.side) + sign * self.delta * MM)
        face_changed(ctrl, self.side)
        for w in f.warning.split(" | "):
            if w:
                self.report({'WARNING'}, w)
        x, y, z = frame_size(f)
        self.report({'INFO'}, "Frame %.1f x %.1f x %.1f mm" % (x, y, z))
        return {'FINISHED'}


CLASSES = (ALUGEN_OT_frame_update, ALUGEN_OT_frame_select, ALUGEN_OT_frame_resize)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
