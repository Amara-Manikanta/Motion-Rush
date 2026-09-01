"""Obstacles.

One pooled class with a `kind` tag rather than a subclass per type: the
spawner recycles a fixed array of these, and a single concrete type keeps the
pool homogeneous. Geometry per kind lives in KIND_GEOMETRY.
"""

import math
from enum import Enum

import config as C


class ObstacleKind(Enum):
    ENERGY_BARRIER = "energy_barrier"   # full height -> change lane
    LASER_BEAM = "laser_beam"           # low         -> jump
    FORCE_FIELD = "force_field"         # high        -> duck
    HOVER_DRONE = "hover_drone"         # moves       -> change lane


# kind -> (y_bottom, y_top, width, depth, colour key)
KIND_GEOMETRY = {
    ObstacleKind.ENERGY_BARRIER: (0.0, C.BARRIER_H, C.OBSTACLE_WIDTH, C.OBSTACLE_DEPTH, "barrier"),
    ObstacleKind.LASER_BEAM:     (0.0, C.LASER_H, 1.30, 0.36, "laser"),
    ObstacleKind.FORCE_FIELD:    (C.FIELD_BOTTOM, C.FIELD_TOP, 1.30, 0.36, "field"),
    ObstacleKind.HOVER_DRONE:    (0.0, C.DRONE_H, C.OBSTACLE_WIDTH, C.OBSTACLE_DEPTH, "drone"),
}

#: How the player is expected to survive each kind -- used by the spawner to
#: guarantee that every generated pattern is actually clearable.
AVOIDANCE = {
    ObstacleKind.ENERGY_BARRIER: "dodge",
    ObstacleKind.LASER_BEAM: "jump",
    ObstacleKind.FORCE_FIELD: "duck",
    ObstacleKind.HOVER_DRONE: "dodge",
}


