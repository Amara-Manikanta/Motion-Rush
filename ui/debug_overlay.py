"""F3 overlay -- frame timing and live input-source state."""

import pygame

import config as C
from ui.fonts import draw_text


class DebugOverlay:
    def __init__(self, theme):
        self.theme = theme

    def draw(self, surface, lines):
        if not lines:
            return
        pad = 8
        box = pygame.Surface((330, 20 * len(lines) + pad * 2), pygame.SRCALPHA)
        box.fill((0, 0, 0, 150))
        surface.blit(box, (16, C.SCREEN_H - box.get_height() - 16))

        y = C.SCREEN_H - box.get_height() - 16 + pad
        for line in lines:
            draw_text(surface, line, 15, self.theme["text_dim"], topleft=(16 + pad, y))
            y += 20
