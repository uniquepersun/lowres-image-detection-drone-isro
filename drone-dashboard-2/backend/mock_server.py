"""
mock_server.py

Hardware-free stand-in for app.py. Generates fake telemetry (sine-wave
roll/pitch, slowly rotating yaw, draining battery, bobbing height) at 10 Hz
and serves a synthetic MJPEG "camera" stream (a moving test pattern) so the
frontend can be built and tested without the Jetson, Cube Orange, or
RealSense connected.

Run:
    pip install -r requirements.txt
    uvicorn mock_server:app --host 0.0.0.0 --port 8000

Same endpoints as the real backend: ws /telemetry, GET /video, GET /health.
"""

import asyncio
import io
import math
import time
import threading

import numpy as np
from PIL import Image
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from frame_recorder import recorder, start_recording_thread, make_recording_zip
from reference_routes import register_reference_routes

app = FastAPI(title="Drone Dashboard MOCK Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

START = time.time()
MODES = ["STABILIZE", "ALT_HOLD", "LOITER", "LAND"]

_frame_cache = None
_frame_lock = threading.Lock()


_vo_x = 0.0
_vo_y = 0.0


def _get_latest_frame():
    """Returns the latest mock JPEG frame for recording/matching."""
    with _frame_lock:
        return _frame_cache


def fake_snapshot():
    t = time.time() - START
    roll = 15 * math.sin(t * 0.6)
    pitch = 8 * math.sin(t * 0.4 + 1.0)
    yaw = (t * 12) % 360
    cycle_time = t % 30
    if cycle_time < 15:
        height = (cycle_time / 15.0) * 2.5
    else:
        height = 2.5 - ((cycle_time - 15.0) / 15.0) * 2.5
    battery_pct = max(20.0, 100.0 - t * 0.05)
    voltage = 9.0 + (battery_pct / 100.0) * (12.6 - 9.0)
    mode = MODES[int(t // 8) % len(MODES)]
    armed = (int(t // 20) % 2) == 0
    return {
        "armed": armed,
        "mode": mode,
        "battery_voltage": round(voltage, 2),
        "battery_percent": round(battery_pct, 1),
        "roll": round(roll, 2),
        "pitch": round(pitch, 2),
        "yaw": round(yaw, 2),
        "lidar_height": round(max(0.0, height), 2),
        "pos_x": round(math.sin(t * 0.1) * 2.0, 3),
        "pos_y": round(math.cos(t * 0.1) * 2.0, 3),
        "pos_z": round(max(0.0, height), 3),
        "vo_x": round(_vo_x, 4),
        "vo_y": round(_vo_y, 4),
        "timestamp": time.time(),
    }


from pydantic import BaseModel
from typing import Optional

class VOData(BaseModel):
    x: float
    y: float

@app.post("/api/vo")
def receive_vo_post(data: Optional[VOData] = None, x: Optional[float] = None, y: Optional[float] = None):
    global _vo_x, _vo_y
    if data is not None:
        _vo_x, _vo_y = data.x, data.y
    elif x is not None and y is not None:
        _vo_x, _vo_y = x, y
    return {"status": "ok"}

@app.get("/api/vo")
def receive_vo_get(x: float, y: float):
    global _vo_x, _vo_y
    _vo_x, _vo_y = x, y
    return {"status": "ok"}


@app.get("/health")
def health():
    return JSONResponse({"status": "ok", "mode": "mock", "telemetry": fake_snapshot()})


@app.websocket("/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(fake_snapshot())
            await asyncio.sleep(0.1)  # 10 Hz
    except WebSocketDisconnect:
        pass


def _make_frame(i: int) -> bytes:
    w, h = 640, 480
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    # simple animated gradient + moving bar so motion is visible
    arr[:, :, 0] = 30
    arr[:, :, 2] = 40
    bar_x = int((math.sin(i * 0.05) * 0.5 + 0.5) * (w - 20))
    arr[:, bar_x:bar_x + 20, 1] = 200
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def _mjpeg_generator():
    global _frame_cache
    i = 0
    boundary = b"--frame"
    while True:
        frame = _make_frame(i)
        with _frame_lock:
            _frame_cache = frame
        i += 1
        yield (
            boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
            + frame + b"\r\n"
        )
        time.sleep(1 / 12)  # ~12 FPS mock feed


@app.get("/video")
def video():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.on_event("startup")
def on_startup():
    start_recording_thread(_get_latest_frame)
    register_reference_routes(app, _get_latest_frame)


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
