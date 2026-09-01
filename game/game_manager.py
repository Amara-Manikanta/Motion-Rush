"""Game state machine, collision resolution and the per-frame orchestration."""

import json
import math
import os
from dataclasses import dataclass, field
from enum import Enum

import pygame

import config as C
from game.collectible import DataOrb
from game.obstacle import ObstacleKind
from game.player import Player, PlayerState
from game.renderer import Camera, NeonPainter, build_background
from game.spawner import Spawner
from game.track import Track
from input.input_manager import Action
from ui.calibration_screen import CalibrationScreen
from ui.debug_overlay import DebugOverlay
from ui.hud import HUD
from ui.menu import Menu

HIGHSCORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              os.pardir, ".highscore.json")
DEATH_FREEZE = 0.75          # seconds of slow-motion before the game-over card
MILESTONE_STEP = 500


class State(Enum):
    CALIBRATING = "calibrating"
    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    GAME_OVER = "game_over"


@dataclass
class RunState:
    score: float = 0.0
    orbs: int = 0
    distance: float = 0.0
    speed: float = 0.0
    elapsed: float = 0.0
    lives: int = 1
    stumbles: int = 0
    next_milestone: int = MILESTONE_STEP


def aabb_overlap(a, b) -> bool:
    """Overlap test for two (x0, x1, y0, y1, z0, z1) boxes."""
    return (a[0] < b[1] and a[1] > b[0] and
            a[2] < b[3] and a[3] > b[2] and
            a[4] < b[5] and a[5] > b[4])


