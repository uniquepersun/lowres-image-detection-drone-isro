# Drone Ground Station Dashboard

Indoor (GPS-denied) drone dashboard: Jetson Orin → MAVROS/RealSense → FastAPI
backend → React/TypeScript dashboard on the Mac. No GPS, maps, or missions.

```
backend/    FastAPI + ROS2 telemetry/video server (runs on the Jetson)
frontend/   React + TypeScript + Tailwind dashboard (runs on the Mac)
```

## Quick run on real hardware (no mock data)

**On the Jetson** (`hostname -I` gives its IP):

```bash
git clone https://github.com/uniquepersun/lowres-image-detection-drone-isro.git
cd lowres-image-detection-drone-isro/drone-dashboard-2/backend

export FCU_URL="udp:127.0.0.1:14550"   # MAVLink source (UDP forward or serial, see app.py)
./start_jetson_all.sh                  # venv + deps + uvicorn on :8000
```

Plug the camera in before starting.

**On the Mac:**

```bash
git clone https://github.com/uniquepersun/lowres-image-detection-drone-isro.git
cd lowres-image-detection-drone-isro/drone-dashboard-2/frontend
npm install && npm run dev             # http://localhost:5173
```

Then in the browser console, point the dashboard at the Jetson
(the default host `car@car.local` is not a valid hostname):

```js
localStorage.setItem("JETSON_HOST", "<JETSON_IP>"); localStorage.setItem("JETSON_PORT", "8000"); location.reload()
```

Check: `curl http://<JETSON_IP>:8000/video -m 3 | head -c 200` should return
MJPEG bytes. If the dashboard shows no telemetry, nothing is reaching
`FCU_URL` — check the serial port (`ls /dev/tty*`) or your MAVLink forwarder.

## Quick start (no hardware, frontend dev only)

Use the mock backend to build/test the UI without the Jetson or drone:

```bash
# Terminal 1 - mock backend
cd backend
./run_mock.sh                 # http://localhost:8000

# Terminal 2 - frontend
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

The dashboard defaults to `localhost:8000`, so it should connect to the
mock backend immediately — no extra config needed. When you switch to the
real Jetson, point it there instead:

```js
localStorage.setItem("JETSON_HOST", "192.168.1.50") // your Jetson's IP
localStorage.setItem("JETSON_PORT", "8000")
location.reload()
```

Edit `frontend/src/config.ts` if you'd rather hardcode the IP instead of
using localStorage.

## Running for real, on the Jetson

The Jetson needs ROS2 (Humble/Iron) with MAVROS already set up and talking
to the Cube Orange, plus the RealSense ROS2 wrapper publishing
`/camera/color/image_raw/compressed`.

```bash
cd backend
source /opt/ros/humble/setup.bash
source ~/your_ws/install/setup.bash   # your MAVROS/RealSense workspace
./run_jetson.sh                        # http://JETSON_IP:8000
```

On the Mac:

```bash
cd frontend
npm install
npm run build      # or `npm run dev` for development
npm run preview    # serve the production build, or use any static host
```

Then set `JETSON_HOST` (see above) to the Jetson's LAN IP.

## What's implemented

**Backend** (`backend/`)
- `telemetry_state.py` — shared telemetry store + quaternion→euler conversion
- `telemetry_server.py` — ROS2 node subscribing to `/mavros/state`,
  `/mavros/battery`, `/mavros/imu/data`, `/tfmini/range`
- `camera_server.py` — ROS2 node subscribing to
  `/camera/color/image_raw/compressed`, holds latest JPEG frame
- `app.py` — FastAPI app: `ws://.../telemetry` (10 Hz JSON) and
  `http://.../video` (MJPEG stream), spins ROS2 nodes on a background thread
- `mock_server.py` — drop-in replacement for `app.py` with fake telemetry +
  a synthetic video stream, for hardware-free development

**Frontend** (`frontend/`)
- `ArtificialHorizon.tsx` — canvas-drawn horizon (sky/ground/pitch ladder/roll arc), matches Mission Planner / QGroundControl style
- `Compass.tsx` — rotating SVG compass strip driven by yaw
- `CameraFeed.tsx` — `<img>` tag pointed at the MJPEG endpoint
- `ArmedBadge.tsx`, `ModeIndicator.tsx`, `BatteryPanel.tsx`, `HeightGauge.tsx` — bottom status bar
- `hooks/useTelemetry.ts` — WebSocket client with auto-reconnect (exponential backoff)
- `config.ts` — Jetson host/port config (via `localStorage`, falls back to a default)

## Adding fields later (per spec's "future expansion")

To add e.g. SLAM status, CPU/GPU temp, or VIO confidence:
1. Add the field to `TelemetrySnapshot` in `backend/telemetry_state.py`
2. Update it from a new subscription in `telemetry_server.py`
3. Add the field to the `Telemetry` interface in `frontend/src/config.ts`
4. Render it wherever you like — the WebSocket payload already carries it

No changes needed to the WebSocket plumbing itself.

## Performance notes

- Telemetry pushes at 10 Hz (`TELEMETRY_HZ` in `app.py`)
- Video reads the *compressed* MAVROS-independent RealSense topic directly
  (no re-encoding), capped at 15 FPS (`VIDEO_FPS_CAP` in `app.py`) to limit
  Jetson CPU/bandwidth load alongside RTAB-Map/MAVROS
- CORS is wide open (`allow_origins=["*"]`) since this is meant for a closed
  local network; tighten this if you expose it beyond your LAN
