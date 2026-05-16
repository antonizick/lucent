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
echo "[Lucent] === TODAY'S SESSION LOG ==="
if [[ -f "$NOTE" ]]; then
  cat "$NOTE"
else
  echo "[Lucent] (No session activity yet)"
fi
echo ""
echo "[Lucent] === STARTUP VALIDATION STATUS ==="

CHECKPOINT_FILE="$LUCENT_DIR/memory/.ritual_checkpoint.json"
if [[ -f "$CHECKPOINT_FILE" ]]; then
  CHECKPOINT_DATE=$(grep -o '"date": "[^"]*"' "$CHECKPOINT_FILE" | head -1 | cut -d'"' -f4)
  if [[ "$CHECKPOINT_DATE" == "$TODAY" ]]; then
    echo "[Lucent] ✓ Startup validated for today (auto-triggered via SessionStart hook)."
  else
    echo "[Lucent] ⚠ Startup checkpoint is stale (from $CHECKPOINT_DATE)."
    echo "[Lucent] Run: python3 /home/nick/dev/lucent/scripts/startup.py"
    echo "[Lucent] This must complete before you respond to Nick."
  fi
else
  echo "[Lucent] ⚠ No startup checkpoint found."
  echo "[Lucent] Run: python3 /home/nick/dev/lucent/scripts/startup.py"
  echo "[Lucent] This must complete before you respond to Nick."
fi
