"""Camera discovery.

OpenCV on macOS addresses cameras by index and exposes no device names, so the
only way to tell a MacBook camera from a Continuity Camera iPhone is to open
each index and look at what it reports. An iPhone typically offers a much
larger native frame and 60fps.
"""

import cv2

MAX_PROBE = 5


def probe(index: int, warmup: int = 3):
    """Return a dict describing camera `index`, or None if it will not open."""
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        cap.release()
        return None
    try:
        ok = False
        frame = None
        for _ in range(warmup):
            ok, frame = cap.read()
            if ok:
                break
        if not ok or frame is None:
            return None
        h, w = frame.shape[:2]
        return {
            "index": index,
            "width": w,
            "height": h,
            "fps": cap.get(cv2.CAP_PROP_FPS) or 0.0,
        }
    finally:
        cap.release()


def list_cameras(max_index: int = MAX_PROBE):
    found = []
    for i in range(max_index):
        info = probe(i)
        if info:
            found.append(info)
    return found


def describe(info) -> str:
    px = info["width"] * info["height"]
    # A Continuity Camera iPhone reports a far larger native frame than the
    # built-in FaceTime camera, which is the only signal available here.
    guess = "likely iPhone / external" if px >= 1920 * 1080 else "likely built-in"
    return (f"  index {info['index']}:  {info['width']}x{info['height']}"
            f"  @ {info['fps']:.0f}fps   ({guess})")
