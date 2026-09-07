"""Property groups: part data on the object, tool settings on the scene."""

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)

from . import catalog

MM = 0.001

SIZE_ITEMS = [(str(int(s)), "%d mm" % int(s), "Edge size %d mm" % int(s))
              for s in catalog.SIZES]

SLOT_ITEMS = [('N5', "Slot 5", "5 mm slot, used on the 20 mm grid"),
              ('N8', "Slot 8", "8 mm slot, used on the 30/40/80 mm grid")]

AXIS_ITEMS = [('X', "X", "Length along X"),
              ('Y', "Y", "Length along Y"),
              ('Z', "Z", "Length along Z (upright)")]

ORIGIN_ITEMS = [('START', "Start", "Origin at the start face"),
                ('CENTER', "Center", "Origin in the middle of the profile"),
                ('END', "End", "Origin at the end face")]

KIND_ITEMS = [('PROFILE', "Profile", ""),
              ('CAP', "End cap", ""),
              ('BRACKET', "Angle bracket", ""),
              ('TNUT', "T-slot nut", ""),
              ('SCREW', "Screw", ""),
              ('CONNECTOR', "Connector", ""),
              ('FRAME', "Frame", ""),
              ('OTHER', "Other", "")]

GRID_ITEMS = [('AUTO', "Automatic", "Use the profile grid")] + \
             [(str(int(s)), "%d" % int(s), "") for s in catalog.SIZES]

# Guard against re-entrant property updates while geometry is being rebuilt
_BUSY = [False]


class busy:
    """Context manager that suppresses property update callbacks."""

    def __enter__(self):
        self.prev = _BUSY[0]
        _BUSY[0] = True
        return self

    def __exit__(self, *exc):
        _BUSY[0] = self.prev
        return False


def is_busy():
    return _BUSY[0]


def _rebuild(self, context):
    if is_busy():
        return
    from . import builder, mounting
    obj = self.id_data
    if isinstance(obj, bpy.types.Object) and obj.alugen.kind == 'PROFILE':
        builder.rebuild_profile(obj)
        mounting.refit_children(obj)


def _remount(self, context):
    if is_busy():
        return
    from . import mounting
    obj = self.id_data
    if isinstance(obj, bpy.types.Object):
        mounting.remount(obj)


def _face_changed(side):
    def fn(self, context):
        if is_busy():
            return
        from . import frames
        frames.face_changed(self.id_data, side)
    return fn


def _frame_layout_changed(self, context):
    if is_busy():
        return
    from . import frames
    frames.update_frame(self.id_data, rebuild_members=True)


def _mm_mirror(attr, doc):
    """Float property in millimetres backed by a stored metre value."""
    def get(self):
        return getattr(self, attr) / MM

    def set(self, value):
        setattr(self, attr, value * MM)

    return FloatProperty(name=doc, get=get, set=set, precision=1)


