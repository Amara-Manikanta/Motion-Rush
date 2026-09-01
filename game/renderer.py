"""Pseudo-3D projection and neon drawing primitives.

The whole game is drawn with a single perspective divide:

    scale = CAM_FOCAL / (CAM_FOCAL + z)

Everything else -- lane spread, object size, ground height -- falls out of
that one number, which is what makes the flat 2D scene read as depth.
"""

import math

import numpy as np
import pygame

import config as C


class Camera:
    """Projects world coordinates (x lateral, y up, z away) to the screen."""

    __slots__ = ()

    @staticmethod
    def scale_at(z: float) -> float:
        # Clamp just in front of the camera plane so things directly beside
        # the viewer don't explode toward infinity.
        denom = C.CAM_FOCAL + max(z, -C.CAM_FOCAL + 1.0)
        return C.CAM_FOCAL / denom

    @staticmethod
    def project(x: float, y: float, z: float):
        """Return (screen_x, screen_y, scale)."""
        s = Camera.scale_at(z)
        sx = C.SCREEN_W * 0.5 + x * C.PERSPECTIVE_X * s
        sy = C.HORIZON_Y + (C.GROUND_Y - C.HORIZON_Y) * s - y * C.PERSPECTIVE_Y * s
        return sx, sy, s

    @staticmethod
    def is_visible(z: float) -> bool:
        return C.DESPAWN_Z <= z <= C.PLAYER_Z + C.DRAW_DISTANCE + 4.0


def _shade(color, factor: float):
    """Multiply a colour's brightness, clamped to valid range."""
    return (
        max(0, min(255, int(color[0] * factor))),
        max(0, min(255, int(color[1] * factor))),
        max(0, min(255, int(color[2] * factor))),
    )


