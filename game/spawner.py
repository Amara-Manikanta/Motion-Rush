"""Pattern-based obstacle/orb spawning with pooling and difficulty scaling.

Every pattern is run through `pattern_is_survivable()` before it is used, so
the game can never generate a wall the player has no legal answer to. Orb runs
are then laid down the safe lane, which doubles as a readable hint.
"""

import random

import config as C
from game.obstacle import Obstacle, ObstacleKind
from game.collectible import DataOrb

K = ObstacleKind

OBSTACLE_POOL_SIZE = 48
ORB_POOL_SIZE = 120

# A pattern is a list of (kind, lane, z_offset). z_offset is world units
# beyond the group's anchor z.
PATTERNS = [
    # (min_difficulty, weight, entries)
    (0.0, 10, [(K.ENERGY_BARRIER, -1, 0.0)]),
    (0.0, 10, [(K.ENERGY_BARRIER, 0, 0.0)]),
    (0.0, 10, [(K.ENERGY_BARRIER, 1, 0.0)]),
    (0.0,  8, [(K.LASER_BEAM, -1, 0.0), (K.LASER_BEAM, 0, 0.0), (K.LASER_BEAM, 1, 0.0)]),
    (0.0,  8, [(K.FORCE_FIELD, -1, 0.0), (K.FORCE_FIELD, 0, 0.0), (K.FORCE_FIELD, 1, 0.0)]),

    (0.15, 9, [(K.ENERGY_BARRIER, -1, 0.0), (K.ENERGY_BARRIER, 0, 0.0)]),
    (0.15, 9, [(K.ENERGY_BARRIER, 0, 0.0), (K.ENERGY_BARRIER, 1, 0.0)]),
    (0.15, 7, [(K.ENERGY_BARRIER, -1, 0.0), (K.ENERGY_BARRIER, 1, 0.0)]),
    (0.15, 7, [(K.LASER_BEAM, 0, 0.0), (K.ENERGY_BARRIER, 1, 0.0)]),
    (0.15, 7, [(K.FORCE_FIELD, 0, 0.0), (K.ENERGY_BARRIER, -1, 0.0)]),

    (0.35, 7, [(K.HOVER_DRONE, -1, 0.0)]),
    (0.35, 7, [(K.HOVER_DRONE, 1, 0.0)]),
    (0.35, 6, [(K.LASER_BEAM, -1, 0.0), (K.LASER_BEAM, 0, 0.0), (K.LASER_BEAM, 1, 0.0),
               (K.ENERGY_BARRIER, 0, 9.0)]),
    (0.35, 6, [(K.ENERGY_BARRIER, -1, 0.0), (K.ENERGY_BARRIER, 0, 6.0),
               (K.ENERGY_BARRIER, 1, 12.0)]),

    (0.55, 6, [(K.FORCE_FIELD, -1, 0.0), (K.FORCE_FIELD, 0, 0.0), (K.FORCE_FIELD, 1, 0.0),
               (K.LASER_BEAM, -1, 18.0), (K.LASER_BEAM, 0, 18.0), (K.LASER_BEAM, 1, 18.0)]),
    (0.55, 5, [(K.ENERGY_BARRIER, -1, 0.0), (K.ENERGY_BARRIER, 1, 0.0),
               (K.LASER_BEAM, 0, 8.0)]),
    (0.55, 5, [(K.HOVER_DRONE, 0, 0.0), (K.ENERGY_BARRIER, -1, 10.0)]),
    (0.75, 5, [(K.ENERGY_BARRIER, -1, 0.0), (K.ENERGY_BARRIER, 0, 0.0),
               (K.FORCE_FIELD, 1, 0.0), (K.LASER_BEAM, 1, 9.0)]),
]

#: z tolerance for treating two obstacles as "the same wall".
_Z_BUCKET = 3.0

#: Minimum world-z between two *timed* actions (jump/duck) in the same lane.
#: At MAX_SPEED this is ~0.5s, which is the floor for a fair reaction window
#: -- and well above it for a camera-driven player, who is slower than a key.
MIN_ACTION_GAP_Z = 16.0


def _slice_pattern(entries):
    """Group entries into z-ordered slices: [(z, {lane: [kinds]})]."""
    buckets = {}
    for kind, lane, dz in entries:
        key = round(dz / _Z_BUCKET)
        slot = buckets.setdefault(key, (dz, {}))
        slot[1].setdefault(lane, []).append(kind)
    return [buckets[k] for k in sorted(buckets)]


def _lane_demand(kinds):
    """What a lane asks of the player at one slice: None | 'jump' | 'duck' | 'blocked'."""
    if not kinds:
        return None
    if K.ENERGY_BARRIER in kinds or K.HOVER_DRONE in kinds:
        return "blocked"
    if K.LASER_BEAM in kinds and K.FORCE_FIELD in kinds:
        return "blocked"          # cannot jump and duck at the same instant
    if K.LASER_BEAM in kinds:
        return "jump"
    if K.FORCE_FIELD in kinds:
        return "duck"
    return None


def _max_lane_moves(dz: float) -> int:
    """How many lanes can be crossed over `dz` world units at worst-case speed."""
    if dz <= 0.0:
        return 0
    return int(C.LANE_SHIFT_SPEED * dz / C.MAX_SPEED)


