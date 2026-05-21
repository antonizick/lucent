#!/usr/bin/env python3
"""
Log session-end timestamp to daily note.

Called by SessionEnd hook when Claude session closes.
Marks the session boundary in the daily note.

Usage: python3 scripts/log_session_end.py
Effect: Appends "[HH:MM] [session-end]" to memory/YYYY-MM-DD.md
"""

from datetime import datetime
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"


def log_session_end():
    """Append session-end timestamp to today's daily note."""
    today = datetime.now().strftime("%Y-%m-%d")
    note_path = MEMORY_DIR / f"{today}.md"

    timestamp = datetime.now().strftime("[%H:%M:%S]")
    entry = f"{timestamp} [session-end] Session closed\n"

    try:
        with open(note_path, 'a') as f:
            f.write(entry)
    except Exception:
        pass  # Silent fail


if __name__ == "__main__":
    log_session_end()
