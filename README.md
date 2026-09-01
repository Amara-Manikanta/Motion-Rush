# Dash Catalyst

A camera-controlled three-lane endless runner. Play it with the keyboard, or
stand up and control it with your body through the webcam.

Original code, art and branding. The *architecture* follows the well-known
endless-runner pattern (discrete lanes, AABB collision, pooled entities).

## Run

```bash
.venv/bin/python main.py                    # keyboard
.venv/bin/python main.py --gesture          # webcam body control
.venv/bin/python main.py --gesture --camera # ...with the webcam picture-in-picture
```

Or double-click **Dash Catalyst.app** on the Desktop.

| Action | Keyboard | Body |
|---|---|---|
| Change lane | `A`/`D` or `←`/`→` | lean left / right |
| Jump | `W` / `↑` / `Space` | jump or stretch up |
| Duck | `S` / `↓` | crouch |
| Pause | `P` | — |
| Switch keyboard ⇄ camera | `G` (on the title screen) | — |
| Debug overlay | `F3` | — |
| Toggle webcam view | `C` | — |
| Recalibrate | `K` | — |
| Quit | `Esc` | — |

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

For webcam control you also need the pose model (~5 MB, downloaded once):

```bash
curl -L -o assets/models/pose_landmarker_lite.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
```

Without it the game still runs; `--gesture` just falls back to the keyboard.

On first use macOS will ask for camera permission. Launch via **Dash
Catalyst.app** so the prompt is attributed to the game (the bundle carries
`NSCameraUsageDescription`). The capture thread retries for ~20s, so you can
grant access while the "waiting for camera" screen is up.

## Tests

```bash
.venv/bin/python -m tests.test_gameplay   # physics, collision, scoring, fairness
.venv/bin/python -m tests.test_gestures   # gesture classification (no camera needed)
```

`test_gameplay` includes an autopilot that plays real runs. It is a fixture,
not a balance oracle — its job is to prove that generated obstacle patterns are
clearable and that physics, collision and spawning agree with each other.

## How it works

**Pseudo-3D.** One perspective divide drives everything:
`scale = CAM_FOCAL / (CAM_FOCAL + z)`. Lane spread, object size and ground
height all fall out of that single number. Gameplay is computed in *world*
coordinates, never screen coordinates, so the camera can be re-framed without
touching collision — and swapping in a real 3D renderer stays contained to
`game/renderer.py`.

**Fair spawning.** `game/spawner.py` runs every candidate pattern through a
reachability solver before use. It models lane-change budgets at `MAX_SPEED`
and refuses to place two timed actions (jump/duck) closer together than a
player can physically perform them. Weaving routes count, so a staircase of
barriers is allowed while an unclearable wall is not.

**Forgiving hitboxes.** Collision boxes are deliberately smaller than the drawn
shapes. Drawn widths against a 1.35-unit lane left only 0.375 units of
clearance, which made contact during a lane change nearly unavoidable. This
matters much more once a webcam is the input, since a camera is laggier than a
key press.

**Input is swappable.** Game logic only sees `Action` values, so
`KeyboardInput` and `GestureInput` are interchangeable. Body control is
*positional*: your lean maps directly onto a lane, and the adapter emits
whatever steps close the gap — leaning and holding keeps you there.

**Gesture robustness.** Offsets are measured in *shoulder-width units*, so
stepping toward or away from the camera does not shift the thresholds.
Hysteresis stops a player hovering on a boundary from strobing between lanes,
and jump/duck must return toward neutral before re-firing.

## Layout

```
config.py            all tuning + branding + theme palette
game/                renderer (projection), player, obstacles, orbs, track,
                     spawner (fairness solver), game_manager (state machine)
input/               Action interface, keyboard, gesture adapter
vision/              pose tracker (MediaPipe Tasks), gesture detector, calibration
ui/                  HUD, menus, calibration screen, debug overlay
audio/               procedurally synthesised sound effects (no audio assets)
tools/               icon + screenshot generators
```

## Notes

* MediaPipe 1.x **removed** the old `mediapipe.solutions.pose` API; this uses
  the current Tasks API (`vision.PoseLandmarker`).
* Use `opencv-contrib-python-headless` 4.x. The non-headless and 5.x builds
  bundle their own `libSDL2` (via FFmpeg's `libavdevice`), which collides with
  pygame's SDL and prints duplicate-class warnings.
* The `.app` launcher must not write logs inside `~/Desktop`: a Finder-launched
  app has no TCC permission there, and the failed redirect aborts `exec`
  silently. It logs to `/tmp/dash_catalyst.log`.
