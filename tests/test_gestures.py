"""Gesture-detector checks driven by synthetic landmarks (no camera needed).

Run: python -m tests.test_gestures
"""

import sys

from vision.calibration import CalibrationProfile
from vision.gesture_detector import GestureDetector
from vision.pose_tracker import PoseFrame, L_SHOULDER, R_SHOULDER

DT = 1 / 30.0
FAILURES = []


def check(label, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  -- {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


# Each synthetic frame needs a distinct, increasing timestamp: the detector
# deliberately ignores repeats, because the game polls faster than the camera
# delivers and re-filtering a stale frame would corrupt the measured velocity.
_CLOCK = [0.0]


def frame(mx, my, width=0.20, vis=0.99):
    _CLOCK[0] += DT
    lms = [(0.5, 0.5, 0.0, 1.0)] * 33
    lms[L_SHOULDER] = (mx - width / 2, my, 0.0, vis)
    lms[R_SHOULDER] = (mx + width / 2, my, 0.0, vis)
    return PoseFrame(lms, _CLOCK[0])


def feed(det, mx, my, n=12, width=0.20, vis=0.99):
    """Run n frames at one pose; return (final state, jumps, ducks)."""
    jumps = ducks = 0
    st = None
    for _ in range(n):
        st = det.update(frame(mx, my, width, vis), DT)
        jumps += int(st.jump)
        ducks += int(st.duck)
    return st, jumps, ducks


def main():
    prof = CalibrationProfile(neutral_x=0.5, neutral_y=0.42,
                              lean_threshold=0.25, jump_threshold=0.20,
                              duck_threshold=0.30, calibrated=True)

    print("\n1. lane zones from leaning")
    det = GestureDetector(prof)
    st, _, _ = feed(det, 0.50, 0.42);  check("standing centre -> zone 0", st.lane_zone == 0)
    st, _, _ = feed(det, 0.42, 0.42);  check("lean left -> zone -1", st.lane_zone == -1, f"lean={st.lean:.2f}")
    st, _, _ = feed(det, 0.50, 0.42);  check("return centre -> zone 0", st.lane_zone == 0)
    st, _, _ = feed(det, 0.58, 0.42);  check("lean right -> zone +1", st.lane_zone == 1, f"lean={st.lean:.2f}")

    print("\n2. distance from camera does not change behaviour")
    # One fixed *absolute* shift, viewed from two distances. Far away it is a
    # large fraction of shoulder width and should fire; up close it is a small
    # fraction and should not. That is the whole point of normalising.
    SHIFT = 0.06
    det = GestureDetector(prof)
    st, _, _ = feed(det, 0.5 - SHIFT, 0.42, width=0.20)   # far: 0.30 sw
    check("shift is 0.30 shoulder-widths when far -> fires",
          st.lane_zone == -1, f"lean={st.lean:.2f}sw")
    det = GestureDetector(prof)
    st, _, _ = feed(det, 0.5 - SHIFT, 0.42, width=0.40)   # close: 0.15 sw
    check("same absolute shift is 0.15 shoulder-widths up close -> ignored",
          st.lane_zone == 0, f"lean={st.lean:.2f}sw")

    print("\n3. deadzone rejects small sway")
    det = GestureDetector(prof)
    st, _, _ = feed(det, 0.5 + 0.20 * 0.03, 0.42, n=30)
    check("3% shoulder-width sway stays neutral", st.lane_zone == 0, f"lean={st.lean:.2f}")

    print("\n4. hysteresis prevents strobing on the boundary")
    det = GestureDetector(prof)
    feed(det, 0.44, 0.42)                       # commit to left
    flips = 0
    prev = det.zone
    for i in range(60):                          # hover right on the threshold
        wobble = 0.20 * (prof.lean_threshold + (0.006 if i % 2 else -0.006))
        st = det.update(frame(0.5 - wobble, 0.42), DT)
        if st.lane_zone != prev:
            flips += 1
            prev = st.lane_zone
    check("no strobing while hovering at the threshold", flips == 0, f"flips={flips}")

    print("\n5. jump fires once per rise, not per frame")
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42)
    _, jumps, _ = feed(det, 0.50, 0.42 - 0.20 * 0.45, n=40)
    check("held-high pose fires exactly one jump", jumps == 1, f"jumps={jumps}")
    _, jumps2, _ = feed(det, 0.50, 0.42, n=20)       # return to neutral
    _, jumps3, _ = feed(det, 0.50, 0.42 - 0.20 * 0.45, n=40)
    check("re-arms after returning to neutral", jumps3 == 1, f"jumps={jumps3}")

    print("\n6. duck fires once per crouch")
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42)
    _, _, ducks = feed(det, 0.50, 0.42 + 0.20 * 0.60, n=40)
    check("held crouch fires exactly one duck", ducks == 1, f"ducks={ducks}")

    print("\n7. jump and duck are not confused")
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42)
    _, j, d = feed(det, 0.50, 0.42 - 0.20 * 0.45, n=30)
    check("rising never emits a duck", d == 0 and j == 1, f"jump={j} duck={d}")
    feed(det, 0.50, 0.42, n=20)
    _, j2, d2 = feed(det, 0.50, 0.42 + 0.20 * 0.60, n=30)
    check("crouching never emits a jump", j2 == 0 and d2 == 1, f"jump={j2} duck={d2}")

    print("\n8. a drifted posture must not disable jumping")
    # The real failure this guards: a session where the player stood lower in
    # frame than during calibration. Every frame then read as a deep crouch,
    # the detector latched into 'down', and jump -- which is only tested from
    # neutral -- could never fire again. 4 jumps in 106 seconds of play.
    det = GestureDetector(prof)
    DRIFT = 0.64 * 0.20                      # 0.64 shoulder-widths lower
    feed(det, 0.50, 0.42 + DRIFT, n=150)     # ~5s standing at the new posture
    check("baseline relearns the drifted posture",
          abs(det.state.rise) < 0.10, f"rise={det.state.rise:+.3f}")
    _, jumps, _ = feed(det, 0.50, 0.42 + DRIFT - 0.20 * 0.45, n=40)
    check("jump still fires after a 0.64sw posture drift", jumps == 1,
          f"jumps={jumps}")

    print("\n9. implausible landmarks are discarded")
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42)
    st = det.update(frame(0.50, 0.42, width=0.004), DT)   # collapsed shoulders
    check("a collapsed shoulder pair is not trusted", st.tracked is False)

    print("\n10. repeated camera frames are ignored, not re-filtered")
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42)
    stale = frame(0.50, 0.42 - 0.20 * 0.45)
    first = det.update(stale, DT)
    repeats = sum(int(det.update(stale, DT).jump) for _ in range(10))
    check("a repeated frame never re-fires a gesture", repeats == 0,
          f"first={first.jump} repeats={repeats}")

    print("\n11. lost tracking is reported, not guessed at")
    det = GestureDetector(prof)
    feed(det, 0.42, 0.42)
    st = det.update(None, DT)
    check("no frame -> tracked False", st.tracked is False)
    check("last lane zone is held, not reset", st.lane_zone == -1)
    st = det.update(frame(0.42, 0.42, vis=0.2), DT)
    check("low-visibility landmarks rejected", st.tracked is False)

    print("\n" + "-" * 58)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)}: {FAILURES}")
        return 1
    print("All gesture checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
