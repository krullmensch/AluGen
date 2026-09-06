"""Geometry generation: profile cross-section, extrusion, accessory meshes.

Everything is calculated in millimetres; the scale factor MM converts to
Blender units (metres) when the mesh data is written.
"""

import math

import bmesh
from mathutils import Matrix, Vector
from mathutils.geometry import delaunay_2d_cdt

from . import catalog

MM = 0.001


# ==========================================================================
# 2D helpers
# ==========================================================================

def arc(cx, cy, r, a0, a1, segs):
    """Points on a circular arc, including start and end point."""
    pts = []
    for i in range(segs + 1):
        t = a0 + (a1 - a0) * i / segs
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def circle(cx, cy, r, segs=24, cw=True):
    pts = []
    for i in range(segs):
        t = 2.0 * math.pi * i / segs
        if cw:
            t = -t
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def rounded_rect(cx, cy, w, h, r, segs=4, cw=False):
    """Rounded rectangle as a closed point loop (counter-clockwise by default)."""
    r = max(0.0, min(r, min(w, h) * 0.5 - 1e-6))
    x0, x1 = cx - w * 0.5, cx + w * 0.5
    y0, y1 = cy - h * 0.5, cy + h * 0.5
    if r <= 1e-9:
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    else:
        pts = []
        pts += arc(x1 - r, y0 + r, r, -math.pi / 2, 0.0, segs)
        pts += arc(x1 - r, y1 - r, r, 0.0, math.pi / 2, segs)
        pts += arc(x0 + r, y1 - r, r, math.pi / 2, math.pi, segs)
        pts += arc(x0 + r, y0 + r, r, math.pi, 1.5 * math.pi, segs)
        pts = _dedup(pts)
    if cw:
        pts.reverse()
    return pts


def _dedup(pts, eps=1e-7):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < eps and abs(out[0][1] - out[-1][1]) < eps:
        out.pop()
    return out


# ==========================================================================
# Profile cross-section
# ==========================================================================

def resolve_spec(a, b, slot):
    """Resolve the geometry parameters for a profile A x B.

    The grid pitch is the smaller edge length. It determines the number of
    cells, the slot positions and the position of the core bores. A 40x80
    profile is therefore two 40 mm cells with two core bores.
    """
    sysd = catalog.SLOT_SYSTEMS[slot]
    pitch = min(a, b)

    def cells(dim):
        n = max(1, int(round(dim / pitch)))
        return n if abs(dim - n * pitch) < 1e-6 else 1

    nx, ny = cells(a), cells(b)

    def centers(dim, n):
        if n <= 1:
            return [0.0]
        step = dim / n
        return [-dim * 0.5 + step * (i + 0.5) for i in range(n)]

    xs = centers(a, nx)
    ys = centers(b, ny)

    o = sysd['opening']
    lip = sysd['lip_t']
    flare_v = sysd['flare_v']
    web = sysd['web']

    # Limit the slot chamber so a web remains towards the neighbouring slot
    c = min(sysd['chamber_w'], pitch - 2.0 * (lip + flare_v + web))
    c = max(c, o + 0.8)
    v_flare = lip + flare_v

    # Slot depth: nominal value, limited by the wall towards the core bore
    depth_max = min(sysd['depth'], pitch * 0.5 - sysd['bore'] * 0.5 - sysd['min_wall'])
    depth_max = max(depth_max, v_flare + 0.5)

    # Depth up to which the chamber keeps its full width; a 45 degree run-out
    # narrows it down to the slot floor from there
    floor_w = min(sysd['floor_w'], c - 1.0)
    v_wide = min(pitch * 0.5 - c * 0.5 - web, depth_max - (c - floor_w) * 0.5)
    v_wide = max(v_wide, v_flare)
    depth = min(depth_max, v_wide + (c - floor_w) * 0.5)
    floor = c - 2.0 * (depth - v_wide)
    if floor < 1.0:
        depth = v_wide + (c - 1.0) * 0.5
        floor = 1.0

    spec = dict(sysd)
    spec.update(dict(
        a=a, b=b, slot=slot, pitch=pitch, nx=nx, ny=ny,
        xs=xs, ys=ys, depth=depth, chamber_w=c, v_flare=v_flare,
        v_wide=v_wide, floor_w=floor,
    ))
    return spec


def _slot_points(spec):
    """Slot contour relative to the slot centre: (u, v) with v = depth inwards."""
    o = spec['opening'] * 0.5
    mc = spec['mouth_chamfer']
    lip = spec['lip_t']
    c = spec['chamber_w'] * 0.5
    f = spec['floor_w'] * 0.5
    d = spec['depth']
    v_flare = spec['v_flare']
    v_wide = spec['v_wide']
    return [
        (-o - mc, 0.0),
        (-o, mc),
        (-o, lip),
        (-c, v_flare),
        (-c, v_wide),
        (-f, d),
        (f, d),
        (c, v_wide),
        (c, v_flare),
        (o, lip),
        (o, mc),
        (o + mc, 0.0),
    ]


