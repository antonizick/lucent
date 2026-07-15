#!/bin/bash
# PewPew LCC Y2KM Service Starter Script

set -e

PORT="${PEWPEW_PORT:-8095}"
PIDFILE="/tmp/pewpew.pid"
LOGDIR="/home/nick/dev/lucent/logs"

mkdir -p "$LOGDIR"

echo "Starting PewPew on port $PORT..."
uvicorn idea.PewPew.backend.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --log-level info &\
    echo $! > "$PIDFILE"

sleep 2

if ss -tlnp | grep -q ":${PORT}"; then
  pid=$(cat "$PIDFILE")
  echo "✓ PewPew running on port ${PORT} (PID: ${pid})"
else
  kill $(cat "$PIDFILE") 2>/dev/null || true
  exit 1
fi

echo 'LCC Y2KM API endpoints:'
echo '  GET /health - health check'
echo '  GET /services - list running services'
echo '  POST /services/{name}/start|stop/restart'
echo '  GET /ollama/models - model inventory'
echo '  DELETE /ollama/models/{model_name}/{unload|delete}'
echo '  GET /docker/containers - container listing'
echo '  GET /resources - CPU/RAM stats with alerts'
