"""Operators: create profiles, join them, place hardware, validate."""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from mathutils import Matrix, Vector

from . import bom, builder, catalog, geometry
from .geometry import MM

FACE_ITEMS = [('X+', "+X", "Face along local +X"),
              ('X-', "-X", "Face along local -X"),
              ('Y+', "+Y", "Face along local +Y"),
              ('Y-', "-Y", "Face along local -Y")]

FACE_VEC = {'X+': Vector((1.0, 0.0, 0.0)), 'X-': Vector((-1.0, 0.0, 0.0)),
            'Y+': Vector((0.0, 1.0, 0.0)), 'Y-': Vector((0.0, -1.0, 0.0))}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def is_profile(obj):
    return bool(obj) and obj.type == 'MESH' and obj.alugen.is_part and obj.alugen.kind == 'PROFILE'


def selected_profiles(context):
    return [o for o in context.selected_objects if is_profile(o)]


def basis(z_dir, y_hint=Vector((0.0, 0.0, 1.0))):
    """Orthonormal basis with the local Z axis along z_dir."""
    z = Vector(z_dir).normalized()
    y = Vector(y_hint)
    if abs(y.dot(z)) > 0.999:
        y = Vector((1.0, 0.0, 0.0)) if abs(z.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    y = (y - z * y.dot(z)).normalized()
    x = y.cross(z).normalized()
    return Matrix(((x.x, y.x, z.x, 0.0),
                   (x.y, y.y, z.y, 0.0),
                   (x.z, y.z, z.z, 0.0),
                   (0.0, 0.0, 0.0, 1.0)))


def local_start_z(obj):
    p = obj.alugen
    L = p.length * MM
    return {'START': 0.0, 'CENTER': -L * 0.5, 'END': -L}[p.origin_mode]


def place_profile(obj, start_world, rot):
    """Position a profile so that its start face sits on start_world."""
    z0 = local_start_z(obj)
    offset = rot.to_3x3() @ Vector((0.0, 0.0, z0))
    obj.matrix_world = Matrix.Translation(Vector(start_world) - offset) @ rot.to_3x3().to_4x4()


def face_normal_world(obj, face):
    return (obj.matrix_world.to_3x3() @ FACE_VEC[face]).normalized()


def face_halfdim(obj, face):
    a, b, _l = builder.profile_dims(obj)
    return (a if face.startswith('X') else b) * 0.5 * MM


# --------------------------------------------------------------------------
# Scene
# --------------------------------------------------------------------------

class ALUGEN_OT_setup_scene(bpy.types.Operator):
    bl_idname = "alugen.setup_scene"
    bl_label = "Set up scene in mm"
    bl_description = "Switch units to millimetres and prepare the AluGen collection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        builder.setup_units(context.scene)
        builder.get_collection(context)
        for area in (context.screen.areas if context.screen else []):
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.clip_start = 0.001
                        space.clip_end = 1000.0
        self.report({'INFO'}, "Units: millimetres")
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------

class ALUGEN_OT_add_profile(bpy.types.Operator):
    bl_idname = "alugen.add_profile"
    bl_label = "Add profile"
    bl_description = "Add an extrusion profile with an exact cut length"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.alugen
        a, b = float(s.a), float(s.b)
        loc = tuple(context.scene.cursor.location) if s.at_cursor else (0.0, 0.0, 0.0)
        obj = builder.create_profile(context, a, b, s.slot, s.length, s.axis,
                                     s.origin_mode, s.corner_cavity, loc)
        builder.select_only(context, obj)
        self.report({'INFO'}, "%gx%g %s, L = %.1f mm" %
                    (a, b, catalog.SLOT_SYSTEMS[s.slot]['label'], s.length))
        return {'FINISHED'}


class ALUGEN_OT_array(bpy.types.Operator):
    bl_idname = "alugen.array"
    bl_label = "Copy in a row"
    bl_description = "Copy the active part several times with a fixed spacing"
    bl_options = {'REGISTER', 'UNDO'}

    count: IntProperty(name="Copies", default=1, min=1, max=200)
    spacing: FloatProperty(name="Spacing (mm)", default=200.0, min=-5000.0, max=5000.0)
    direction: EnumProperty(name="Direction", default='X',
                            items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""),
                                   ('AXIS', "Profile axis", "")])

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        src = context.active_object
        if self.direction == 'AXIS' and is_profile(src):
            d = builder.profile_axis_world(src)
        else:
            d = {'X': Vector((1.0, 0.0, 0.0)), 'Y': Vector((0.0, 1.0, 0.0)),
                 'Z': Vector((0.0, 0.0, 1.0))}.get(self.direction, Vector((1.0, 0.0, 0.0)))
        coll = builder.get_collection(context)
        made = []
        for i in range(1, self.count + 1):
            new = src.copy()
            new.data = src.data.copy()
            coll.objects.link(new)
            new.matrix_world = Matrix.Translation(d * (self.spacing * MM * i)) @ src.matrix_world
            made.append(new)
        for o in made:
            o.select_set(True)
        self.report({'INFO'}, "%d copies" % self.count)
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Joining
# --------------------------------------------------------------------------

