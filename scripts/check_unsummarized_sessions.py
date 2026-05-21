#!/usr/bin/env python3
"""
Check for unsummarized daily notes.

Scans memory/ for daily notes (YYYY-MM-DD.md) that are not yet
summarized in LTMemory.md Recent Sessions. Returns JSON list
of sessions needing summary with archive preview.

Usage:
  python3 scripts/check_unsummarized_sessions.py
  Returns JSON: {"unsummarized": [...], "count": N}
"""

import json
import re
from pathlib import Path
from datetime import datetime, date, timedelta

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"

def get_summarized_sessions():
    """Extract session dates from LTMemory.md Recent Sessions."""
    ltmemory_path = MEMORY_DIR / "LTMemory.md"
    summarized = set()

    if not ltmemory_path.exists():
        return summarized

    try:
        with open(ltmemory_path, 'r') as f:
            content = f.read()

        # Extract all "### Session YYYY-MM-DD" entries in Recent Sessions section
        # Look for section between "## Recent Sessions" and end (no subsection limiting needed)
        if "## Recent Sessions" in content:
            parts = content.split("## Recent Sessions")
            if len(parts) > 1:
                recent_section = parts[1]
                # Find all session entries (### Session YYYY-MM-DD) at subsection level
                # This captures all subsections in Recent Sessions
                matches = re.findall(r'### Session (\d{4}-\d{2}-\d{2})', recent_section)
                summarized.update(matches)

    except Exception:
        pass

    return summarized

def get_daily_notes():
    """Get list of daily note files (YYYY-MM-DD.md)."""
    notes = []
    try:
        for file in MEMORY_DIR.glob("*.md"):
            match = re.match(r'(\d{4}-\d{2}-\d{2})\.md$', file.name)
            if match:
                notes.append(match.group(1))
    except Exception:
        pass
    return sorted(notes, reverse=True)  # Most recent first

def get_archive_preview(date_str: str):
    """Get first few lines from archive as preview."""
    archive_path = MEMORY_DIR / "archive" / f"{date_str}.md"
    if not archive_path.exists():
        return None

    try:
        with open(archive_path, 'r') as f:
            lines = [line.rstrip() for line in f.readlines()[:5]]
            return lines
    except Exception:
        return None

def check_unsummarized():
    """Find sessions without summaries in LTMemory. Excludes today and notes older than 10 days."""
    today = date.today()
    cutoff = today - timedelta(days=10)
    summarized = get_summarized_sessions()
    daily_notes = get_daily_notes()

    unsummarized = []
    for date_str in daily_notes:
        note_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        if note_date == today:
            continue  # Today's session is still active — never unsummarized
        if note_date < cutoff:
            continue  # Beyond lookback window
        if date_str not in summarized:
            preview = get_archive_preview(date_str)
            unsummarized.append({
                "date": date_str,
                "preview": preview or ["(archive not found)"]
            })

    return unsummarized

if __name__ == "__main__":
    unsummarized = check_unsummarized()
    result = {
        "unsummarized": unsummarized,
        "count": len(unsummarized)
    }
    print(json.dumps(result))
