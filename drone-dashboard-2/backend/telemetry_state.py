"""
telemetry_state.py

Holds the latest telemetry snapshot and the quaternion -> euler conversion.
Shared between the ROS2 node (telemetry_server.py) and the FastAPI app
(app.py), and also imported by the mock server (mock_server.py) for
hardware-free frontend development.
"""

from dataclasses import dataclass, asdict
import math
import threading
import time


@dataclass
class TelemetrySnapshot:
    armed: bool = False
    mode: str = "UNKNOWN"
    battery_voltage: float = 0.0
    battery_percent: float = 0.0
    roll: float = 0.0          # degrees
    pitch: float = 0.0         # degrees
    yaw: float = 0.0           # degrees, 0-360
    lidar_height: float = 0.0  # meters
    pos_x: float = 0.0         # rtabmap x
    pos_y: float = 0.0         # rtabmap y
    pos_z: float = 0.0         # rtabmap z
    vo_x: float = 0.0          # visual odometry x
    vo_y: float = 0.0          # visual odometry y
    timestamp: float = 0.0

    def to_json(self) -> dict:
        d = asdict(self)
        d["timestamp"] = time.time()
        return d


class TelemetryStore:
    """Thread-safe holder for the latest telemetry values."""

    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = TelemetrySnapshot()

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._snapshot, k):
                    setattr(self._snapshot, k, v)

    def get(self) -> TelemetrySnapshot:
        with self._lock:
            # return a shallow copy
            return TelemetrySnapshot(**asdict(self._snapshot))


def quaternion_to_euler_deg(x: float, y: float, z: float, w: float):
    """
    Convert a MAVROS/ROS quaternion (ENU, body frame) to roll/pitch/yaw
    in degrees. Yaw is normalized to [0, 360).
    """
    # roll (x-axis rotation)
    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # pitch (y-axis rotation)
    sinp = 2 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)

    # yaw (z-axis rotation)
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    roll_deg = math.degrees(roll)
    pitch_deg = math.degrees(pitch)
    yaw_deg = math.degrees(yaw)
    if yaw_deg < 0:
        yaw_deg += 360.0

    return roll_deg, pitch_deg, yaw_deg


# Module-level singleton shared by the ROS node and the API process
# (they run in the same process - see app.py).
store = TelemetryStore()
