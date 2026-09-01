"""Webcam body control, exposed through the same InputManager interface.

Lane control is *positional*, not incremental: the player's body zone maps
directly onto a lane, and this emits whatever LEFT/RIGHT steps are needed to
close the gap. Leaning and holding therefore keeps you in that lane, which is
what a body naturally expects -- an edge-triggered mapping would drift out of
sync the moment a frame was dropped.

Keyboard events still pass through, so ESC/restart/pause always work even when
the camera is driving the game.
"""

import pygame

import config as C
from input.input_manager import Action, InputManager
from input.keyboard_input import KeyboardInput
from vision.calibration import Calibrator
from vision.gesture_detector import GestureDetector
from vision.pose_tracker import (PoseTracker, L_SHOULDER, R_SHOULDER,
                                 L_HIP, R_HIP, NOSE)
from vision.telemetry import GestureLog

PREVIEW_POINTS = (NOSE, L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)


class GestureInput(InputManager):
    name = "camera"

    def __init__(self, camera_index=0, preview=True, log=True):
        self.tracker = PoseTracker(camera_index=camera_index)
        self.tracker.start()

        self.calibrator = Calibrator()
        self.detector = GestureDetector(self.calibrator.profile)
        self.keyboard = KeyboardInput()

        self.preview_enabled = preview
        self._surface = None
        self._zone = 0
        self.state = None
        self.calibrating = True
        self.log = GestureLog(enabled=log)
        self._logged_header = False

    # -- InputManager -------------------------------------------------------

    def handle_event(self, event):
        action = self.keyboard.handle_event(event)
        if action is Action.RECALIBRATE or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_k):
            self.restart_calibration()
            return None
        return action

    def poll(self, dt: float):
        frame = self.tracker.latest()

        if self.calibrating:
            self.calibrator.update(dt, frame)
            if self.calibrator.done:
                self.finish_calibration()
            self._refresh_preview(frame)
            return ()

        state = self.detector.update(frame, dt)
        self.state = state
        self._refresh_preview(frame)

        if not self._logged_header:
            self.log.session_header(self.detector.profile,
                                    self.tracker.reported_fps)
            self._logged_header = True
        seen, hits = self.tracker.stats()
        self.log.write(state, seen, hits)

        if not state.tracked:
            return ()

        actions = []
        delta = state.lane_zone - self._zone
        if delta:
            step = Action.RIGHT if delta > 0 else Action.LEFT
            actions.extend([step] * abs(delta))
            self._zone = state.lane_zone
        if state.jump:
            actions.append(Action.JUMP)
        if state.duck:
            actions.append(Action.DUCK)
        return actions

    @property
    def camera_status(self):
        return self.tracker.status

    def debug_lines(self):
        seen, hits = self.tracker.stats()
        prof = self.detector.profile
        if self.calibrating:
            return (f"input: camera  CALIBRATING {self.calibrator.step.name}",
                    f"camera {self.tracker.status}  frames {seen}  poses {hits}")
        s = self.state
        if s is None:
            return ("input: camera  (starting up)",)
        return (
            f"input: camera   frames {seen}  poses {hits}",
            f"tracked {s.tracked}  zone {s.lane_zone:+d} (raw {s.raw_zone:+d})",
            f"lean {s.lean:+.2f}sw  rise {s.rise:+.2f}sw  "
            f"vel {s.rise_vel:+.2f}sw/s",
            f"camera {self.tracker.reported_fps:.0f}fps  log {self.log.path}",
            f"thresholds: {prof.describe()}",
        )

    def close(self):
        self.log.close()
        self.tracker.close()

    # -- calibration --------------------------------------------------------

    def restart_calibration(self):
        self.calibrator.reset()
        self.calibrating = True

    def skip_calibration(self):
        self.calibrator.skip()
        self.finish_calibration()

    def finish_calibration(self):
        self.calibrating = False
        self.detector.set_profile(self.calibrator.profile)
        self._zone = 0
        self.log.note(f"calibration done: {self.calibrator.profile.describe()}")

    # -- preview ------------------------------------------------------------

    def preview_surface(self):
        return self._surface if self.preview_enabled else None

    def _refresh_preview(self, frame):
        if not self.preview_enabled:
            return
        arr = self.tracker.preview_array()
        if arr is None:
            return
        # make_surface wants (width, height, 3); the capture is (h, w, 3).
        surf = pygame.surfarray.make_surface(arr.swapaxes(0, 1))
        if frame is not None:
            self._draw_skeleton(surf, frame)
        self._surface = surf

    def _draw_skeleton(self, surf, frame):
        theme = C.theme()
        w, h = surf.get_size()

        def pt(idx):
            lm = frame.landmarks[idx]
            return int(lm[0] * w), int(lm[1] * h)

        for a, b in ((L_SHOULDER, R_SHOULDER), (L_HIP, R_HIP),
                     (L_SHOULDER, L_HIP), (R_SHOULDER, R_HIP)):
            if frame.visible(a, 0.5) and frame.visible(b, 0.5):
                pygame.draw.line(surf, theme["accent"], pt(a), pt(b), 2)
        for idx in PREVIEW_POINTS:
            if frame.visible(idx, 0.5):
                pygame.draw.circle(surf, theme["orb"], pt(idx), 3)

        # Neutral line and the live shoulder midpoint, so the player can see
        # exactly how far they are leaning relative to their calibration.
        prof = self.detector.profile
        nx = int(prof.neutral_x * w)
        pygame.draw.line(surf, theme["text_dim"], (nx, 0), (nx, h), 1)
        if frame.visible(L_SHOULDER, 0.5) and frame.visible(R_SHOULDER, 0.5):
            mx, my = frame.midpoint(L_SHOULDER, R_SHOULDER)
            pygame.draw.circle(surf, theme["player"],
                               (int(mx * w), int(my * h)), 5)