class ALUGEN_OT_snap_end(bpy.types.Operator):
    bl_idname = "alugen.snap_end"
    bl_label = "Butt against end"
    bl_description = ("Move the active profile against the end face of the second "
                      "selected profile, keeping the same direction")
    bl_options = {'REGISTER', 'UNDO'}

    target_end: EnumProperty(name="Target end", default='END',
                             items=[('END', "End", ""), ('START', "Start", "")])
    gap: FloatProperty(name="Gap (mm)", default=0.0, min=-100.0, max=100.0)
    align: BoolProperty(name="Copy orientation", default=True)

    @classmethod
    def poll(cls, context):
        return len(selected_profiles(context)) >= 2 and is_profile(context.active_object)

    def execute(self, context):
        act = context.active_object
        others = [o for o in selected_profiles(context) if o is not act]
        if not others:
            self.report({'ERROR'}, "Select two profiles, the active one is moved")
            return {'CANCELLED'}
        tgt = others[0]
        start, stop = builder.profile_span(tgt)
        axis = builder.profile_axis_world(tgt)
        if self.target_end == 'END':
            p = stop + axis * (self.gap * MM)
            rot = tgt.matrix_world.to_3x3().to_4x4() if self.align \
                else act.matrix_world.to_3x3().to_4x4()
        else:
            p = start - axis * (self.gap * MM)
            rot = (tgt.matrix_world.to_3x3().to_4x4()
                   @ Matrix.Rotation(math.radians(180.0), 4, 'X')) if self.align \
                else act.matrix_world.to_3x3().to_4x4()
        place_profile(act, p, rot)
        return {'FINISHED'}


class ALUGEN_OT_attach(bpy.types.Operator):
    bl_idname = "alugen.attach"
    bl_label = "Attach to profile"
    bl_description = "Attach the active profile to a face of the second selected profile"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(
        name="Mode", default='PERP',
        items=[('PERP', "Perpendicular on face", "Profile stands on the face"),
               ('PARALLEL', "Parallel to face", "Profile lies flat against the face")])
    face: EnumProperty(name="Target face", items=FACE_ITEMS, default='X+')
    offset: FloatProperty(name="Offset from target start (mm)", default=0.0, precision=1)
    lateral: FloatProperty(name="Lateral offset (mm)", default=0.0, precision=1)
    flip: BoolProperty(name="Flip direction", default=False)

    @classmethod
    def poll(cls, context):
        return len(selected_profiles(context)) >= 2 and is_profile(context.active_object)

    def execute(self, context):
        act = context.active_object
        others = [o for o in selected_profiles(context) if o is not act]
        if not others:
            self.report({'ERROR'}, "Select two profiles")
            return {'CANCELLED'}
        tgt = others[0]
        t_start, _t_stop = builder.profile_span(tgt)
        t_axis = builder.profile_axis_world(tgt)
        n = face_normal_world(tgt, self.face)
        base = t_start + t_axis * (self.offset * MM) + n * face_halfdim(tgt, self.face)
        side = n.cross(t_axis).normalized()

        if self.mode == 'PERP':
            base = base + side * (self.lateral * MM)
            d = -n if self.flip else n
            place_profile(act, base, basis(d, t_axis))
        else:
            a_dim = face_halfdim(act, 'X+') * 2.0 if self.face.startswith('X') \
                else face_halfdim(act, 'Y+') * 2.0
            p = base + n * (a_dim * 0.5) + side * (self.lateral * MM)
            rot = tgt.matrix_world.to_3x3().to_4x4()
            if self.flip:
                rot = rot @ Matrix.Rotation(math.radians(180.0), 4, 'X')
            z0 = local_start_z(act)
            offs = rot.to_3x3() @ Vector((0.0, 0.0, z0))
            act.matrix_world = Matrix.Translation(p - offs) @ rot.to_3x3().to_4x4()
        return {'FINISHED'}


