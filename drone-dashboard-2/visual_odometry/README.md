# visual_odometry

Monocular visual odometry demo for a live webcam feed using OpenCV, ORB
features, Lucas-Kanade tracking, essential matrix pose recovery, adaptive scale,
and optional pose filtering.

## Features

- Live capture from `cv2.VideoCapture(0)`
- ORB feature detection with configurable parameters
- Lucas-Kanade optical flow tracking with forward-backward verification
- RANSAC-based essential matrix estimation
- Relative pose recovery with adaptive scale clamping
- Optional EMA, moving average, median filter, and 6-state Kalman smoothing
- Live overlay with pose, confidence, FPS, feature counts, and quality metrics
- Separate 1000x1000 trajectory window

## Install

```bash
cd visual_odometry
python3 -m pip install -r requirements.txt
```

## Run

```bash
python3 main.py
```

## Controls

- `q` or `Esc` to quit
- `r` to reset the estimator

## Notes

- The camera intrinsics in `config.py` are defaults. For better metric stability,
  calibrate your webcam and replace `FX`, `FY`, `CX`, and `CY`.
- Monocular VO cannot recover true metric scale without additional sensors.
  This project uses adaptive relative scaling to keep the trajectory stable and
  bounded.
