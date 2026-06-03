#!/usr/bin/env bash
# Lucent session init hook — runs before each Claude Code response.
#
# SLIM VERSION (post-efficiency refactor 2026-05-24):
# Identity / LTMemory / core rules are now injected ONCE at SessionStart by
# startup.py (see print_identity_bundle). This per-prompt hook handles only
# dynamic state that changes between turns:
#   - Date + active rules reminder (compaction insurance)
#   - NERO Phase 1: semantic recall (relevant memories injected as fenced block)
#   - Active reminders (filtered)
#   - Priority email alert
#   - Last 10 lines of today's daily note
#   - Startup readiness marker check (one-shot, auto-deletes)

LUCENT_DIR="/home/nick/dev/lucent"
TODAY=$(date +%Y-%m-%d)
NOTE="$LUCENT_DIR/memory/$TODAY.md"

# Read hook stdin ONCE — contains Claude Code UserPromptSubmit JSON payload
# (has the user's message; passed to recall script below)
HOOK_STDIN=$(cat)

if [[ ! -f "$NOTE" ]]; then
  printf "# %s\n\nSession started.\n" "$TODAY" > "$NOTE"
fi

# Compaction-insurance rules reminder — tiny, always present, survives /compact.
cat <<EOF
[Lucent] Today is $TODAY.
[Lucent] === RULES ACTIVE (full text in SessionStart bundle) ===
[Lucent] 1. Voice — POST to http://localhost:8001/speak before every text reply.
[Lucent] 2. Daily note — append to memory/$TODAY.md every response.
[Lucent] 3. Text — respond in Claude Code.
[Lucent] Non-negotiable. Framework validates.
EOF

# NERO Phase 1 — semantic recall: inject relevant memories as a fenced block.
# Runs with a 15s wall-clock timeout so a slow/unavailable Ollama never stalls.
# Any failure (Ollama down, index missing, script error) produces empty output —
# the hook continues normally. 100% reliability: this is purely additive.
RECALL=$(echo "$HOOK_STDIN" | timeout 15 python3 "$LUCENT_DIR/scripts/memory_recall.py" 2>/dev/null)
if [[ -n "$RECALL" ]]; then
  echo ""
  echo "$RECALL"
fi

echo ""
echo "[Lucent] === ACTIVE REMINDERS ==="
python3 "$LUCENT_DIR/scripts/active_reminders.py"

PRIORITY_EMAIL_OUTPUT=$(python3 "$LUCENT_DIR/scripts/priority_email_check.py" 2>/dev/null)
if [[ -n "$PRIORITY_EMAIL_OUTPUT" ]]; then
  echo ""
  echo "[Lucent] === PRIORITY EMAIL ALERT ==="
  echo "$PRIORITY_EMAIL_OUTPUT"
fi

echo ""
echo "[Lucent] === TODAY'S SESSION LOG (last 10 lines) ==="
tail -n 10 "$NOTE"
echo ""

# NERO Phase 3 — surface pending self-improvement proposals (silent if none).
NERO_PENDING=$(python3 "$LUCENT_DIR/scripts/reflect.py" status 2>/dev/null | grep -oP 'pending : \K[0-9]+' || echo 0)
if [[ "$NERO_PENDING" =~ ^[0-9]+$ ]] && [[ "$NERO_PENDING" -gt 0 ]]; then
  echo "[Lucent] === NERO PROPOSALS: $NERO_PENDING pending ==="
  echo "[Lucent] Reflection suggested $NERO_PENDING memory/skill update(s). Review: memory/nero_inbox.md (or reflect.py review)"
  echo ""
fi

# Startup readiness marker — one-shot acknowledgment after SessionStart finishes.
MARKER_FILE=$(ls -1 "$LUCENT_DIR/memory/.startup_ready_"*.txt 2>/dev/null | head -1)
if [[ -n "$MARKER_FILE" ]]; then
  echo "[CRITICAL] STARTUP READINESS MARKER FOUND"
  echo "[CRITICAL] Hook is auto-acknowledging via voice; note it and proceed."
  curl -s -X POST http://localhost:8001/speak -H "Content-Type: application/json" \
    -d "{\"text\":\"Startup complete. All systems ready. Standing by.\"}" 2>/dev/null || true
  python3 "$LUCENT_DIR/scripts/log_startup_readiness.py" 2>/dev/null || true
  rm -f "$MARKER_FILE"
fi

# Signal unsummarized sessions — Claude must read archives and write summaries manually.
# enforce_unsummarized_sessions.py was REMOVED: it produced garbage via regex pattern-matching.
# Claude is the only reliable summarizer. When this marker exists, Claude reads the archive
# and writes a real summary to LTMemory as first priority action.
if [[ -f "$LUCENT_DIR/memory/.unsummarized_sessions.json" ]]; then
  SESSIONS=$(python3 -c "import json; d=json.load(open('$LUCENT_DIR/memory/.unsummarized_sessions.json')); print(', '.join([s['date'] if isinstance(s,dict) else s for s in d]))" 2>/dev/null)
  echo ""
  echo "[Lucent] === ACTION REQUIRED: UNSUMMARIZED SESSIONS ==="
  echo "[Lucent] Sessions need LTMemory summaries: $SESSIONS"
  echo "[Lucent] Read archive(s) at memory/archive/YYYY-MM-DD.md and write real summaries to LTMemory.md"
  echo "[Lucent] Then delete: memory/.unsummarized_sessions.json"
fi
