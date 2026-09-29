"""Live camera setup screen.

Positioning is the single biggest lever on gesture reliability -- more than the
camera itself -- so this exists to be looked at while you physically move the
camera, rather than to be read afterwards in a log.
"""

import pygame

import config as C
from ui.fonts import draw_text
from vision.gesture_detector import FRAMING_IDEAL, FRAMING_MIN, FRAMING_MAX

PREVIEW_W = 560


class CameraCheck:
    def __init__(self, theme):
        self.theme = theme
        self.t = 0.0
        self.best_seen = 0.0
        self.worst_seen = 9.0

    def update(self, dt, width):
        self.t += dt
        if width > 0:
            self.best_seen = max(self.best_seen, width)
            self.worst_seen = min(self.worst_seen, width)

    def draw(self, surface, glow, preview, state, fps, status, size=None):
        t = self.theme
        surface.fill((7, 4, 22))
        cx = C.SCREEN_W // 2

        draw_text(surface, "CAMERA SETUP", 40, t["text"], center=(cx, 44),
                  bold=True, glow_surface=glow)
        draw_text(surface, "Move the camera until the bar sits in the green band",
                  17, t["text_dim"], center=(cx, 82))

        self._preview(surface, preview, state, status, cx)
        self._gauge(surface, glow, state, cx)
        self._stats(surface, state, fps, cx, size)

        draw_text(surface, "SPACE  continue to calibration     •     ESC  quit",
                  16, t["text_dim"], center=(cx, C.SCREEN_H - 28))

    def _preview(self, surface, preview, state, status, cx):
        t = self.theme
        top = 108
        h = int(PREVIEW_W * 0.75)
        rect = pygame.Rect(0, 0, PREVIEW_W, h)
        rect.midtop = (cx, top)
        if preview is None:
            pygame.draw.rect(surface, (18, 12, 38), rect, border_radius=10)
            msg = ("camera access denied" if status == "denied"
                   else "waiting for camera…")
            draw_text(surface, msg, 20, t["text_dim"], center=rect.center)
        else:
            scaled = pygame.transform.smoothscale(preview, (PREVIEW_W, h))
            surface.blit(scaled, rect)
        ok = state is not None and state.tracked
        pygame.draw.rect(surface, t["accent"] if ok else t["danger"],
                         rect.inflate(6, 6), width=3, border_radius=8)
        if not ok:
            draw_text(surface, "no body detected", 19, t["danger"],
                      center=(cx, rect.bottom + 22), bold=True)

    def _gauge(self, surface, glow, state, cx):
        """Shoulder width as a fraction of frame -- the distance proxy."""
        t = self.theme
        x, y, w, h = cx - 300, 560, 600, 26
        lo, hi = 0.0, 0.50

        def px(v):
            return x + int(w * (v - lo) / (hi - lo))

        pygame.draw.rect(surface, (26, 18, 48), (x, y, w, h), border_radius=6)
        # usable range, then the ideal band inside it
        pygame.draw.rect(surface, (44, 32, 76),
                         (px(FRAMING_MIN), y, px(FRAMING_MAX) - px(FRAMING_MIN), h))
        good = pygame.Rect(px(FRAMING_IDEAL[0]), y,
                           px(FRAMING_IDEAL[1]) - px(FRAMING_IDEAL[0]), h)
        pygame.draw.rect(surface, (0, 110, 80), good)
        pygame.draw.rect(surface, t["player"], good, width=2)

        draw_text(surface, "TOO FAR", 13, t["text_dim"], topleft=(x + 4, y + h + 6))
        draw_text(surface, "GOOD", 13, t["player"],
                  center=(good.centerx, y + h + 14), bold=True)
        draw_text(surface, "TOO CLOSE", 13, t["text_dim"],
                  topright=(x + w - 4, y + h + 6))

        if state is not None and state.tracked and state.width > 0:
            mx = max(x, min(x + w, px(state.width)))
            pygame.draw.polygon(surface, t["accent"],
                                [(mx, y - 10), (mx - 9, y - 24), (mx + 9, y - 24)])
            pygame.draw.line(surface, t["accent"], (mx, y), (mx, y + h), 3)
            pygame.draw.line(glow, (*[c // 2 for c in t["accent"]], 120),
                             (mx, y - 4), (mx, y + h + 4), 7)

    def _stats(self, surface, state, fps, cx, size=None):
        t = self.theme
        y = 624
        verdict = {
            "good": ("GOOD FRAMING", t["player"]),
            "too_far": ("MOVE CLOSER", t["danger"]),
            "too_close": ("STEP BACK", t["danger"]),
        }.get(getattr(state, "framing", "unknown"), ("POSITION YOURSELF", t["text_dim"]))
        draw_text(surface, verdict[0], 30, verdict[1], center=(cx, y), bold=True)

        w = getattr(state, "width", 0.0) or 0.0
        bits = [f"shoulder width {w:.3f}", f"camera {fps:.0f} fps"]
        if size and size[0]:
            ratio = size[0] / max(1, size[1])
            bits.append(f"{size[0]}x{size[1]} ({'4:3' if abs(ratio-4/3)<0.05 else '16:9' if abs(ratio-16/9)<0.05 else f'{ratio:.2f}'})")
        if self.worst_seen < 9.0:
            spread = self.best_seen / max(1e-4, self.worst_seen)
            bits.append(f"distance spread {spread:.1f}x")
        draw_text(surface, "     •     ".join(bits), 16, t["text_dim"],
                  center=(cx, y + 32))
