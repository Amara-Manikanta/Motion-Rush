"""Title, pause and game-over screens."""

import math

import pygame

import config as C
from ui.fonts import draw_text


def _scrim(surface, alpha=170):
    veil = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    veil.fill((4, 2, 16, alpha))
    surface.blit(veil, (0, 0))


class Menu:
    def __init__(self, theme):
        self.theme = theme
        self.t = 0.0

    def update(self, dt):
        self.t += dt

    # -- title --------------------------------------------------------------

    def draw_title(self, surface, glow, input_name, best_score):
        t = self.theme
        _scrim(surface, 150)
        cx = C.SCREEN_W // 2

        pulse = 0.75 + 0.25 * math.sin(self.t * 2.4)
        accent = tuple(int(c * pulse) for c in t["accent"])

        draw_text(surface, C.GAME_TITLE, 92, t["text"], center=(cx, 190),
                  bold=True, glow_surface=glow)
        draw_text(surface, C.GAME_TAGLINE, 24, accent, center=(cx, 250))

        draw_text(surface, f"Run as {C.HERO_NAME}. Don't stop.", 20,
                  t["text_dim"], center=(cx, 316))

        rows = [
            ("MOVE", "A / D   or   ← →"),
            ("JUMP", "W  /  ↑  /  SPACE"),
            ("DUCK", "S  /  ↓"),
            ("PAUSE", "P"),
            ("CAMERA", "G  to use body control"),
            ("FULLSCREEN", "F  /  F11"),
            ("PACE", f"M  —  now: {C.ACTIVE_MODE.upper()}"),
        ]
        y = 372
        for label, keys in rows:
            draw_text(surface, label, 18, t["text_dim"], topright=(cx - 24, y))
            draw_text(surface, keys, 18, t["text"], topleft=(cx + 24, y))
            y += 32

        if best_score:
            draw_text(surface, f"BEST  {int(best_score):,}", 22, t["orb"],
                      center=(cx, y + 18), bold=True)

        blink = 0.5 + 0.5 * math.sin(self.t * 4.0)
        col = tuple(int(c * (0.45 + 0.55 * blink)) for c in t["text"])
        draw_text(surface, "PRESS  SPACE  TO  RUN", 30, col,
                  center=(cx, C.SCREEN_H - 118), bold=True, glow_surface=glow)
        draw_text(surface, f"input: {input_name}", 15, t["text_dim"],
                  center=(cx, C.SCREEN_H - 72))

    # -- game over ----------------------------------------------------------

    def draw_game_over(self, surface, glow, state, best_score, is_best):
        t = self.theme
        _scrim(surface, 190)
        cx = C.SCREEN_W // 2

        draw_text(surface, "RUN TERMINATED", 60, t["danger"], center=(cx, 190),
                  bold=True, glow_surface=glow)

        draw_text(surface, f"{int(state.score):,}", 96, t["text"],
                  center=(cx, 300), bold=True, glow_surface=glow)
        draw_text(surface, "FINAL SCORE", 18, t["text_dim"], center=(cx, 358))

        stats = [
            ("DISTANCE", f"{int(state.distance)} m"),
            ("ORBS", f"{state.orbs}"),
            ("TOP SPEED", f"{state.speed:.1f}"),
        ]
        y = 412
        for label, value in stats:
            draw_text(surface, label, 18, t["text_dim"], topright=(cx - 20, y))
            draw_text(surface, value, 18, t["text"], topleft=(cx + 20, y))
            y += 30

        if is_best:
            pulse = 0.6 + 0.4 * math.sin(self.t * 6.0)
            draw_text(surface, "NEW BEST", 30,
                      tuple(int(c * pulse) for c in t["orb"]),
                      center=(cx, y + 24), bold=True, glow_surface=glow)
        elif best_score:
            draw_text(surface, f"BEST  {int(best_score):,}", 20, t["text_dim"],
                      center=(cx, y + 24))

        blink = 0.5 + 0.5 * math.sin(self.t * 4.0)
        col = tuple(int(c * (0.45 + 0.55 * blink)) for c in t["text"])
        draw_text(surface, "R  TO  RUN  AGAIN", 30, col,
                  center=(cx, C.SCREEN_H - 96), bold=True, glow_surface=glow)

    # -- pause --------------------------------------------------------------

    def draw_paused(self, surface, glow):
        t = self.theme
        _scrim(surface, 160)
        cx = C.SCREEN_W // 2
        draw_text(surface, "PAUSED", 68, t["text"], center=(cx, C.SCREEN_H // 2 - 20),
                  bold=True, glow_surface=glow)
        draw_text(surface, "P to resume    •    ESC to quit", 20, t["text_dim"],
                  center=(cx, C.SCREEN_H // 2 + 42))
