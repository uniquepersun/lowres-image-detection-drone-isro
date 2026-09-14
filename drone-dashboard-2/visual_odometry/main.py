"""Entry point for the monocular visual odometry demo."""

from __future__ import annotations

import time
import threading
import urllib.request
import json
import os

import cv2

try:  # Support both ``python main.py`` and ``import visual_odometry.main``.
    from .config import build_default_config
    from .vo import VisualOdometry
except ImportError:  # pragma: no cover - fallback for script execution
    from config import build_default_config
    from vo import VisualOdometry


# Dashboard URL for sending Visual Odometry data, defaults to localhost:8000
DASHBOARD_VO_URL = os.environ.get("DASHBOARD_VO_URL", "http://localhost:8000/api/vo")


def send_vo_to_dashboard(x: float, y: float):
    """Sends visual odometry coordinates asynchronously using a background thread."""
    def worker():
        try:
            req = urllib.request.Request(
                DASHBOARD_VO_URL,
                data=json.dumps({"x": x, "y": y}).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            # Use a short timeout to prevent blocking
            urllib.request.urlopen(req, timeout=0.1)
        except Exception:
            pass  # Suppress errors if server is unreachable

    threading.Thread(target=worker, daemon=True).start()


def _open_camera(cfg):
    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        raise RuntimeError("Could not open cv2.VideoCapture(0).")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.frame_height)
    cap.set(cv2.CAP_PROP_FPS, cfg.target_fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def main() -> int:
    cfg = build_default_config()
    cap = _open_camera(cfg)
    estimator = VisualOdometry(cfg)
    last_time = time.perf_counter()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera frame capture failed.")
                break

            if frame.shape[1] != cfg.frame_width or frame.shape[0] != cfg.frame_height:
                frame = cv2.resize(frame, (cfg.frame_width, cfg.frame_height), interpolation=cv2.INTER_LINEAR)

            now = time.perf_counter()
            dt = max(now - last_time, 1e-6)
            last_time = now
            result = estimator.process_frame(frame, dt)
            position = result.position
            print(f"{position[0]:.4f} {position[1]:.4f}", flush=True)
            send_vo_to_dashboard(position[0], position[1])
    finally:
        cap.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
