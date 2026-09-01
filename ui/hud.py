"""In-run HUD: score, orbs, speed."""

import pygame

import config as C
from ui.fonts import draw_text, get_font


class HUD:
    def __init__(self, theme):
        self.theme = theme

    def draw(self, surface, glow, state):
        t = self.theme

        draw_text(surface, f"{int(state.score):,}", 46, t["text"],
                  topright=(C.SCREEN_W - 28, 22), bold=True, glow_surface=glow)
        draw_text(surface, "SCORE", 16, t["text_dim"],
                  topright=(C.SCREEN_W - 28, 74))

        # Orb counter with a small icon.
        pygame.draw.circle(surface, t["orb"], (44, 40), 11)
        pygame.draw.circle(glow, (t["orb"][0] // 2, t["orb"][1] // 2, 0, 110), (44, 40), 18)
        draw_text(surface, f"{state.orbs}", 34, t["orb"],
                  topleft=(64, 22), bold=True)

        draw_text(surface, f"{int(state.distance)} m", 20, t["text_dim"],
                  topleft=(28, 62))

        self._speed_bar(surface, glow, state.speed)
        if C.LIVES > 1:
            self._lives(surface, glow, state)

    def _lives(self, surface, glow, state):
        t = self.theme
        x, y = 30, 130
        draw_text(surface, "LIVES", 13, t["text_dim"], topleft=(x, y + 16))
        for i in range(C.LIVES):
            cx = x + 8 + i * 22
            alive = i < state.lives
            col = t["player"] if alive else (58, 44, 88)
            pygame.draw.circle(surface, col, (cx, y + 6), 7)
            if alive:
                pygame.draw.circle(glow, (*[c // 2 for c in col], 110),
                                   (cx, y + 6), 11)

    def _speed_bar(self, surface, glow, speed):
        t = self.theme
        x, y, w, h = 28, 96, 190, 9
        frac = (speed - C.BASE_SPEED) / max(1e-6, C.MAX_SPEED - C.BASE_SPEED)
        frac = max(0.0, min(1.0, frac))

        pygame.draw.rect(surface, (255, 255, 255, 30), (x, y, w, h), border_radius=4)
        pygame.draw.rect(surface, (40, 30, 70), (x, y, w, h), border_radius=4)
        fill_w = int(w * frac)
        if fill_w > 0:
            col = t["accent"] if frac < 0.75 else t["danger"]
            pygame.draw.rect(surface, col, (x, y, fill_w, h), border_radius=4)
            pygame.draw.rect(glow, (col[0] // 2, col[1] // 2, col[2] // 2, 100),
                             (x - 2, y - 2, fill_w + 4, h + 4), border_radius=5)
        draw_text(surface, "SPEED", 13, t["text_dim"], topleft=(x, y + 14))
