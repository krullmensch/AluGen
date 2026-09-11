"""Object creation, materials and placement."""

import math

import bpy
from mathutils import Matrix, Vector

from . import catalog, geometry
from .geometry import MM

COLLECTION = "AluGen"

MATERIALS = {
    'ALU':   ("AluGen Aluminium", (0.72, 0.73, 0.75, 1.0), 0.85, 0.30),
    'STEEL': ("AluGen Steel", (0.62, 0.63, 0.66, 1.0), 1.0, 0.22),
    'PLASTIC': ("AluGen Plastic", (0.02, 0.02, 0.02, 1.0), 0.0, 0.55),
}


# --------------------------------------------------------------------------
# Scene / collection / material
# --------------------------------------------------------------------------

def setup_units(scene):
    us = scene.unit_settings
    us.system = 'METRIC'
    us.scale_length = 1.0
    us.length_unit = 'MILLIMETERS'


def get_collection(context):
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
        context.scene.collection.children.link(coll)
    elif coll.name not in {c.name for c in context.scene.collection.children_recursive}:
        try:
            context.scene.collection.children.link(coll)
        except RuntimeError:
            pass
    return coll


def get_material(key):
    name, color, metallic, rough = MATERIALS[key]
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Metallic"].default_value = metallic
            bsdf.inputs["Roughness"].default_value = rough
        mat.diffuse_color = color
    return mat


def new_object(context, name, verts, faces, mat_key='ALU'):
    me = bpy.data.meshes.new(name)
    geometry.write_mesh(me, verts, faces)
    obj = bpy.data.objects.new(name, me)
    obj.data.materials.append(get_material(mat_key))
    get_collection(context).objects.link(obj)
    return obj


def select_only(context, obj):
    for o in context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------

AXIS_MATRIX = {
    'X': Matrix.Rotation(math.radians(90.0), 4, 'Y'),
    'Y': Matrix.Rotation(math.radians(-90.0), 4, 'X'),
    'Z': Matrix.Identity(4),
}


def profile_name(a, b, slot, length):
    return "Profile %gx%g %s L%.0f" % (
        a, b, catalog.SLOT_SYSTEMS[slot]['label'].replace(" ", ""), length)


def create_profile(context, a, b, slot, length, axis='X', origin='START',
                   corner_cavity=False, location=(0.0, 0.0, 0.0)):
    verts, faces = geometry.profile_mesh(a, b, slot, length, origin, corner_cavity)
    obj = new_object(context, profile_name(a, b, slot, length), verts, faces, 'ALU')

    p = obj.alugen
    p.is_part = True
    p.kind = 'PROFILE'
    p.a = str(int(a))
    p.b = str(int(b))
    p.slot = slot
    p.length = length
    p.origin_mode = origin
    p.corner_cavity = corner_cavity

    obj["alugen_section"] = section_signature(p)
    obj.matrix_world = Matrix.Translation(Vector(location)) @ AXIS_MATRIX[axis]
    return obj


def section_signature(p):
    """Everything that changes the cross-section, but not the length."""
    return "%s|%s|%s|%d|%d|%d|%s" % (p.a, p.b, p.slot, int(p.corner_cavity),
                                     p.arc_segs, p.bore_segs, p.origin_mode)


def span_z(p):
    """Local start and end of the extrusion in millimetres."""
    if p.origin_mode == 'CENTER':
        return -p.length * 0.5, p.length * 0.5
    if p.origin_mode == 'END':
        return -p.length, 0.0
    return 0.0, p.length


def rebuild_profile(obj, allow_fast=True):
    """Regenerate the profile mesh.

    When only the length changed, the cross-section is reused and just the two
    end caps are moved. That keeps dragging a length or a frame side smooth.
    """
    p = obj.alugen
    a, b = float(p.a), float(p.b)
    sig = section_signature(p)
    me = obj.data
    z0, z1 = span_z(p)
    n = len(me.vertices)
    if (allow_fast and n and n % 2 == 0 and obj.get("alugen_section") == sig):
        half = n // 2
        co = [0.0] * (n * 3)
        me.vertices.foreach_get("co", co)
        for i in range(half):
            co[i * 3 + 2] = z0 * MM
            co[(half + i) * 3 + 2] = z1 * MM
        me.vertices.foreach_set("co", co)
        me.update()
    else:
        verts, faces = geometry.profile_mesh(
            a, b, p.slot, p.length, p.origin_mode, p.corner_cavity,
            p.arc_segs, p.bore_segs)
        geometry.write_mesh(me, verts, faces)
        obj["alugen_section"] = sig
    obj.name = profile_name(a, b, p.slot, p.length)
    obj.data.name = obj.name
    for child in obj.children:
        if child.alugen.is_part and child.alugen.kind == 'CAP':
            place_cap(child, obj)


def profile_dims(obj):
    """(a, b, length) in mm."""
    p = obj.alugen
    return float(p.a), float(p.b), p.length