def profile_section(spec, corner_cavity=False, arc_segs=5, bore_segs=24):
    """Outer contour (CCW) and hole contours (CW) of the cross-section."""
    a, b = spec['a'], spec['b']
    r = spec['corner_r']
    slot = _slot_points(spec)

    faces = [
        ((0.0, -1.0), (1.0, 0.0), b * 0.5, a, sorted(spec['xs'])),
        ((1.0, 0.0), (0.0, 1.0), a * 0.5, b, sorted(spec['ys'])),
        ((0.0, 1.0), (-1.0, 0.0), b * 0.5, a, sorted(-x for x in spec['xs'])),
        ((-1.0, 0.0), (0.0, -1.0), a * 0.5, b, sorted(-y for y in spec['ys'])),
    ]

    outer = []
    n_faces = len(faces)
    for k in range(n_faces):
        n, t, half, length, slots = faces[k]

        def P(u, v):
            return (n[0] * (half - v) + t[0] * u, n[1] * (half - v) + t[1] * u)

        u_start = -length * 0.5 + r
        u_end = length * 0.5 - r
        outer.append(P(u_start, 0.0))
        for su in slots:
            if su - spec['chamber_w'] * 0.5 < u_start or su + spec['chamber_w'] * 0.5 > u_end:
                continue  # slot would run into the corner radius, skip it
            for (du, dv) in slot:
                outer.append(P(su + du, dv))
        outer.append(P(u_end, 0.0))

        # corner radius towards the next face
        n2, _t2, half2, _l2, _s2 = faces[(k + 1) % n_faces]
        corner = (n[0] * half + n2[0] * half2, n[1] * half + n2[1] * half2)
        cc = (corner[0] - r * (n[0] + n2[0]), corner[1] - r * (n[1] + n2[1]))
        a0 = math.atan2(n[1], n[0])
        a1 = math.atan2(n2[1], n2[0])
        while a1 <= a0:
            a1 += 2.0 * math.pi
        pts = arc(cc[0], cc[1], r, a0, a1, arc_segs)
        outer.extend(pts[1:-1])

    outer = _dedup(outer)

    holes = []
    br = spec['bore'] * 0.5
    if br > 0.05:
        for x in spec['xs']:
            for y in spec['ys']:
                holes.append(circle(x, y, br, bore_segs, cw=True))

    if corner_cavity:
        cav = spec['pitch'] * 0.14
        inset = spec['pitch'] * 0.15
        rad = cav * 0.18
        if spec['depth'] - (inset + cav * 0.5) > 1.2 and inset - cav * 0.5 > 1.5:
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    holes.append(rounded_rect(
                        sx * (a * 0.5 - inset), sy * (b * 0.5 - inset),
                        cav, cav, rad, segs=3, cw=True))
    return outer, holes


# ==========================================================================
# Extrusion / mesh building
# ==========================================================================

def _triangulate(loops):
    """Constrained Delaunay triangulation over outer contour plus holes.

    Returns (points_2d, triangles); the index list starts with the input points.
    """
    verts = []
    edges = []
    faces = []
    for lp in loops:
        s = len(verts)
        verts.extend(Vector(p) for p in lp)
        edges.extend((s + i, s + (i + 1) % len(lp)) for i in range(len(lp)))
        faces.append(list(range(s, s + len(lp))))

    out_v, _out_e, out_f, orig_v, _oe, _of = delaunay_2d_cdt(verts, edges, faces, 2, 1e-7)

    pts = [(v.x, v.y) for v in verts]
    vmap = []
    for i, orig in enumerate(orig_v):
        if orig:
            vmap.append(orig[0])
        else:
            vmap.append(len(pts))
            pts.append((out_v[i].x, out_v[i].y))

    tris = []
    for f in out_f:
        idx = [vmap[i] for i in f]
        if len(idx) == 3:
            tris.append(idx)
        else:  # fan fallback, does not occur with output type 2
            for i in range(1, len(idx) - 1):
                tris.append([idx[0], idx[i], idx[i + 1]])
    return pts, tris