class GameManager:
    def __init__(self, screen, input_source, sound, show_camera=False):
        self.screen = screen
        self.input = input_source
        self.sound = sound
        self.theme = C.theme()

        self.painter = NeonPainter(screen)
        self.background = build_background(self.theme)

        self.player = Player()
        self.track = Track()
        self.spawner = Spawner()
        self.hud = HUD(self.theme)
        self.menu = Menu(self.theme)
        self.calib_screen = CalibrationScreen(self.theme)
        self.debug = DebugOverlay(self.theme)

        # A camera source starts in calibration; a keyboard source never does.
        self.state = (State.CALIBRATING
                      if getattr(input_source, "calibrating", False)
                      else State.MENU)
        self.run = RunState()
        self.best_score = self._load_best()
        self.is_best = False
        self.death_timer = 0.0
        self.shake = 0.0
        self.last_hit = None

        self.show_debug = False
        self.show_camera = show_camera
        self.camera_preview = None      # set by a vision input source
        self.fps = 0.0
        self.running = True
        self.request_input_switch = False
        self.request_fullscreen_toggle = False
        self.notice = ""
        self.notice_timer = 0.0

    # -- persistence --------------------------------------------------------

    def _load_best(self) -> float:
        try:
            with open(HIGHSCORE_PATH) as fh:
                return float(json.load(fh).get("best", 0.0))
        except (OSError, ValueError, TypeError):
            return 0.0

    def _save_best(self):
        try:
            with open(HIGHSCORE_PATH, "w") as fh:
                json.dump({"best": self.best_score}, fh)
        except OSError:
            pass    # a read-only checkout shouldn't crash the game

    # -- lifecycle ----------------------------------------------------------

    def start_run(self):
        self.player.reset()
        self.track.reset()
        self.spawner.reset()
        self.run = RunState()
        self.run.speed = C.BASE_SPEED
        self.run.lives = C.LIVES
        self.is_best = False
        self.death_timer = 0.0
        self.shake = 0.0
        self.state = State.PLAYING
        self.sound.play("start")

    def _end_run(self):
        self.state = State.GAME_OVER
        if self.run.score > self.best_score:
            self.best_score = self.run.score
            self.is_best = True
            self._save_best()
        self.sound.play("over")

    # -- input --------------------------------------------------------------

    def handle_action(self, action):
        if action is None:
            return
        if action is Action.QUIT:
            self.running = False
            return
        if action is Action.TOGGLE_DEBUG:
            self.show_debug = not self.show_debug
            return
        if action is Action.TOGGLE_CAMERA:
            self.show_camera = not self.show_camera
            return
        if action is Action.TOGGLE_FULLSCREEN:
            self.request_fullscreen_toggle = True
            return
        if action is Action.TOGGLE_MODE and self.state in (State.MENU,
                                                           State.GAME_OVER):
            order = list(C.MODES)
            nxt = order[(order.index(C.ACTIVE_MODE) + 1) % len(order)]
            C.apply_mode(nxt)
            gap = C.SPAWN_GAP_MIN / C.MAX_SPEED
            self.show_notice(
                f"{nxt.upper()} pace  —  {C.BASE_SPEED:.0f} to {C.MAX_SPEED:.0f} speed,"
                f"  {gap:.1f}s minimum between obstacles", 4.0)
            return
        if action is Action.SWITCH_INPUT and self.state in (State.MENU,
                                                            State.GAME_OVER):
            self.request_input_switch = True
            return

        if self.state is State.CALIBRATING:
            if action is Action.START:
                skip = getattr(self.input, "skip_calibration", None)
                if skip is not None:
                    skip()
            return

        if self.state is State.MENU:
            if action in (Action.START, Action.JUMP, Action.RESTART):
                self.start_run()

        elif self.state is State.PLAYING:
            if action is Action.LEFT:
                if self.player.lane > C.LANES[0]:
                    self.sound.play("lane")
                self.player.move_left()
            elif action is Action.RIGHT:
                if self.player.lane < C.LANES[-1]:
                    self.sound.play("lane")
                self.player.move_right()
            elif action is Action.JUMP:
                if self.player.on_ground or self.player.time_since_grounded <= C.COYOTE_TIME:
                    self.sound.play("jump")
                self.player.jump()
            elif action is Action.DUCK:
                if self.player.state is not PlayerState.DUCKING:
                    self.sound.play("duck")
                self.player.duck()
            elif action is Action.PAUSE:
                self.state = State.PAUSED

        elif self.state is State.PAUSED:
            if action in (Action.PAUSE, Action.START):
                self.state = State.PLAYING

        elif self.state is State.GAME_OVER:
            if self.death_timer <= 0.0 and action in (Action.RESTART, Action.START, Action.JUMP):
                self.start_run()

    def set_input(self, source):
        """Swap the input source at runtime (keyboard <-> camera)."""
        self.input = source
        self.request_input_switch = False
        self.state = (State.CALIBRATING
                      if getattr(source, "calibrating", False) else State.MENU)

    def show_notice(self, text, seconds=5.0):
        self.notice = text
        self.notice_timer = seconds

    # -- update -------------------------------------------------------------

    def update(self, dt: float):
        self.menu.update(dt)
        self.shake = max(0.0, self.shake - dt * 2.4)
        self.notice_timer = max(0.0, self.notice_timer - dt)

        # Keep the picture-in-picture fed from whichever source provides one.
        getter = getattr(self.input, "preview_surface", None)
        if getter is not None:
            self.camera_preview = getter()

        if self.state is State.CALIBRATING:
            self.calib_screen.update(dt)
            if not getattr(self.input, "calibrating", False):
                self.state = State.MENU
                pending = getattr(self.input, "pending_notice", None)
                if pending:
                    self.show_notice(pending, 9.0)
                    self.input.pending_notice = None
            return

        if self.state is State.GAME_OVER and self.death_timer > 0.0:
            # Slow-motion beat so the crash is legible before the card appears.
            self.death_timer = max(0.0, self.death_timer - dt)
            slow = dt * 0.25
            self.player.update(slow, self.run.speed)
            self.track.update(slow, self.run.speed * 0.35)
            self.spawner.update(slow, self.run.speed * 0.35)
            return

        if self.state is not State.PLAYING:
            return

        run = self.run
        run.elapsed += dt
        run.speed = min(C.MAX_SPEED, C.BASE_SPEED + run.elapsed * C.SPEED_ACCEL)
        step = run.speed * dt
        run.distance += step
        run.score += step * C.DISTANCE_POINTS

        if run.score >= run.next_milestone:
            run.next_milestone += MILESTONE_STEP
            self.sound.play("milestone")

        self.player.update(dt, run.speed)
        self.track.update(dt, run.speed)
        self.spawner.update(dt, run.speed)
        self._resolve_collisions()

    def _resolve_collisions(self):
        box = self.player.bounds()

        for orb in self.spawner.orbs:
            if orb.active and aabb_overlap(box, orb.bounds()):
                orb.active = False
                self.run.orbs += 1
                self.run.score += C.ORB_VALUE
                self.sound.play("orb")

        if self.player.invuln > 0.0:
            return                      # recovering from a stumble

        for ob in self.spawner.obstacles:
            if ob.active and aabb_overlap(box, ob.bounds()):
                if self._forgiven(ob):
                    continue
                if self.run.lives > 1:
                    # A stumble: lose the speed you had built up, not the run.
                    self.run.lives -= 1
                    self.run.stumbles += 1
                    self.run.elapsed = max(0.0, self.run.elapsed * 0.45)
                    self.player.stumble(C.STUMBLE_INVULN)
                    ob.active = False
                    self.sound.play("hit")
                    self.shake = 0.7
                    return
                # Recorded for the debug overlay and the headless diagnostics.
                self.last_hit = (ob.kind, round(ob.lane_pos, 2), round(ob.z, 2),
                                 round(self.player.lane_visual, 2),
                                 round(self.player.y, 2), self.player.state)
                self.player.kill()
                self.sound.play("hit")
                self.shake = 1.0
                self.death_timer = DEATH_FREEZE
                self._end_run()
                return

    def _forgiven(self, ob) -> bool:
        """Was the right gesture made, just fractionally too late?

        Only timed obstacles qualify: a barrier has no 'correct moment', so
        forgiving one would simply delete the obstacle.
        """
        p = self.player
        if ob.kind is ObstacleKind.LASER_BEAM:
            return p.since_jump_request <= C.LATE_GRACE
        if ob.kind is ObstacleKind.FORCE_FIELD:
            return p.since_duck_request <= C.LATE_GRACE
        return False

    # -- draw ---------------------------------------------------------------

    def draw(self):
        surface = self.screen
        surface.blit(self.background, (0, 0))
        self.painter.begin_frame()

        self.track.draw(self.painter, self.theme, self.run.speed)

        # Painter's algorithm: everything in one list, far to near.
        drawables = [(ob.z, ob) for ob in self.spawner.obstacles if ob.active]
        drawables += [(o.z, o) for o in self.spawner.orbs if o.active]
        if self.state is not State.MENU:
            drawables.append((C.PLAYER_Z, self.player))
        drawables.sort(key=lambda pair: pair[0], reverse=True)
        for _, entity in drawables:
            entity.draw(self.painter, self.theme)

        self.painter.end_frame()

        if self.state in (State.PLAYING, State.PAUSED) or self.death_timer > 0.0:
            glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            self.hud.draw(surface, glow, self.run)
            surface.blit(glow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        overlay_glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        if self.state is State.CALIBRATING:
            calib = getattr(self.input, "calibrator", None)
            tracked = bool(self.input.poll and getattr(
                getattr(self.input, "state", None), "tracked", False))
            if calib is not None:
                self.calib_screen.draw(
                    surface, overlay_glow, calib, self.camera_preview,
                    tracked or calib.sample_count() > 0,
                    getattr(self.input, "camera_status", "ok"))
        elif self.state is State.MENU:
            self.menu.draw_title(surface, overlay_glow, self.input.name, self.best_score)
        elif self.state is State.PAUSED:
            self.menu.draw_paused(surface, overlay_glow)
        elif self.state is State.GAME_OVER and self.death_timer <= 0.0:
            self.menu.draw_game_over(surface, overlay_glow, self.run,
                                     self.best_score, self.is_best)
        surface.blit(overlay_glow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        if (self.show_camera and self.camera_preview is not None
                and self.state is not State.CALIBRATING):
            self._draw_camera_pip(surface)

        if self.notice_timer > 0.0 and self.notice:
            self._draw_notice(surface)

        if self.show_debug:
            self.debug.draw(surface, self._debug_lines())

    def _draw_camera_pip(self, surface):
        pip = self.camera_preview
        w, h = pip.get_size()
        x, y = C.SCREEN_W - w - 24, C.SCREEN_H - h - 24
        pygame.draw.rect(surface, self.theme["accent"],
                         (x - 3, y - 3, w + 6, h + 6), border_radius=6)
        surface.blit(pip, (x, y))

    def _draw_notice(self, surface):
        from ui.fonts import draw_text
        fade = min(1.0, self.notice_timer / 0.6)
        lines = self.notice.split("\n")
        h = 26 * len(lines) + 22
        box = pygame.Surface((C.SCREEN_W - 240, h), pygame.SRCALPHA)
        box.fill((10, 4, 26, int(226 * fade)))
        pygame.draw.rect(box, self.theme["danger"], box.get_rect(), width=2,
                         border_radius=8)
        rect = box.get_rect(midtop=(C.SCREEN_W // 2, 96))
        surface.blit(box, rect)
        for i, line in enumerate(lines):
            draw_text(surface, line, 19, self.theme["text"],
                      center=(rect.centerx, rect.top + 22 + i * 26))

    def _debug_lines(self):
        p = self.player
        lines = [
            f"fps {self.fps:5.1f}   state {self.state.value}",
            f"speed {self.run.speed:5.2f}   dist {self.run.distance:7.1f}",
            f"lane {p.lane:+d} (vis {p.lane_visual:+.2f})  y {p.y:5.2f}  {p.state.value}",
            f"obstacles {len(self.spawner.active_obstacles()):3d}  "
            f"orbs {len(self.spawner.active_orbs()):3d}  "
            f"gap {self.spawner.group_gap:.1f}",
        ]
        lines.extend(self.input.debug_lines())
        return lines

    # -- shake offset -------------------------------------------------------

    def screen_offset(self):
        if self.shake <= 0.0:
            return (0, 0)
        mag = self.shake * 14.0
        return (int(math.sin(self.shake * 47.0) * mag),
                int(math.cos(self.shake * 39.0) * mag))