class ALUGEN_OT_fit_length(bpy.types.Operator):
    bl_idname = "alugen.fit_length"
    bl_label = "Fit length between"
    bl_description = ("Set the length of the active profile so that it fits between the "
                      "two other selected profiles")
    bl_options = {'REGISTER', 'UNDO'}

    clearance: FloatProperty(name="Clearance (mm)", default=0.0, min=-10.0, max=10.0)

    @classmethod
    def poll(cls, context):
        return len(selected_profiles(context)) >= 3 and is_profile(context.active_object)

    def execute(self, context):
        act = context.active_object
        others = [o for o in selected_profiles(context) if o is not act]
        if len(others) < 2:
            self.report({'ERROR'}, "Select three profiles: two stops plus the active one")
            return {'CANCELLED'}
        axis = builder.profile_axis_world(act)
        start, _stop = builder.profile_span(act)

        def face_dist(other):
            o_start, o_stop = builder.profile_span(other)
            centre = (o_start + o_stop) * 0.5
            a, b, _l = builder.profile_dims(other)
            o_axis = builder.profile_axis_world(other)
            mw = other.matrix_world.to_3x3()
            ext = 0.0
            for vec, dim in ((mw @ Vector((1.0, 0.0, 0.0)), a * MM),
                             (mw @ Vector((0.0, 1.0, 0.0)), b * MM),
                             (o_axis, (o_stop - o_start).length)):
                ext += abs(vec.normalized().dot(axis)) * dim * 0.5
            return (centre - start).dot(axis), ext

        ds = sorted((face_dist(o) for o in others), key=lambda t: t[0])
        low = ds[0][0] + ds[0][1]
        high = ds[-1][0] - ds[-1][1]
        length_mm = (high - low) / MM - self.clearance
        if length_mm < catalog.LEN_MIN:
            self.report({'ERROR'}, "Result %.1f mm is below the %.0f mm minimum"
                        % (length_mm, catalog.LEN_MIN))
            return {'CANCELLED'}
        act.alugen.length = min(length_mm, catalog.LEN_MAX)
        place_profile(act, start + axis * low, act.matrix_world.to_3x3().to_4x4())
        self.report({'INFO'}, "Length = %.1f mm" % act.alugen.length)
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Hardware
# --------------------------------------------------------------------------

class ALUGEN_OT_add_caps(bpy.types.Operator):
    bl_idname = "alugen.add_caps"
    bl_label = "Add end caps"
    bl_description = "Add end caps to the ends of the selected profiles"
    bl_options = {'REGISTER', 'UNDO'}

    ends: EnumProperty(name="Ends", default='BOTH',
                       items=[('BOTH', "Both", ""), ('START', "Start", ""), ('END', "End", "")])

    @classmethod
    def poll(cls, context):
        return bool(selected_profiles(context))

    def execute(self, context):
        n = 0
        notes = []
        for prof in selected_profiles(context):
            existing = {c.alugen.attach_end for c in prof.children
                        if c.alugen.is_part and c.alugen.kind == 'CAP'}
            for end in (('START', 'END') if self.ends == 'BOTH' else (self.ends,)):
                if end in existing:
                    continue
                cap = builder.add_end_cap(context, prof, end)
                if cap.alugen.note:
                    notes.append(cap.alugen.note)
                n += 1
        if notes:
            self.report({'WARNING'}, "%d caps flagged: %s" % (len(notes), notes[0]))
        self.report({'INFO'}, "%d end caps placed" % n)
        return {'FINISHED'}


