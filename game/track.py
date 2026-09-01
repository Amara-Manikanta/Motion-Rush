"""The infinite scrolling track: ground bands, lane lines and edge pillars.

Nothing here is stateful except `distance` -- the illusion of motion comes
entirely from offsetting the world-z of a fixed set of bands by
`distance % RUNG_SPACING`, so the geometry is recycled rather than spawned.
"""

import math

import config as C
from game.renderer import Camera

TRACK_HALF_W = 1.5 * C.LANE_WIDTH + 0.18      # world x of the track edge
POST_X = TRACK_HALF_W + 0.55


class Track:
    def __init__(self):
        self.distance = 0.0
        span = C.DRAW_DISTANCE + C.PLAYER_Z - C.TRACK_NEAR_Z
        self._n_bands = int(span / C.RUNG_SPACING) + 2
        self._n_posts = int(span / C.SIDE_POST_SPACING) + 2

    def reset(self):
        self.distance = 0.0

    def update(self, dt: float, speed: float):
        self.distance += speed * dt

    # -- drawing ------------------------------------------------------------

    def draw(self, painter, theme, speed: float):
        self._draw_bands(painter, theme)
        self._draw_lane_lines(painter, theme)
        self._draw_posts(painter, theme, speed)

    def _draw_bands(self, painter, theme):
        offset = self.distance % C.RUNG_SPACING
        band_index = int(self.distance // C.RUNG_SPACING)

        # Far to near, so nearer bands paint over the ones behind them.
        for i in range(self._n_bands, -1, -1):
            z_near = C.TRACK_NEAR_Z + i * C.RUNG_SPACING - offset
            z_far = z_near + C.RUNG_SPACING
            if z_far < C.TRACK_NEAR_Z:
                continue

            nl = Camera.project(-TRACK_HALF_W, 0.0, max(z_near, C.TRACK_NEAR_Z))
            nr = Camera.project(TRACK_HALF_W, 0.0, max(z_near, C.TRACK_NEAR_Z))
            fl = Camera.project(-TRACK_HALF_W, 0.0, z_far)
            fr = Camera.project(TRACK_HALF_W, 0.0, z_far)

            col = theme["rung"] if (band_index + i) % 2 else theme["rung_alt"]
            painter.polygon([(nl[0], nl[1]), (nr[0], nr[1]),
                             (fr[0], fr[1]), (fl[0], fl[1])], col)

    def _draw_lane_lines(self, painter, theme):
        col = theme["lane_line"]
        # Divider lines sit between lanes; the outer two are the track edges.
        xs = [-TRACK_HALF_W, -0.5 * C.LANE_WIDTH, 0.5 * C.LANE_WIDTH, TRACK_HALF_W]
        steps = 26
        for xi, x in enumerate(xs):
            edge = xi in (0, len(xs) - 1)
            pts = []
            for s in range(steps + 1):
                t = s / steps
                # Sample z quadratically so near segments get more detail.
                z = C.TRACK_NEAR_Z + (C.DRAW_DISTANCE + C.PLAYER_Z - C.TRACK_NEAR_Z) * (t ** 1.7)
                sx, sy, _ = Camera.project(x, 0.0, z)
                pts.append((sx, sy))
            for a, b in zip(pts, pts[1:]):
                # Width tapers with distance, which reinforces the perspective.
                w = 4.0 if edge else 2.0
                painter.line(a, b, col, width=w, glow=3 if edge else 2,
                             glow_alpha=60 if edge else 35)

    def _draw_posts(self, painter, theme, speed: float):
        offset = self.distance % C.SIDE_POST_SPACING
        idx = int(self.distance // C.SIDE_POST_SPACING)
        col = theme["post"]
        # Pillars pulse faster the quicker you go -- a readable speed cue.
        pulse_rate = 2.0 + speed * 0.16

        for i in range(self._n_posts, -1, -1):
            z = C.TRACK_NEAR_Z + i * C.SIDE_POST_SPACING - offset
            if z < C.TRACK_NEAR_Z or z > C.PLAYER_Z + C.DRAW_DISTANCE:
                continue
            lit = 0.55 + 0.45 * math.sin(pulse_rate * self.distance * 0.05 + (idx + i) * 0.9)
            c = (int(col[0] * lit), int(col[1] * lit), int(col[2] * lit))
            for side in (-1, 1):
                painter.box(side * POST_X, 0.22, 0.0, 2.6, z, 0.22, c, glow=4)
