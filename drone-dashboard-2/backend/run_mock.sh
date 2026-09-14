#!/usr/bin/env bash
# Run the hardware-free mock backend for frontend dev/testing.
set -e
cd "$(dirname "$0")"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt
echo "Starting MOCK backend on http://0.0.0.0:8000 (telemetry + fake video)"
uvicorn mock_server:app --host 0.0.0.0 --port 8000 --reload