class ALUGEN_OT_add_bracket(bpy.types.Operator):
    bl_idname = "alugen.add_bracket"
    bl_label = "Add bracket at joint"
    bl_description = ("Place an angle bracket between the two selected profiles; the "
                      "active profile is the one butting against the other")
    bl_options = {'REGISTER', 'UNDO'}

    variant: IntProperty(name="Side", default=0, min=0, max=1,
                         description="Cycle the mounting face on the butting profile")
    both_sides: BoolProperty(name="Two brackets (opposite)", default=False)

    @classmethod
    def poll(cls, context):
        return len(selected_profiles(context)) >= 2 and is_profile(context.active_object)

    def execute(self, context):
        rail = context.active_object
        others = [o for o in selected_profiles(context) if o is not rail]
        if not others:
            self.report({'ERROR'}, "Select two profiles")
            return {'CANCELLED'}
        post = others[0]
        r_start, r_stop = builder.profile_span(rail)
        p_start, p_stop = builder.profile_span(post)
        p_axis = builder.profile_axis_world(post)
        p_mid = (p_start + p_stop) * 0.5

        # Which end of the rail sits at the post?
        d_start = (r_start - p_mid) - p_axis * (r_start - p_mid).dot(p_axis)
        d_stop = (r_stop - p_mid) - p_axis * (r_stop - p_mid).dot(p_axis)
        if d_start.length <= d_stop.length:
            joint, into = r_start, (r_stop - r_start).normalized()
        else:
            joint, into = r_stop, (r_start - r_stop).normalized()

        n_b = into  # normal of the post face, pointing into the rail
        mw = rail.matrix_world.to_3x3()
        a, b, _l = builder.profile_dims(rail)
        cands = [(mw @ Vector((1.0, 0.0, 0.0)), a), (mw @ Vector((-1.0, 0.0, 0.0)), a),
                 (mw @ Vector((0.0, 1.0, 0.0)), b), (mw @ Vector((0.0, -1.0, 0.0)), b)]
        # The second leg runs along the post, so the mounting face on the rail
        # has to be perpendicular to the post axis.
        cands = [(v.normalized(), d) for v, d in cands
                 if abs(v.normalized().dot(p_axis)) > 0.9]
        if not cands:
            self.report({'ERROR'}, "The profiles are not perpendicular to each other")
            return {'CANCELLED'}
        cands.sort(key=lambda t: -t[0].dot(p_axis if p_axis.z >= 0 else -p_axis))
        idx = self.variant % len(cands)
        grid = min(builder.profile_dims(rail)[0], builder.profile_dims(rail)[1],
                   builder.profile_dims(post)[0], builder.profile_dims(post)[1])
        slot = rail.alugen.slot

        picks = [idx]
        if self.both_sides:
            opp = min(range(len(cands)), key=lambda i: cands[i][0].dot(cands[idx][0]))
            if opp != idx:
                picks.append(opp)
        for i in picks:
            n_a, dim = cands[i]
            builder.add_bracket(context, grid, slot, joint + n_a * (dim * 0.5 * MM), n_a, n_b)
        self.report({'INFO'}, "%d bracket(s) placed (grid %g, %s)" % (len(picks), grid, slot))
        return {'FINISHED'}


