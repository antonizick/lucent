#!/bin/bash
# Memory backup daemon — runs every 2 hours
# Usage: nohup bash scripts/memory_backup_daemon.sh > /tmp/memory-backup.log 2>&1 &

LUCENT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
BACKUP_SCRIPT="$LUCENT_ROOT/scripts/backup_memory.py"
INTERVAL=7200  # 2 hours in seconds
LOG_FILE="/tmp/memory-backup.log"

echo "[$(date)] Memory backup daemon started (2-hour interval)" >> "$LOG_FILE"

while true; do
    sleep $INTERVAL
    echo "[$(date)] Running memory backup..." >> "$LOG_FILE"
    python3 "$BACKUP_SCRIPT" >> "$LOG_FILE" 2>&1
    echo "[$(date)] Backup complete" >> "$LOG_FILE"
done
