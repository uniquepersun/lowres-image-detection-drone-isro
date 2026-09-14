"""
app.py

FastAPI server for the drone dashboard. Runs on the Jetson Orin.

Exposes:
  ws://JETSON_IP:8000/telemetry   - telemetry JSON pushed at 10 Hz
  http://JETSON_IP:8000/video     - MJPEG camera stream
  http://JETSON_IP:8000/health    - simple health check

ROS2 spinning happens in a background thread (rclpy is not asyncio-native),
while FastAPI/uvicorn handles the WebSocket + HTTP side on the main thread's
event loop.

Run:
    source /opt/ros/humble/setup.bash
    source ~/your_ws/install/setup.bash
    pip install -r requirements.txt
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

import asyncio
import threading
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from telemetry_state import store
from reference_routes import register_reference_routes
from frame_recorder import recorder, start_recording_thread, make_recording_zip

TELEMETRY_HZ = 10
VIDEO_FPS_CAP = 15  # don't push frames faster than this even if ROS does

app = FastAPI(title="Drone Ground Station Backend")

# Mac dashboard runs on a different host - allow all origins on the local
# network. Tighten this if the dashboard is exposed beyond your LAN.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_services_started = False
_frame_store = None


def _get_latest_frame():
    """Returns the latest JPEG bytes from the camera for recording/matching."""
    if _frame_store is None:
        return None
    return _frame_store.get()


def _start_backend_services():
    """Start the pure Python background telemetry reader and webcam streamer threads."""
    global _services_started
    if _services_started:
        return

    # 1. Start direct OpenCV webcam capture
    from camera_server import start_opencv_webcam_thread
    start_opencv_webcam_thread()

    # 2. Start pymavlink telemetry listener (attitude, battery, heartbeat)
    import os
    from telemetry_server import MavlinkTelemetryReader, CoordReader, _parse_fcu_url
    fcu_url = os.environ.get("FCU_URL", "udp:127.0.0.1:14550")
    port, baud = _parse_fcu_url(fcu_url)

    reader = MavlinkTelemetryReader(connection_string=port, baudrate=baud)
    reader.start()

    # 3. Start coordinate reader (LOCAL_POSITION_NED -> pos_x/pos_y/pos_z)
    #    Listens on COORD_URL (default udp:127.0.0.1:14560).
    #    These are the coordinates stamped onto saved frames.
    coord_url, _ = _parse_fcu_url(os.environ.get("COORD_URL", "udp:127.0.0.1:14560"))
    coord_reader = CoordReader(connection_string=coord_url)
    coord_reader.start()

    _services_started = True


@app.on_event("startup")
def on_startup():
    global _frame_store
    _start_backend_services()
    time.sleep(1)
    
    # Capture the frame_store instance for recording/matching features
    from camera_server import frame_store as fs
    _frame_store = fs

    # Start the recording and matching threads
    start_recording_thread(_get_latest_frame)
    register_reference_routes(app, _get_latest_frame)


from pydantic import BaseModel
from typing import Optional

class VOData(BaseModel):
    x: float
    y: float

@app.post("/api/vo")
def receive_vo_post(data: Optional[VOData] = None, x: Optional[float] = None, y: Optional[float] = None):
    if data is not None:
        store.update(vo_x=data.x, vo_y=data.y)
    elif x is not None and y is not None:
        store.update(vo_x=x, vo_y=y)
    return {"status": "ok"}

@app.get("/api/vo")
def receive_vo_get(x: float, y: float):
    store.update(vo_x=x, vo_y=y)
    return {"status": "ok"}


@app.get("/health")
def health():
    return JSONResponse({"status": "ok", "telemetry": store.get().to_json()})


@app.websocket("/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await websocket.accept()
    period = 1.0 / TELEMETRY_HZ
    try:
        while True:
            snapshot = store.get().to_json()
            await websocket.send_json(snapshot)
            await asyncio.sleep(period)
    except WebSocketDisconnect:
        pass


def _mjpeg_generator():
    from camera_server import frame_store

    boundary = b"--frame"
    min_period = 1.0 / VIDEO_FPS_CAP
    last_sent = 0.0
    while True:
        now = time.time()
        if now - last_sent < min_period:
            time.sleep(min_period - (now - last_sent))
        frame = frame_store.get()
        if frame is None:
            time.sleep(0.05)
            continue
        last_sent = time.time()
        yield (
            boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
            + frame + b"\r\n"
        )


@app.get("/video")
def video():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/recording/start")
def start_recording():
    ok = recorder.start()
    return JSONResponse({"recording": ok})


@app.post("/recording/stop")
def stop_recording():
    was_recording, frame_count = recorder.stop()
    return JSONResponse({"was_recording": was_recording, "frame_count": frame_count})


@app.get("/recording/status")
def recording_status():
    return JSONResponse({"recording": recorder.is_recording(), "frame_count": recorder.get_frame_count()})


@app.get("/recording/download")
def download_recording():
    data = make_recording_zip()
    if data is None:
        return JSONResponse({"error": "No frames recorded"}, status_code=400)
    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=drone_frames.zip",
            "Content-Length": str(len(data))
        },
    )
