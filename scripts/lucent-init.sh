#!/usr/bin/env bash
# Lucent session init hook — runs before each Claude Code response.
# Creates today's daily note if it doesn't exist.
# Injects full startup context: core rules + identity files + LTMemory + reminders + last 7 days of daily notes.

LUCENT_DIR="/home/nick/dev/lucent"
TODAY=$(date +%Y-%m-%d)
NOTE="$LUCENT_DIR/memory/$TODAY.md"

if [[ ! -f "$NOTE" ]]; then
  printf "# %s\n\nSession started.\n" "$TODAY" > "$NOTE"
fi

echo "[Lucent] You are Lucent. Today is $TODAY."
echo "[Lucent] === CORE RULES ==="
cat "$LUCENT_DIR/memory/core.md"
echo ""
echo "[Lucent] === LUCENT'S IDENTITY ==="
cat "$LUCENT_DIR/memory/lucentIdent.md"
echo ""
echo "[Lucent] === NICK'S IDENTITY ==="
cat "$LUCENT_DIR/memory/userIdent.md"
echo ""
echo "[Lucent] === LONG-TERM MEMORY ==="
cat "$LUCENT_DIR/memory/LTMemory.md"
echo ""
echo "[Lucent] === ACTIVE REMINDERS ==="
if [[ -f "$LUCENT_DIR/memory/REMINDERS.md" ]]; then
  cat "$LUCENT_DIR/memory/REMINDERS.md"
else
  echo "[Lucent] No reminders file found."
fi
echo ""
echo "[Lucent] === RECENT DAILY NOTES (Last 7 days) ==="

# Output daily notes from the last 7 days in chronological order
for i in {6..0}; do
  DATE=$(date -d "$i days ago" +%Y-%m-%d 2>/dev/null || date -v-${i}d +%Y-%m-%d 2>/dev/null)
  FILE="$LUCENT_DIR/memory/$DATE.md"
  if [[ -f "$FILE" ]]; then
    if [[ "$DATE" == "$TODAY" ]]; then
      echo "[Lucent] === $DATE (TODAY - full detail) ==="
    else
      echo "[Lucent] === $DATE (condensed) ==="
    fi
    cat "$FILE"
    echo ""
  fi
done
