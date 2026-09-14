"""
telemetry_server.py

Pure Python telemetry collector using pymavlink. Two readers run in parallel:

  MavlinkTelemetryReader  – connects to the flight controller (default udp:127.0.0.1:14550)
                            and reads HEARTBEAT, SYS_STATUS, ATTITUDE, DISTANCE_SENSOR.

  CoordReader             – connects to the coordinate publisher (default udp:127.0.0.1:14560)
                            and reads LOCAL_POSITION_NED, writing pos_x / pos_y / pos_z
                            into the same shared store so frame_recorder uses the right
                            coordinates when saving images.

Can be run standalone:
    python3 telemetry_server.py udp:127.0.0.1:14550
"""

import threading
import time
import math
from pymavlink import mavutil
from telemetry_state import store

# ArduPilot Copter flight modes map (custom_mode -> string)
COPTER_MODE_MAP = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    9: "LAND",
    11: "DRIFT",
    13: "SPORT",
    14: "FLIP",
    15: "AUTOTUNE",
    16: "POSHOLD",
    17: "BRAKE",
    18: "THROW",
    19: "AVOID_ADSB",
    20: "GUIDED_NOGPS",
    21: "SMART_RTL",
    22: "FLOWHOLD",
    23: "FOLLOW",
    24: "ZIGZAG",
    25: "SYSTEM_ID",
    26: "AUTOROTATE",
}


def _parse_fcu_url(fcu_url: str):
    """
    Parse an FCU_URL into (connection_string, baudrate).

    Recognised formats
    ------------------
    udp:127.0.0.1:14550           -> connection_string='udp:127.0.0.1:14550', baud=115200
    tcp:127.0.0.1:5760            -> connection_string='tcp:127.0.0.1:5760',  baud=115200
    /dev/ttyACM0                  -> connection_string='/dev/ttyACM0',          baud=115200
    /dev/ttyACM0:115200           -> connection_string='/dev/ttyACM0',          baud=115200
    /dev/serial/by-id/....:57600  -> connection_string='/dev/serial/...',        baud=57600
    """
    # Network protocols: pass the whole string verbatim to pymavlink
    for prefix in ("udp:", "tcp:", "udpin:", "udpout:", "udpbcast:", "tcpin:"):
        if fcu_url.lower().startswith(prefix):
            return fcu_url, 115200

    # Serial path – optionally ends with :baudrate
    baud = 115200
    parts = fcu_url.rsplit(":", 1)
    if len(parts) == 2:
        try:
            baud = int(parts[1])
            return parts[0], baud
        except ValueError:
            pass
    return fcu_url, baud


