"""Property groups: part data on the object, tool settings on the scene."""

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)

from . import catalog

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
              ('OTHER', "Other", "")]


def _rebuild(self, context):
    from . import builder
    obj = self.id_data
    if isinstance(obj, bpy.types.Object) and obj.alugen.kind == 'PROFILE':
        builder.rebuild_profile(obj)


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

    # Parts list data
    part_id: StringProperty(name="Part id", default="")
    part_name: StringProperty(name="Description", default="")
    note: StringProperty(name="Note", default="")


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

    # Parts list
    bom_path: StringProperty(name="File", subtype='FILE_PATH',
                             default="//parts_list.csv")


CLASSES = (ALUGEN_PG_object, ALUGEN_PG_scene)


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
