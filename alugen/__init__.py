"""AluGen - parametric aluminium extrusion profiles for Blender.

Creates I-type extrusion profiles (slot 5 and slot 8) with exact cut lengths,
joins them, places hardware and produces a parts list you can order from.
"""

bl_info = {
    "name": "AluGen",
    "author": "Marvin Krullmann",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar (N) > AluGen",
    "description": "Parametric aluminium extrusion profiles, joints and parts list",
    "category": "Add Mesh",
}

import importlib

if "catalog" in locals():  # Blender "Reload Scripts"
    for _name in ("catalog", "geometry", "props", "builder", "bom",
                  "operators", "assemblies", "ui"):
        if _name in locals():
            importlib.reload(locals()[_name])

from . import catalog, geometry, props, builder, bom, operators, assemblies, ui

_REGISTER = (props, bom, operators, assemblies, ui)


def register():
    for m in _REGISTER:
        m.register()


def unregister():
    for m in reversed(_REGISTER):
        m.unregister()
