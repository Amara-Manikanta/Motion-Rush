"""Landmark -> gesture classification.

Four things keep this fast without making it twitchy:

* **shoulder-width normalisation** -- all offsets are measured in units of the
  player's own shoulder width, so stepping toward or away from the camera does
  not change the thresholds;
* **velocity triggers** -- a jump fires on upward *speed*, not just height.
  A real jump begins with a downward counter-movement, so a height-only
  trigger has to sit through the dip and then wait for the body to climb past
  the threshold, which lands near the apex. Speed peaks at takeoff, which is
  far earlier -- this is worth well over 100ms.
* **adaptive smoothing** -- the filter opens up when the signal moves fast, so
  a deliberate gesture passes through almost unfiltered while breathing and
  sway stay damped;
* **hysteresis + refractory** -- leaving a lane zone needs a smaller offset
  than entering it, and jump/duck must return toward neutral before re-firing.
"""

import math
from dataclasses import dataclass

from vision.pose_tracker import L_SHOULDER, R_SHOULDER, L_HIP, R_HIP

EXIT_RATIO = 0.55          # fraction of the entry threshold needed to leave
COMMIT_TIME = 0.12         # seconds a new lane zone must persist to be accepted
#: Once a lane is taken, hold it briefly before another change is allowed.
#: Without this a player hovering near the boundary produced 0.1s zone flips --
#: 22 of 119 holds in one real session were under a third of a second.
MIN_ZONE_DWELL = 0.30
RELEASE_RATIO = 0.5        # return this far toward neutral to re-arm jump/duck
REFRACTORY = 0.28          # seconds before the same vertical gesture re-fires
VISIBILITY = 0.6

# Adaptive filter: alpha rises toward 1.0 (no smoothing) as movement gets
# faster, so gestures are responsive while idle noise stays damped.
BASE_ALPHA = 0.30
ADAPT_SCALE = 0.15         # per-frame delta (shoulder-widths) that fully opens it

# Velocity triggers, in shoulder-widths per second.
JUMP_VELOCITY = 1.00
DUCK_VELOCITY = 1.40
# ...but the body must already have travelled this fraction of the displacement
# threshold. Without it, the downward dip that *precedes* a jump reads as a
# duck, and camera noise spikes read as gestures.
# The jump gate is *negative*: at the moment of takeoff the body is still
# below neutral, coming out of the counter-movement dip. Requiring positive
# height here would throw away the earliest and clearest part of the signal.
JUMP_VEL_GATE = -0.45
DUCK_VEL_GATE = 0.50
# Velocity is derived from the *raw* signal, not the smoothed one. Taking the
# derivative of an already-filtered value stacks two lags and was costing ~35ms
# on its own -- the smoothed curve did not cross the threshold until well after
# the raw motion had.
VEL_SMOOTH = 0.55

# --- Posture baseline -------------------------------------------------------
# Gestures are measured against a slowly-adapting baseline, not the frozen
# neutral captured during calibration. Real sessions drift: the player stands
# further back, shifts weight, or simply held a different posture while being
# calibrated. A frozen neutral turns that drift into a permanent offset -- and
# once the offset exceeds the duck threshold the detector latches into "down"
# and jump, which is only tested from neutral, can never fire again.
BASELINE_TAU = 2.5         # seconds; how fast the resting posture is relearned
BASELINE_QUIET_VEL = 0.60  # only relearn while the body is roughly still
STUCK_TIME = 2.5           # holding a gesture this long re-baselines instead
STUCK_VEL = 0.35

# Frames from a mis-detected shoulder pair are dropped so they cannot poison
# the baseline or the velocity estimate. The test is on shoulder *width*, not
# on the offset from the calibration neutral: that offset is divided by width,
# so a distant player legitimately produces huge values, and testing it
# rejected every frame and froze the state machine entirely.
MIN_USABLE_WIDTH = 0.06
MAX_USABLE_WIDTH = 0.75
#: Sanity bound applied after the baseline is removed. A jump lifts the
#: shoulders well under one shoulder-width; a real session's 99th percentile
#: was 1.80. Anything past this is a mis-detected frame, and letting it through
#: at 3.89 both corrupted the velocity estimate and masked a genuine jump.
MAX_RELATIVE_OFFSET = 2.2

#: Losing the body for longer than this discards the carried state. Coming back
#: after a break should start clean -- otherwise the posture, the smoothed
#: signals and the vertical mode from before you walked away all still apply.
LOST_RESET_AFTER = 0.6

