#!/usr/bin/env python3
"""
PreToolUse guard: block a Write tool call that would replace a daily note or
archive file's content with something drastically shorter.

Root cause of the 2026-07-17 incident: qwen3.5-coder (a local Ollama model,
run through the same unrestricted Claude Code tool suite as any frontier
model) tried to log a daily-note entry, hit "Invalid tool parameters", retried
with a full-file Write, and replaced 201 lines with 5 — deleting the entire
day's session record. Nothing in the harness validated the new content before
it hit disk. This hook is that validation, independent of which model or
platform is driving the session.

Only blocks; never modifies content. The known legitimate shrink case (the
next day's auto-compress placeholder) is allowlisted by its distinct
"UNSUMMARIZED" marker text (see backup_memory.py compress_yesterday_if_needed).

Usage: wired as a PreToolUse hook (matcher "Write") in .claude/settings.json.
Reads the hook payload JSON from stdin; writes a permission decision to stdout.
"""

import json
import re
import sys
from pathlib import Path

MIN_EXISTING_LINES = 20   # ignore small/new files
SHRINK_RATIO = 0.5        # block if new size < 50% of existing size
DAILY_NOTE_RE = re.compile(r'(?:^|/)(?:archive/)?\d{4}-\d{2}-\d{2}\.md$')


def allow():
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }))
    sys.exit(0)


def deny(reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()  # fail open — a broken guard must not block all writes
        return

    if payload.get("tool_name") != "Write":
        allow()
        return

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or ""
    new_content = tool_input.get("content", "") or ""

    if not DAILY_NOTE_RE.search(file_path.replace("\\", "/")):
        allow()
        return

    path = Path(file_path)
    if not path.exists():
        allow()  # new file, nothing to compare against
        return

    try:
        existing_lines = sum(1 for _ in open(path, "r"))
    except Exception:
        allow()  # can't read existing file — fail open
        return

    new_lines = new_content.count("\n") + (1 if new_content else 0)

    if existing_lines < MIN_EXISTING_LINES:
        allow()
        return

    if new_lines >= existing_lines * SHRINK_RATIO:
        allow()
        return

    if "UNSUMMARIZED" in new_content:
        allow()  # known legitimate case: auto-compress placeholder
        return

    deny(
        f"Blocked: Write to {path.name} would shrink it from {existing_lines} to "
        f"{new_lines} lines ({existing_lines - new_lines} lines would be lost). "
        f"Daily notes/archives are append-only. If this is intentional (e.g. "
        f"manual cleanup), use the Edit tool with a targeted replacement instead "
        f"of a full-file Write, or ask Nick to confirm before overwriting."
    )


if __name__ == "__main__":
    main()