def _route_exists(slices, entry_lane: int) -> bool:
    """Can the player start in `entry_lane` and get through every slice?"""
    states = {entry_lane: -1e9}          # lane -> z of last timed action
    prev_z = None

    for z, lane_map in slices:
        if prev_z is not None:
            budget = _max_lane_moves(z - prev_z)
            expanded = {}
            for lane, last_act in states.items():
                for target in C.LANES:
                    if abs(target - lane) <= budget:
                        # Keep the earliest last-action: more recovery time.
                        if target not in expanded or last_act < expanded[target]:
                            expanded[target] = last_act
            states = expanded

        survivors = {}
        for lane, last_act in states.items():
            demand = _lane_demand(lane_map.get(lane, []))
            if demand == "blocked":
                continue
            if demand in ("jump", "duck"):
                if z - last_act < MIN_ACTION_GAP_Z:
                    continue          # no time to recover from the last action
                survivors[lane] = z
            else:
                survivors[lane] = last_act

        if not survivors:
            return False
        states = survivors
        prev_z = z

    return True


def solve_pattern(entries):
    """Return the set of lanes the player can safely enter this pattern in.

    Weaving counts: a route may cross lanes between slices, budgeted by the
    distance available at MAX_SPEED. Each entry lane is traced independently,
    since collapsing them would lose viable starts.
    """
    slices = _slice_pattern(entries)
    if not slices:
        return set(C.LANES)
    return {lane for lane in C.LANES if _route_exists(slices, lane)}


def pattern_is_survivable(entries) -> bool:
    return bool(solve_pattern(entries))


def safe_lanes(entries):
    """Viable entry lanes, preferring ones that start on empty track."""
    viable = solve_pattern(entries)
    if not viable:
        return []
    first = _slice_pattern(entries)[0][1] if entries else {}
    empty = [l for l in C.LANES if l in viable and not first.get(l)]
    rest = [l for l in C.LANES if l in viable and first.get(l)]
    return empty + rest


class Spawner:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.obstacles = [Obstacle() for _ in range(OBSTACLE_POOL_SIZE)]
        self.orbs = [DataOrb() for _ in range(ORB_POOL_SIZE)]
        self.reset()

    def reset(self):
        for o in self.obstacles:
            o.active = False
        for o in self.orbs:
            o.active = False
        self.distance = 0.0
        self.elapsed = 0.0
        # Give the player a moment of clear track before the first wall.
        self.next_group_at = C.FIRST_GAP

    # -- pool helpers -------------------------------------------------------

    def _free_obstacle(self):
        for o in self.obstacles:
            if not o.active:
                return o
        return None

    def _free_orb(self):
        for o in self.orbs:
            if not o.active:
                return o
        return None

    # -- difficulty ---------------------------------------------------------

    @property
    def difficulty(self) -> float:
        """0.0 at the start, saturating at 1.0 after ~110 seconds."""
        return min(1.0, self.elapsed / 110.0)

    @property
    def group_gap(self) -> float:
        gap = C.SPAWN_GAP_START - self.elapsed * C.SPAWN_GAP_DECAY
        return max(C.SPAWN_GAP_MIN, gap)

    # -- spawning -----------------------------------------------------------

    def _choose_pattern(self):
        d = self.difficulty
        pool = [(w, e) for (mind, w, e) in PATTERNS if mind <= d]
        total = sum(w for w, _ in pool)
        pick = self.rng.uniform(0, total)
        upto = 0.0
        for w, entries in pool:
            upto += w
            if pick <= upto:
                return entries
        return pool[-1][1]

    def _spawn_group(self, anchor_z: float):
        entries = self._choose_pattern()
        if not pattern_is_survivable(entries):
            # Defensive: a bad table entry degrades to a single barrier rather
            # than an unwinnable wall.
            entries = [(K.ENERGY_BARRIER, self.rng.choice(C.LANES), 0.0)]

        max_dz = 0.0
        for kind, lane, dz in entries:
            ob = self._free_obstacle()
            if ob is None:
                break
            ob.spawn(kind, lane, anchor_z + dz)
            max_dz = max(max_dz, dz)

        self._spawn_orbs(entries, anchor_z, max_dz)
        return max_dz

    def _spawn_orbs(self, entries, anchor_z: float, max_dz: float):
        lanes = safe_lanes(entries)
        if not lanes:
            return
        lane = lanes[0]

        # Does the safe lane need a jump? If so, arc the orbs over the beam.
        jump_zs = [anchor_z + dz for kind, ln, dz in entries
                   if ln == lane and kind is K.LASER_BEAM]

        start_z = anchor_z - C.ORB_SPACING * (C.ORB_RUN_LENGTH + 1)
        for i in range(C.ORB_RUN_LENGTH):
            orb = self._free_orb()
            if orb is None:
                return
            orb.spawn(lane, start_z + i * C.ORB_SPACING)

        # A second run trailing the group keeps the safe route rewarding.
        if max_dz > 0.0:
            tail_z = anchor_z + max_dz + C.ORB_SPACING * 2
            for i in range(3):
                orb = self._free_orb()
                if orb is None:
                    return
                orb.spawn(lane, tail_z + i * C.ORB_SPACING)

    def update(self, dt: float, speed: float):
        self.elapsed += dt
        self.distance += speed * dt

        if self.distance >= self.next_group_at:
            self._spawn_group(C.PLAYER_Z + C.DRAW_DISTANCE)
            self.next_group_at = self.distance + self.group_gap

        for o in self.obstacles:
            o.update(dt, speed)
        for o in self.orbs:
            o.update(dt, speed)

    # -- iteration ----------------------------------------------------------

    def active_obstacles(self):
        return [o for o in self.obstacles if o.active]

    def active_orbs(self):
        return [o for o in self.orbs if o.active]
