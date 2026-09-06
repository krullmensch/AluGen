"""Reference data: slot systems, profile sizes and generic accessory types.

All dimensions are millimetres. The numbers describe the widely used I-type
(also sold as "B-type") aluminium extrusion standard with 5 mm and 8 mm slots.
Suppliers differ in the internal details of the slot, so every value here is a
single source of truth you can re-measure and adjust: the whole cross-section
is generated from this table.
"""

# --------------------------------------------------------------------------
# Slot systems
# --------------------------------------------------------------------------
# opening       : slot mouth width (clear width between the slot lips)
# mouth_chamfer : chamfer at the outer slot edge
# lip_t         : thickness of the slot lip (straight part of the mouth)
# flare_v       : depth gained by the transition from mouth to slot chamber
# chamber_w     : inner width of the slot chamber (T-nut width plus clearance)
# depth         : nominal slot depth from the outer face to the slot floor
# floor_w       : width of the slot floor; a 45 degree run-out connects the two
# web           : minimum web left towards the slot of the neighbouring face
# bore          : core bore (for M5 / M8 self-tapping screws)
# corner_r      : outer corner radius
# min_wall      : minimum wall between the slot floor and the core bore
SLOT_SYSTEMS = {
    'N5': dict(
        label="Slot 5",
        opening=5.2, mouth_chamfer=0.4, lip_t=1.6, flare_v=1.0,
        chamber_w=8.6, depth=6.5, floor_w=3.5, web=0.8,
        bore=4.2, corner_r=1.5, min_wall=1.6,
        tnut=(7.7, 4.7, 12.0),      # T-slot nut: width x height x length
        tnut_web=(4.6, 1.6),        # boss: width x height
        screw="M5", screw_head_d=9.5, screw_head_h=2.7,
        bracket=dict(thickness=4.0, hole=4.5),
        threads=("M3", "M4", "M5"),
        default_thread="M5",
    ),
    'N8': dict(
        label="Slot 8",
        opening=8.2, mouth_chamfer=0.6, lip_t=2.0, flare_v=1.5,
        chamber_w=14.0, depth=10.5, floor_w=6.0, web=0.8,
        bore=6.8, corner_r=2.0, min_wall=2.0,
        tnut=(13.5, 7.2, 22.0),
        tnut_web=(7.8, 2.5),
        screw="M8", screw_head_d=14.0, screw_head_h=4.4,
        bracket=dict(thickness=8.0, hole=9.0),
        threads=("M5", "M6", "M8"),
        default_thread="M8",
    ),
}

# Common profile edge sizes
SIZES = (20.0, 30.0, 40.0, 80.0)

# Sanity limits for a cut length. Most cut-to-size services stay inside this
# range; adjust if your supplier differs.
LEN_MIN = 15.0
LEN_MAX = 5000.0
CUT_TOLERANCE = 1.0  # typical sawing tolerance in mm, informational only

MATERIAL = "EN AW-6060 / AlMgSi, anodised"


def default_slot(a, b):
    """Usual slot for a given size: 20 mm profiles use slot 5, larger slot 8."""
    return 'N5' if max(a, b) <= 20.0 else 'N8'


# --------------------------------------------------------------------------
# Accessory types
# --------------------------------------------------------------------------
# Generic part descriptions, independent of any supplier. The parts list groups
# by part id, so the id has to carry every ordering-relevant detail.

# Profile sizes end caps are commonly stocked for
COMMON_CAP_SIZES = {
    (20.0, 20.0, 'N5'),
    (30.0, 30.0, 'N8'),
    (40.0, 40.0, 'N8'),
    (40.0, 80.0, 'N8'),
    (80.0, 80.0, 'N8'),
}

# Grid sizes angle bracket sets are commonly stocked for
COMMON_BRACKET_GRIDS = {
    'N5': (20.0,),
    'N8': (30.0, 40.0, 80.0),
}


def cap_part(a, b, slot):
    """Part id and label for an end cap."""
    lo, hi = min(a, b), max(a, b)
    pid = "CAP-%s-%gx%g" % (slot, lo, hi)
    label = "End cap %gx%g, %s" % (lo, hi, SLOT_SYSTEMS[slot]['label'].lower())
    common = (lo, hi, slot) in COMMON_CAP_SIZES
    return pid, label, common


def bracket_part(grid, slot):
    """Part id and label for an angle bracket set (bracket plus fasteners)."""
    pid = "BRACKET-%s-%g" % (slot, grid)
    label = ("Angle bracket set %gx%g, %s (incl. 2 screws and 2 T-slot nuts)"
             % (grid, grid, SLOT_SYSTEMS[slot]['label'].lower()))
    common = grid in COMMON_BRACKET_GRIDS.get(slot, ())
    return pid, label, common


def tnut_part(slot, thread=None):
    sysd = SLOT_SYSTEMS[slot]
    thread = thread or sysd['default_thread']
    w, h, l = sysd['tnut']
    pid = "TNUT-%s-%s" % (slot, thread)
    label = ("T-slot nut %s %g x %g x %g mm, thread %s"
             % (sysd['label'].lower(), w, h, l, thread))
    return pid, label, thread in sysd['threads']


def bar_connector_part(slot, length):
    pid = "BARCON-%s-%g" % (slot, length)
    label = ("Slot bar connector %s, %g mm, with grub screws"
             % (SLOT_SYSTEMS[slot]['label'].lower(), length))
    return pid, label, True


def butt_connector_part(slot):
    sysd = SLOT_SYSTEMS[slot]
    pid = "BUTTCON-%s" % slot
    label = ("Butt joint connector set %s (%s socket screw into the core bore)"
             % (sysd['label'].lower(), sysd['screw']))
    return pid, label, True


def cube_connector_part(grid, slot):
    pid = "CUBECON-%s-%g" % (slot, grid)
    label = ("Cube corner connector %gx%g, %s, three-way"
             % (grid, grid, SLOT_SYSTEMS[slot]['label'].lower()))
    return pid, label, grid in (40.0, 80.0)
