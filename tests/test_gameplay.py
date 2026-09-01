"""Headless end-to-end checks. Run: python -m tests.test_gameplay"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import config as C
from game.game_manager import GameManager, State
from input.keyboard_input import KeyboardInput
from tests.autopilot import choose_action

DT = 1.0 / 60.0
FAILURES = []


class SilentSound:
    enabled = False
    sounds = {}
    def play(self, name): pass
    def close(self): pass


def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}" + (f"  -- {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


def new_game():
    canvas = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    gm = GameManager(canvas, KeyboardInput(), SilentSound())
    gm.best_score = 0.0
    gm._save_best = lambda: None        # don't touch the real highscore file
    return gm


def run_autopilot(gm, seconds, draw_every=0):
    frames = int(seconds / DT)
    for i in range(frames):
        gm.handle_action(choose_action(gm))
        gm.update(DT)
        if draw_every and i % draw_every == 0:
            gm.draw()
        if gm.state is State.GAME_OVER:
            return i * DT
    return seconds


def main():
    pygame.init()
    pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H), pygame.HIDDEN)

    print("\n1. scoring and speed scaling")
    gm = new_game()
    gm.start_run()
    for _ in range(600):                       # 10 seconds of clear running
        gm.update(DT)
    check("score accrues with distance", gm.run.score > 80,
          f"score={gm.run.score:.0f}")
    check("speed scales up", gm.run.speed > C.BASE_SPEED,
          f"{C.BASE_SPEED} -> {gm.run.speed:.2f}")
    check("speed respects cap", gm.run.speed <= C.MAX_SPEED)

    print("\n2. collision ends the run")
    gm = new_game()
    gm.start_run()
    ob = gm.spawner.obstacles[0]
    from game.obstacle import ObstacleKind
    ob.spawn(ObstacleKind.ENERGY_BARRIER, gm.player.lane, C.PLAYER_Z)
    gm.update(DT)
    check("barrier in player's lane is fatal", gm.state is State.GAME_OVER)
    check("player marked dead", gm.player.state.value == "dead")

    print("\n3. jumping clears a laser, standing does not")
    for jumping in (True, False):
        gm = new_game(); gm.start_run()
        ob = gm.spawner.obstacles[0]
        ob.spawn(ObstacleKind.LASER_BEAM, gm.player.lane, C.PLAYER_Z)
        if jumping:
            gm.player.jump()
            for _ in range(14):
                gm.player.update(DT, gm.run.speed)
        gm._resolve_collisions()
        died = gm.state is State.GAME_OVER
        check(f"laser while {'jumping' if jumping else 'standing'}",
              died != jumping, f"died={died}")

    print("\n4. ducking clears a force field, standing does not")
    for ducking in (True, False):
        gm = new_game(); gm.start_run()
        ob = gm.spawner.obstacles[0]
        ob.spawn(ObstacleKind.FORCE_FIELD, gm.player.lane, C.PLAYER_Z)
        if ducking:
            gm.player.duck()
        gm._resolve_collisions()
        died = gm.state is State.GAME_OVER
        check(f"force field while {'ducking' if ducking else 'standing'}",
              died != ducking, f"died={died}")

    print("\n5. orbs are collected and scored")
    gm = new_game(); gm.start_run()
    for o in gm.spawner.orbs:
        o.active = False
    gm.spawner.orbs[0].spawn(gm.player.lane, C.PLAYER_Z)
    before = gm.run.score
    gm._resolve_collisions()
    check("orb collected", gm.run.orbs == 1)
    check("orb scored", gm.run.score == before + C.ORB_VALUE)
    check("orb deactivated", not gm.spawner.orbs[0].active)

    print("\n6. lane movement is clamped")
    gm = new_game(); gm.start_run()
    for _ in range(6):
        gm.player.move_left()
    check("cannot go past left lane", gm.player.lane == C.LANES[0])
    for _ in range(6):
        gm.player.move_right()
    check("cannot go past right lane", gm.player.lane == C.LANES[-1])

    print("\n7. autopilot survival (fairness of generated patterns)")
    # The bot is a fixture, not a balance oracle -- a human weaves further
    # ahead than it does. What this proves is that generated patterns are
    # clearable and that physics, collision and spawning agree with each other.
    survivals = []
    for seed in range(8):
        import random
        gm = new_game()
        gm.spawner.rng = random.Random(seed)
        gm.start_run()
        t = run_autopilot(gm, 180.0, draw_every=180)
        survivals.append(t)
        print(f"     seed {seed}: survived {t:6.1f}s  score={gm.run.score:8.0f}  "
              f"orbs={gm.run.orbs:3d}  speed={gm.run.speed:.1f}")
    worst = min(survivals)
    median = sorted(survivals)[len(survivals) // 2]
    check("autopilot clears the early game on every seed", worst >= 30.0,
          f"worst={worst:.1f}s")
    check("median survival is a full run", median >= 45.0,
          f"median={median:.1f}s")

    print("\n8. restart resets cleanly")
    gm = new_game(); gm.start_run()
    run_autopilot(gm, 20.0)
    gm.death_timer = 0.0
    gm.state = State.GAME_OVER
    gm.start_run()
    check("score reset", gm.run.score == 0.0)
    check("distance reset", gm.run.distance == 0.0)
    check("player alive", gm.player.state.value != "dead")
    check("track reset", gm.track.distance == 0.0)
    check("obstacles cleared", len(gm.spawner.active_obstacles()) == 0)

    print("\n9. rendering does not raise in any state")
    gm = new_game()
    gm.draw()                                   # menu
    gm.start_run(); run_autopilot(gm, 3.0); gm.draw()
    gm.state = State.PAUSED; gm.draw()
    gm.state = State.GAME_OVER; gm.death_timer = 0.0; gm.draw()
    gm.show_debug = True; gm.draw()
    check("all states render", True)

    pygame.quit()
    print("\n" + ("-" * 58))
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
