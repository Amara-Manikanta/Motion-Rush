"""Keyboard control -- the Phase 1 input source and the fallback for Phase 2."""

import pygame

from input.input_manager import Action, InputManager

KEYMAP = {
    pygame.K_LEFT: Action.LEFT,
    pygame.K_a: Action.LEFT,
    pygame.K_RIGHT: Action.RIGHT,
    pygame.K_d: Action.RIGHT,
    pygame.K_UP: Action.JUMP,
    pygame.K_w: Action.JUMP,
    pygame.K_SPACE: Action.JUMP,
    pygame.K_DOWN: Action.DUCK,
    pygame.K_s: Action.DUCK,
    pygame.K_RETURN: Action.START,
    pygame.K_r: Action.RESTART,
    pygame.K_p: Action.PAUSE,
    pygame.K_ESCAPE: Action.QUIT,
    pygame.K_F3: Action.TOGGLE_DEBUG,
    pygame.K_c: Action.TOGGLE_CAMERA,
    pygame.K_g: Action.SWITCH_INPUT,
    pygame.K_F11: Action.TOGGLE_FULLSCREEN,
    pygame.K_m: Action.TOGGLE_MODE,
    pygame.K_f: Action.TOGGLE_FULLSCREEN,
    pygame.K_k: Action.RECALIBRATE,
}


class KeyboardInput(InputManager):
    name = "keyboard"

    def handle_event(self, event):
        # Edge-triggered on key-down: holding left must not slide you across
        # every lane, and holding up must not auto-bunny-hop.
        if event.type == pygame.KEYDOWN:
            return KEYMAP.get(event.key)
        return None

    def debug_lines(self):
        return ("input: keyboard",)
