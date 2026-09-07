"""Mounting hardware on a single profile: placement math and re-fitting.

A mounted part stores where it sits on its host profile, so the placement can
be recomputed whenever the host changes length or the part is dragged.
"""

import math

from mathutils import Matrix, Vector

from . import builder, geometry, props
from .geometry import MM


def snap_angle(value, step=math.pi / 2.0):
    return round(value / step) * step


def local_start(host):
    """Local Z of the host start face, in millimetres."""
    p = host.alugen
    return {'START': 0.0, 'CENTER': -p.length * 0.5, 'END': -p.length}[p.origin_mode]


def mount_frame(host, offset, rotation, spin, lateral=0.0,
                snap_faces=True, snap_spin=True):
    """Return (corner_world, n_a, n_b) for a part mounted on a profile.

    offset and lateral are millimetres, rotation and spin are radians.
    n_a is the mounting face normal, n_b the direction the mounted leg runs.
    """
    a, b, _length = builder.profile_dims(host)
    slot = host.alugen.slot
    ang = snap_angle(rotation) if snap_faces else rotation
    n_local = Vector((math.cos(ang), math.sin(ang), 0.0))
    t_local = Vector((-math.sin(ang), math.cos(ang), 0.0))

    # Support function of the rounded rectangle: the part sits tangent to the
    # surface at any angle, not only on the four faces.
    r_corner = geometry.resolve_spec(a, b, slot)['corner_r']
    surf = ((a * 0.5 - r_corner) * abs(n_local.x)
            + (b * 0.5 - r_corner) * abs(n_local.y) + r_corner)

    z_local = local_start(host) + offset
    p_local = n_local * surf + t_local * lateral + Vector((0.0, 0.0, z_local))
    corner = host.matrix_world @ Vector((p_local.x * MM, p_local.y * MM, p_local.z * MM))

    mw3 = host.matrix_world.to_3x3()
    n_a = (mw3 @ n_local).normalized()
    axis = builder.profile_axis_world(host)
    turn = snap_angle(spin) if snap_spin else spin
    n_b = (Matrix.Rotation(turn, 4, n_a).to_3x3() @ axis).normalized()
    return corner, n_a, n_b


def basis_matrix(corner, n_a, n_b):
    z = Vector(n_a).normalized()
    y = Vector(n_b).normalized()
    x = y.cross(z).normalized()
    y = z.cross(x).normalized()
    return Matrix(((x.x, y.x, z.x, corner[0]),
                   (x.y, y.y, z.y, corner[1]),
                   (x.z, y.z, z.z, corner[2]),
                   (0.0, 0.0, 0.0, 1.0)))


def store_mount(obj, offset, rotation, spin, lateral, snap_faces, snap_spin, grid='AUTO'):
    """Remember the placement so it can be reproduced and edited later."""
    p = obj.alugen
    with props.busy():
        p.has_mount = True
        p.mount_offset = offset
        p.mount_rotation = rotation
        p.mount_spin = spin
        p.mount_lateral = lateral
        p.mount_snap_faces = snap_faces
        p.mount_snap_spin = snap_spin
        p.mount_grid = grid


def host_of(obj):
    host = obj.parent
    if host is not None and host.alugen.is_part and host.alugen.kind == 'PROFILE':
        return host
    return None


def apply_mount(obj, host=None):
    """Place a mounted part from its stored parameters."""
    host = host or host_of(obj)
    if host is None or not obj.alugen.has_mount:
        return False
    p = obj.alugen
    corner, n_a, n_b = mount_frame(host, p.mount_offset, p.mount_rotation, p.mount_spin,
                                   p.mount_lateral, p.mount_snap_faces, p.mount_snap_spin)
    obj.matrix_world = basis_matrix(corner, n_a, n_b)
    return True


def extent_on_host(obj, host):
    """(min, max) of the part along the host axis, in millimetres."""
    m = host.matrix_world.inverted() @ obj.matrix_world
    zs = [(m @ Vector(c)).z / MM for c in obj.bound_box]
    return min(zs), max(zs)


def fit_offset(obj, host=None):
    """Keep a mounted part on its host; returns a note, empty when nothing moved."""
    host = host or host_of(obj)
    if host is None or not obj.alugen.has_mount:
        return ""
    apply_mount(obj, host)
    z0 = local_start(host)
    z1 = z0 + host.alugen.length
    lo, hi = extent_on_host(obj, host)
    footprint = hi - lo
    if footprint > host.alugen.length + 1e-6:
        return ("does not fit on %s: needs %.1f mm, profile is %.1f mm"
                % (host.name, footprint, host.alugen.length))
    delta = 0.0
    if lo < z0 - 1e-6:
        delta = z0 - lo
    elif hi > z1 + 1e-6:
        delta = z1 - hi
    if abs(delta) < 1e-6:
        return ""
    old = obj.alugen.mount_offset
    with props.busy():
        obj.alugen.mount_offset = old + delta
    apply_mount(obj, host)
    return "moved by %.1f mm to stay on %s" % (delta, host.name)


def remount(obj):
    """Re-place a part after one of its mount parameters changed."""
    host = host_of(obj)
    if host is None:
        return ""
    note = fit_offset(obj, host)
    with props.busy():
        obj.alugen.note = note
    return note


def refit_children(host):
    """Re-place every mounted part on a profile; returns the collected notes."""
    notes = []
    for child in host.children:
        if child.alugen.has_mount:
            note = fit_offset(child, host)
            with props.busy():
                child.alugen.note = note
            if note:
                notes.append("%s: %s" % (child.name, note))
        elif child.alugen.is_part and child.alugen.kind == 'CAP':
            builder.place_cap(child, host)
    return notes
