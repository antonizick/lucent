# Compression System — Mandatory Startup Step

## Overview

The compression system ensures that daily notes are automatically condensed at the start of each new day. This prevents context bloat and keeps memory dense.

**Status:** Compression is a MANDATORY startup step. You cannot proceed with user work until it's complete.

## Enforcement Points

1. **CLAUDE.md Startup Ritual** — Step 2 explicitly requires compression
2. **Checkpoint Verification** — `memory/.ritual_checkpoint.json` tracks `compressed_yesterday` flag
3. **Blocking Task** — Task #1 blocks other work until compression is done
4. **Voice Feedback** — Startup ritual sends voice acknowledgment after compression completes

## How It Works (Lucent's Workflow)

### Step 1: Check if Compression is Needed

```bash
python3 scripts/check_compression.py status
```

**Output:**
- If compression needed: `⚠ Compression needed for: 2026-05-10.md`
- If no compression needed: `✓ No compression needed`

### Step 2: If Compression is Needed, Invoke Curator

Read `agents/curator-agent.md` and respond as Curator:

```
[Curator] Please compress 2026-05-10.md to 1-2 paragraphs:
- Include only outcomes and key decisions
- Add to today's note: "Compressed 2026-05-10 at session start"
- Update the note file directly
```

Curator will:
1. Read yesterday's full note
2. Extract outcomes and key decisions
3. Write compressed version back to yesterday's file
4. Add the marker to today's note

### Step 3: Mark Compression as Complete

After Curator finishes:

```bash
python3 scripts/check_compression.py mark-done
```

This verifies the marker exists and updates the checkpoint.

### Step 4: Send Voice Feedback

```bash
curl -s -X POST http://localhost:8001/speak -H "Content-Type: application/json" -d '{"text":"Startup ritual complete. Ready for your input."}'
```

## Checkpoint Schema

```json
{
  "timestamp": "2026-05-11T10:58:32.861348Z",
  "date": "2026-05-11",
  "context_hash": "...",
  "model": "haiku",
  "compressed_yesterday": true,
  "version": 2
}
```

**Key field:** `compressed_yesterday: true` means compression is done for today.

## If Compression Fails

If the marker doesn't appear in today's note, Curator may have encountered an issue:

1. Check today's note: `/home/nick/dev/lucent/memory/2026-05-11.md`
2. Verify marker exists: `Compressed YYYY-MM-DD at session start`
3. If missing, invoke Curator again with explicit instructions
4. Once marker is added, run `mark-done` to update checkpoint

## For External Agents (Discord, Scripts)

If calling `invoke_agent.py` from command line:

```bash
python3 scripts/invoke_agent.py curator "Compress 2026-05-10.md"
```

The script will fail with clear error if compression is needed but not done:

```
RuntimeError: Startup ritual incomplete: Yesterday's daily note (2026-05-10.md) needs compression.
Invoke Curator first: python3 scripts/invoke_agent.py curator 'Compress 2026-05-10.md'
```

## Files Involved

- `CLAUDE.md` — Startup ritual (Step 2 is compression)
- `scripts/verify_startup.py` — Checkpoint management + compression verification
- `scripts/check_compression.py` — CLI utility for checking/marking compression
- `scripts/invoke_agent.py` — Enforces compression before delegating to agents
- `memory/.ritual_checkpoint.json` — Checkpoint file (tracks `compressed_yesterday` flag)
- `agents/curator-agent.md` — Curator agent (does the compression)

## Safety

- **Non-destructive:** Compression only summarizes; original notes can be retrieved from git history
- **Idempotent:** Running compression twice is safe (marker prevents re-compression)
- **Reversible:** If compression was too aggressive, revert via git and re-run
