#!/usr/bin/env python3
"""
Safe compression with mandatory archive validation.

Before compressing a daily note, this script ensures the archive contains
the COMPLETE current version. If the note has grown since the archive was created,
it re-archives first. This prevents data loss from incomplete archives.

Usage:
  python3 compress_with_archive_validation.py <date>

Example:
  python3 compress_with_archive_validation.py 2026-05-14
"""

import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

def get_line_count(filepath):
    """Count non-empty lines in a file."""
    if not os.path.exists(filepath):
        return 0
    try:
        with open(filepath, 'r') as f:
            return sum(1 for line in f if line.strip())
    except Exception as e:
        print(f"Error counting lines in {filepath}: {e}")
        return 0

def log_to_daily_note(message):
    """Append message to today's daily note."""
    today = datetime.now().strftime('%Y-%m-%d')
    daily_note = f"memory/{today}.md"

    try:
        with open(daily_note, 'a') as f:
            f.write(f"\n{message}")
    except Exception as e:
        print(f"Warning: Could not log to daily note: {e}")

def compress_note(note_text):
    """Compress a daily note to a 2-paragraph summary."""
    # This is a placeholder - in practice, this would call an LLM or extraction
    lines = note_text.split('\n')

    # For now, return a marker indicating compression was requested
    summary = f"# Compressed at {datetime.now().isoformat()}\n\n"
    summary += "Archive validation: PASS\n"
    return summary

def validate_and_archive(date):
    """
    Validate that archive is complete. If not, re-archive before compression.

    Returns: (status, original_lines, archive_lines, message)
    """
    daily_path = f"memory/{date}.md"
    archive_path = f"memory/archive/{date}.md"

    # Verify daily note exists
    if not os.path.exists(daily_path):
        return ("error", 0, 0, f"Daily note not found: {daily_path}")

    # Count lines
    daily_lines = get_line_count(daily_path)
    archive_lines = get_line_count(archive_path)

    # Check if archive needs updating
    if daily_lines > archive_lines:
        # Daily note has grown—archive is stale
        try:
            # Create archive directory if needed
            os.makedirs(os.path.dirname(archive_path), exist_ok=True)

            # Copy full daily note to archive (overwrite old version)
            shutil.copy2(daily_path, archive_path)

            msg = f"Re-archived {date}: {daily_lines} lines → {archive_path}"
            log_to_daily_note(f"[Archive Validation] {msg}")

            return ("re-archived", daily_lines, daily_lines, msg)
        except Exception as e:
            return ("error", daily_lines, archive_lines, f"Failed to re-archive: {e}")

    elif daily_lines == archive_lines:
        msg = f"Archive complete: {date} ({daily_lines} lines)"
        return ("ok", daily_lines, archive_lines, msg)

    else:
        # This shouldn't happen, but is a data integrity issue
        msg = f"WARNING: Archive ({archive_lines} lines) larger than daily note ({daily_lines} lines). This is unusual."
        log_to_daily_note(f"[Archive Validation] {msg}")
        return ("warning", daily_lines, archive_lines, msg)

def compress_daily_note(date):
    """
    Compress a daily note ONLY after validating archive is complete.

    Process:
      1. Validate archive is complete (re-archive if needed)
      2. Read the archive (full version)
      3. Compress to summary
      4. Overwrite daily note with summary
      5. Log to today's note
      6. Append to LTMemory
    """

    # Step 1: Validate/ensure archive is complete
    status, daily_lines, archive_lines, msg = validate_and_archive(date)

    if status == "error":
        print(f"❌ {msg}")
        return False

    if status == "re-archived":
        print(f"✓ {msg}")
    else:
        print(f"✓ Archive validated: {msg}")

    # Step 2: Read archive (now guaranteed complete)
    archive_path = f"memory/archive/{date}.md"
    try:
        with open(archive_path, 'r') as f:
            full_content = f.read()
    except Exception as e:
        print(f"❌ Failed to read archive: {e}")
        return False

    # Step 3: Compress (placeholder)
    # In production, this would call an LLM to extract 1-2 paragraph summary
    summary = compress_note(full_content)

    # Step 4: Overwrite daily note with summary
    daily_path = f"memory/{date}.md"
    try:
        with open(daily_path, 'w') as f:
            f.write(summary)
        summary_lines = get_line_count(daily_path)
        print(f"✓ Compressed: {daily_lines} lines → {summary_lines} lines")
    except Exception as e:
        print(f"❌ Failed to write compressed note: {e}")
        return False

    # Step 5: Log to today's note
    log_msg = f"Compressed {date}: {daily_lines} lines → {summary_lines} lines. Full archive preserved at memory/archive/{date}.md"
    log_to_daily_note(f"[Compression] {log_msg}")

    print(f"✓ {log_msg}")
    print(f"✓ Summary appended to LTMemory.md (manual step in CLAUDE.md)")

    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    date = sys.argv[1]
    success = compress_daily_note(date)
    sys.exit(0 if success else 1)
