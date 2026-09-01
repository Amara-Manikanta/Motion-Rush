"""Calibration: turn a few seconds of posing into per-player thresholds.

Everything is expressed in *shoulder-width units* rather than raw image
fractions, so the profile stays valid when the player steps closer to or
further from the camera mid-run.
"""

import time
from dataclasses import dataclass, field
from enum import Enum

from vision.pose_tracker import L_SHOULDER, R_SHOULDER


@dataclass
class CalibrationProfile:
    """Neutral pose plus the thresholds derived from the player's own range."""
    neutral_x: float = 0.5
    neutral_y: float = 0.42
    lean_threshold: float = 0.45      # shoulder-widths sideways to switch lane
    jump_threshold: float = 0.26      # shoulder-widths up to trigger a jump
    duck_threshold: float = 0.38      # shoulder-widths down to trigger a duck
    calibrated: bool = False
    weak: bool = False                # the player barely moved; thresholds
                                      # fell back to their floors

    def describe(self):
        tag = "" if self.calibrated else "  (defaults)"
        if self.weak:
            tag = "  (WEAK - movements were small)"
        return (f"lean {self.lean_threshold:.2f}  "
                f"jump {self.jump_threshold:.2f}  duck {self.duck_threshold:.2f}"
                + tag)


class Step(Enum):
    NEUTRAL = "Stand still, arms relaxed"
    LEFT = "Lean LEFT"
    RIGHT = "Lean RIGHT"
    JUMP = "JUMP (or stretch up tall)"
    DUCK = "CROUCH down"
    DONE = "Calibration complete"


ORDER = [Step.NEUTRAL, Step.LEFT, Step.RIGHT, Step.JUMP, Step.DUCK, Step.DONE]

HOLD_SECONDS = 1.6          # sampling window per step
LEAD_SECONDS = 1.5          # countdown before sampling starts
#: Fraction of the player's demonstrated range used as the trigger point.
#: Well under half, because during play they move faster and less deliberately
#: than they do while posing for the calibration screen.
TRIGGER_FRACTION = 0.42


class Calibrator:
    """Drives the guided calibration sequence and builds a profile."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.index = 0
        self.elapsed = 0.0
        self.samples = {s: [] for s in ORDER}
        self.profile = CalibrationProfile()
        self.weak_steps = []
        self._failed = False

    # -- state --------------------------------------------------------------

    @property
    def step(self) -> Step:
        return ORDER[self.index]

    @property
    def done(self) -> bool:
        return self.step is Step.DONE

    @property
    def sampling(self) -> bool:
        return self.elapsed >= LEAD_SECONDS

    @property
    def countdown(self) -> float:
        return max(0.0, LEAD_SECONDS - self.elapsed)

    @property
    def progress(self) -> float:
        if not self.sampling:
            return 0.0
        return min(1.0, (self.elapsed - LEAD_SECONDS) / HOLD_SECONDS)

    def sample_count(self) -> int:
        return len(self.samples[self.step])

    # -- feeding ------------------------------------------------------------

    def update(self, dt: float, frame):
        """Advance the sequence. `frame` may be None when no body is visible."""
        if self.done:
            return

        self.elapsed += dt
        if self.sampling and frame is not None:
            if frame.visible(L_SHOULDER, 0.5) and frame.visible(R_SHOULDER, 0.5):
                mx, my = frame.midpoint(L_SHOULDER, R_SHOULDER)
                self.samples[self.step].append((mx, my, frame.shoulder_width))

        if self.elapsed >= LEAD_SECONDS + HOLD_SECONDS:
            self._finish_step()

    def _finish_step(self):
        self.index = min(self.index + 1, len(ORDER) - 1)
        self.elapsed = 0.0
        if self.done:
            self._build_profile()

    def skip(self):
        """Abandon calibration and keep the defaults."""
        self.index = len(ORDER) - 1
        self.elapsed = 0.0
        self.profile = CalibrationProfile()

    # -- profile ------------------------------------------------------------

    @staticmethod
    def _mean(rows):
        """Median, not mean -- a couple of mis-detected frames would otherwise
        drag a whole step's average and silently distort the profile."""
        if not rows:
            return None
        import statistics
        return (statistics.median(r[0] for r in rows),
                statistics.median(r[1] for r in rows),
                statistics.median(r[2] for r in rows))

    def _build_profile(self):
        neutral = self._mean(self.samples[Step.NEUTRAL])
        if neutral is None:
            self.profile = CalibrationProfile()      # never saw a body
            return

        nx, ny, nw = neutral
        nw = max(1e-4, nw)
        p = CalibrationProfile(neutral_x=nx, neutral_y=ny, calibrated=True)

        # Sideways range: use whichever direction the player committed to less,
        # so the easier side doesn't set an unreachable threshold on the other.
        weak = []
        spans = []
        for step in (Step.LEFT, Step.RIGHT):
            m = self._mean(self.samples[step])
            if m is not None:
                spans.append(abs(m[0] - nx) / nw)
        if spans:
            raw = min(spans) * TRIGGER_FRACTION
            p.lean_threshold = max(0.16, raw)
            if raw < 0.16:
                weak.append("lean")

        up = self._mean(self.samples[Step.JUMP])
        if up is not None:
            # Image y grows downward, so a jump makes it smaller.
            rise = max(0.0, (ny - up[1]) / nw)
            if rise > 0.05:
                raw = rise * TRIGGER_FRACTION
                p.jump_threshold = max(0.10, raw)
                if raw < 0.10:
                    weak.append("jump")
            else:
                weak.append("jump")

        down = self._mean(self.samples[Step.DUCK])
        if down is not None:
            drop = max(0.0, (down[1] - ny) / nw)
            if drop > 0.05:
                raw = drop * TRIGGER_FRACTION
                p.duck_threshold = max(0.14, raw)
                if raw < 0.14:
                    weak.append("duck")
            else:
                weak.append("duck")

        p.weak = bool(weak)
        self.weak_steps = weak
        self.profile = p
