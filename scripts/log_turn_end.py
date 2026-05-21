#!/usr/bin/env python3
"""
Log turn-end timestamp to daily note.

Called by Stop hook after Claude finishes generating a response.
Provides a backstop timestamp even if Claude forgets to log.

Usage: python3 scripts/log_turn_end.py
Effect: Appends "[HH:MM] [turn-end]" to memory/YYYY-MM-DD.md
"""

from datetime import datetime
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"


def log_turn_end():
    """Append turn-end timestamp to today's daily note."""
    today = datetime.now().strftime("%Y-%m-%d")
    note_path = MEMORY_DIR / f"{today}.md"

    timestamp = datetime.now().strftime("[%H:%M:%S]")
    entry = f"{timestamp} [turn-end] Claude response completed\n"

    try:
        with open(note_path, 'a') as f:
            f.write(entry)
    except Exception:
        pass  # Silent fail


if __name__ == "__main__":
    log_turn_end()