def extrude_section(loops, z0, z1):
    """Closed solid built from 2D contours between z0 and z1.

    loops[0] is the outer contour (CCW), the rest are holes (CW).
    Returns (verts, faces) in millimetres.
    """
    pts, tris = _triangulate(loops)
    n = len(pts)
    verts = [(p[0], p[1], z0) for p in pts] + [(p[0], p[1], z1) for p in pts]
    faces = []
    for t in tris:
        faces.append([t[2], t[1], t[0]])                  # bottom cap, normal -Z
        faces.append([t[0] + n, t[1] + n, t[2] + n])      # top cap, normal +Z

    offset = 0
    for lp in loops:
        m = len(lp)
        for i in range(m):
            j = (i + 1) % m
            ia, ib = offset + i, offset + j
            faces.append([ia, ib, ib + n, ia + n])
        offset += m
    return verts, faces


def merge(parts):
    """Combine several (verts, faces) pairs into one mesh."""
    verts, faces = [], []
    for v, f in parts:
        o = len(verts)
        verts.extend(v)
        faces.extend([[i + o for i in poly] for poly in f])
    return verts, faces


def transform(part, matrix):
    verts, faces = part
    return [tuple(matrix @ Vector(v)) for v in verts], faces


def write_mesh(me, verts, faces, smooth_angle=math.radians(35.0)):
    """Write mesh data into an existing mesh datablock (mm to metres)."""
    bm = bmesh.new()
    bverts = [bm.verts.new((v[0] * MM, v[1] * MM, v[2] * MM)) for v in verts]
    bm.verts.ensure_lookup_table()
    for poly in faces:
        try:
            bm.faces.new([bverts[i] for i in poly])
        except ValueError:
            pass  # duplicate face, skip
    bm.faces.ensure_lookup_table()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()

    if smooth_angle and len(me.polygons):
        for p in me.polygons:
            p.use_smooth = True
        _mark_sharp_by_angle(me, smooth_angle)
    me.update()
    return me


def _mark_sharp_by_angle(me, angle):
    """Mark edges above the given angle as sharp (replaces legacy auto smooth)."""
    normals = {p.index: Vector(p.normal) for p in me.polygons}
    edge_faces = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            edge_faces.setdefault(ek, []).append(p.index)
    key_to_edge = {e.key: e for e in me.edges}
    for ek, faces in edge_faces.items():
        e = key_to_edge.get(ek)
        if e is None:
            continue
        if len(faces) != 2:
            e.use_edge_sharp = True
            continue
        n1, n2 = normals[faces[0]], normals[faces[1]]
        try:
            ang = n1.angle(n2)
        except ValueError:
            ang = 0.0
        e.use_edge_sharp = ang > angle


# ==========================================================================
# Profile
# ==========================================================================

def profile_mesh(a, b, slot, length, origin='START', corner_cavity=False,
                 arc_segs=5, bore_segs=24):
    spec = resolve_spec(a, b, slot)
    outer, holes = profile_section(spec, corner_cavity, arc_segs, bore_segs)
    if origin == 'CENTER':
        z0, z1 = -length * 0.5, length * 0.5
    elif origin == 'END':
        z0, z1 = -length, 0.0
    else:
        z0, z1 = 0.0, length
    return extrude_section([outer] + holes, z0, z1)


# ==========================================================================
# Primitives for accessories
# ==========================================================================

