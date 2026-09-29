"""Summarise a gesture telemetry session.

Reports the things that have actually gone wrong in practice: bad calibration,
distance drift, the detector parking in one mode, and how many real jumps were
caught. Run after a session to see whether a change helped.
"""

import statistics as st
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from vision.gesture_detector import FRAMING_IDEAL, framing_of  # noqa: E402

DEFAULT_LOG = "/tmp/dash_catalyst_gestures.csv"


def load(path):
    notes, rows = [], []
    for line in open(path):
        if line.startswith("#"):
            notes.append(line.strip())
            continue
        if line.startswith("t_ms"):
            continue
        p = line.strip().split(",")
        if len(p) < 14 or p[6] == "":
            continue
        rows.append(dict(t=float(p[0]) / 1000, tracked=int(p[1]),
                         lean=float(p[2]), rise=float(p[3]), vel=float(p[4]),
                         base=float(p[5]), mx=float(p[6]), my=float(p[7]),
                         w=float(p[8]), zone=int(p[9]), jump=int(p[10]),
                         duck=int(p[11]), cf=int(p[12]), det=int(p[13])))
    return notes, rows


def main(path=DEFAULT_LOG):
    try:
        notes, rows = load(path)
    except OSError as exc:
        print(f"could not read {path}: {exc}")
        return 1
    if not rows:
        print(f"{path} has no usable rows yet — play a session first.")
        return 1

    print(f"\n=== {path} ===")
    for n in notes:
        if "session" in n or "calibration" in n:
            print("  " + n.lstrip("# "))

    dur = rows[-1]["t"] - rows[0]["t"]
    tr = [r for r in rows if r["tracked"]]
    cam = []
    for r in tr:
        if not cam or (r["mx"], r["my"]) != (cam[-1]["mx"], cam[-1]["my"]):
            cam.append(r)

    print(f"\nSESSION      {dur:.0f}s   tracked {100*len(tr)/len(rows):.0f}%"
          f"   camera {rows[-1]['cf']/dur:.0f}fps"
          f"   pose {rows[-1]['det']/dur:.0f}fps")

    # -- framing / distance -------------------------------------------------
    ws = sorted(r["w"] for r in cam)
    med = st.median(ws)
    verdict = framing_of(med)
    # p5..p95, not min..max: a handful of mis-detected frames make the raw
    # range look like wild movement and sends the player chasing a problem
    # they do not have.
    if len(ws) >= 20:
        q = st.quantiles(ws, n=100)
        lo, hi = q[4], q[94]
    else:
        lo, hi = ws[0], ws[-1]
    spread = hi / max(1e-4, lo)
    outliers = sum(1 for w in ws if w < lo or w > hi)
    print(f"\nDISTANCE     median shoulder width {med:.3f} ({verdict})"
          f"   ideal {FRAMING_IDEAL[0]:.2f}-{FRAMING_IDEAL[1]:.2f}")
    print(f"             typical range {lo:.3f}-{hi:.3f} = {spread:.1f}x spread"
          f"   ({outliers} outlier frames ignored)")
    if spread > 2.5:
        print("             ^ you moved a lot; a fixed camera position helps most")

    # -- dropouts -----------------------------------------------------------
    gaps, run, start, prev = [], 0.0, None, rows[0]["t"]
    for r in rows:
        dt = max(0.0, r["t"] - prev)
        prev = r["t"]
        if not r["tracked"]:
            if start is None:
                start = r["t"]
            run += dt
        else:
            if start is not None and run > 0.25:
                gaps.append(run)
            start, run = None, 0.0
    print(f"\nDROPOUTS     {len(gaps)} longer than 0.25s"
          f"   total {sum(gaps):.1f}s   longest {max(gaps, default=0):.1f}s")

    # -- gestures -----------------------------------------------------------
    jumps = sum(r["jump"] for r in rows)
    ducks = sum(r["duck"] for r in rows)
    lanes = sum(1 for a, b in zip(rows, rows[1:]) if a["zone"] != b["zone"])
    print(f"\nGESTURES     jumps {jumps}   ducks {ducks}   lane changes {lanes}")

    # -- real upward movements vs detections --------------------------------
    n = len(cam)
    ys = [r["my"] for r in cam]
    w = st.median(r["w"] for r in cam)

    def local(i, half=35):
        lo, hi = max(0, i - half), min(n, i + half)
        return st.median(ys[lo:hi])

    above = [(local(i) - ys[i]) / w for i in range(n)]
    jt = [r["t"] for r in cam if r["jump"]]
    eps, i = [], 0
    while i < n:
        if above[i] > 0.15:
            k, pk = i, 0.0
            while k < n and above[k] > 0.07:
                pk = max(pk, above[k])
                k += 1
            hit = any(cam[i]["t"] - 0.2 <= x <= cam[k - 1]["t"] + 0.2 for x in jt)
            eps.append((pk, hit))
            i = k
        else:
            i += 1
    # An apparent "jump" of several shoulder-widths is a mis-detected frame,
    # not a movement anyone made; counting those as misses understates the
    # detector.
    big = [e for e in eps if 0.25 <= e[0] <= 1.8]
    bogus = sum(1 for e in eps if e[0] > 1.8)
    if big:
        got = sum(1 for e in big if e[1])
        print(f"             real jumps (raw peak 0.25-1.8sw): {len(big)}"
              f"   detected {got}   rate {100*got/len(big):.0f}%")
        if bogus:
            print(f"             ({bogus} implausible peak(s) ignored as bad frames)")

    # -- baseline stability -------------------------------------------------
    bases = [r["base"] for r in cam]
    print(f"\nBASELINE     range {min(bases):+.2f} .. {max(bases):+.2f} sw"
          f"   (drift {max(bases)-min(bases):.2f})")

    weak = any("WEAK" in x for x in notes)
    print("\nVERDICT")
    if weak:
        print("  ! calibration was WEAK — redo it (K) with big, deliberate moves")
    if spread > 2.5:
        print("  ! large distance variation — fix the camera in one spot")
    if verdict != "good":
        print(f"  ! typical distance is {verdict} — aim for shoulder width "
              f"{FRAMING_IDEAL[0]:.2f}-{FRAMING_IDEAL[1]:.2f}")
    if not weak and spread <= 2.0 and verdict == "good":
        print("  setup looks good")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG))
