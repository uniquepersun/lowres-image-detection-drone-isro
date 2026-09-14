#!/usr/bin/env bash
# Run the real backend on the Jetson. Requires ROS2 + MAVROS already
# installed and a workspace with mavros_msgs/sensor_msgs built.
set -e
cd "$(dirname "$0")"

# Adjust these to your setup:
source /opt/ros/humble/setup.bash
# source ~/your_ws/install/setup.bash

pip install -q -r requirements.txt --break-system-packages 2>/dev/null || pip install -q -r requirements.txt

echo "Starting drone dashboard backend on http://0.0.0.0:8000"
uvicorn app:app --host 0.0.0.0 --port 8000
