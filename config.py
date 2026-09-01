"""Global configuration for Dash Catalyst.

Everything tunable lives here. Branding and palette are centralised at the top
so the game can be re-themed without touching gameplay code.
"""

# --------------------------------------------------------------------------
# Branding  (change these to re-brand the whole game)
# --------------------------------------------------------------------------
GAME_TITLE = "DASH CATALYST"
GAME_TAGLINE = "OUTRUN THE GRID"
HERO_NAME = "VOLT"
ACTIVE_THEME = "neon_city"

# --------------------------------------------------------------------------
# Display
# --------------------------------------------------------------------------
SCREEN_W = 1280
SCREEN_H = 720
FPS = 60
MAX_DT = 1.0 / 20.0          # clamp dt so a stall can't tunnel through walls

# --------------------------------------------------------------------------
# Pseudo-3D camera
#
# World space: +z runs away from the camera, y is up (0 == ground), x is
# lateral. The camera sits at z=0; the player runs at z=PLAYER_Z.
# Projection is a real perspective divide: scale = FOCAL / (FOCAL + z)
# --------------------------------------------------------------------------
HORIZON_Y = 250.0            # screen y of the vanishing point
GROUND_Y = 900.0             # screen y the ground would hit at z=0
CAM_FOCAL = 9.0
# The camera sits well behind the runner: at PLAYER_Z=5 the character filled
# the lower half of the frame and hid the lane it was standing in.
PLAYER_Z = 8.0
PERSPECTIVE_X = 300.0        # px per world unit of x at scale 1.0
PERSPECTIVE_Y = 170.0        # px per world unit of y at scale 1.0
DRAW_DISTANCE = 130.0        # how far ahead entities are spawned / drawn
# Recycled just behind the runner. The camera sits at z=0, so anything left
# alive further back is between camera and player and blows up into a
# full-width bar across the bottom of the frame.
DESPAWN_Z = PLAYER_Z - 2.0

# The track is scenery, not an entity: it must keep drawing past the runner
# and off the bottom of the frame, so it gets its own near limit.
TRACK_NEAR_Z = 0.6

# --------------------------------------------------------------------------
# Lanes
# --------------------------------------------------------------------------
LANES = (-1, 0, 1)
LANE_WIDTH = 1.35            # world units between lane centres
LANE_SHIFT_SPEED = 9.0       # lanes per second of lateral interpolation

def lane_to_x(lane: float) -> float:
    """Lane index (may be fractional mid-shift) -> world x."""
    return lane * LANE_WIDTH

# --------------------------------------------------------------------------
# Player physics
# --------------------------------------------------------------------------
PLAYER_WIDTH = 0.68
PLAYER_DEPTH = 0.80
PLAYER_STAND_H = 1.80
PLAYER_DUCK_H = 0.90
GRAVITY = 15.0               # world units / s^2   (set by apply_mode)
JUMP_VELOCITY = 9.2          # -> apex ~2.82 units, ~1.23s airtime
DUCK_DURATION = 0.85
COYOTE_TIME = 0.08           # grace period for a late jump input
LATE_GRACE = 0.20            # a gesture landing this late still clears

# --------------------------------------------------------------------------
# Speed / difficulty curve
#
# These are set by apply_mode() below -- the module-level values are the
# active ones and every consumer reads them at runtime.
#
# Pacing is a movement budget, not a taste setting. To clear an obstacle with
# your body you need: camera detection (~130ms) + human reaction (~250ms) +
# the movement itself (a lane slide is ~110ms, a jump ~780ms of airtime).
# EXERCISE mode sizes the gaps so that whole budget fits with room to spare;
# CLASSIC is the arcade pacing, which is genuinely too fast for body control.
# --------------------------------------------------------------------------
MODES = {
    "exercise": dict(
        base_speed=9.0,
        speed_accel=0.05,        # a very gentle ramp -- this is a workout,
        max_speed=16.0,          # not an endurance test of reflexes
        spawn_gap_start=36.0,    # ~4.0s between groups at starting speed
        spawn_gap_min=24.0,      # ~1.5s between groups at top speed
        spawn_gap_decay=0.10,
        first_gap=44.0,
        # A laggy input needs BOTH: a strong launch so the body clears the
        # beam quickly after a late trigger, and low gravity so it stays clear
        # for a long time. Lowering jump velocity to get float was a mistake --
        # it delayed the moment of clearing, which is what actually kills you.
        gravity=15.0,
        jump_velocity=9.2,
        duck_duration=0.85,
        # Known input latency deserves explicit forgiveness: a gesture that
        # lands just after the obstacle still counts.
        late_grace=0.20,
    ),
    "classic": dict(
        base_speed=14.0,
        speed_accel=0.28,
        max_speed=34.0,
        spawn_gap_start=26.0,
        spawn_gap_min=13.0,
        spawn_gap_decay=0.35,
        first_gap=34.0,
        gravity=22.0,
        jump_velocity=8.6,
        duck_duration=0.55,
        late_grace=0.08,
    ),
}

