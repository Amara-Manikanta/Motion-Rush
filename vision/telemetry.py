"""Gesture telemetry.

Writes one CSV row per camera frame so a real play session can be analysed
afterwards -- which is the only way to tune thresholds against how a person
actually moves, rather than against a synthetic model of it.

Cheap by construction: ~30 rows/second, buffered, and truncated at the start
of every session so the file never grows without bound.
"""

import os
import time

LOG_PATH = "/tmp/dash_catalyst_gestures.csv"
HEADER = ("t_ms,tracked,lean_sw,rise_sw,rise_vel_sw_s,zone,"
          "jump,duck,cam_frames,detections\n")
FLUSH_EVERY = 30


class GestureLog:
    def __init__(self, path=LOG_PATH, enabled=True):
        self.enabled = enabled
        self.path = path
        self._fh = None
        self._t0 = time.time()
        self._pending = 0
        self._rows = 0
        if not enabled:
            return
        try:
            self._fh = open(path, "w", buffering=1 << 16)
        except OSError:
            self.enabled = False
            return
        self._fh.write(HEADER)

    def session_header(self, profile, camera_fps, extra=""):
        if not self.enabled or self._fh is None:
            return
        self._fh.write(
            f"# session {time.strftime('%Y-%m-%d %H:%M:%S')}  "
            f"camera_fps={camera_fps:.1f}  "
            f"neutral=({profile.neutral_x:.3f},{profile.neutral_y:.3f})  "
            f"lean={profile.lean_threshold:.3f}  "
            f"jump={profile.jump_threshold:.3f}  "
            f"duck={profile.duck_threshold:.3f}  "
            f"calibrated={profile.calibrated}  {extra}\n")
        self._fh.write(HEADER)

    def write(self, state, cam_frames, detections):
        if not self.enabled or self._fh is None:
            return
        t_ms = (time.time() - self._t0) * 1000.0
        self._fh.write(
            f"{t_ms:.0f},{int(state.tracked)},{state.lean:.4f},"
            f"{state.rise:.4f},{state.rise_vel:.3f},{state.lane_zone},"
            f"{int(state.jump)},{int(state.duck)},{cam_frames},{detections}\n")
        self._rows += 1
        self._pending += 1
        if self._pending >= FLUSH_EVERY:
            self._fh.flush()
            self._pending = 0

    def note(self, text):
        """Record a one-off event (calibration finished, run started, ...)."""
        if not self.enabled or self._fh is None:
            return
        t_ms = (time.time() - self._t0) * 1000.0
        self._fh.write(f"# {t_ms:.0f}ms  {text}\n")

    def close(self):
        if self._fh is not None:
            try:
                self._fh.write(f"# {self._rows} rows\n")
                self._fh.close()
            except OSError:
                pass
            self._fh = None