class ALUGEN_PG_frame(bpy.types.PropertyGroup):
    """Parameters of a generated frame, stored on its controller object.

    The frame is described as a box in the controller's local space, so a face
    can be dragged without moving the opposite one.
    """

    fid: StringProperty(name="Frame id", default="")

    x_min: FloatProperty(name="X min", unit='LENGTH', default=-0.3,
                         update=_face_changed('x_min'))
    x_max: FloatProperty(name="X max", unit='LENGTH', default=0.3,
                         update=_face_changed('x_max'))
    y_min: FloatProperty(name="Y min", unit='LENGTH', default=-0.2,
                         update=_face_changed('y_min'))
    y_max: FloatProperty(name="Y max", unit='LENGTH', default=0.2,
                         update=_face_changed('y_max'))
    z_min: FloatProperty(name="Z min", unit='LENGTH', default=0.0,
                         update=_face_changed('z_min'))
    z_max: FloatProperty(name="Z max", unit='LENGTH', default=0.8,
                         update=_face_changed('z_max'))

    a: EnumProperty(name="A", items=SIZE_ITEMS, default='40',
                    update=_frame_layout_changed)
    b: EnumProperty(name="B", items=SIZE_ITEMS, default='40',
                    update=_frame_layout_changed)
    slot: EnumProperty(name="Slot", items=SLOT_ITEMS, default='N8',
                       update=_frame_layout_changed)
    levels: IntProperty(name="Intermediate levels", default=0, min=0, max=6,
                        update=_frame_layout_changed)
    top: BoolProperty(name="Top frame", default=True, update=_frame_layout_changed)
    bottom: BoolProperty(name="Bottom frame", default=True, update=_frame_layout_changed)
    brackets: BoolProperty(name="Brackets", default=True, update=_frame_layout_changed)
    caps: BoolProperty(name="End caps", default=True, update=_frame_layout_changed)
    corner_cavity: BoolProperty(name="Corner cavities", default=False,
                                update=_frame_layout_changed)

    def _size(axis):
        def get(self):
            return (getattr(self, axis + "_max") - getattr(self, axis + "_min")) / MM

        def set(self, value):
            # Typing a size keeps the minimum face where it is
            setattr(self, axis + "_max", getattr(self, axis + "_min") + value * MM)

        return FloatProperty(name="Size %s (mm)" % axis.upper(), get=get, set=set,
                             precision=1)

    size_x: _size('x')
    size_y: _size('y')
    size_z: _size('z')

    # Mirrors so an arrow gizmo pointing outwards always grows the frame
    def _neg(attr):
        def get(self):
            return -getattr(self, attr)

        def set(self, value):
            setattr(self, attr, -value)

        return FloatProperty(name="-" + attr, unit='LENGTH', get=get, set=set)

    x_min_neg: _neg('x_min')
    y_min_neg: _neg('y_min')
    z_min_neg: _neg('z_min')

    warning: StringProperty(name="Warning", default="")


class ALUGEN_PG_object(bpy.types.PropertyGroup):
    is_part: BoolProperty(name="AluGen part", default=False)
    kind: EnumProperty(name="Type", items=KIND_ITEMS, default='OTHER')

    a: EnumProperty(name="A", items=SIZE_ITEMS, default='40', update=_rebuild)
    b: EnumProperty(name="B", items=SIZE_ITEMS, default='40', update=_rebuild)
    slot: EnumProperty(name="Slot", items=SLOT_ITEMS, default='N8', update=_rebuild)
    length: FloatProperty(
        name="Length", description="Cut length in mm",
        default=500.0, min=catalog.LEN_MIN, max=catalog.LEN_MAX,
        step=100, precision=1, unit='NONE', update=_rebuild)
    origin_mode: EnumProperty(name="Origin", items=ORIGIN_ITEMS,
                              default='START', update=_rebuild)
    corner_cavity: BoolProperty(
        name="Corner cavities",
        description="Show hollow chambers in the corners (visual only)",
        default=False, update=_rebuild)
    arc_segs: IntProperty(name="Corner segments", default=5, min=1, max=16, update=_rebuild)
    bore_segs: IntProperty(name="Bore segments", default=24, min=6, max=64, update=_rebuild)

    attach_end: EnumProperty(
        name="End", items=[('START', "Start", ""), ('END', "End", "")], default='END')

    # --- hardware mounted on a single profile -----------------------------
    has_mount: BoolProperty(default=False)
    mount_offset: FloatProperty(
        name="Offset (mm)", description="Position along the host profile",
        default=0.0, precision=1, update=_remount)
    mount_rotation: FloatProperty(
        name="Around profile", description="Rotation around the host profile axis",
        default=0.0, subtype='ANGLE', update=_remount)
    mount_spin: FloatProperty(
        name="Spin", description="Rotation of the part on the mounting face",
        default=0.0, subtype='ANGLE', update=_remount)
    mount_lateral: FloatProperty(
        name="Lateral (mm)", description="Shift across the mounting face",
        default=0.0, precision=1, update=_remount)
    mount_snap_faces: BoolProperty(name="Snap to faces", default=True, update=_remount)
    mount_snap_spin: BoolProperty(name="Snap spin to 90 deg", default=True, update=_remount)
    mount_grid: EnumProperty(name="Bracket size", items=GRID_ITEMS, default='AUTO')

    # --- frame membership --------------------------------------------------
    fid: StringProperty(name="Frame id", default="")
    role: StringProperty(name="Frame role", default="")
    role_i: IntProperty(name="Role index", default=0)
    frame: PointerProperty(type=ALUGEN_PG_frame)

    # --- parts list --------------------------------------------------------
    part_id: StringProperty(name="Part id", default="")
    part_name: StringProperty(name="Description", default="")
    note: StringProperty(name="Note", default="")

    # Gizmo target: cut length expressed in Blender units
    def _len_bu_get(self):
        return self.length * MM

    def _len_bu_set(self, value):
        self.length = max(catalog.LEN_MIN, min(catalog.LEN_MAX, value / MM))

    length_bu: FloatProperty(name="Length", unit='LENGTH',
                             get=_len_bu_get, set=_len_bu_set)

    def _off_bu_get(self):
        return self.mount_offset * MM

    def _off_bu_set(self, value):
        self.mount_offset = value / MM

    mount_offset_bu: FloatProperty(name="Offset", unit='LENGTH',
                                   get=_off_bu_get, set=_off_bu_set)


