#!/usr/bin/env python3
"""Dash Catalyst -- entry point.

    python3 main.py                 keyboard controls
    python3 main.py --gesture       webcam body controls (Phase 2)
    python3 main.py --gesture --camera --debug
"""

import argparse
import sys

import pygame

import config as C
from audio.sound_manager import SoundManager
from game.game_manager import GameManager
from input.keyboard_input import KeyboardInput


def build_input(args, sound):
    """Pick an input source, falling back to the keyboard if vision fails."""
    if not args.gesture:
        return KeyboardInput()
    try:
        from input.gesture_input import GestureInput
        return GestureInput(camera_index=args.camera_index,
                            preview=args.camera or args.debug,
                            log=not args.no_gesture_log,
                            mirror=not args.no_mirror,
                            capture_size=parse_size(args.capture_size))
    except Exception as exc:                      # noqa: BLE001
        print(f"[dash-catalyst] gesture input unavailable ({exc}); "
              f"falling back to keyboard.", file=sys.stderr)
        return KeyboardInput()


def switch_input(game, source, args):
    """Toggle between keyboard and camera control without restarting."""
    if source.name == "keyboard":
        try:
            from input.gesture_input import GestureInput
            new_source = GestureInput(camera_index=args.camera_index,
                                      preview=True,
                                      log=not args.no_gesture_log,
                                      mirror=not args.no_mirror,
                                      capture_size=parse_size(args.capture_size))
        except Exception as exc:                  # noqa: BLE001
            game.request_input_switch = False
            game.show_notice(f"Camera unavailable.\n{exc}", 8.0)
            return source
        game.show_camera = True
    else:
        new_source = KeyboardInput()
        game.show_camera = False

    source.close()
    game.set_input(new_source)
    return new_source


def parse_size(text, default=(1280, 960)):
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return default


def run_camera_check(args):
    """Live framing helper. Returns 0 when the player continues, 1 on quit."""
    import config as C
    from ui.camera_check import CameraCheck

    pygame.init()
    pygame.display.set_caption(f"{C.GAME_TITLE} — camera setup")
    flags = pygame.SCALED | (0 if args.windowed else pygame.FULLSCREEN)
    screen = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H), flags)
    clock = pygame.time.Clock()

    try:
        from input.gesture_input import GestureInput
        source = GestureInput(camera_index=args.camera_index, preview=True,
                              log=False, mirror=not args.no_mirror,
                              capture_size=parse_size(args.capture_size))
    except Exception as exc:                      # noqa: BLE001
        print(f"[dash-catalyst] camera unavailable: {exc}", file=sys.stderr)
        pygame.quit()
        return 1

    # Skip calibration; this screen only cares about framing.
    source.calibrating = False
    check = CameraCheck(C.theme())
    running, proceed = True, False
    try:
        while running:
            dt = min(clock.tick(C.FPS) / 1000.0, C.MAX_DT)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        running, proceed = False, True
            source.poll(dt)
            st = source.state
            check.update(dt, getattr(st, "width", 0.0) or 0.0)
            glow = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
            check.draw(screen, glow, source.preview_surface(), st,
                       source.tracker.reported_fps, source.camera_status,
                       source.tracker.actual_size)
            screen.blit(glow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            pygame.display.flip()
    finally:
        source.close()
        pygame.quit()
    return 0 if proceed else 1


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Dash Catalyst")
    p.add_argument("--gesture", action="store_true",
                   help="use webcam body tracking instead of the keyboard")
    p.add_argument("--camera", action="store_true",
                   help="show the webcam picture-in-picture during play")
    p.add_argument("--camera-index", type=int, default=0,
                   help="OpenCV camera index (default 0). Use --list-cameras "
                        "to find your iPhone's index.")
    p.add_argument("--list-cameras", action="store_true",
                   help="probe attached cameras and exit")
    p.add_argument("--capture-size", default="1280x960",
                   help="requested camera resolution, e.g. 1280x960 (4:3, more "
                        "vertical view) or 1920x1080. The driver picks the "
                        "closest mode it supports.")
    p.add_argument("--camera-check", action="store_true",
                   help="live framing helper: aim the camera before playing")
    p.add_argument("--no-mirror", action="store_true",
                   help="do not flip the camera image (use if leaning left "
                        "moves you right)")
    p.add_argument("--debug", action="store_true",
                   help="start with the F3 debug overlay visible")
    p.add_argument("--no-sound", action="store_true", help="disable audio")
    p.add_argument("--mode", choices=sorted(C.MODES), default="exercise",
                   help="pacing profile (default: exercise)")
    p.add_argument("--windowed", action="store_true",
                   help="run in a window instead of fullscreen")
    p.add_argument("--no-gesture-log", action="store_true",
                   help="disable gesture telemetry (/tmp/dash_catalyst_gestures.csv)")
    p.add_argument("--frames", type=int, default=0,
                   help="run N frames headless then exit (used by tests)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.list_cameras:
        from vision.cameras import list_cameras, describe
        found = list_cameras()
        if not found:
            print("No cameras opened. Grant camera access, or check that "
                  "Continuity Camera is enabled on your iPhone.")
            return 1
        print(f"{len(found)} camera(s):")
        for info in found:
            print(describe(info))
        print("\nRun with:  python main.py --gesture --camera-index N")
        return 0
    headless = args.frames > 0

    C.apply_mode(args.mode)

    if args.camera_check:
        return run_camera_check(args)

    pygame.init()
    pygame.display.set_caption(f"{C.GAME_TITLE} — {C.GAME_TAGLINE}")

    if headless:
        flags = pygame.HIDDEN
    else:
        # SCALED keeps the logical 1280x720 canvas and lets SDL letterbox and
        # scale it to the display, so no layout code has to know the monitor.
        flags = pygame.SCALED
        if not args.windowed:
            flags |= pygame.FULLSCREEN
    screen = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H), flags, vsync=1)
    # The game draws to an offscreen canvas so screen-shake can offset it.
    canvas = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    clock = pygame.time.Clock()

    sound = SoundManager(enabled=not args.no_sound and not headless)
    source = build_input(args, sound)
    game = GameManager(canvas, source, sound, show_camera=args.camera)
    game.show_debug = args.debug

    frame = 0
    try:
        while game.running:
            dt = min(clock.tick(C.FPS) / 1000.0, C.MAX_DT)
            game.fps = clock.get_fps()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    game.running = False
                    break
                game.handle_action(source.handle_event(event))

            for action in source.poll(dt):
                game.handle_action(action)

            if game.request_input_switch:
                source = switch_input(game, source, args)
            if game.request_fullscreen_toggle:
                game.request_fullscreen_toggle = False
                if not headless:
                    pygame.display.toggle_fullscreen()

            game.update(dt)
            game.draw()

            ox, oy = game.screen_offset()
            screen.fill((0, 0, 0))
            screen.blit(canvas, (ox, oy))
            pygame.display.flip()

            frame += 1
            if headless and frame >= args.frames:
                break
    finally:
        source.close()
        sound.close()
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
