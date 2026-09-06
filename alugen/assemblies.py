"""Assembly generators (frames) with an exact cut list."""

import bpy
from bpy.props import BoolProperty
from mathutils import Vector

from . import builder, catalog
from .geometry import MM


def build_frame(context, X, Y, Z, a, b, slot, levels=0, top=True, bottom=True,
                brackets=True, caps=True, origin=(0.0, 0.0, 0.0), cavity=False):
    """Cuboid frame with the outer dimensions X * Y * Z (mm).

    Layout: four full-height posts, rails butting against them.
    Cut lengths: post = Z, X rail = X - 2*A, Y rail = Y - 2*B.
    """
    ox, oy, oz = origin
    made = dict(posts=[], rails=[], brackets=0, caps=0, warnings=[])

    len_x = X - 2.0 * a
    len_y = Y - 2.0 * b
    if abs(a - b) > 1e-6:
        made['warnings'].append("A and B differ: brackets sit in the middle of the face, "
                                "which may not be a slot on multi-cell profiles")
    for name, val in (("X rail", len_x), ("Y rail", len_y), ("Post", Z)):
        if val < catalog.LEN_MIN:
            made['warnings'].append("%s would be %.1f mm, below the %.0f mm minimum"
                                    % (name, val, catalog.LEN_MIN))

    def loc(x, y, z):
        return ((ox + x) * MM, (oy + y) * MM, (oz + z) * MM)

    # --- posts ---
    if Z >= catalog.LEN_MIN:
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                made['posts'].append(builder.create_profile(
                    context, a, b, slot, Z, 'Z', 'START', cavity,
                    loc(sx * (X * 0.5 - a * 0.5), sy * (Y * 0.5 - b * 0.5), 0.0)))

    # --- rail levels ---
    levels_z = []
    if bottom:
        levels_z.append(('BOTTOM', a * 0.5, b * 0.5))
    if top:
        levels_z.append(('TOP', Z - a * 0.5, Z - b * 0.5))
    for k in range(levels):
        h = Z * (k + 1.0) / (levels + 1.0)
        levels_z.append(('MID', h, h))

    for kind, zx, zy in levels_z:
        # Brackets sit on the top or bottom face of the rail so that the second
        # leg runs along the post.
        n_face = Vector((0.0, 0.0, -1.0 if kind == 'TOP' else 1.0))
        if len_x >= catalog.LEN_MIN:
            for sy in (-1.0, 1.0):
                r = builder.create_profile(
                    context, a, b, slot, len_x, 'X', 'START', cavity,
                    loc(-(X * 0.5 - a), sy * (Y * 0.5 - b * 0.5), zx))
                made['rails'].append((r, n_face, a))   # on X rails, A runs along Z
        if len_y >= catalog.LEN_MIN:
            for sx in (-1.0, 1.0):
                r = builder.create_profile(
                    context, a, b, slot, len_y, 'Y', 'START', cavity,
                    loc(sx * (X * 0.5 - a * 0.5), -(Y * 0.5 - b), zy))
                made['rails'].append((r, n_face, b))   # on Y rails, B runs along Z

    # --- one bracket at each rail end ---
    grid = min(a, b)
    if brackets:
        for rail, n_face, dim in made['rails']:
            if rail.alugen.length < grid + 2.0:
                made['warnings'].append("%s is too short for a bracket (%.0f mm)"
                                        % (rail.name, rail.alugen.length))
                continue
            start, stop = builder.profile_span(rail)
            axis = builder.profile_axis_world(rail)
            for joint, n_b in ((start, axis), (stop, -axis)):
                builder.add_bracket(context, grid, slot,
                                    joint + n_face * (dim * 0.5 * MM), n_face, n_b)
                made['brackets'] += 1

    # --- end caps on the post ends ---
    if caps:
        for p in made['posts']:
            for end in ('START', 'END'):
                builder.add_end_cap(context, p, end)
                made['caps'] += 1

    made['cut'] = dict(post=(len(made['posts']), Z), rail_x=len_x, rail_y=len_y)
    return made


class ALUGEN_OT_build_frame(bpy.types.Operator):
    bl_idname = "alugen.build_frame"
    bl_label = "Build frame"
    bl_description = ("Build a complete cuboid frame with exact outer dimensions: "
                      "posts, rails, brackets and end caps")
    bl_options = {'REGISTER', 'UNDO'}

    at_cursor: BoolProperty(name="At 3D cursor", default=False)

    def execute(self, context):
        s = context.scene.alugen
        a, b = float(s.a), float(s.b)
        origin = (0.0, 0.0, 0.0)
        if self.at_cursor:
            c = context.scene.cursor.location
            origin = (c.x / MM, c.y / MM, c.z / MM)
        made = build_frame(context, s.frame_x, s.frame_y, s.frame_z, a, b, s.slot,
                           s.frame_levels, s.frame_top, s.frame_bottom,
                           s.frame_brackets, s.frame_caps, origin, s.corner_cavity)
        for w in made['warnings']:
            self.report({'WARNING'}, w)
        self.report({'INFO'}, "Frame: %d posts %.1f mm, %d rails, %d brackets, %d caps"
                    % (len(made['posts']), s.frame_z, len(made['rails']),
                       made['brackets'], made['caps']))
        return {'FINISHED'}


CLASSES = (ALUGEN_OT_build_frame,)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