# A vertical mode may never be held longer than this. Release depends on the
# body returning past a threshold, and if the baseline has drifted that may
# simply never happen -- real sessions parked in one mode for 12s and 22s at a
# stretch, during which the opposite gesture cannot fire at all.
MAX_HOLD = 1.6

# Walking toward or away from the camera moves the body in frame just like a
# jump does. Shoulder width is the distance proxy: when it changes materially
# the vertical baseline is re-seated at once rather than drifting there over
# seconds, and gestures are suppressed briefly so the move itself is not read
# as one.
DISTANCE_CHANGE = 0.25      # fractional change in *smoothed* shoulder width
DISTANCE_SETTLE = 0.25      # seconds of suppression after a distance change
WIDTH_SMOOTH = 0.25         # shoulder width is noisy; compare like with like

# Usable framing, as shoulder width in fractions of the frame.
FRAMING_MIN = 0.10
FRAMING_MAX = 0.38
FRAMING_IDEAL = (0.14, 0.30)

# Rising fast from below neutral is also what standing up out of a crouch
# looks like. A blanket lockout was the wrong answer: a squat jump -- crouch,
# then drive upward -- is how people actually jump, so the lockout swallowed
# real jumps that arrived 150ms after the duck released.
#
# The honest discriminator is displacement, not time. Standing up *returns to*
# the baseline and stops; a jump carries clearly above it. So after a vertical
# gesture we disable only the velocity shortcut for its opposite, leaving the
# displacement path fully live.
OPPOSITE_VEL_LOCK = 0.80


@dataclass
class GestureState:
    lane_zone: int = 0         # -1 left, 0 centre, +1 right
    jump: bool = False         # edge-triggered this frame
    duck: bool = False         # edge-triggered this frame
    tracked: bool = False      # is a body visible at all
    width: float = 0.0         # shoulder width in frame -- the distance proxy
    framing: str = "unknown"   # too_close | good | too_far | unknown
    lean: float = 0.0          # smoothed sideways offset from baseline
    rise: float = 0.0          # smoothed vertical offset from baseline, + is up
    base_rise: float = 0.0     # current resting posture, for diagnostics
    rise_vel: float = 0.0      # vertical speed, shoulder-widths per second
    raw_zone: int = 0          # pre-debounce, for the debug overlay


def framing_of(width: float) -> str:
    """Is the player usefully framed? width is shoulder width / frame width."""
    if width < FRAMING_MIN:
        return "too_far"
    if width > FRAMING_MAX:
        return "too_close"
    return "good"


