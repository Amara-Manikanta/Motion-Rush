"""MediaPipe Pose wrapper running on a background thread.

MediaPipe 1.x removed the old `mediapipe.solutions.pose` helper entirely, so
this uses the Tasks API (`vision.PoseLandmarker`) in LIVE_STREAM mode. That
needs a model file on disk -- see MODEL_URL / ensure_model().

Capture runs off the main thread: a webcam read blocks for ~30ms, which would
otherwise cost the game a third of its frame budget.
"""

import os
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         os.pardir, "assets", "models")
MODEL_NAME = "pose_landmarker_lite.task"
MODEL_PATH = os.path.normpath(os.path.join(MODEL_DIR, MODEL_NAME))
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_lite/float16/1/pose_landmarker_lite.task")

# The 33-landmark topology, by index.
NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28


class ModelMissing(RuntimeError):
    """Raised when the pose model has not been downloaded yet."""

    def __init__(self):
        super().__init__(
            f"pose model not found at {MODEL_PATH}\n"
            f"Download it once with:\n"
            f"  curl -L -o '{MODEL_PATH}' '{MODEL_URL}'")


@dataclass
class PoseFrame:
    """One frame of normalised landmarks. x/y are in [0, 1] image space."""
    landmarks: list          # [(x, y, z, visibility), ...] length 33
    timestamp: float

    def point(self, idx):
        return self.landmarks[idx]

    def visible(self, idx, thresh=0.7) -> bool:
        return self.landmarks[idx][3] >= thresh

    def midpoint(self, a, b):
        pa, pb = self.landmarks[a], self.landmarks[b]
        return ((pa[0] + pb[0]) * 0.5, (pa[1] + pb[1]) * 0.5)

    @property
    def shoulder_width(self) -> float:
        la, ra = self.landmarks[L_SHOULDER], self.landmarks[R_SHOULDER]
        return max(1e-4, abs(la[0] - ra[0]))


class PoseTracker:
    def __init__(self, camera_index=0, model_path=MODEL_PATH,
                 capture_size=(640, 480), preview_size=(224, 168),
                 mirror=True):
        if not os.path.exists(model_path):
            raise ModelMissing()

        # Imported lazily so the game still starts without mediapipe present.
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            PoseLandmarker, PoseLandmarkerOptions, RunningMode)
        import mediapipe as mp

        self._mp = mp
        self.mirror = mirror
        self.preview_size = preview_size

        # The camera is opened on the worker thread, not here. On macOS the
        # first access raises the TCC permission prompt, and opening inline
        # would fail instantly while that prompt is still on screen -- the
        # player would have to grant access and then retry. Retrying in the
        # background lets the game sit on "waiting for camera" and connect the
        # moment they approve.
        self.camera_index = camera_index
        self.capture_size = capture_size
        self.cap = None
        self.reported_fps = 0.0
        self.status = "starting"        # starting | ok | denied

        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.LIVE_STREAM,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            result_callback=self._on_result,
        )
        self.landmarker = PoseLandmarker.create_from_options(options)

        self._lock = threading.Lock()
        self._frame = None            # latest PoseFrame
        self._preview = None          # latest small RGB ndarray
        self._running = False
        self._thread = None
        self._frames_seen = 0
        self._detections = 0
        self._t0 = time.time()

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="pose-tracker")
        self._thread.start()

    def close(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        try:
            self.landmarker.close()
        except Exception:
            pass
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    # -- capture thread -----------------------------------------------------

    def _open_camera(self) -> bool:
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            cap.release()
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_size[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_size[1])
        # A capture buffer is pure input lag: by the time a queued frame is
        # read it already describes the past. One slot keeps us on the newest.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        # Ask for 60fps. Halving the frame interval halves the quantisation
        # floor on every gesture; the driver clamps to what it supports.
        cap.set(cv2.CAP_PROP_FPS, 60)
        self.cap = cap
        self.reported_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        return True

    def _loop(self):
        attempts = 0
        while self._running and self.cap is None:
            if self._open_camera():
                self.status = "ok"
                break
            attempts += 1
            # ~20s of patience: long enough for the player to find the dialog.
            self.status = "starting" if attempts < 40 else "denied"
            time.sleep(0.5)

        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue

            if self.mirror:
                # Mirror so leaning left on screen matches leaning left in life.
                frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            small = cv2.resize(rgb, self.preview_size,
                               interpolation=cv2.INTER_AREA)
            with self._lock:
                self._preview = small
                self._frames_seen += 1

            mp_image = self._mp.Image(
                image_format=self._mp.ImageFormat.SRGB, data=rgb)
            # Timestamps must increase monotonically for LIVE_STREAM mode.
            ts_ms = int((time.time() - self._t0) * 1000)
            try:
                self.landmarker.detect_async(mp_image, ts_ms)
            except Exception:
                pass

    def _on_result(self, result, output_image, timestamp_ms):
        if not result.pose_landmarks:
            return
        lms = result.pose_landmarks[0]
        packed = [(lm.x, lm.y, lm.z, getattr(lm, "visibility", 1.0))
                  for lm in lms]
        with self._lock:
            self._frame = PoseFrame(packed, time.time())
            self._detections += 1

    # -- main-thread accessors ---------------------------------------------

    def latest(self):
        with self._lock:
            return self._frame

    def preview_array(self):
        with self._lock:
            return None if self._preview is None else self._preview.copy()

    def stats(self):
        with self._lock:
            return self._frames_seen, self._detections
