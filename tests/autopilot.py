"""A scripted player, used to verify the game is winnable and the loop is sound.

Two things make it competent rather than merely reactive:

* it only ever steps **one** lane at a time, and refuses a step unless the
  destination stays clear for as long as the slide takes -- a two-lane dash
  physically transits the middle lane, which a naive planner ignores;
* it scores only obstacles that are still ahead. Counting ones already behind
  makes a clear lane look lethal and pins the bot in place.
"""

import config as C
from game.obstacle import ObstacleKind as K
from game.player import PlayerState
from input.input_manager import Action

BLOCKING = (K.ENERGY_BARRIER, K.HOVER_DRONE)
TIMED = (K.LASER_BEAM, K.FORCE_FIELD)

_P_HALF = C.PLAYER_WIDTH * C.PLAYER_HITBOX_W * 0.5


def _occupies(ob, lane) -> bool:
    """Would this obstacle overlap a player standing in `lane`?"""
    lane_x = C.lane_to_x(lane)
    b = ob.bounds()
    return b[0] < lane_x + _P_HALF and b[1] > lane_x - _P_HALF


def _ahead(gm, lane, horizon):
    """Obstacles still in front of the player that occupy `lane`."""
    return [o for o in gm.spawner.active_obstacles()
            if 0.0 < (o.z - C.PLAYER_Z) <= horizon and _occupies(o, lane)]


def _lead_needed(kind, speed):
    """World-z head start required to perform the action for `kind`."""
    if kind is K.LASER_BEAM:
        return speed * 0.42          # rise clear before the beam arrives
    if kind is K.FORCE_FIELD:
        return speed * 0.24
    return 0.0


def _lane_cost(gm, lane, horizon, speed):
    cost = 0.0
    for ob in _ahead(gm, lane, horizon):
        gap = max(0.5, ob.z - C.PLAYER_Z)
        if ob.kind in BLOCKING or gap < _lead_needed(ob.kind, speed):
            cost += 400.0 / gap
        else:
            cost += 25.0 / gap
    return cost


def _transit_safe(gm, target, speed, extra_lead=0.0) -> bool:
    """Can the player finish sliding into `target` before anything arrives?"""
    slide_z = speed / C.LANE_SHIFT_SPEED      # distance covered during a slide
    window = slide_z * 1.8 + 1.5 + extra_lead
    for ob in _ahead(gm, target, window):
        if ob.kind in BLOCKING:
            return False
        if (ob.z - C.PLAYER_Z) < _lead_needed(ob.kind, speed):
            return False
    return True


class LaggyPilot:
    """The autopilot with an input delay, to model body control honestly.

    A camera player does not act the instant an obstacle becomes avoidable:
    pose detection costs ~130ms and human reaction another ~250ms. Testing
    pacing without that delay flatters the game.
    """

    def __init__(self, latency_s=0.38, compensate=True):
        self.latency = latency_s
        # compensate=False models a player who has not learned to lead their
        # gestures yet -- the worst realistic case, and the one that decides
        # whether the game is welcoming on a first session.
        self.compensate = compensate
        self.queue = []          # [(due_time, action)]
        self.clock = 0.0

    def step(self, gm, dt):
        self.clock += dt
        # A player who knows their input is laggy leads their gestures. Passing
        # the latency in separates "the game is unfair" from "the bot is naive".
        decided = choose_action(
            gm, extra_lead_s=self.latency if self.compensate else 0.0)
        if decided is not None:
            self.queue.append((self.clock + self.latency, decided))
        ready = [a for (due, a) in self.queue if due <= self.clock]
        self.queue = [(d, a) for (d, a) in self.queue if d > self.clock]
        return ready


def choose_action(gm, extra_lead_s=0.0):
    p = gm.player
    speed = max(1e-3, gm.run.speed)
    lane = p.lane
    horizon = max(30.0, speed * 1.7)
    lead_bonus = speed * extra_lead_s

    # 1. A timed threat in the committed lane takes priority over repositioning.
    for ob in sorted(_ahead(gm, lane, speed * 1.0), key=lambda o: o.z):
        gap = ob.z - C.PLAYER_Z
        if ob.kind in BLOCKING:
            break                          # must move; fall through to planning
        lead = _lead_needed(ob.kind, speed) + lead_bonus
        if ob.kind is K.LASER_BEAM:
            return Action.JUMP if (gap <= lead and p.on_ground) else None
        if ob.kind is K.FORCE_FIELD:
            if gap <= lead and p.on_ground and p.state is not PlayerState.DUCKING:
                return Action.DUCK
            return None

    # 2. Reposition, one lane at a time, only into a lane we can reach in time.
    costs = {l: _lane_cost(gm, l, horizon, speed) for l in C.LANES}
    reachable = [adj for adj in (lane - 1, lane + 1)
                 if adj in C.LANES and _transit_safe(gm, adj, speed, lead_bonus)]

    # Staying in a lane with a wall in it is certain death, so vacate while a
    # move is still possible even if the destination scores slightly worse.
    # Waiting for a strictly cheaper lane is how a planner traps itself.
    blocking_ahead = [o for o in _ahead(gm, lane, horizon) if o.kind in BLOCKING]
    if blocking_ahead and reachable:
        nearest = min(o.z - C.PLAYER_Z for o in blocking_ahead)
        best_adj = min(reachable, key=lambda l: (costs[l], abs(l - lane)))
        must_go_now = nearest < speed * 1.3
        if must_go_now or costs[best_adj] < costs[lane] - 1e-6:
            return Action.LEFT if best_adj < lane else Action.RIGHT

    best = min([lane] + reachable, key=lambda l: (costs[l], abs(l - lane)))
    if best != lane and costs[best] < costs[lane] - 1e-6:
        return Action.LEFT if best < lane else Action.RIGHT
    return None