class NeonPainter:
    """Draws to a base surface plus an additive glow layer.

    Glow is accumulated on its own surface and composited once per frame with
    BLEND_RGB_ADD, which is far cheaper than blitting a soft sprite per shape.
    """

    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        self.glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

    def begin_frame(self):
        self.glow.fill((0, 0, 0, 0))

    def end_frame(self):
        self.surface.blit(self.glow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    # -- primitives ---------------------------------------------------------

    def polygon(self, points, color, glow=0, glow_alpha=70):
        if len(points) < 3:
            return
        pygame.draw.polygon(self.surface, color, points)
        if glow:
            pygame.draw.polygon(self.glow, (*_shade(color, 0.5), glow_alpha),
                                points, glow)

    def line(self, p1, p2, color, width=2, glow=0, glow_alpha=70):
        pygame.draw.line(self.surface, color, p1, p2, max(1, int(width)))
        if glow:
            pygame.draw.line(self.glow, (*_shade(color, 0.5), glow_alpha),
                             p1, p2, max(1, int(width + glow)))

    def circle(self, center, radius, color, glow=0, glow_alpha=80):
        r = max(1, int(radius))
        pygame.draw.circle(self.surface, color, center, r)
        if glow:
            pygame.draw.circle(self.glow, (*_shade(color, 0.6), glow_alpha),
                               center, r + int(glow))

    # -- pseudo-3D volumes --------------------------------------------------

    def box(self, x, width, y_bottom, y_top, z, depth, color,
            glow=4, alpha=255):
        """Draw an axis-aligned world-space box as a solid pseudo-3D block."""
        z_near = z - depth * 0.5
        z_far = z + depth * 0.5
        if z_far < C.DESPAWN_Z:
            return

        hw = width * 0.5
        # Corners: (near|far) x (left|right) x (bottom|top)
        nlb = Camera.project(x - hw, y_bottom, z_near)
        nrb = Camera.project(x + hw, y_bottom, z_near)
        nlt = Camera.project(x - hw, y_top, z_near)
        nrt = Camera.project(x + hw, y_top, z_near)
        flb = Camera.project(x - hw, y_bottom, z_far)
        frb = Camera.project(x + hw, y_bottom, z_far)
        flt = Camera.project(x - hw, y_top, z_far)
        frt = Camera.project(x + hw, y_top, z_far)

        p = lambda t: (t[0], t[1])

        # Far face (darkest), then the top and side faces, then the near face.
        self.polygon([p(flb), p(frb), p(frt), p(flt)], _shade(color, 0.35))
        # Top face is visible because the camera sits above the ground plane.
        self.polygon([p(nlt), p(nrt), p(frt), p(flt)], _shade(color, 0.62))
        # Side faces -- only the one facing the camera centre matters, but
        # drawing both is cheap and correct at the edges of the track.
        self.polygon([p(nlb), p(flb), p(flt), p(nlt)], _shade(color, 0.48))
        self.polygon([p(nrb), p(frb), p(frt), p(nrt)], _shade(color, 0.48))
        # Near face last, full brightness.
        self.polygon([p(nlb), p(nrb), p(nrt), p(nlt)], color)

        if glow:
            outline = [p(nlb), p(nrb), p(nrt), p(nlt)]
            pygame.draw.polygon(self.glow, (*_shade(color, 0.7), 90),
                                outline, max(1, glow))

    def billboard_rect(self, x, width, y_bottom, y_top, z, color, glow=3):
        """A flat quad facing the camera -- used for beams and fields."""
        hw = width * 0.5
        lb = Camera.project(x - hw, y_bottom, z)
        rb = Camera.project(x + hw, y_bottom, z)
        lt = Camera.project(x - hw, y_top, z)
        rt = Camera.project(x + hw, y_top, z)
        pts = [(lb[0], lb[1]), (rb[0], rb[1]), (rt[0], rt[1]), (lt[0], lt[1])]
        self.polygon(pts, color, glow=glow, glow_alpha=110)


def build_background(theme) -> pygame.Surface:
    """Pre-render the static sky/ground gradient once at startup."""
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    horizon = int(C.HORIZON_Y)

    for y in range(0, horizon):
        t = y / max(1, horizon)
        col = (
            int(theme["sky_top"][0] + (theme["sky_bottom"][0] - theme["sky_top"][0]) * t),
            int(theme["sky_top"][1] + (theme["sky_bottom"][1] - theme["sky_top"][1]) * t),
            int(theme["sky_top"][2] + (theme["sky_bottom"][2] - theme["sky_top"][2]) * t),
        )
        pygame.draw.line(surf, col, (0, y), (C.SCREEN_W, y))

    for y in range(horizon, C.SCREEN_H):
        t = (y - horizon) / max(1, C.SCREEN_H - horizon)
        col = (
            int(theme["ground_far"][0] + (theme["ground_near"][0] - theme["ground_far"][0]) * t),
            int(theme["ground_far"][1] + (theme["ground_near"][1] - theme["ground_far"][1]) * t),
            int(theme["ground_far"][2] + (theme["ground_near"][2] - theme["ground_far"][2]) * t),
        )
        pygame.draw.line(surf, col, (0, y), (C.SCREEN_W, y))

    # Soft bloom on the vanishing point. Stacked ellipses left a hard-edged
    # blob, so the falloff is computed per-pixel instead.
    yy, xx = np.mgrid[0:C.SCREEN_H, 0:C.SCREEN_W]
    dx = (xx - C.SCREEN_W * 0.5) / (C.SCREEN_W * 0.62)
    dy = (yy - horizon) / 150.0
    dist = np.sqrt(dx * dx + dy * dy)
    intensity = np.clip(1.0 - dist, 0.0, 1.0) ** 2.4

    bloom = np.zeros((C.SCREEN_W, C.SCREEN_H, 3), dtype=np.uint8)
    glow_col = theme["horizon_glow"]
    for ch in range(3):
        bloom[:, :, ch] = (intensity.T * glow_col[ch]).astype(np.uint8)
    bloom_surf = pygame.surfarray.make_surface(bloom)
    surf.blit(bloom_surf, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    return surf
