#!/bin/bash
set -e

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python3" ]; then
  echo "Creating venv..."
  python3 -m venv .venv
fi

echo "Installing dependencies..."
.venv/bin/pip install -r requirements.txt -q

echo "Starting Lucent Voice UI on http://localhost:8001"
exec .venv/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8001
