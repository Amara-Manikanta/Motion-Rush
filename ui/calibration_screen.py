"""The guided calibration screen shown before a camera-controlled run."""

import math

import pygame

import config as C
from ui.fonts import draw_text
from vision.calibration import ORDER, Step

PREVIEW_W = 420


class CalibrationScreen:
    def __init__(self, theme):
        self.theme = theme
        self.t = 0.0

    def update(self, dt):
        self.t += dt

    def draw(self, surface, glow, calibrator, preview, tracked,
             camera_status="ok"):
        t = self.theme
        cx = C.SCREEN_W // 2

        veil = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        veil.fill((4, 2, 16, 215))
        surface.blit(veil, (0, 0))

        draw_text(surface, "CALIBRATION", 46, t["text"], center=(cx, 62),
                  bold=True, glow_surface=glow)
        draw_text(surface, "Stand back so your head and hips are both in frame",
                  17, t["text_dim"], center=(cx, 104))

        self._draw_preview(surface, glow, preview, tracked, camera_status)
        self._draw_step(surface, glow, calibrator, cx)
        self._draw_dots(surface, calibrator, cx)

        draw_text(surface, "SPACE  skip and use defaults     •     ESC  quit",
                  16, t["text_dim"], center=(cx, C.SCREEN_H - 34))

    # -- pieces -------------------------------------------------------------

    def _draw_preview(self, surface, glow, preview, tracked,
                      camera_status="ok"):
        t = self.theme
        cx = C.SCREEN_W // 2
        top = 140
        if preview is None:
            box = pygame.Rect(0, 0, PREVIEW_W, int(PREVIEW_W * 0.75))
            box.midtop = (cx, top)
            pygame.draw.rect(surface, (18, 12, 38), box, border_radius=10)
            pygame.draw.rect(surface, t["text_dim"], box, width=2, border_radius=10)
            if camera_status == "denied":
                draw_text(surface, "camera access denied", 20, t["danger"],
                          center=(box.centerx, box.centery - 14), bold=True)
                draw_text(surface, "System Settings > Privacy & Security > Camera",
                          15, t["text_dim"], center=(box.centerx, box.centery + 14))
            else:
                draw_text(surface, "waiting for camera…", 18, t["text_dim"],
                          center=(box.centerx, box.centery - 12))
                draw_text(surface, "allow access if macOS asks", 15, t["text_dim"],
                          center=(box.centerx, box.centery + 14))
            return

        scaled = pygame.transform.smoothscale(
            preview, (PREVIEW_W, int(PREVIEW_W * preview.get_height()
                                     / preview.get_width())))
        rect = scaled.get_rect(midtop=(cx, top))
        surface.blit(scaled, rect)

        edge = t["accent"] if tracked else t["danger"]
        pygame.draw.rect(surface, edge, rect.inflate(6, 6), width=3,
                         border_radius=8)
        if not tracked:
            draw_text(surface, "no body detected", 18, t["danger"],
                      center=(cx, rect.bottom + 20), bold=True)

    def _draw_step(self, surface, glow, calibrator, cx):
        t = self.theme
        y = 500
        step = calibrator.step

        if step is Step.DONE:
            draw_text(surface, "CALIBRATED", 44, t["player"], center=(cx, y),
                      bold=True, glow_surface=glow)
            return

        draw_text(surface, step.value, 40, t["text"], center=(cx, y),
                  bold=True, glow_surface=glow)

        if not calibrator.sampling:
            n = math.ceil(calibrator.countdown)
            pulse = 1.0 - (calibrator.countdown % 1.0)
            size = int(30 + 26 * pulse)
            draw_text(surface, f"{n}", size, t["accent"],
                      center=(cx, y + 62), bold=True, glow_surface=glow)
            draw_text(surface, "get into position", 16, t["text_dim"],
                      center=(cx, y + 100))
            return

        # Sampling: a bar that fills over the hold window.
        w, h = 380, 12
        x = cx - w // 2
        yy = y + 54
        pygame.draw.rect(surface, (36, 24, 66), (x, yy, w, h), border_radius=6)
        fill = int(w * calibrator.progress)
        if fill:
            pygame.draw.rect(surface, t["player"], (x, yy, fill, h),
                             border_radius=6)
            pygame.draw.rect(glow, (*[c // 2 for c in t["player"]], 110),
                             (x - 2, yy - 2, fill + 4, h + 4), border_radius=7)
        draw_text(surface, f"hold it…  {calibrator.sample_count()} samples",
                  16, t["text_dim"], center=(cx, yy + 32))

    def _draw_dots(self, surface, calibrator, cx):
        t = self.theme
        steps = [s for s in ORDER if s is not Step.DONE]
        gap = 34
        start = cx - (len(steps) - 1) * gap // 2
        for i, s in enumerate(steps):
            done = ORDER.index(s) < calibrator.index
            active = s is calibrator.step
            col = t["player"] if done else (t["accent"] if active else (60, 46, 96))
            pygame.draw.circle(surface, col, (start + i * gap, 618),
                               8 if active else 6)
