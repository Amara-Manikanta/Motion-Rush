"""Measure how long after a jump starts the detector actually fires.

Simulates the real pipeline: a webcam delivering frames at CAM_FPS while the
game polls at GAME_FPS, so the detector sees each camera frame repeated. The
jump itself is modelled as the shoulder-height arc of someone hopping in place.

Run: python -m tests.bench_latency
"""

import math

from vision.calibration import CalibrationProfile
from vision.gesture_detector import GestureDetector
from vision.pose_tracker import PoseFrame, L_SHOULDER, R_SHOULDER

CAM_FPS = 30.0
GAME_FPS = 60.0
SHOULDER_W = 0.20
NEUTRAL_Y = 0.42


def jump_arc(t, peak=0.45, air=0.50, crouch=0.06, wind=0.12):
    """Shoulder rise in shoulder-widths at time t (s). Jump starts at t=0.

    Real jumps start with a small downward counter-movement (the wind-up),
    which is exactly the part a displacement-only trigger has to sit through.
    """
    if t < 0:
        return 0.0
    if t < wind:
        return -crouch * math.sin(math.pi * t / wind)
    a = t - wind
    if a < air:
        return peak * math.sin(math.pi * a / air)
    return 0.0


def duck_arc(t, depth=0.60, hold=0.45):
    if t < 0:
        return 0.0
    if t < hold:
        return -depth * min(1.0, t / 0.12)
    return -depth * max(0.0, 1.0 - (t - hold) / 0.15)


def frame_at(rise_sw, ts, lean_sw=0.0):
    mx = 0.5 + lean_sw * SHOULDER_W
    my = NEUTRAL_Y - rise_sw * SHOULDER_W
    lms = [(0.5, 0.5, 0.0, 1.0)] * 33
    lms[L_SHOULDER] = (mx - SHOULDER_W / 2, my, 0.0, 0.99)
    lms[R_SHOULDER] = (mx + SHOULDER_W / 2, my, 0.0, 0.99)
    return PoseFrame(lms, ts)


def run(arc, profile, seconds=1.4, start_at=0.30, gesture="jump"):
    """Return (latency_ms or None, false_fires_before_start)."""
    det = GestureDetector(profile)
    game_dt = 1.0 / GAME_FPS
    cam_dt = 1.0 / CAM_FPS

    t = 0.0
    next_cam = 0.0
    current = frame_at(0.0, 0.0)
    fired_at = None
    early = 0

    while t < seconds:
        if t >= next_cam:
            current = frame_at(arc(t - start_at), t)
            next_cam += cam_dt
        st = det.update(current, game_dt)
        hit = st.jump if gesture == "jump" else st.duck
        if hit:
            if t < start_at:
                early += 1
            elif fired_at is None:
                fired_at = t
        t += game_dt

    latency = None if fired_at is None else (fired_at - start_at) * 1000.0
    return latency, early


def idle_noise_test(profile, seconds=6.0):
    """Breathing/sway must never fire a gesture."""
    det = GestureDetector(profile)
    game_dt = 1.0 / GAME_FPS
    cam_dt = 1.0 / CAM_FPS
    t = 0.0
    next_cam = 0.0
    cur = frame_at(0.0, 0.0)
    fires = 0
    while t < seconds:
        if t >= next_cam:
            # breathing (~0.25Hz, 0.03sw) + small postural sway
            rise = 0.03 * math.sin(2 * math.pi * 0.25 * t)
            lean = 0.05 * math.sin(2 * math.pi * 0.13 * t)
            cur = frame_at(rise, t, lean)
            next_cam += cam_dt
        st = det.update(cur, game_dt)
        fires += int(st.jump) + int(st.duck)
        t += game_dt
    return fires


def hop_arc(t, peak=0.30, air=0.34, crouch=0.03, wind=0.07):
    """A quick low hop -- less wind-up, faster."""
    return jump_arc(t, peak=peak, air=air, crouch=crouch, wind=wind)


def stretch_arc(t, peak=0.40, rise_time=0.30):
    """Reaching up tall with no counter-movement at all."""
    if t < 0:
        return 0.0
    if t < rise_time:
        return peak * (t / rise_time)
    return peak


def duck_then_stand(t, depth=0.60, down=0.12, hold=0.55, up=0.20):
    """Crouch, hold, then stand back up.

    Standing up is a fast upward move from below neutral -- the exact shape of
    a jump takeoff. It must NOT be read as a jump.
    """
    if t < 0:
        return 0.0
    if t < down:
        return -depth * (t / down)
    if t < down + hold:
        return -depth
    a = t - down - hold
    if a < up:
        return -depth * (1.0 - a / up)
    return 0.0


def count_fires(arc, profile, seconds=2.0, start_at=0.30):
    det = GestureDetector(profile)
    gdt, cdt = 1.0 / GAME_FPS, 1.0 / CAM_FPS
    t, nxt, cur = 0.0, 0.0, frame_at(0.0, 0.0)
    jumps = ducks = 0
    while t < seconds:
        if t >= nxt:
            cur = frame_at(arc(t - start_at), t)
            nxt += cdt
        st = det.update(cur, gdt)
        jumps += int(st.jump)
        ducks += int(st.duck)
        t += gdt
    return jumps, ducks


def main():
    prof = CalibrationProfile(neutral_x=0.5, neutral_y=NEUTRAL_Y,
                              lean_threshold=0.25, jump_threshold=0.19,
                              duck_threshold=0.29, calibrated=True)

    jl, je = run(jump_arc, prof, gesture="jump")
    dl, de = run(duck_arc, prof, gesture="duck")
    noise = idle_noise_test(prof)

    print(f"  jump latency : {('%.0f ms' % jl) if jl else 'NEVER FIRED':>12}"
          f"   (false fires before jump: {je})")
    print(f"  duck latency : {('%.0f ms' % dl) if dl else 'NEVER FIRED':>12}"
          f"   (false fires before duck: {de})")
    print(f"  idle 6s      : {noise} false gesture(s) from breathing/sway")
    hl, _ = run(hop_arc, prof, gesture="jump")
    sl, _ = run(stretch_arc, prof, gesture="jump")
    print(f"  quick hop    : {('%.0f ms' % hl) if hl else 'NEVER FIRED':>12}")
    print(f"  stretch up   : {('%.0f ms' % sl) if sl else 'NEVER FIRED':>12}"
          f"   (no counter-movement)")

    print("\n  false-positive guards:")
    j, d = count_fires(duck_then_stand, prof)
    print(f"    crouch-then-stand -> {d} duck (want 1), {j} jump (want 0)")
    j2, d2 = count_fires(jump_arc, prof)
    print(f"    jump              -> {j2} jump (want 1), {d2} duck (want 0)")

    print(f"\n  camera {CAM_FPS:.0f}fps -> {1000/CAM_FPS:.0f}ms is the hard floor "
          f"(one frame interval)")
    return jl, dl, noise


if __name__ == "__main__":
    main()
