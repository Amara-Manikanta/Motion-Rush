# ⚡ Motion Rush

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Pygame-CE](https://img.shields.io/badge/Pygame--CE-2.5%2B-green.svg)](https://pyga.me/)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-Tasks%20Vision-orange.svg?logo=google)](https://developers.google.com/mediapipe)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An exhilarating, camera-controlled three-lane pseudo-3D endless runner. Play using standard keyboard inputs, or step back and control your avatar directly through your webcam using real-time body tracking!

---

## 🌟 Features

- **🧍 Real-Time Body Tracking**: Powered by Google MediaPipe Pose Landmarker Tasks for low-latency full-body tracking.
  - **Lean Left / Right**: Instant lane switching with shoulder-width invariant detection.
  - **Jump / Reach Up**: Jump over low obstacles.
  - **Crouch / Duck**: Slide under overhead hazards.
- **🎮 Seamless Dual Controls**: Switch between webcam motion tracking and keyboard controls on the fly (`G` key on title screen).
- **📐 Custom Pseudo-3D Engine**: Built from scratch with pure Pygame perspective projection math ($scale = \frac{focal}{focal + z}$) without requiring heavy 3D game engines.
- **🧠 Fair Spawner & Reachability Solver**: Evaluates player reaction times and lane change budgets before placing obstacles, guaranteeing that every generated run is physically beatable.
- **🪟 Live Picture-in-Picture (PiP) & Calibration**: Dynamic calibration screen, landmark overlays, and real-time telemetry HUD.
- **🔊 Procedural Audio Engine**: Retro-futuristic sound effects generated programmatically via numpy waveforms—no external sound files required.

---

## 🕹️ Controls

| Action | Keyboard | Body Gesture |
|---|---|---|
| **Change Lane** | `A` / `D` or `←` / `→` | **Lean Left / Right** |
| **Jump** | `W` / `↑` / `Space` | **Jump or Stretch Up** |
| **Duck / Slide** | `S` / `↓` | **Crouch / Duck Down** |
| **Pause / Resume** | `P` | — |
| **Switch Control Mode** | `G` (on title screen) | — |
| **Toggle PiP Camera Feed** | `C` | — |
| **Recalibrate Pose** | `K` | — |
| **Toggle Debug Overlay** | `F3` | — |
| **Quit** | `Esc` | — |

---

## 🚀 Quick Start

### 1. Clone & Environment Setup

```bash
git clone https://github.com/Amara-Manikanta/Motion-Rush.git
cd Motion-Rush

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Download MediaPipe Pose Model

Webcam gesture tracking utilizes the lightweight float16 Pose Landmarker model (~5 MB):

```bash
curl -L -o assets/models/pose_landmarker_lite.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
```

*(If the model file is absent, the game will automatically fall back to keyboard mode.)*

### 3. Launch the Game

```bash
# Standard keyboard mode
python main.py

# Webcam gesture control mode
python main.py --gesture

# Webcam gesture control with live camera PiP feed
python main.py --gesture --camera
```

> **macOS Note**: On first launch with `--gesture`, macOS will request camera permissions. If launching as a packaged `.app`, camera permission prompt will be attributed directly to the application.

---

## 🏗️ Architecture & How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                      Game Loop (60 FPS)                     │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
       [ Input Provider ]              [ World Simulation ]
    ┌──────────┴──────────┐                    │
    ▼                     ▼                    ├─► Player Physics (jump, duck, shift)
KeyboardInput       GestureInput               ├─► Spawner (reachability solver)
                          │                    ├─► Obstacles & Collectibles
                    [ MediaPipe ]              └─► Collision Detection (AABB)
                          │                            │
                    Pose Tracker                       ▼
                          │                    [ Renderer ]
                    Gesture Detector                   │
                          │                    ├─► Perspective Projection
                          └─────────────►      ├─► Dynamic Horizon & Grid
                                               └─► PiP Camera Overlay & HUD
```

### 1. Pseudo-3D Perspective Projection
World space uses standard conventions: $+z$ extends into the screen, $y$ points upwards ($0$ is ground level), and $x$ denotes lateral lane position. Every world coordinate $(x, y, z)$ projects to the screen via:
$$\text{scale} = \frac{\text{CAM\_FOCAL}}{\text{CAM\_FOCAL} + z}$$
Game physics and collision boundaries are computed in world units rather than pixels, keeping simulation independent of screen resolution and camera FOV.

### 2. Gesture Invariance & Hysteresis
- **Scale Invariance**: Lateral displacement is normalized against the player's detected shoulder width, ensuring detection remains accurate regardless of distance from the camera.
- **Hysteresis Buffers**: Prevents rapid jitter when standing near lane borders.
- **State Relaxation**: Jumps and crouches require returning to a neutral baseline before re-triggering.

### 3. Fair Spawner
`game/spawner.py` utilizes a reachability solver that models maximum lateral velocity and action execution intervals at peak speed (`MAX_SPEED`). It prevents unnavigable walls while permitting dynamic patterns like weaving staircases.

---

## 🧪 Testing & Verification

Run the comprehensive test suite and autopilot simulations:

```bash
# Verify physics, collision geometry, scoring, and spawner fairness
python -m tests.test_gameplay

# Test pose classification logic without requiring a physical camera
python -m tests.test_gestures

# Benchmark pose detection latency
python -m tests.bench_latency
```

The test runner includes an intelligent autopilot fixture that navigates real obstacle patterns to mathematically prove level fairness and collision consistency.

---

## 📁 Repository Structure

```
Motion-Rush/
├── assets/                 # Icons, fonts, models
│   ├── images/             # App icons (.icns)
│   └── models/             # Pose landmarker model
├── audio/                  # Synthesizer & audio management
│   └── sound_manager.py    # Procedural waveform sound generator
├── game/                   # Core game mechanics
│   ├── game_manager.py     # Game state machine
│   ├── player.py           # Physics & lane interpolation
│   ├── obstacle.py         # Jump/duck/lane barrier definitions
│   ├── collectible.py      # Energy orbs & bonus scoring
│   ├── spawner.py          # Reachability & fairness solver
│   ├── track.py            # Road grid & environment lines
│   └── renderer.py         # Pseudo-3D projection pipeline
├── input/                  # Input abstractions
│   ├── input_manager.py    # Action interface & dispatcher
│   ├── keyboard_input.py   # Keyboard event mapper
│   └── gesture_input.py    # Body pose to Action bridge
├── vision/                 # Computer vision pipeline
│   ├── pose_tracker.py     # MediaPipe Tasks wrapper
│   ├── gesture_detector.py # Pose geometry & gesture classifier
│   ├── calibration.py      # User baseline calibration
│   └── telemetry.py        # Visual landmark debugging
├── ui/                     # User interface & menus
│   ├── menu.py             # Title, pause & game over screens
│   ├── hud.py              # Score, multiplier, speed display
│   ├── calibration_screen.py # Interactive setup screen
│   ├── debug_overlay.py    # Performance & debug stats
│   └── fonts.py            # Typography loaders
├── tests/                  # Automated verification & benchmarks
│   ├── test_gameplay.py    # Gameplay & fairness tests
│   ├── test_gestures.py    # Mock gesture tests
│   ├── autopilot.py        # Autonomous runner fixture
│   └── bench_latency.py    # Latency evaluation
├── config.py               # Global tunable parameters & color themes
├── main.py                 # Application entry point
├── requirements.txt        # Python package dependencies
└── README.md
```

---

## ⚙️ Configuration

All game balance parameters, display resolutions, colors, and camera settings are centrally managed in [`config.py`](config.py):
- **Speeds & Acceleration**: `INITIAL_SPEED`, `MAX_SPEED`, `SPEED_ACCEL`
- **Camera Tuning**: `CAM_FOCAL`, `HORIZON_Y`, `GROUND_Y`
- **Vision Thresholds**: `LEAN_ENTER_RATIO`, `JUMP_DY_RATIO`, `DUCK_DY_RATIO`
- **Visual Themes**: Switch between palettes (e.g. `neon_city`) seamlessly.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