ACTIVE_MODE = "exercise"

BASE_SPEED = 9.0             # world units / second
SPEED_ACCEL = 0.05           # added per second of survival
MAX_SPEED = 16.0

SPAWN_GAP_START = 36.0       # world-z gap between obstacle groups
SPAWN_GAP_MIN = 24.0
SPAWN_GAP_DECAY = 0.10
FIRST_GAP = 44.0             # clear track before the first obstacle


def apply_mode(name: str):
    """Switch the active pacing profile. Consumers read these at runtime."""
    global ACTIVE_MODE, BASE_SPEED, SPEED_ACCEL, MAX_SPEED
    global SPAWN_GAP_START, SPAWN_GAP_MIN, SPAWN_GAP_DECAY, FIRST_GAP
    global GRAVITY, JUMP_VELOCITY, DUCK_DURATION, LATE_GRACE
    if name not in MODES:
        raise ValueError(f"unknown mode {name!r}; expected one of {sorted(MODES)}")
    m = MODES[name]
    ACTIVE_MODE = name
    BASE_SPEED = m["base_speed"]
    SPEED_ACCEL = m["speed_accel"]
    MAX_SPEED = m["max_speed"]
    SPAWN_GAP_START = m["spawn_gap_start"]
    SPAWN_GAP_MIN = m["spawn_gap_min"]
    SPAWN_GAP_DECAY = m["spawn_gap_decay"]
    FIRST_GAP = m["first_gap"]
    GRAVITY = m["gravity"]
    JUMP_VELOCITY = m["jump_velocity"]
    DUCK_DURATION = m["duck_duration"]
    LATE_GRACE = m["late_grace"]


def seconds_between_groups(speed=None) -> float:
    """How long the player gets between obstacle groups at a given speed."""
    return SPAWN_GAP_MIN / (speed or MAX_SPEED)

# --------------------------------------------------------------------------
# Obstacle geometry (world units; y measured from the ground)
# --------------------------------------------------------------------------
BARRIER_H = 2.20             # EnergyBarrier: full height, must change lane
LASER_H = 0.70               # LaserBeam: low, must jump
FIELD_BOTTOM = 1.30          # ForceField: crawl space below this, must duck
FIELD_TOP = 3.00
DRONE_H = 2.00               # HoverDrone: full height and it moves sideways
DRONE_DWELL = 1.15           # seconds held in a lane before hopping
DRONE_HOP_TIME = 0.38        # seconds to slide one lane across

OBSTACLE_DEPTH = 1.10
OBSTACLE_WIDTH = 1.10

# Collision boxes are deliberately smaller than the drawn shapes. Visual
# width 0.85 vs lane width 1.35 leaves only 0.375 units of clearance, which
# makes mid-lane-change contact almost unavoidable. Shrinking the boxes keeps
# near-misses readable as near-misses -- and matters far more once the input
# is a webcam, which is inherently laggier than a key press.
PLAYER_HITBOX_W = 0.78       # fraction of PLAYER_WIDTH used for collision
PLAYER_HITBOX_D = 0.80
OBSTACLE_HITBOX_W = 0.88
OBSTACLE_HITBOX_D = 0.90

# --------------------------------------------------------------------------
# Collectibles
# --------------------------------------------------------------------------
ORB_RADIUS = 0.28
ORB_HOVER_Y = 1.05
ORB_VALUE = 10
ORB_SPIN_SPEED = 3.4
ORB_RUN_LENGTH = 5           # orbs per spawned line
ORB_SPACING = 2.6

# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
DISTANCE_POINTS = 1.0        # score per world unit travelled

# --------------------------------------------------------------------------
# Track decoration
# --------------------------------------------------------------------------
RUNG_SPACING = 6.0           # world-z between ground stripes
SIDE_POST_SPACING = 12.0

# --------------------------------------------------------------------------
# Themes
# --------------------------------------------------------------------------
THEMES = {
    "neon_city": {
        "sky_top":       (6, 4, 26),
        "sky_bottom":    (46, 12, 72),
        "ground_near":   (9, 6, 22),
        "ground_far":    (18, 11, 40),
        "horizon_glow":  (120, 40, 190),
        "lane_line":     (0, 240, 255),
        "rung":          (56, 30, 104),
        "rung_alt":      (33, 19, 68),
        "post":          (255, 40, 150),
        "player":        (0, 255, 200),
        "player_dark":   (0, 150, 130),
        "barrier":       (255, 40, 110),
        "laser":         (255, 190, 40),
        "field":         (120, 90, 255),
        "drone":         (255, 90, 40),
        "orb":           (255, 220, 60),
        "text":          (232, 240, 255),
        "text_dim":      (140, 155, 190),
        "accent":        (0, 240, 255),
        "danger":        (255, 60, 90),
    },
}

def theme():
    return THEMES[ACTIVE_THEME]
