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
echo ""
echo "[Lucent] === STARTUP READINESS MARKER CHECK ==="

# Check for startup readiness marker created by startup.py (SessionStart hook)
# If marker exists, startup.py just completed and acknowledged startup via voice.
# This hook handles the acknowledgment at the platform level (not Claude level),
# ensuring it always happens automatically.
#
# Marker file: memory/.startup_ready_YYYY-MM-DD.txt (created by startup.py on STARTUP_OK)
# Acknowledgment: Send voice, log to daily note, report [CRITICAL] flag to context, delete marker
MARKER_FILE=$(ls -1 "$LUCENT_DIR/memory/.startup_ready_"*.txt 2>/dev/null | head -1)
if [[ -n "$MARKER_FILE" ]]; then
  # Marker found: startup just completed. Report [CRITICAL] flag for Claude to acknowledge.
  echo "[CRITICAL] STARTUP READINESS MARKER FOUND"
  echo "[CRITICAL] Before responding to Nick, you MUST:"
  echo "[CRITICAL] 1. Send voice + text: 'Startup complete. All systems ready. Standing by.'"
  echo "[CRITICAL] 2. Log to daily note: 'Startup readiness acknowledged (auto via hook)'"
  echo "[CRITICAL] 3. Then proceed to handle Nick's request"
  echo ""

  # Execute acknowledgment at hook level (truly automatic — no Claude compliance needed)
  TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S")
  curl -s -X POST http://localhost:8001/speak -H "Content-Type: application/json" -d "{\"text\":\"Startup complete. All systems ready. Standing by.\"}" 2>/dev/null || true
  echo "[$TIMESTAMP] Startup readiness acknowledged (auto via UserPromptSubmit hook)" >> "$NOTE"
  rm -f "$MARKER_FILE"
else
  # No marker found: normal flow (startup ran earlier or this is a continuation message)
  echo "[Lucent] ✓ No startup marker — normal response flow"
fi
