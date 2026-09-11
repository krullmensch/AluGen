"""Viewport gizmos: drag a profile length, a mounted part or a frame side."""

import bpy
from mathutils import Matrix, Vector

from . import frames, mounting
from .geometry import MM

LENGTH_COLOR = (0.28, 0.62, 0.95)
SPIN_COLOR = (0.95, 0.62, 0.18)
FACE_COLOR = (0.30, 0.80, 0.45)


def _gizmos_on(context):
    return getattr(context.scene, "alugen", None) and context.scene.alugen.show_gizmos


def _axis_matrix(location, z_dir, y_hint=Vector((0.0, 0.0, 1.0))):
    z = Vector(z_dir).normalized()
    y = Vector(y_hint)
    if abs(y.dot(z)) > 0.999:
        y = Vector((1.0, 0.0, 0.0)) if abs(z.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    y = (y - z * y.dot(z)).normalized()
    x = y.cross(z).normalized()
    return Matrix(((x.x, y.x, z.x, location[0]),
                   (x.y, y.y, z.y, location[1]),
                   (x.z, y.z, z.z, location[2]),
                   (0.0, 0.0, 0.0, 1.0)))


def _style(gz, color, alpha=0.75):
    gz.color = color
    gz.alpha = alpha
    gz.color_highlight = tuple(min(1.0, c + 0.25) for c in color)
    gz.alpha_highlight = 1.0
    gz.use_draw_modal = True


class ALUGEN_GGT_profile(bpy.types.GizmoGroup):
    """Length handle on a standalone profile."""

    bl_idname = "ALUGEN_GGT_profile"
    bl_label = "AluGen profile"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not _gizmos_on(context) or obj is None or obj.mode != 'OBJECT':
            return False
        p = obj.alugen
        # Members of a frame are driven by the frame, not by their own handle
        return p.is_part and p.kind == 'PROFILE' and not p.fid

    def setup(self, context):
        gz = self.gizmos.new("GIZMO_GT_arrow_3d")
        gz.draw_style = 'BOX'
        _style(gz, LENGTH_COLOR)
        self.length_gz = gz

    def refresh(self, context):
        obj = context.object
        from . import builder
        start, _stop = builder.profile_span(obj)
        axis = builder.profile_axis_world(obj)
        self.length_gz.matrix_basis = _axis_matrix(start, axis)
        self.length_gz.target_set_prop("offset", obj.alugen, "length_bu")


class ALUGEN_GGT_mount(bpy.types.GizmoGroup):
    """Offset arrow and rotation dials on hardware mounted to a profile."""

    bl_idname = "ALUGEN_GGT_mount"
    bl_label = "AluGen mounted part"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not _gizmos_on(context) or obj is None or obj.mode != 'OBJECT':
            return False
        if not context.scene.alugen.gizmo_hardware:
            return False
        return obj.alugen.has_mount and mounting.host_of(obj) is not None

    def setup(self, context):
        gz = self.gizmos.new("GIZMO_GT_arrow_3d")
        gz.draw_style = 'NORMAL'
        _style(gz, LENGTH_COLOR)
        self.offset_gz = gz

        dial = self.gizmos.new("GIZMO_GT_dial_3d")
        dial.draw_options = {'ANGLE_VALUE'}
        _style(dial, SPIN_COLOR)
        self.spin_gz = dial

        dial2 = self.gizmos.new("GIZMO_GT_dial_3d")
        dial2.draw_options = {'ANGLE_VALUE'}
        _style(dial2, FACE_COLOR)
        self.face_gz = dial2

    def refresh(self, context):
        obj = context.object
        host = mounting.host_of(obj)
        if host is None:
            return
        from . import builder
        start, _stop = builder.profile_span(host)
        axis = builder.profile_axis_world(host)
        corner = obj.matrix_world.translation
        n_a = (obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()

        self.offset_gz.matrix_basis = _axis_matrix(start, axis)
        self.offset_gz.target_set_prop("offset", obj.alugen, "mount_offset_bu")

        self.spin_gz.matrix_basis = _axis_matrix(corner + n_a * 0.012, n_a)
        self.spin_gz.target_set_prop("offset", obj.alugen, "mount_spin")

        on_axis = start + axis * ((corner - start).dot(axis))
        self.face_gz.matrix_basis = _axis_matrix(on_axis, axis)
        self.face_gz.target_set_prop("offset", obj.alugen, "mount_rotation")


class ALUGEN_GGT_frame(bpy.types.GizmoGroup):
    """One arrow per frame side; dragging it moves that side only."""

    bl_idname = "ALUGEN_GGT_frame"
    bl_label = "AluGen frame"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    SIDES = (
        ('x_max', Vector((1.0, 0.0, 0.0)), 'x'),
        ('x_min_neg', Vector((-1.0, 0.0, 0.0)), 'x'),
        ('y_max', Vector((0.0, 1.0, 0.0)), 'y'),
        ('y_min_neg', Vector((0.0, -1.0, 0.0)), 'y'),
        ('z_max', Vector((0.0, 0.0, 1.0)), 'z'),
        ('z_min_neg', Vector((0.0, 0.0, -1.0)), 'z'),
    )

    @classmethod
    def poll(cls, context):
        if not _gizmos_on(context) or context.object is None:
            return False
        if context.object.mode != 'OBJECT':
            return False
        return frames.controller_for(context.object) is not None

    def setup(self, context):
        self.side_gz = []
        for prop, _dir, _axis in self.SIDES:
            gz = self.gizmos.new("GIZMO_GT_arrow_3d")
            gz.draw_style = 'NORMAL'
            _style(gz, FACE_COLOR)
            self.side_gz.append((prop, gz))

    def refresh(self, context):
        ctrl = frames.controller_for(context.object)
        if ctrl is None:
            return
        f = ctrl.alugen.frame
        mid = {
            'x': ((f.y_min + f.y_max) * 0.5, (f.z_min + f.z_max) * 0.5),
            'y': ((f.x_min + f.x_max) * 0.5, (f.z_min + f.z_max) * 0.5),
            'z': ((f.x_min + f.x_max) * 0.5, (f.y_min + f.y_max) * 0.5),
        }
        world = ctrl.matrix_world
        for (prop, direction, axis), (_p, gz) in zip(self.SIDES, self.side_gz):
            if axis == 'x':
                local = Vector((0.0, mid['x'][0], mid['x'][1]))
            elif axis == 'y':
                local = Vector((mid['y'][0], 0.0, mid['y'][1]))
            else:
                local = Vector((mid['z'][0], mid['z'][1], 0.0))
            origin = world @ local
            gz.matrix_basis = _axis_matrix(origin, world.to_3x3() @ direction)
            gz.target_set_prop("offset", f, prop)


CLASSES = (ALUGEN_GGT_profile, ALUGEN_GGT_mount, ALUGEN_GGT_frame)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
