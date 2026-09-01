"""Font loading, plus additive-safe text glow."""

import numpy as np
import pygame

_CACHE = {}
_GLOW_CACHE = {}
# Preferred first; SysFont falls back to the default face if none are present.
_PREFERRED = "menlo,dejavusansmono,couriernew,monospace"


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _CACHE:
        _CACHE[key] = pygame.font.SysFont(_PREFERRED, size, bold=bold)
    return _CACHE[key]


def _premultiplied(text, size, bold, color):
    """A text surface whose RGB is scaled by its own alpha.

    pygame renders glyphs with the text colour in *every* pixel and encodes
    coverage purely in the alpha channel. BLEND_RGB_ADD ignores alpha, so
    adding such a surface lights up the whole bounding box as a solid slab.
    Premultiplying first makes the additive blit follow the glyph shapes.
    """
    key = (text, size, bold, color)
    cached = _GLOW_CACHE.get(key)
    if cached is not None:
        return cached

    img = get_font(size, bold).render(text, True, color).convert_alpha()
    rgb = pygame.surfarray.pixels3d(img)
    alpha = pygame.surfarray.pixels_alpha(img)
    rgb[:] = (rgb * (alpha[:, :, None].astype(np.float32) / 255.0)).astype(np.uint8)
    del rgb, alpha

    if len(_GLOW_CACHE) > 512:            # bounded: strings here are few
        _GLOW_CACHE.clear()
    _GLOW_CACHE[key] = img
    return img


def draw_text(surface, text, size, color, center=None, topleft=None,
              topright=None, bold=False, glow_surface=None):
    font = get_font(size, bold)
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = center
    elif topright:
        rect.topright = topright
    else:
        rect.topleft = topleft or (0, 0)

    if glow_surface is not None:
        faint = _premultiplied(text, size, bold,
                               (color[0] // 3, color[1] // 3, color[2] // 3))
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            glow_surface.blit(faint, rect.move(dx, dy),
                              special_flags=pygame.BLEND_RGB_ADD)

    surface.blit(img, rect)
    return rect