def box(w, d, h, center=(0.0, 0.0, 0.0)):
    x, y, z = center
    hw, hd, hh = w * 0.5, d * 0.5, h * 0.5
    v = [(x - hw, y - hd, z - hh), (x + hw, y - hd, z - hh),
         (x + hw, y + hd, z - hh), (x - hw, y + hd, z - hh),
         (x - hw, y - hd, z + hh), (x + hw, y - hd, z + hh),
         (x + hw, y + hd, z + hh), (x - hw, y + hd, z + hh)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
         [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return v, f


def cylinder(r, h, segs=24, z0=0.0):
    v = []
    for i in range(segs):
        t = 2.0 * math.pi * i / segs
        v.append((r * math.cos(t), r * math.sin(t), z0))
    for i in range(segs):
        t = 2.0 * math.pi * i / segs
        v.append((r * math.cos(t), r * math.sin(t), z0 + h))
    f = []
    for i in range(1, segs - 1):
        f.append([0, i + 1, i])
        f.append([segs, segs + i, segs + i + 1])
    for i in range(segs):
        j = (i + 1) % segs
        f.append([i, j, j + segs, i + segs])
    return v, f


def plate(w, h, t, holes=(), r=0.0, hole_segs=16):
    """Plate in XY (thickness t along +Z from z=0) with through holes.

    holes: list of (x, y, diameter)
    """
    outer = rounded_rect(0.0, 0.0, w, h, r, segs=4, cw=False)
    loops = [outer]
    for (hx, hy, hd) in holes:
        loops.append(circle(hx, hy, hd * 0.5, hole_segs, cw=True))
    return extrude_section(loops, 0.0, t)


# ==========================================================================
# Accessory meshes
# ==========================================================================

def end_cap_mesh(a, b, slot, thickness=2.0):
    """End cap: cover plate plus pegs that reach into the slots."""
    spec = resolve_spec(a, b, slot)
    r = spec['corner_r']
    parts = [extrude_section([rounded_rect(0, 0, a, b, r, segs=4)], 0.0, thickness)]

    peg_len = min(6.0, spec['depth'] - 1.0)
    pw = spec['opening'] - 0.4
    ph = spec['lip_t'] + 1.2
    for x in spec['xs']:
        for sy in (-1.0, 1.0):
            parts.append(box(pw, ph, peg_len,
                             (x, sy * (b * 0.5 - ph * 0.5 - 0.2), -peg_len * 0.5)))
    for y in spec['ys']:
        for sx in (-1.0, 1.0):
            parts.append(box(ph, pw, peg_len,
                             (sx * (a * 0.5 - ph * 0.5 - 0.2), y, -peg_len * 0.5)))
    return merge(parts)


def bracket_mesh(grid, slot):
    """Angle bracket.

    Leg A lies in XY (mounting face normal +Z, runs towards +Y), leg B stands
    in XZ (mounting face normal +Y, runs towards +Z). The corner sits in the
    local origin.
    """
    sysd = catalog.SLOT_SYSTEMS[slot]
    br = sysd['bracket']
    t = br['thickness']
    hole = br['hole']
    w = grid * 0.95
    leg = grid

    pa = plate(w, leg, t, holes=[(0.0, 0.0, hole)], r=grid * 0.12)
    pa = transform(pa, Matrix.Translation(Vector((0.0, leg * 0.5, 0.0))))

    pb = plate(w, leg - t, t, holes=[(0.0, 0.0, hole)], r=grid * 0.12)
    mb = (Matrix.Translation(Vector((0.0, 0.0, t + (leg - t) * 0.5)))
          @ Matrix.Rotation(math.radians(-90.0), 4, 'X'))
    pb = transform(pb, mb)

    # stiffening rib in the corner
    rib_w = w * 0.25
    rib = grid * 0.55
    rv = [(-rib_w * 0.5, t, t), (-rib_w * 0.5, rib, t), (-rib_w * 0.5, t, rib),
          (rib_w * 0.5, t, t), (rib_w * 0.5, rib, t), (rib_w * 0.5, t, rib)]
    rf = [[0, 2, 1], [3, 4, 5], [0, 1, 4, 3], [1, 2, 5, 4], [2, 0, 3, 5]]
    return merge([pa, pb, (rv, rf)])


def tnut_mesh(slot):
    """T-slot nut with boss; boss points towards +Z, thread along Z."""
    sysd = catalog.SLOT_SYSTEMS[slot]
    bw, bh, bl = sysd['tnut']
    ww, wh = sysd['tnut_web']
    base_h = bh - wh
    thread = 5.0 if slot == 'N5' else 8.0
    body = plate(bw, bl, base_h, holes=[(0.0, 0.0, thread)], r=0.6)
    web = plate(ww, bl, wh, holes=[(0.0, 0.0, thread)], r=0.4)
    web = transform(web, Matrix.Translation(Vector((0.0, 0.0, base_h))))
    return merge([body, web])


def screw_mesh(slot, length):
    """Button head screw: head at z=0 pointing up, shank towards -Z."""
    sysd = catalog.SLOT_SYSTEMS[slot]
    hd = sysd['screw_head_d']
    hh = sysd['screw_head_h']
    shaft_d = 5.0 if slot == 'N5' else 8.0
    head = cylinder(hd * 0.5, hh, 24, z0=0.0)
    shaft = cylinder(shaft_d * 0.5, length, 20, z0=-length)
    return merge([head, shaft])


def bar_connector_mesh(slot, length=None):
    """Slot bar connector; sits inside the slot, length along Z."""
    sysd = catalog.SLOT_SYSTEMS[slot]
    w = sysd['chamber_w'] - 0.6
    h = 4.0 if slot == 'N8' else 2.5
    if length is None:
        length = 180.0 if slot == 'N8' else 45.0
    return box(w, h, length, (0.0, 0.0, 0.0))


def cube_connector_mesh(grid):
    """Three-way cube corner connector."""
    s = grid * 0.7
    parts = [box(s, s, s, (0.0, 0.0, 0.0))]
    peg = grid * 0.28
    plen = grid * 0.45
    parts.append(box(peg, peg, plen, (0.0, 0.0, s * 0.5 + plen * 0.5)))
    parts.append(box(plen, peg, peg, (s * 0.5 + plen * 0.5, 0.0, 0.0)))
    parts.append(box(peg, plen, peg, (0.0, s * 0.5 + plen * 0.5, 0.0)))
    return merge(parts)
