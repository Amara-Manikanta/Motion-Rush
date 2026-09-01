"""Data orbs -- the collectible, pooled the same way obstacles are."""

import math

import config as C
from game.renderer import Camera


class DataOrb:
    __slots__ = ("lane", "z", "active", "spin", "collected_flash")

    def __init__(self):
        self.active = False
        self.lane = 0
        self.z = 0.0
        self.spin = 0.0
        self.collected_flash = 0.0

    def spawn(self, lane: int, z: float):
        self.lane = lane
        self.z = z
        self.active = True
        self.spin = (z * 0.7) % (math.pi * 2)   # de-sync orbs in a line
        self.collected_flash = 0.0

    def update(self, dt: float, speed: float):
        if not self.active:
            return
        self.z -= speed * dt
        self.spin += C.ORB_SPIN_SPEED * dt
        if self.z < C.DESPAWN_Z:
            self.active = False

    def bounds(self):
        x = C.lane_to_x(self.lane)
        r = C.ORB_RADIUS
        # A slightly generous z/height box -- orbs should feel easy to grab,
        # unlike obstacles which are tight.
        return (x - r * 1.6, x + r * 1.6,
                C.ORB_HOVER_Y - r * 2.2, C.ORB_HOVER_Y + r * 2.2,
                self.z - r * 1.8, self.z + r * 1.8)

    def draw(self, painter, theme):
        if not self.active:
            return
        x = C.lane_to_x(self.lane)
        sx, sy, scale = Camera.project(x, C.ORB_HOVER_Y, self.z)
        if scale <= 0.01:
            return

        # The "spin" is a horizontal squash cycle -- cheap, and reads clearly
        # as a rotating coin at every distance.
        squash = abs(math.cos(self.spin))
        rx = max(1.0, C.ORB_RADIUS * C.PERSPECTIVE_X * scale * (0.25 + 0.75 * squash))
        ry = max(1.0, C.ORB_RADIUS * C.PERSPECTIVE_Y * scale)
        col = theme["orb"]

        import pygame
        rect = pygame.Rect(0, 0, int(rx * 2), int(ry * 2))
        rect.center = (int(sx), int(sy))
        pygame.draw.ellipse(painter.surface, col, rect)
        pygame.draw.ellipse(painter.surface,
                            (min(255, col[0]), min(255, col[1] + 30), 200), rect, 2)

        grect = rect.inflate(int(6 + 10 * scale), int(6 + 10 * scale))
        pygame.draw.ellipse(painter.glow, (col[0] // 2, col[1] // 2, col[2] // 3, 110), grect)
