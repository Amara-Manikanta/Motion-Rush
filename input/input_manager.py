"""Input abstraction.

Game logic only ever sees `Action` values, so a keyboard and a webcam are
interchangeable. Any source implements this interface.
"""

from enum import Enum


class Action(Enum):
    LEFT = "left"
    RIGHT = "right"
    JUMP = "jump"
    DUCK = "duck"
    START = "start"
    RESTART = "restart"
    PAUSE = "pause"
    QUIT = "quit"
    TOGGLE_DEBUG = "toggle_debug"
    TOGGLE_CAMERA = "toggle_camera"
    RECALIBRATE = "recalibrate"
    SWITCH_INPUT = "switch_input"
    TOGGLE_FULLSCREEN = "toggle_fullscreen"
    TOGGLE_MODE = "toggle_mode"


class InputManager:
    """Base class. Sources may use events, polling, or both."""

    name = "input"

    def handle_event(self, event):
        """Translate a pygame event into an Action, or None."""
        return None

    def poll(self, dt: float):
        """Actions produced by a continuous source this frame."""
        return ()

    def debug_lines(self):
        """Human-readable state for the debug overlay."""
        return ()

    def close(self):
        pass
