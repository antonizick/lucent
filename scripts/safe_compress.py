#!/usr/bin/env python3
"""
Safe compress with mandatory archival enforcement.

Ensures daily notes are archived BEFORE compression. Refuses to compress
if archival fails. This is a binding mechanism — agents must use this.

Usage:
  python3 scripts/safe_compress.py 2026-05-12
  Returns exit code 0 on success, 1 on failure
"""

import sys
from pathlib import Path
from datetime import date
from verify_startup import archive_daily_note

LUCENT_ROOT = Path(__file__).parent.parent

def safe_compress(note_date: str) -> int:
    """
    Archive a daily note and write the compression marker to today's note.
    Archival is mandatory — marker is only written if archival succeeds.
    Actual summarization is performed by Claude after this script exits.

    Args:
        note_date: Date string (YYYY-MM-DD)

    Returns:
        0 on success, 1 on failure
    """
    note_path = LUCENT_ROOT / "memory" / f"{note_date}.md"

    if not note_path.exists():
        print(f"✗ Note not found: {note_path}")
        return 1

    # STEP 1: Archive (mandatory — refuses to proceed if archival fails)
    success, message = archive_daily_note(LUCENT_ROOT, note_date)
    print(message)

    if not success:
        print(f"✗ ARCHIVAL FAILED — refusing to compress.")
        print(f"  Archival is mandatory and must succeed before compression.")
        return 1

    # STEP 2: Write compression marker to today's note
    # check_compression.py mark-done looks for this string in today's note
    today_note = LUCENT_ROOT / "memory" / f"{date.today().isoformat()}.md"
    marker = f"\nCompressed {note_date} at session start.\n"
    try:
        with open(today_note, "a") as f:
            f.write(marker)
        print(f"✓ Compression marker written to {today_note.name}")
    except Exception as e:
        print(f"✗ Failed to write compression marker: {e}")
        return 1

    print(f"→ Ready for Claude to summarize: memory/archive/{note_date}.md")
    print(f"  After summarizing, overwrite memory/{note_date}.md with the summary.")

    return 0

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/safe_compress.py YYYY-MM-DD")
        sys.exit(1)

    note_date = sys.argv[1]
    exit_code = safe_compress(note_date)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
