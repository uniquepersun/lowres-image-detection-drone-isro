"""
camera_server.py

Pure Python camera streamer. Captures images directly from a USB webcam using OpenCV,
compresses them to JPEG, and holds the latest frame in memory for the MJPEG stream
in app.py. Bypasses ROS2 completely.
"""

import threading
import time
import cv2
import os

class FrameStore:
    """Thread-safe holder for the latest raw JPEG bytes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._frame: bytes | None = None

    def set(self, frame: bytes):
        with self._lock:
            self._frame = frame

    def get(self) -> bytes | None:
        with self._lock:
            return self._frame


# Single global frame store for FastAPI app.py to import
frame_store = FrameStore()


def start_opencv_webcam_thread():
    """Starts a background daemon thread that scans webcam devices and pulls frames."""
    def worker():
        # Perform user diagnostic checks on /dev/video* permissions
        for idx in range(5):
            dev_path = f"/dev/video{idx}"
            if os.path.exists(dev_path):
                readable = os.access(dev_path, os.R_OK)
                writable = os.access(dev_path, os.W_OK)
                if not (readable and writable):
                    print(f"\n[Camera] WARNING: Device {dev_path} exists but is NOT readable/writable by the current user!", flush=True)
                    print(f"[Camera] HINT: Please run 'sudo chmod a+rw {dev_path}' or 'sudo usermod -aG video $USER' and restart the server.\n", flush=True)

        cap = None
        # Try camera indices 0 to 4 using V4L2 backend first
        for idx in [0, 1, 2, 3, 4]:
            print(f"[Camera] OpenCV: Testing webcam index {idx} with V4L2...", flush=True)
            c = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if c.isOpened():
                # Set format properties BEFORE the first frame read
                c.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                c.set(cv2.CAP_PROP_FPS, 15)
                
                # Perform a test frame read. Some devices open but fail to produce frames
                ret, _ = c.read()
                if ret:
                    cap = c
                    print(f"[Camera] OpenCV: Successfully opened webcam index {idx} using V4L2", flush=True)
                    break
                c.release()

        # Fallback to default backend if V4L2 fails
        if cap is None:
            for idx in [0, 1, 2, 3, 4]:
                print(f"[Camera] OpenCV: Testing webcam index {idx} with default backend...", flush=True)
                c = cv2.VideoCapture(idx)
                if c.isOpened():
                    c.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    c.set(cv2.CAP_PROP_FPS, 15)
                    
                    ret, _ = c.read()
                    if ret:
                        cap = c
                        print(f"[Camera] OpenCV: Successfully opened webcam index {idx} using default backend", flush=True)
                        break
                    c.release()

        if cap is None:
            print("[Camera] OpenCV: Failed to open any working webcam (tried indices 0-4). No live feed will be available.", flush=True)
            return

        read_fail_count = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    read_fail_count += 1
                    if read_fail_count % 100 == 0:
                        print(f"[Camera] Warning: cap.read() failed {read_fail_count} times in loop!", flush=True)
                    time.sleep(0.03)
                    continue
                
                read_fail_count = 0 # reset on success
                
                # Encode frame to JPEG
                ret_jpeg, jpeg_bytes = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ret_jpeg:
                    frame_store.set(jpeg_bytes.tobytes())
                
                time.sleep(1.0 / 15.0)
        except Exception as e:
            print(f"[Camera] OpenCV capture error: {e}", flush=True)
        finally:
            cap.release()
            print("[Camera] OpenCV: webcam capture device released.", flush=True)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
