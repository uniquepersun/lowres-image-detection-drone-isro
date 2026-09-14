"""
rtabmap_manager.py

Monitors telemetry lidar_height in the background. Once the drone is above
a specific threshold (e.g., 1.0 meters), it spawns the RTAB-Map ROS2 node
as a subprocess.
"""

import threading
import time
import subprocess
import os

from telemetry_state import store

RTABMAP_CMD = [
    "ros2", "launch", "rtabmap_launch", "rtabmap.launch.py",
    "rgb_topic:=/camera/camera/color/image_raw",
    "depth_topic:=/camera/camera/aligned_depth_to_color/image_raw",
    "camera_info_topic:=/camera/camera/color/camera_info",
    "frame_id:=camera_link",
    "approx_sync:=true",
    "rviz:=false",
    "rtabmap_viz:=true",
    "rtabmap_args:=--delete_db_on_start"
]

class RtabmapManager:
    def __init__(self):
        self._thread = None
        self._process = None
        self._running = False
        self._threshold = 1.0  # meters

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            print("RtabmapManager started, waiting for height > 1.0m...")

    def _monitor_loop(self):
        while self._running:
            height = store.get().lidar_height
            
            if height > self._threshold and self._process is None:
                print(f"Lidar height ({height}m) exceeded {self._threshold}m. Starting RTAB-Map...")
                self._launch_rtabmap()
            elif height < 0.5 and self._process is not None:
                print(f"Lidar height ({height}m) dropped below 0.5m. Stopping RTAB-Map...")
                self._stop_rtabmap_process()
                
            time.sleep(1.0)  # check at 1 Hz

    def _launch_rtabmap(self):
        # We spawn the subprocess. Note that environment variables (like ROS_DOMAIN_ID)
        # must already be set in the shell that runs app.py.
        try:
            self._process = subprocess.Popen(
                RTABMAP_CMD,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy()
            )
            print("RTAB-Map launched successfully.")
        except Exception as e:
            print(f"Failed to launch RTAB-Map: {e}")

    def _stop_rtabmap_process(self):
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None
            print("RTAB-Map stopped.")

    def stop(self):
        self._running = False
        self._stop_rtabmap_process()

manager = RtabmapManager()