def profile_axis_world(obj):
    return (obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()


def profile_span(obj):
    """Start and end point of the profile axis in world space (metres)."""
    p = obj.alugen
    L = p.length * MM
    if p.origin_mode == 'CENTER':
        z0, z1 = -L * 0.5, L * 0.5
    elif p.origin_mode == 'END':
        z0, z1 = -L, 0.0
    else:
        z0, z1 = 0.0, L
    mw = obj.matrix_world
    return mw @ Vector((0.0, 0.0, z0)), mw @ Vector((0.0, 0.0, z1))


# --------------------------------------------------------------------------
# Accessories
# --------------------------------------------------------------------------

def _tag_part(obj, kind, part_id, label, note=""):
    p = obj.alugen
    p.is_part = True
    p.kind = kind
    p.part_id = part_id or ""
    p.part_name = label or ""
    p.note = note
    return obj


def add_end_cap(context, profile, end='END'):
    a, b, _length = profile_dims(profile)
    slot = profile.alugen.slot
    verts, faces = geometry.end_cap_mesh(a, b, slot)
    part_id, label, common = catalog.cap_part(a, b, slot)
    note = "" if common else "Uncommon size, check availability"
    obj = new_object(context, "End cap %gx%g" % (a, b), verts, faces, 'PLASTIC')
    _tag_part(obj, 'CAP', part_id, label, note)

    obj.alugen.attach_end = end
    obj.parent = profile
    obj.matrix_parent_inverse = profile.matrix_world.inverted()
    place_cap(obj, profile)
    return obj


def place_cap(cap, profile):
    start, stop = profile_span(profile)
    rot3 = profile.matrix_world.to_3x3().to_4x4()
    if cap.alugen.attach_end == 'START':
        loc = start
        rot = rot3 @ Matrix.Rotation(math.radians(180.0), 4, 'X')
    else:
        loc = stop
        rot = rot3
    cap.matrix_world = Matrix.Translation(loc) @ rot


def add_bracket(context, grid, slot, corner, n_mount_a, n_mount_b):
    """Place an angle bracket.

    corner    : corner point (world space, metres)
    n_mount_a : normal of the face leg A sits on (local +Z)
    n_mount_b : normal of the face leg B sits on (local +Y)
    """
    verts, faces = geometry.bracket_mesh(grid, slot)
    part_id, label, common = catalog.bracket_part(grid, slot)
    note = "" if common else "Uncommon grid size, check availability"
    obj = new_object(context, "Bracket %s %g" % (slot, grid), verts, faces, 'ALU')
    _tag_part(obj, 'BRACKET', part_id, label, note)

    z = Vector(n_mount_a).normalized()
    y = Vector(n_mount_b).normalized()
    x = y.cross(z).normalized()
    y = z.cross(x).normalized()
    obj.matrix_world = Matrix((
        (x.x, y.x, z.x, corner[0]),
        (x.y, y.y, z.y, corner[1]),
        (x.z, y.z, z.z, corner[2]),
        (0.0, 0.0, 0.0, 1.0),
    ))
    return obj


def add_tnut(context, slot, matrix, thread=None):
    verts, faces = geometry.tnut_mesh(slot)
    part_id, label, ok = catalog.tnut_part(slot, thread)
    obj = new_object(context, "T-slot nut %s" % slot, verts, faces, 'STEEL')
    _tag_part(obj, 'TNUT', part_id, label, "" if ok else "Unusual thread for this slot")
    obj.matrix_world = matrix
    return obj


def add_bar_connector(context, slot, matrix, length=None):
    verts, faces = geometry.bar_connector_mesh(slot, length)
    if length is None:
        length = 180.0 if slot == 'N8' else 45.0
    part_id, label, _ok = catalog.bar_connector_part(slot, length)
    obj = new_object(context, "Bar connector %s" % slot, verts, faces, 'STEEL')
    _tag_part(obj, 'CONNECTOR', part_id, label)
    obj.matrix_world = matrix
    return obj


def add_cube_connector(context, grid, slot, matrix):
    verts, faces = geometry.cube_connector_mesh(grid)
    part_id, label, common = catalog.cube_connector_part(grid, slot)
    obj = new_object(context, "Cube connector %g" % grid, verts, faces, 'STEEL')
    _tag_part(obj, 'CONNECTOR', part_id, label,
              "" if common else "Uncommon grid size, check availability")
    obj.matrix_world = matrix
    return obj


def add_butt_connector(context, slot, matrix, screw_length=25.0):
    verts, faces = geometry.screw_mesh(slot, screw_length)
    part_id, label, _ok = catalog.butt_connector_part(slot)
    obj = new_object(context, "Butt connector %s" % slot, verts, faces, 'STEEL')
    _tag_part(obj, 'CONNECTOR', part_id, label)
    obj.matrix_world = matrix
    return obj
