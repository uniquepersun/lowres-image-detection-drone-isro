#!/usr/bin/env bash
#
# start_jetson_all.sh
#
# Brings up the Jetson-side stack for the drone dashboard:
#   1. FastAPI backend (which runs pymavlink serial reader and OpenCV camera streamer)
#
# Edit the variables below to match your setup, then just run:
#   ./start_jetson_all.sh
#
# Ctrl+C kills everything cleanly.

set -e
cd "$(dirname "$0")"

# ---- EDIT THESE -----------------------------------------------------------
export FCU_URL="udp:127.0.0.1:14550"
# -----------------------------------------------------------------------------

# Create and use virtual environment if possible
if python3 -m venv .venv 2>/dev/null; then
  echo "Using Python virtual environment (.venv)..."
  source .venv/bin/activate
  pip install -q -r requirements.txt
else
  echo "Virtual environment creation not supported. Installing system-wide..."
  pip install -q -r requirements.txt --break-system-packages 2>/dev/null || pip install -q -r requirements.txt --break-system-packages
fi

echo "Starting dashboard backend (FastAPI)..."
uvicorn app:app --host 0.0.0.0 --port 8000
