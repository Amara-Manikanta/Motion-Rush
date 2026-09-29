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

    print("\n4b. a lane is held for a minimum dwell, so it cannot flicker")
    # A real session produced 22 zone holds under 0.35s, including a -1 -> +1
    # flip inside 0.1s. Lane control is positional, so a player hovering near
    # the boundary must not be thrown between lanes.
    from vision.gesture_detector import MIN_ZONE_DWELL
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42, n=20)
    holds, prev, run = [], det.zone, 0.0
    for i in range(400):
        # oscillate across the threshold, as a swaying player does
        swing = prof.lean_threshold * (1.35 if (i // 4) % 2 else -1.35)
        st = det.update(frame(0.50 + swing * 0.20, 0.42), DT)
        run += DT
        if st.lane_zone != prev:
            holds.append(run)
            run = 0.0
            prev = st.lane_zone
    short = [h for h in holds if h < MIN_ZONE_DWELL - 1e-6]
    check("no lane is held for less than the dwell", not short,
          f"{len(short)} short holds of {len(holds)}")

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

    print("\n8. a squat jump must fire, a plain stand-up must not")
    # Taken from a real logged session: crouch at t=0, drive upward 0.4s later,
    # peak 0.60sw above baseline. An earlier build armed a 340ms lockout when
    # the duck released and swallowed the jump 150ms later -- which is how
    # people actually jump.
    import math

    def squat_jump(t):
        if t < 0.45:                      # the crouch
            return -0.60 * math.sin(math.pi * t / 0.45)
        a = t - 0.45
        if a < 0.75:                      # drive upward and airborne
            return 0.62 * math.sin(math.pi * a / 0.75)
        return 0.0

    def stand_up(t):
        if t < 0.45:
            return -0.60 * math.sin(math.pi * t / 0.45)
        a = t - 0.45
        if a < 0.40:                      # return to neutral and stop there
            return -0.60 * (1.0 - a / 0.40)
        return 0.0

    def play(arc, seconds=2.0):
        det = GestureDetector(prof)
        feed(det, 0.50, 0.42, n=20)       # settle the baseline
        jumps = ducks = 0
        steps = int(seconds / DT)
        for i in range(steps):
            rise = arc(i * DT)
            st = det.update(frame(0.50, 0.42 - rise * 0.20), DT)
            jumps += int(st.jump)
            ducks += int(st.duck)
        return jumps, ducks

    j, d = play(squat_jump)
    check("squat jump fires a jump", j >= 1, f"jumps={j} ducks={d}")
    check("squat jump also registers the crouch", d >= 1, f"ducks={d}")
    j2, d2 = play(stand_up)
    check("standing up out of a crouch fires NO jump", j2 == 0,
          f"jumps={j2} ducks={d2}")

    print("\n9. a drifted posture must not disable jumping")
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

    print("\n10. implausible landmarks are discarded")
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42)
    st = det.update(frame(0.50, 0.42, width=0.004), DT)   # collapsed shoulders
    check("a collapsed shoulder pair is not trusted", st.tracked is False)

    print("\n11. repeated camera frames are ignored, not re-filtered")
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42)
    stale = frame(0.50, 0.42 - 0.20 * 0.45)
    first = det.update(stale, DT)
    repeats = sum(int(det.update(stale, DT).jump) for _ in range(10))
    check("a repeated frame never re-fires a gesture", repeats == 0,
          f"first={first.jump} repeats={repeats}")

    print("\n12. a vertical mode is never held indefinitely")
    # A real session parked in "down" for 22.8s. Release depends on the body
    # returning past a threshold, which a drifted baseline can make impossible,
    # so there is a hard ceiling regardless.
    from vision.gesture_detector import MAX_HOLD
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42, n=20)
    held = 0.0
    for _ in range(400):                       # hold a deep crouch for >13s
        det.update(frame(0.50, 0.42 + 0.20 * 0.80), DT)
        if det._vertical_mode != "neutral":
            held += DT
        else:
            held = 0.0
        check_max = held
    check("mode is released within the hold ceiling", held <= MAX_HOLD + 0.2,
          f"held={held:.2f}s ceiling={MAX_HOLD}s")

    print("\n13. moving toward the camera is not read as a gesture")
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42, n=30)
    fires = 0
    for i in range(60):                        # walk closer: width 0.20 -> 0.34
        w = 0.20 + 0.14 * (i / 59)
        st = det.update(frame(0.50, 0.44, width=w), DT)
        fires += int(st.jump) + int(st.duck)
    check("approaching the camera fires no gesture", fires == 0, f"fires={fires}")
    st, j, _ = feed(det, 0.50, 0.44 - 0.34 * 0.45, n=40, width=0.34)
    check("jump still works at the new distance", j == 1, f"jumps={j}")

    print("\n14. returning after an absence starts clean")
    det = GestureDetector(prof)
    feed(det, 0.50, 0.42 + 0.20 * 0.70, n=30)  # crouched when tracking was lost
    for _ in range(40):                        # gone for >0.6s
        det.update(None, DT)
    st = det.update(frame(0.50, 0.42), DT)
    check("carried-over posture is discarded", det._vertical_mode == "neutral",
          f"mode={det._vertical_mode}")
    _, j2, _ = feed(det, 0.50, 0.42 - 0.20 * 0.45, n=40)
    check("jump works immediately after returning", j2 == 1, f"jumps={j2}")

    print("\n15. framing is reported so the player can be told")
    from vision.gesture_detector import framing_of
    check("far away -> too_far", framing_of(0.06) == "too_far")
    check("normal distance -> good", framing_of(0.18) == "good")
    check("very close -> too_close", framing_of(0.45) == "too_close")
    det = GestureDetector(prof)
    st = det.update(frame(0.50, 0.42, width=0.02), DT)
    check("unusably far reads as untracked (triggers auto-pause)",
          st.tracked is False)

    print("\n16. calibration waits for the player instead of running on a timer")
    from vision.calibration import (Calibrator, Step, READY_HOLD, LOST_ABORT,
                                    LEAD_SECONDS, HOLD_SECONDS)

    def cal_frame(mx=0.50, my=0.42, w=0.20):
        lms = [(0.5, 0.5, 0.0, 1.0)] * 33
        lms[L_SHOULDER] = (mx - w / 2, my, 0.0, 0.99)
        lms[R_SHOULDER] = (mx + w / 2, my, 0.0, 0.99)
        return PoseFrame(lms, 0.0)

    CDT = 1 / 30.0
    c = Calibrator()
    for _ in range(600):                       # 20s with an empty room
        c.update(CDT, None)
    check("empty frame never advances the sequence", c.index == 0 and c.waiting,
          f"step={c.step.name}")
    check("nothing is sampled from an empty room",
          c.sample_count() == 0)

    c = Calibrator()
    for _ in range(600):                       # present, but badly framed
        c.update(CDT, cal_frame(), framing_ok=False)
    check("a badly framed player does not start it", c.index == 0 and c.waiting)

    c = Calibrator()
    for _ in range(int(READY_HOLD / CDT) + 2):
        c.update(CDT, cal_frame(), framing_ok=True)
    check("starts once the player is framed and steady", c.armed is True,
          f"ready={c.ready_fraction:.2f}")

    c = Calibrator()                            # manual start
    c.update(CDT, None)
    c.begin_step()
    check("SPACE starts the step immediately", c.armed is True)

    # Losing the body mid-step abandons it rather than banking a partial sample
    c = Calibrator()
    for _ in range(int((READY_HOLD + LEAD_SECONDS + 0.4) / CDT)):
        c.update(CDT, cal_frame(), framing_ok=True)
    check("sampling has begun", c.sampling and c.sample_count() > 0,
          f"samples={c.sample_count()}")
    for _ in range(int((LOST_ABORT + 0.1) / CDT)):
        c.update(CDT, None)
    check("walking out mid-step abandons it", c.waiting and c.index == 0,
          f"step={c.step.name} waiting={c.waiting}")
    check("the partial sample is discarded", c.sample_count() == 0)

    # And a full, properly-attended run still completes
    c = Calibrator()
    poses = {Step.NEUTRAL: (0.50, 0.42), Step.LEFT: (0.36, 0.42),
             Step.RIGHT: (0.64, 0.42), Step.JUMP: (0.50, 0.33),
             Step.DUCK: (0.50, 0.56)}
    guard = 0
    while not c.done and guard < 4000:
        c.update(CDT, cal_frame(*poses[c.step]), framing_ok=True)
        guard += 1
    check("an attended run still completes", c.done, f"iterations={guard}")
    check("and produces real thresholds, not defaults",
          not c.profile.weak, c.profile.describe())

    print("\n17. lost tracking is reported, not guessed at")
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
