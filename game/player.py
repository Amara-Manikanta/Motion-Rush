"""The player character -- lane movement, jump/duck physics, collision box."""

import math
from enum import Enum

import config as C
from game.renderer import Camera


class PlayerState(Enum):
    RUNNING = "running"
    JUMPING = "jumping"
    DUCKING = "ducking"
    DEAD = "dead"


class Player:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state = PlayerState.RUNNING
        self.lane = 0                # discrete target lane in {-1, 0, 1}
        self.lane_visual = 0.0       # smoothly interpolated toward `lane`
        self.y = 0.0
        self.vy = 0.0
        self.duck_timer = 0.0
        self.run_phase = 0.0
        self.time_since_grounded = 0.0
        self.hit_flash = 0.0
        # Time since the player last *asked* for these, whether or not the
        # action was possible. Used to forgive an input that lands slightly
        # late, which is what input latency produces.
        self.since_jump_request = 99.0
        self.since_duck_request = 99.0
        self.invuln = 0.0

    # -- queries ------------------------------------------------------------

    @property
    def height(self) -> float:
        return C.PLAYER_DUCK_H if self.state is PlayerState.DUCKING else C.PLAYER_STAND_H

    @property
    def on_ground(self) -> bool:
        return self.y <= 1e-4

    @property
    def world_x(self) -> float:
        return C.lane_to_x(self.lane_visual)

    def bounds(self):
        """World-space AABB as (x0, x1, y0, y1, z0, z1)."""
        hw = C.PLAYER_WIDTH * C.PLAYER_HITBOX_W * 0.5
        hd = C.PLAYER_DEPTH * C.PLAYER_HITBOX_D * 0.5
        x = self.world_x
        return (x - hw, x + hw,
                self.y, self.y + self.height,
                C.PLAYER_Z - hd, C.PLAYER_Z + hd)

    # -- input --------------------------------------------------------------

    def move_left(self):
        if self.state is not PlayerState.DEAD and self.lane > C.LANES[0]:
            self.lane -= 1

    def move_right(self):
        if self.state is not PlayerState.DEAD and self.lane < C.LANES[-1]:
            self.lane += 1

    def jump(self):
        if self.state is PlayerState.DEAD:
            return
        self.since_jump_request = 0.0
        # Coyote time keeps a slightly-late jump from being swallowed, which
        # matters a lot when the input source is a camera rather than a key.
        if self.on_ground or self.time_since_grounded <= C.COYOTE_TIME:
            self.vy = C.JUMP_VELOCITY
            self.state = PlayerState.JUMPING
            self.duck_timer = 0.0
            self.time_since_grounded = C.COYOTE_TIME + 1.0

    def duck(self):
        if self.state is PlayerState.DEAD:
            return
        self.since_duck_request = 0.0
        if self.on_ground:
            self.state = PlayerState.DUCKING
            self.duck_timer = C.DUCK_DURATION
        else:
            # Ducking mid-air slams you back down -- a fast way to recover.
            self.vy = min(self.vy, -C.JUMP_VELOCITY * 0.55)

    def kill(self):
        self.state = PlayerState.DEAD
        self.hit_flash = 0.45

    def stumble(self, invuln: float):
        """Take a hit without ending the run."""
        self.hit_flash = 0.45
        self.invuln = invuln
        if self.state is PlayerState.DUCKING:
            self.state = PlayerState.RUNNING
            self.duck_timer = 0.0

    # -- update -------------------------------------------------------------

    def update(self, dt: float, speed: float):
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.since_jump_request += dt
        self.since_duck_request += dt
        self.invuln = max(0.0, self.invuln - dt)
        if self.state is PlayerState.DEAD:
            # Fall through the floor a little for a bit of death feedback.
            self.vy -= C.GRAVITY * dt
            self.y = max(-1.5, self.y + self.vy * dt)
            return

        # Lateral interpolation toward the target lane.
        target = float(self.lane)
        delta = target - self.lane_visual
        step = C.LANE_SHIFT_SPEED * dt
        if abs(delta) <= step:
            self.lane_visual = target
        else:
            self.lane_visual += step * (1.0 if delta > 0 else -1.0)

        # Vertical physics (semi-implicit Euler).
        if not self.on_ground or self.vy > 0.0:
            self.vy -= C.GRAVITY * dt
            self.y += self.vy * dt
            if self.y <= 0.0:
                self.y = 0.0
                self.vy = 0.0
                self.state = PlayerState.RUNNING
            else:
                self.state = PlayerState.JUMPING

        if self.on_ground:
            self.time_since_grounded = 0.0
        else:
            self.time_since_grounded += dt

        # Duck expiry.
        if self.state is PlayerState.DUCKING:
            self.duck_timer -= dt
            if self.duck_timer <= 0.0:
                self.state = PlayerState.RUNNING

        # Run cycle advances with speed so the legs match the ground.
        self.run_phase += dt * (4.0 + speed * 0.42)

    # -- drawing ------------------------------------------------------------

    def draw(self, painter, theme):
        if self.invuln > 0.0 and int(self.invuln * 12) % 2 == 0:
            return                      # blink while recovering from a stumble
        col = theme["danger"] if self.hit_flash > 0 else theme["player"]
        dark = theme["player_dark"]
        x = self.world_x
        z = C.PLAYER_Z
        w = C.PLAYER_WIDTH
        d = C.PLAYER_DEPTH
        h = self.height
        base = self.y

        if self.state is PlayerState.DUCKING:
            # Squashed and widened so "low" reads instantly at any distance.
            painter.box(x, w * 1.35, base + h * 0.20, base + h, z, d * 1.35,
                        col, glow=5)
            painter.box(x - w * 0.34, w * 0.34, base, base + h * 0.26,
                        z - 0.12, d * 0.7, dark, glow=0)
            painter.box(x + w * 0.34, w * 0.34, base, base + h * 0.26,
                        z + 0.12, d * 0.7, dark, glow=0)
            self._draw_visor(painter, x, base + h * 0.74, z, theme, wide=True)
            return

        airborne = not self.on_ground
        swing = 0.0 if airborne else math.sin(self.run_phase)
        arm_swing = 0.0 if airborne else math.sin(self.run_phase + math.pi)

        leg_top = base + h * 0.40
        torso_b = base + h * 0.42
        torso_t = base + h * 0.78
        head_b = base + h * 0.82          # neck gap keeps the head distinct
        head_t = base + h

        # Legs -- stride faked with a z offset, which reads right from behind.
        if airborne:
            painter.box(x - w * 0.26, w * 0.30, base + 0.16, leg_top, z - 0.16, 0.28, dark)
            painter.box(x + w * 0.26, w * 0.30, base + 0.16, leg_top, z + 0.16, 0.28, dark)
        else:
            painter.box(x - w * 0.26, w * 0.30, base + max(0.0, swing) * 0.20,
                        leg_top, z + swing * 0.26, 0.28, dark)
            painter.box(x + w * 0.26, w * 0.30, base + max(0.0, -swing) * 0.20,
                        leg_top, z - swing * 0.26, 0.28, dark)

        # Arms, swinging opposite the legs.
        painter.box(x - w * 0.58, w * 0.26, torso_b + h * 0.06, torso_t - h * 0.04,
                    z + arm_swing * 0.20, 0.22, dark)
        painter.box(x + w * 0.58, w * 0.26, torso_b + h * 0.06, torso_t - h * 0.04,
                    z - arm_swing * 0.20, 0.22, dark)

        # Torso, with a glowing core on the back plate.
        painter.box(x, w, torso_b, torso_t, z, d, col, glow=5)
        core_y = torso_b + (torso_t - torso_b) * 0.55
        painter.billboard_rect(x, w * 0.34, core_y - h * 0.05, core_y + h * 0.05,
                               z - d * 0.51, theme["accent"], glow=6)

        # Head sits above a visible neck gap.
        painter.box(x, w * 0.62, head_b, head_t, z, d * 0.66, col, glow=4)
        self._draw_visor(painter, x, head_b + (head_t - head_b) * 0.55, z, theme)

    def _draw_visor(self, painter, x, y, z, theme, wide=False):
        w = C.PLAYER_WIDTH * (0.9 if wide else 0.44)
        painter.billboard_rect(x, w, y - 0.06, y + 0.06,
                               z - C.PLAYER_DEPTH * 0.36, theme["accent"], glow=5)