class Obstacle:
    __slots__ = ("kind", "lane", "lane_pos", "z", "active",
                 "drone_dir", "phase", "y_bottom", "y_top", "width", "depth",
                 "color_key", "drone_from", "drone_to", "drone_t", "drone_wait")

    def __init__(self):
        self.active = False
        self.kind = ObstacleKind.ENERGY_BARRIER
        self.lane = 0
        self.lane_pos = 0.0
        self.z = 0.0
        self.drone_dir = 1.0
        self.phase = 0.0
        self.drone_from = 0.0
        self.drone_to = 0.0
        self.drone_t = 0.0
        self.drone_wait = 0.0
        self._apply_geometry()

    def _apply_geometry(self):
        (self.y_bottom, self.y_top, self.width,
         self.depth, self.color_key) = KIND_GEOMETRY[self.kind]

    def spawn(self, kind: ObstacleKind, lane: int, z: float):
        self.kind = kind
        self.lane = lane
        self.lane_pos = float(lane)
        self.z = z
        self.active = True
        self.drone_dir = 1.0 if lane <= 0 else -1.0
        self.phase = 0.0
        self.drone_from = float(lane)
        self.drone_to = float(lane)
        self.drone_t = 1.0
        self.drone_wait = C.DRONE_DWELL
        self._apply_geometry()

    # -- update -------------------------------------------------------------

    def update(self, dt: float, speed: float):
        if not self.active:
            return
        self.z -= speed * dt
        self.phase += dt

        if self.kind is ObstacleKind.HOVER_DRONE:
            self._update_drone(dt)

        if self.z < C.DESPAWN_Z:
            self.active = False

    def _update_drone(self, dt: float):
        """Discrete lane hops with a dwell, not a continuous sweep.

        A drone that slides smoothly across the track is effectively a moving
        wall the player cannot read; hopping lane-to-lane with a pause gives a
        clear "it is in that lane now" signal and a window to commit to.
        """
        if self.drone_t < 1.0:
            self.drone_t = min(1.0, self.drone_t + dt / C.DRONE_HOP_TIME)
            # Smoothstep so the hop reads as deliberate rather than linear.
            e = self.drone_t * self.drone_t * (3.0 - 2.0 * self.drone_t)
            self.lane_pos = self.drone_from + (self.drone_to - self.drone_from) * e
            if self.drone_t >= 1.0:
                self.lane_pos = self.drone_to
                self.drone_wait = C.DRONE_DWELL
            return

        self.drone_wait -= dt
        if self.drone_wait <= 0.0:
            nxt = self.drone_to + self.drone_dir
            if nxt > C.LANES[-1] or nxt < C.LANES[0]:
                self.drone_dir *= -1.0
                nxt = self.drone_to + self.drone_dir
            self.drone_from = self.drone_to
            self.drone_to = float(nxt)
            self.drone_t = 0.0

    def is_off_screen(self) -> bool:
        return self.z < C.DESPAWN_Z

    # -- collision ----------------------------------------------------------

    def bounds(self):
        """World-space AABB as (x0, x1, y0, y1, z0, z1)."""
        x = C.lane_to_x(self.lane_pos)
        hw = self.width * C.OBSTACLE_HITBOX_W * 0.5
        hd = self.depth * C.OBSTACLE_HITBOX_D * 0.5
        return (x - hw, x + hw,
                self.y_bottom, self.y_top,
                self.z - hd, self.z + hd)

    # -- drawing ------------------------------------------------------------

    def draw(self, painter, theme):
        if not self.active:
            return
        x = C.lane_to_x(self.lane_pos)
        col = theme[self.color_key]

        if self.kind is ObstacleKind.ENERGY_BARRIER:
            painter.box(x, self.width, 0.0, self.y_top, self.z, self.depth,
                        col, glow=6)
            # Pulsing band so it reads as energy rather than concrete.
            pulse = 0.5 + 0.5 * math.sin(self.phase * 5.0)
            band = self.y_top * (0.35 + 0.25 * pulse)
            painter.billboard_rect(x, self.width * 1.02, band, band + 0.14,
                                   self.z - self.depth * 0.51,
                                   theme["accent"], glow=6)

        elif self.kind is ObstacleKind.LASER_BEAM:
            # Emitter posts either side make the beam's extent obvious.
            for side in (-1, 1):
                painter.box(x + side * self.width * 0.52, 0.20, 0.0,
                            self.y_top + 0.18, self.z, 0.24,
                            theme["post"], glow=3)
            n = 3
            for i in range(n):
                t = (i + 1) / (n + 1)
                yy = self.y_top * t
                flick = 0.75 + 0.25 * math.sin(self.phase * 14.0 + i)
                painter.billboard_rect(
                    x, self.width, yy - 0.045, yy + 0.045, self.z,
                    (int(col[0] * flick), int(col[1] * flick), int(col[2] * flick)),
                    glow=7)

        elif self.kind is ObstacleKind.FORCE_FIELD:
            for side in (-1, 1):
                painter.box(x + side * self.width * 0.52, 0.20, 0.0,
                            self.y_top, self.z, 0.24, theme["post"], glow=3)
            # Horizontal scan lines instead of a solid fill: cheaper, and it
            # keeps the crawl space underneath visually open.
            rows = 7
            for i in range(rows):
                t = i / (rows - 1)
                yy = self.y_bottom + (self.y_top - self.y_bottom) * t
                shimmer = 0.6 + 0.4 * math.sin(self.phase * 4.0 + i * 0.8)
                painter.billboard_rect(
                    x, self.width, yy - 0.05, yy + 0.05, self.z,
                    (int(col[0] * shimmer), int(col[1] * shimmer), int(col[2] * shimmer)),
                    glow=4)
            painter.billboard_rect(x, self.width, self.y_bottom - 0.07,
                                   self.y_bottom, self.z, theme["danger"], glow=6)

        elif self.kind is ObstacleKind.HOVER_DRONE:
            bob = math.sin(self.phase * 3.0) * 0.10
            painter.box(x, self.width, 0.55 + bob, self.y_top + bob, self.z,
                        self.depth, col, glow=6)
            # Thruster glow under the chassis.
            painter.billboard_rect(x, self.width * 0.55, 0.18 + bob, 0.52 + bob,
                                   self.z - self.depth * 0.5,
                                   theme["accent"], glow=7)