class ALUGEN_OT_add_bracket_on_profile(bpy.types.Operator):
    bl_idname = "alugen.add_bracket_on_profile"
    bl_label = "Add bracket on profile"
    bl_description = ("Mount an angle bracket anywhere on a single profile, free to "
                      "position along the length and to rotate around the profile axis. "
                      "Use it for panels, plates, feet or any part that is not another profile")
    bl_options = {'REGISTER', 'UNDO'}

    offset: FloatProperty(name="Offset from start (mm)", default=100.0, precision=1,
                          description="Position of the bracket corner along the profile")
    rotation: FloatProperty(name="Around profile (deg)", default=0.0, min=-360.0, max=360.0,
                            description="Rotate the mounting position around the profile "
                                        "axis; 0 is the local +X face")
    snap_faces: BoolProperty(name="Snap to faces", default=True,
                             description="Snap the position to the four profile faces")
    spin: FloatProperty(name="Bracket spin (deg)", default=0.0, min=-360.0, max=360.0,
                        description="Rotate the bracket in place on that face; 0 puts the "
                                    "mounted leg along the profile towards its end, 180 "
                                    "towards its start, 90 and 270 across the face")
    snap_spin: BoolProperty(name="Snap spin to 90 deg", default=True,
                            description="Snap the spin to quarter turns")
    lateral: FloatProperty(name="Lateral offset (mm)", default=0.0, precision=1,
                           description="Shift across the face, for example to reach the "
                                       "second slot of a multi-cell profile")
    grid: EnumProperty(
        name="Bracket size", default='AUTO',
        items=[('AUTO', "Automatic", "Use the profile grid"), ('20', "20", ""),
               ('30', "30", ""), ('40', "40", ""), ('80', "80", "")])
    parent_to_profile: BoolProperty(
        name="Parent to profile", default=True,
        description="Move the bracket together with the profile")

    @classmethod
    def poll(cls, context):
        return is_profile(context.active_object)

    def execute(self, context):
        prof = context.active_object
        a, b, length = builder.profile_dims(prof)
        slot = prof.alugen.slot

        ang = math.radians(self.rotation)
        if self.snap_faces:
            ang = math.radians(round(self.rotation / 90.0) * 90.0)
        n_local = Vector((math.cos(ang), math.sin(ang), 0.0))
        t_local = Vector((-math.sin(ang), math.cos(ang), 0.0))

        # Distance from the profile axis to the outer surface along n_local.
        # Support function of the rounded rectangle, so the bracket also sits
        # tangent to the rounded corners at free angles.
        r_corner = geometry.resolve_spec(a, b, slot)['corner_r']
        surf = ((a * 0.5 - r_corner) * abs(n_local.x)
                + (b * 0.5 - r_corner) * abs(n_local.y) + r_corner)

        z_local = local_start_z(prof) / MM + self.offset
        if self.offset < -1e-6 or self.offset > length + 1e-6:
            self.report({'WARNING'}, "Offset %.1f mm is outside the profile length %.1f mm"
                        % (self.offset, length))
        p_local = n_local * surf + t_local * self.lateral + Vector((0.0, 0.0, z_local))
        corner = prof.matrix_world @ Vector((p_local.x * MM, p_local.y * MM, p_local.z * MM))

        mw3 = prof.matrix_world.to_3x3()
        n_a = (mw3 @ n_local).normalized()
        axis = builder.profile_axis_world(prof)
        spin = math.radians(round(self.spin / 90.0) * 90.0 if self.snap_spin
                            else self.spin)
        # Spin turns the bracket in place around the mounting face normal, so the
        # corner stays put and only the direction of the mounted leg changes.
        n_b = (Matrix.Rotation(spin, 4, n_a).to_3x3() @ axis).normalized()

        grid = min(a, b) if self.grid == 'AUTO' else float(self.grid)
        obj = builder.add_bracket(context, grid, slot, corner, n_a, n_b)
        if self.parent_to_profile:
            mat = obj.matrix_world.copy()
            obj.parent = prof
            obj.matrix_parent_inverse = prof.matrix_world.inverted()
            obj.matrix_world = mat
        # The profile stays active so several brackets can be placed in a row
        # and the redo panel keeps working.
        obj.select_set(True)
        self.report({'INFO'}, "Bracket %g at %.1f mm, face %.0f deg, spin %.0f deg" %
                    (grid, self.offset, math.degrees(ang) % 360.0,
                     math.degrees(spin) % 360.0))
        return {'FINISHED'}


class ALUGEN_OT_add_tnut(bpy.types.Operator):
    bl_idname = "alugen.add_tnut"
    bl_label = "Add T-slot nut"
    bl_description = "Place a T-slot nut inside a slot of the active profile"
    bl_options = {'REGISTER', 'UNDO'}

    face: EnumProperty(name="Slot face", items=FACE_ITEMS, default='X+')
    offset: FloatProperty(name="Offset from profile start (mm)", default=50.0, precision=1)
    slot_index: IntProperty(name="Slot no.", default=0, min=0, max=7)
    thread: EnumProperty(name="Thread", default='AUTO',
                         items=[('AUTO', "Automatic", ""), ('M3', "M3", ""), ('M4', "M4", ""),
                                ('M5', "M5", ""), ('M6', "M6", ""), ('M8', "M8", "")])

    @classmethod
    def poll(cls, context):
        return is_profile(context.active_object)

    def execute(self, context):
        prof = context.active_object
        a, b, _l = builder.profile_dims(prof)
        slot = prof.alugen.slot
        spec = geometry.resolve_spec(a, b, slot)
        centers = spec['xs'] if self.face.startswith('Y') else spec['ys']
        c = centers[min(self.slot_index, len(centers) - 1)]
        n_local = FACE_VEC[self.face]
        half = (a if self.face.startswith('X') else b) * 0.5
        depth = spec['lip_t'] + spec['tnut'][1] * 0.5 + 0.2
        if self.face.startswith('X'):
            local = Vector((n_local.x * (half - depth), c, 0.0))
        else:
            local = Vector((c, n_local.y * (half - depth), 0.0))
        local.z = local_start_z(prof) / MM + self.offset
        loc_m = Vector((local.x * MM, local.y * MM, local.z * MM))
        rot = basis(-(prof.matrix_world.to_3x3() @ n_local).normalized(),
                    builder.profile_axis_world(prof))
        mat = Matrix.Translation(prof.matrix_world @ loc_m) @ rot.to_3x3().to_4x4()
        builder.add_tnut(context, slot, mat, None if self.thread == 'AUTO' else self.thread)
        return {'FINISHED'}


