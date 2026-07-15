#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Installing dependencies..."
pip3 install -r requirements.txt

echo "Starting Lucent Voice UI on http://localhost:8001"
python3 -m uvicorn server:app --host 0.0.0.0 --port 8001