class GestureDetector:
    def __init__(self, profile, smoothing=0.45):
        self.profile = profile
        self.smoothing = smoothing
        self.reset()

    def reset(self):
        self._lean = 0.0
        self._rise = 0.0
        self._rise_vel = 0.0
        self._prev_raw_rise = None
        self._last_ts = None
        # Seeded from calibration (zero offset), not from the first frame a
        # camera happens to deliver -- a player who is mid-lean at start-up
        # would otherwise have that pose adopted as their neutral.
        self._base_rise = 0.0
        self._base_lean = 0.0
        self._mode_time = 0.0
        self._recent_duck = 0.0
        self._recent_jump = 0.0
        self._still_time = 0.0
        self._base_width = None
        self._width_ema = None
        self._settle = 0.0
        self._lost_for = 0.0
        self._primed = False
        self.zone = 0
        self._candidate = 0
        self._candidate_time = 0.0
        self._zone_age = 0.0
        self._vertical_mode = "neutral"     # neutral | up | down
        self._refractory = 0.0
        self.state = GestureState()

    def set_profile(self, profile):
        self.profile = profile
        self.reset()

    # -- main entry ---------------------------------------------------------

    def update(self, frame, dt: float) -> GestureState:
        self._refractory = max(0.0, self._refractory - dt)
        self._recent_duck = max(0.0, self._recent_duck - dt)
        self._recent_jump = max(0.0, self._recent_jump - dt)
        self._settle = max(0.0, self._settle - dt)

        if frame is None or not self._usable(frame):
            self._lost_for += dt
            self.state = GestureState(lane_zone=self.zone, tracked=False,
                                      lean=self._lean, rise=self._rise,
                                      rise_vel=self._rise_vel)
            return self.state

        # The game polls at 60fps but the camera delivers ~30. Advancing the
        # filter on repeated frames would double-count them and make the
        # measured velocity meaningless, so only new frames move the state on.
        if self._last_ts is not None and frame.timestamp == self._last_ts:
            held = GestureState(lane_zone=self.zone, tracked=True,
                                lean=self._lean, rise=self._rise,
                                rise_vel=self._rise_vel,
                                base_rise=self._base_rise,
                                raw_zone=self._candidate)
            self.state = held
            return held

        cam_dt = (1.0 / 30.0 if self._last_ts is None
                  else max(1e-3, frame.timestamp - self._last_ts))
        self._last_ts = frame.timestamp

        returning = self._lost_for >= LOST_RESET_AFTER
        self._lost_for = 0.0

        p = self.profile
        mx, my = frame.midpoint(L_SHOULDER, R_SHOULDER)
        width = frame.shoulder_width

        lean = (mx - p.neutral_x) / width
        rise = (p.neutral_y - my) / width       # image y grows downward

        if returning:
            # Back after an absence: adopt the pose you came back in.
            self._base_width = self._width_ema = width
            self._reseat(rise, lean)
            self._primed = False
            self._settle = DISTANCE_SETTLE

        # Relearn the resting posture. Two paths:
        #
        #  * slow drift correction while the body is still and near baseline;
        #  * a hard re-seat when a vertical gesture has been "held" so long
        #    that it is plainly the player's new posture rather than a gesture.
        #    The hard reset matters: easing toward the pose would leave the
        #    offset above threshold and immediately re-fire the same gesture.
        # Distance change: re-seat at once rather than drifting there. Compare
        # smoothed widths -- a raw per-frame width is noisy enough to trip a
        # tight threshold constantly.
        if self._base_width is None:
            self._base_width = self._width_ema = width
        self._width_ema += (width - self._width_ema) * WIDTH_SMOOTH
        if (abs(self._width_ema - self._base_width)
                / max(1e-4, self._base_width) > DISTANCE_CHANGE):
            self._base_width = self._width_ema
            self._reseat(rise, lean)
            self._settle = DISTANCE_SETTLE
        else:
            a_w = 1.0 - math.exp(-cam_dt / BASELINE_TAU)
            self._base_width += (self._width_ema - self._base_width) * a_w

        self._mode_time += cam_dt
        # A hard ceiling on how long a mode may be held, independent of
        # stillness: during active play the body is rarely still enough for the
        # stillness-based escape to ever fire.
        if self._vertical_mode != "neutral" and self._mode_time > MAX_HOLD:
            self._reseat(rise, lean)
        if abs(self._rise_vel) < STUCK_VEL:
            self._still_time += cam_dt
        else:
            self._still_time = 0.0
        stuck = (self._vertical_mode != "neutral"
                 and self._mode_time > STUCK_TIME
                 and self._still_time > STUCK_TIME)
        if stuck:
            self._reseat(rise, lean)

        # Stillness is the discriminator, not proximity: a deliberate gesture
        # always carries velocity, whereas a wrongly-calibrated posture sits
        # motionless. Gating on proximity too would have left a large offset
        # permanently uncorrectable -- exactly the case that broke jumping.
        quiet = abs(self._rise_vel) < BASELINE_QUIET_VEL
        if self._vertical_mode == "neutral" and quiet:
            a = 1.0 - math.exp(-cam_dt / BASELINE_TAU)
            self._base_rise += (rise - self._base_rise) * a

        # The lean baseline may only drift while the player is centred and
        # inside the deadzone. Lane control is positional -- absorbing a held
        # lean would quietly slide the player back out of the lane they chose.
        if (self.zone == 0
                and abs(lean - self._base_lean) < p.lean_threshold * EXIT_RATIO):
            a = 1.0 - math.exp(-cam_dt / BASELINE_TAU)
            self._base_lean += (lean - self._base_lean) * a

        lean -= self._base_lean
        rise -= self._base_rise

        if (abs(lean) > MAX_RELATIVE_OFFSET or abs(rise) > MAX_RELATIVE_OFFSET):
            # Implausible even after baselining -- hold rather than trust it.
            self.state = GestureState(lane_zone=self.zone, tracked=False,
                                      lean=self._lean, rise=self._rise,
                                      rise_vel=self._rise_vel,
                                      base_rise=self._base_rise,
                                      width=width, framing=framing_of(width))
            return self.state

        # Adaptive EMA on the normalised signals (not the raw landmarks, so one
        # jittery joint cannot drag the result). Alpha opens up with speed.
        if not self._primed:
            self._lean, self._rise, self._primed = lean, rise, True
            self._rise_vel = 0.0
        else:
            self._lean += (lean - self._lean) * self._alpha(lean - self._lean)
            self._rise += (rise - self._rise) * self._alpha(rise - self._rise)
            raw_vel = (rise - self._prev_raw_rise) / cam_dt
            self._rise_vel += (raw_vel - self._rise_vel) * VEL_SMOOTH
        self._prev_raw_rise = rise

        zone = self._resolve_zone(cam_dt)
        if self._settle > 0.0:
            jump = duck = False
        else:
            jump, duck = self._resolve_vertical()

        self.state = GestureState(lane_zone=zone, jump=jump, duck=duck,
                                  tracked=True, lean=self._lean,
                                  rise=self._rise, rise_vel=self._rise_vel,
                                  base_rise=self._base_rise,
                                  width=width, framing=framing_of(width),
                                  raw_zone=self._candidate)
        return self.state

    # -- helpers ------------------------------------------------------------

    def _reseat(self, rise, lean):
        """Adopt the current pose as the new resting posture.

        Clearing the smoothed values is the whole point: moving the baseline
        alone leaves `self._rise` -- which is what the state machine reads --
        still carrying the old offset, so the mode re-enters itself on the very
        next frame and the release is undone.
        """
        self._base_rise = rise
        self._base_lean = lean
        self._rise = 0.0
        self._lean = 0.0
        self._rise_vel = 0.0
        self._prev_raw_rise = rise
        self._vertical_mode = "neutral"
        self._mode_time = 0.0
        self._still_time = 0.0

    @staticmethod
    def _alpha(delta: float) -> float:
        return BASE_ALPHA + (1.0 - BASE_ALPHA) * min(1.0, abs(delta) / ADAPT_SCALE)

    def _usable(self, frame) -> bool:
        if not (frame.visible(L_SHOULDER, VISIBILITY)
                and frame.visible(R_SHOULDER, VISIBILITY)):
            return False
        # A plausible shoulder width guards against a garbage detection, and
        # also treats "so far away the landmarks are meaningless" as untracked,
        # which is what triggers the game's auto-pause.
        return MIN_USABLE_WIDTH < frame.shoulder_width < MAX_USABLE_WIDTH

    def _resolve_zone(self, cam_dt: float) -> int:
        t = self.profile.lean_threshold
        exit_t = t * EXIT_RATIO
        self._zone_age += cam_dt

        if self.zone == 0:
            target = 1 if self._lean > t else (-1 if self._lean < -t else 0)
        else:
            # Already committed: hold the zone until well back toward centre.
            if abs(self._lean) < exit_t:
                target = 0
            elif self._lean > t:
                target = 1
            elif self._lean < -t:
                target = -1
            else:
                target = self.zone

        if target == self._candidate:
            self._candidate_time += cam_dt
        else:
            self._candidate = target
            self._candidate_time = 0.0

        if (self._candidate_time >= COMMIT_TIME
                and self._candidate != self.zone
                and self._zone_age >= MIN_ZONE_DWELL):
            self.zone = self._candidate
            self._zone_age = 0.0
        return self.zone

    def _resolve_vertical(self):
        p = self.profile
        jump = duck = False

        if self._vertical_mode == "up":
            if self._rise < p.jump_threshold * RELEASE_RATIO:
                self._vertical_mode = "neutral"
                self._mode_time = 0.0
                self._recent_jump = OPPOSITE_VEL_LOCK
        elif self._vertical_mode == "down":
            if self._rise > -p.duck_threshold * RELEASE_RATIO:
                self._vertical_mode = "neutral"
                self._mode_time = 0.0
                self._recent_duck = OPPOSITE_VEL_LOCK
        else:
            if self._refractory <= 0.0:
                # Either the body has clearly displaced, or it is moving fast
                # in that direction and has already started to displace.
                # Straight after a duck, a fast rise is ambiguous with simply
                # standing up -- so require genuine displacement above the
                # baseline. The displacement path always stays live.
                allow_vel_jump = self._recent_duck <= 0.0
                allow_vel_duck = self._recent_jump <= 0.0
                jump_now = (self._rise >= p.jump_threshold
                            or (allow_vel_jump
                                and self._rise_vel >= JUMP_VELOCITY
                                and self._rise >= p.jump_threshold * JUMP_VEL_GATE))

                duck_now = (self._rise <= -p.duck_threshold
                            or (allow_vel_duck
                                and self._rise_vel <= -DUCK_VELOCITY
                                and self._rise <= -p.duck_threshold * DUCK_VEL_GATE))
                if jump_now:
                    jump = True
                    self._vertical_mode = "up"
                    self._mode_time = 0.0
                    self._refractory = REFRACTORY
                elif duck_now:
                    duck = True
                    self._vertical_mode = "down"
                    self._mode_time = 0.0
                    self._refractory = REFRACTORY

        return jump, duck