class ALUGEN_OT_add_connector(bpy.types.Operator):
    bl_idname = "alugen.add_connector"
    bl_label = "Add connector"
    bl_description = "Add a slot bar, butt joint or cube connector"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(
        name="Type", default='BAR',
        items=[('BAR', "Slot bar connector", "Steel bar inside the slot, joins two profiles"),
               ('BUTT', "Butt joint connector", "Screw through the profile into the core bore"),
               ('CUBE', "Cube corner connector", "Three-way corner block")])
    offset: FloatProperty(name="Offset from profile start (mm)", default=0.0, precision=1)
    face: EnumProperty(name="Slot face", items=FACE_ITEMS, default='X+')

    @classmethod
    def poll(cls, context):
        return is_profile(context.active_object)

    def execute(self, context):
        prof = context.active_object
        a, b, _length = builder.profile_dims(prof)
        slot = prof.alugen.slot
        spec = geometry.resolve_spec(a, b, slot)
        axis = builder.profile_axis_world(prof)
        start, _stop = builder.profile_span(prof)

        if self.kind == 'CUBE':
            builder.add_cube_connector(context, min(a, b), slot,
                                       Matrix.Translation(start + axis * (self.offset * MM)))
        elif self.kind == 'BUTT':
            n = face_normal_world(prof, self.face)
            p = start + axis * (self.offset * MM) + n * face_halfdim(prof, self.face)
            mat = Matrix.Translation(p) @ basis(n, axis).to_3x3().to_4x4()
            builder.add_butt_connector(context, slot, mat)
        else:
            n_local = FACE_VEC[self.face]
            half = (a if self.face.startswith('X') else b) * 0.5
            depth = spec['lip_t'] + 2.5
            centers = spec['xs'] if self.face.startswith('Y') else spec['ys']
            c = centers[0]
            if self.face.startswith('X'):
                local = Vector((n_local.x * (half - depth), c, 0.0))
            else:
                local = Vector((c, n_local.y * (half - depth), 0.0))
            local.z = local_start_z(prof) / MM + self.offset
            loc_m = Vector((local.x * MM, local.y * MM, local.z * MM))
            rot = basis(axis, (prof.matrix_world.to_3x3() @ n_local).normalized())
            mat = Matrix.Translation(prof.matrix_world @ loc_m) @ rot.to_3x3().to_4x4()
            builder.add_bar_connector(context, slot, mat)
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

class ALUGEN_OT_check(bpy.types.Operator):
    bl_idname = "alugen.check"
    bl_label = "Check assembly"
    bl_description = "Check lengths, object scale and part availability"
    bl_options = {'REGISTER'}

    def execute(self, context):
        issues = bom.check_scene(context)
        if not issues:
            self.report({'INFO'}, "All good, no problems found")
            return {'FINISHED'}
        for msg in issues[:5]:
            self.report({'WARNING'}, msg)
        for msg in issues:
            print("[AluGen] " + msg)
        self.report({'WARNING'}, "%d findings, details in the system console" % len(issues))
        return {'FINISHED'}


CLASSES = (
    ALUGEN_OT_setup_scene,
    ALUGEN_OT_add_profile,
    ALUGEN_OT_array,
    ALUGEN_OT_snap_end,
    ALUGEN_OT_attach,
    ALUGEN_OT_fit_length,
    ALUGEN_OT_add_caps,
    ALUGEN_OT_add_bracket,
    ALUGEN_OT_add_bracket_on_profile,
    ALUGEN_OT_add_tnut,
    ALUGEN_OT_add_connector,
    ALUGEN_OT_check,
)


def menu_func(self, context):
    self.layout.operator("alugen.add_profile", text="AluGen Profile", icon='MESH_CUBE')


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
