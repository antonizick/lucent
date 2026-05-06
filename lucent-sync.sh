#!/bin/bash
# lucent-sync.sh — Push lucent files to the private GitHub repo
# Checks if already synced today to avoid redundant commits/pushes.

set -e

LUCENT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_REMOTE="https://github.com/antonizick/lucent.git"
LOG_FILE="$LUCENT_DIR/.sync.log"
TODAY=$(date +%Y-%m-%d)

# Check if already synced today
if [ -f "$LOG_FILE" ]; then
    last_synced=$(grep "^# synced:" "$LOG_FILE" | tail -1 | awk '{print $3}')
    if [ "$last_synced" = "$TODAY" ]; then
        echo "Already synced today ($TODAY). Skipping."
        exit 0
    fi
fi

# Commit changes
cd "$LUCENT_DIR"
git add -A
if [ -z "$(git diff --cached --name-only)" ]; then
    echo "No changes to sync."
    exit 0
fi

git commit -m "lucent: sync $(date +%Y-%m-%d\ %H:%M:%S)" || true
git push "$REPO_REMOTE" main

echo "$TODAY" >> "$LOG_FILE"
echo "# synced: $TODAY $(date +%Y-%m-%d\ %H:%M:%S)" >> "$LOG_FILE"
echo "Synced to $REPO_REMOTE at $(date)"

# Clean up log — keep today's entry and the last 30 days of history
if [ -f "$LOG_FILE" ]; then
    cutoff=$(date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null)
    [ -n "$cutoff" ] && grep -v "^#[0-9]" "$LOG_FILE" | grep -E "^#$|^[0-9]" | awk -v d="$cutoff" '$0 ~ /^[0-9]/ && $1 >= d {print}' > "$LOG_FILE.tmp" && grep "^#" "$LOG_FILE" >> "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi
