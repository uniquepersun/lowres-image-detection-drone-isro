"""
frame_recorder.py

Records camera frames to disk at a configurable interval. Used by the
dashboard to collect a batch of frames for analysis/review.

Two pieces:
  - FrameRecorder     - manages recording on/off, writes JPEGs + JSON sidecars to a temp folder
  - get_recording_zip - packages recorded frames into a zip for download

Each saved frame is named:
    <index>_x<local_x>_y<local_y>.jpg

A companion JSON sidecar (<index>_x<local_x>_y<local_y>.json) is written
alongside every JPEG with the full position snapshot:
    {
        "frame": <index>,
        "local_x": <pos_x>,   # LOCAL_POSITION_NED X in metres
        "local_y": <pos_y>,   # LOCAL_POSITION_NED Y in metres
        "local_z": <pos_z>,   # LOCAL_POSITION_NED Z (up positive) in metres
        "vo_x": <vo_x>,       # visual-odometry X
        "vo_y": <vo_y>,       # visual-odometry Y
        "timestamp": <unix>
    }
"""

import json
import os
import shutil
import threading
import time
from pathlib import Path
from zipfile import ZipFile
from datetime import datetime

RECORD_DIR = "/tmp/drone_frames"
FRAME_INTERVAL = 1.0  # seconds between frames


class FrameRecorder:
    def __init__(self):
        self._lock = threading.Lock()
        self._recording = False
        self._frame_count = 0
        self._start_time = 0.0

    def start(self):
        with self._lock:
            if self._recording:
                return False
            if os.path.exists(RECORD_DIR):
                shutil.rmtree(RECORD_DIR)
            os.makedirs(RECORD_DIR, exist_ok=True)
            self._recording = True
            self._frame_count = 0
            self._start_time = time.time()
            return True

    def stop(self) -> tuple[bool, int]:
        with self._lock:
            was_recording = self._recording
            self._recording = False
            return was_recording, self._frame_count

    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def record_frame(self, jpeg_bytes: bytes) -> bool:
        with self._lock:
            if not self._recording:
                return False

            from telemetry_state import store
            t = store.get()

            # Zero-padded index so frames sort correctly in file explorers
            idx = self._frame_count
            stem = f"{idx:05d}_x{t.pos_x:.4f}_y{t.pos_y:.4f}"
            jpg_path  = os.path.join(RECORD_DIR, f"{stem}.jpg")
            json_path = os.path.join(RECORD_DIR, f"{stem}.json")

            meta = {
                "frame":   idx,
                "local_x": t.pos_x,   # LOCAL_POSITION_NED X (metres)
                "local_y": t.pos_y,   # LOCAL_POSITION_NED Y (metres)
                "local_z": t.pos_z,   # LOCAL_POSITION_NED Z up-positive (metres)
                "vo_x":    t.vo_x,    # visual-odometry X
                "vo_y":    t.vo_y,    # visual-odometry Y
                "timestamp": time.time(),
            }

            try:
                with open(jpg_path, "wb") as f:
                    f.write(jpeg_bytes)
                with open(json_path, "w") as f:
                    json.dump(meta, f, indent=2)
                self._frame_count += 1
                return True
            except Exception:
                return False

    def get_frame_count(self) -> int:
        with self._lock:
            return self._frame_count


recorder = FrameRecorder()


def make_recording_zip() -> bytes | None:
    """Zip up all recorded frames (JPEGs + JSON sidecars) into memory and return the bytes."""
    if not os.path.exists(RECORD_DIR):
        return None
    frames = sorted(os.listdir(RECORD_DIR))
    if not frames:
        return None
    zip_path = f"/tmp/drone_frames_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    with ZipFile(zip_path, "w") as zf:
        for frame in frames:
            frame_path = os.path.join(RECORD_DIR, frame)
            zf.write(frame_path, arcname=frame)
    with open(zip_path, "rb") as f:
        data = f.read()
    os.remove(zip_path)
    return data


def recording_loop(frame_getter):
    """
    Runs in a background thread. Checks recorder.is_recording() and if True,
    fetches a frame every FRAME_INTERVAL seconds and writes it to disk.
    """
    last_save = 0.0
    while True:
        if recorder.is_recording():
            now = time.time()
            if now - last_save >= FRAME_INTERVAL:
                jpeg = frame_getter()
                if jpeg is not None:
                    recorder.record_frame(jpeg)
                    last_save = now
        time.sleep(0.05)  # check frequently but don't spin


def start_recording_thread(frame_getter) -> threading.Thread:
    t = threading.Thread(target=recording_loop, args=(frame_getter,), daemon=True)
    t.start()
    return t