class MavlinkTelemetryReader:
    def __init__(self, connection_string="udp:127.0.0.1:14550", baudrate=115200):
        self.connection_string = connection_string
        self.baudrate = baudrate
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _loop(self):
        print(f"[Telemetry] Connecting to FCU on {self.connection_string} at {self.baudrate}...", flush=True)
        while self.running:
            try:
                # Open MAVLink connection
                master = mavutil.mavlink_connection(self.connection_string, baud=self.baudrate)
                print("[Telemetry] Waiting for FCU heartbeat...", flush=True)
                master.wait_heartbeat(timeout=5)
                print(f"[Telemetry] Connected to FCU (System ID: {master.target_system})", flush=True)
                
                # Request critical message rates (ArduPilot/PX4 parameter configuration fallback)
                # ATTITUDE (30) -> 10 Hz (100,000 us)
                # LOCAL_POSITION_NED (32) -> 10 Hz (100,000 us)
                # SYS_STATUS (1) -> 2 Hz (500,000 us)
                # DISTANCE_SENSOR (132) -> 10 Hz (100,000 us)
                # HEARTBEAT (0) -> 1 Hz (1,000,000 us)
                for msg_id, rate_hz in [(30, 10), (32, 10), (1, 2), (132, 10), (0, 1)]:
                    interval_us = int(1e6 / rate_hz)
                    master.mav.command_long_send(
                        master.target_system,
                        master.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                        0,          # confirmation
                        msg_id,     # param 1: message ID
                        interval_us,# param 2: interval in us
                        0, 0, 0, 0, 0 # param 3-7: unused
                    )
                
                # Read loop
                while self.running:
                    msg = master.recv_match(blocking=True, timeout=1.0)
                    if msg is None:
                        continue
                    
                    msg_type = msg.get_type()
                    
                    if msg_type == "HEARTBEAT":
                        # Only parse heartbeats from the flight controller itself (Component ID 1)
                        # to avoid flickering caused by companion computers or GCS components.
                        if msg.get_srcComponent() == 1:
                            # msg.base_mode & MAV_MODE_FLAG_SAFETY_ARMED
                            armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                            
                            # First try ArduPilot Copter modes map
                            mode_str = COPTER_MODE_MAP.get(msg.custom_mode)
                            
                            # Fallback to standard pymavlink mapping if not found
                            if not mode_str:
                                mode_str = mavutil.mode_string_v10(msg)
                            if not mode_str:
                                mode_str = f"Mode({msg.custom_mode})"
                                
                            store.update(armed=armed, mode=mode_str)
                        
                    elif msg_type == "SYS_STATUS":
                        # Battery voltage: millivolts -> Volts
                        voltage = msg.voltage_battery / 1000.0
                        # Battery percentage: 0 to 100 (-1 if invalid/uncalibrated)
                        percent = msg.battery_remaining
                        if percent < 0:
                            percent = 0.0
                        store.update(battery_voltage=round(voltage, 2), battery_percent=round(percent, 1))
                        
                    elif msg_type == "ATTITUDE":
                        roll = math.degrees(msg.roll)
                        pitch = math.degrees(msg.pitch)
                        yaw = math.degrees(msg.yaw)
                        if yaw < 0:
                            yaw += 360
                        store.update(roll=round(roll, 2), pitch=round(pitch, 2), yaw=round(yaw, 2))
                        
                    elif msg_type == "DISTANCE_SENSOR":
                        # current_distance in cm -> meters
                        height = msg.current_distance / 100.0
                        store.update(lidar_height=round(height, 3))
                        
                    elif msg_type == "LOCAL_POSITION_NED":
                        # msg.x, y, z in meters. Z is down in NED, negate for height/altitude
                        # NOTE: if COORD_URL is set, CoordReader owns these fields instead.
                        import os
                        if not os.environ.get("COORD_URL"):
                            store.update(
                                pos_x=round(msg.x, 3),
                                pos_y=round(msg.y, 3),
                                pos_z=round(-msg.z, 3)
                            )

            except Exception as e:
                print(f"[Telemetry] Connection error: {e}. Retrying in 3 seconds...", flush=True)
                time.sleep(3)



class CoordReader:
    """
    Lightweight MAVLink listener that reads LOCAL_POSITION_NED from a
    dedicated coord endpoint (e.g. udp:127.0.0.1:14560) and writes
    pos_x / pos_y / pos_z into the shared telemetry store.

    This is intentionally kept separate from MavlinkTelemetryReader so
    the coordinate source can be a different system (companion computer,
    visual-odometry node, RTAB-Map, etc.) publishing on its own port.
    """

    def __init__(self, connection_string: str = "udp:127.0.0.1:14560"):
        self.connection_string = connection_string
        self.running = False
        self.thread: threading.Thread | None = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _loop(self):
        print(f"[CoordReader] Connecting to coord source on {self.connection_string}...", flush=True)
        while self.running:
            try:
                conn = mavutil.mavlink_connection(self.connection_string)
                # Don't require a heartbeat – some coord publishers skip it.
                # Try to wait briefly; if it times out, keep going anyway.
                try:
                    conn.wait_heartbeat(timeout=5)
                    print(f"[CoordReader] Heartbeat received from {self.connection_string}", flush=True)
                except Exception:
                    print(f"[CoordReader] No heartbeat on {self.connection_string}, continuing anyway...", flush=True)

                while self.running:
                    msg = conn.recv_match(
                        type="LOCAL_POSITION_NED",
                        blocking=True,
                        timeout=2.0,
                    )
                    if msg is None:
                        continue
                    # Z is down in NED; negate for up-positive altitude
                    store.update(
                        pos_x=round(msg.x, 4),
                        pos_y=round(msg.y, 4),
                        pos_z=round(-msg.z, 4),
                    )

            except Exception as e:
                print(f"[CoordReader] Error: {e}. Retrying in 3 s...", flush=True)
                time.sleep(3)


def main():
    import sys
    import os
    fcu_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FCU_URL", "udp:127.0.0.1:14550")
    port, baud = _parse_fcu_url(fcu_url)
    reader = MavlinkTelemetryReader(connection_string=port, baudrate=baud)
    reader.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping telemetry reader...")
        reader.stop()


if __name__ == "__main__":
    main()