class ALUGEN_PG_scene(bpy.types.PropertyGroup):
    # New profile
    a: EnumProperty(name="A", items=SIZE_ITEMS, default='40')
    b: EnumProperty(name="B", items=SIZE_ITEMS, default='40')
    slot: EnumProperty(name="Slot", items=SLOT_ITEMS, default='N8')
    length: FloatProperty(name="Length (mm)", default=500.0,
                          min=catalog.LEN_MIN, max=catalog.LEN_MAX, precision=1)
    axis: EnumProperty(name="Axis", items=AXIS_ITEMS, default='X')
    origin_mode: EnumProperty(name="Origin", items=ORIGIN_ITEMS, default='START')
    corner_cavity: BoolProperty(name="Corner cavities", default=False)
    at_cursor: BoolProperty(name="At 3D cursor", default=True)

    # Frame generator
    frame_x: FloatProperty(name="Width X (mm)", default=600.0, min=50.0, max=5000.0)
    frame_y: FloatProperty(name="Depth Y (mm)", default=400.0, min=50.0, max=5000.0)
    frame_z: FloatProperty(name="Height Z (mm)", default=800.0, min=50.0, max=5000.0)
    frame_levels: IntProperty(name="Intermediate levels", default=0, min=0, max=6)
    frame_top: BoolProperty(name="Top frame", default=True)
    frame_bottom: BoolProperty(name="Bottom frame", default=True)
    frame_brackets: BoolProperty(name="Add brackets", default=True)
    frame_caps: BoolProperty(name="Add end caps", default=True)

    # Viewport
    show_gizmos: BoolProperty(
        name="Show gizmos", default=True,
        description="Draw drag handles on the selected profile, part or frame")
    gizmo_hardware: BoolProperty(
        name="Hardware handles", default=True,
        description="Draw the offset arrow and the rotation dials on mounted hardware")

    # Parts list
    bom_path: StringProperty(name="File", subtype='FILE_PATH',
                             default="//parts_list.csv")


CLASSES = (ALUGEN_PG_frame, ALUGEN_PG_object, ALUGEN_PG_scene)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.alugen = PointerProperty(type=ALUGEN_PG_object)
    bpy.types.Scene.alugen = PointerProperty(type=ALUGEN_PG_scene)


def unregister():
    del bpy.types.Scene.alugen
    del bpy.types.Object.alugen
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
