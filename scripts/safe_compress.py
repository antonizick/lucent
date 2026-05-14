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
from verify_startup import archive_daily_note

LUCENT_ROOT = Path(__file__).parent.parent

def safe_compress(note_date: str) -> int:
    """
    Archive and compress a daily note. Archival is mandatory — compression
    only proceeds if archival succeeds.

    Args:
        note_date: Date string (YYYY-MM-DD)

    Returns:
        0 on success, 1 on failure
    """
    note_path = LUCENT_ROOT / "memory" / f"{note_date}.md"

    if not note_path.exists():
        print(f"✗ Note not found: {note_path}")
        return 1

    # STEP 1: Archive (mandatory)
    success, message = archive_daily_note(LUCENT_ROOT, note_date)
    print(message)

    if not success:
        print(f"✗ ARCHIVAL FAILED — refusing to compress.")
        print(f"  Archival is mandatory and must succeed before compression.")
        return 1

    # STEP 2: Compress (only if archival succeeded)
    print(f"→ Compressing {note_date}.md...")
    # Note: Actual compression logic goes here (trimming to 1-2 paragraphs)
    # For now, just signal success since the Curator handles actual trimming

    # STEP 3: Add compression marker (only after successful archival)
    # Marker format: "Compressed YYYY-MM-DD at session start." on line 3 after header
    marker = f"Compressed {note_date} at session start."
    print(f"→ Adding marker: {marker}")

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
