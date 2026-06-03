#!/usr/bin/env python3
"""
Auto-summarizer: calls Haiku API to write LTMemory session summaries.

Runs hourly via cron (2 minutes after backup_memory.py). Finds daily notes
marked UNSUMMARIZED, reads their archives, calls Haiku, and writes
comprehensive summaries to LTMemory.md Recent Sessions.

Safe to run manually:
  python3 scripts/auto_summarize.py
  python3 scripts/auto_summarize.py --dry-run  # show what would be written
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import date, timedelta

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
ARCHIVE_DIR = MEMORY_DIR / "archive"
LTMEMORY_PATH = MEMORY_DIR / "LTMemory.md"
UNSUMMARIZED_MARKER = MEMORY_DIR / ".unsummarized_sessions.json"

HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_ARCHIVE_CHARS = 60_000  # ~15K tokens — well within Haiku's context

SUMMARY_PROMPT = """You are summarizing a day's work log for Nick's personal productivity system (Lucent).

Read the archive below and write a concise, comprehensive summary for LTMemory.md.

FORMAT RULES:
- Group items by project using **Project Name:** headers
- Each item is a bullet: - ✅ Brief description of what was built, fixed, or decided
- 15-30 bullets total (more for busy days, fewer for quiet ones)
- Focus on: features shipped, bugs fixed, architecture decisions, key lessons
- Include commit hashes when mentioned (e.g. commit abc1234)
- SKIP: raw log lines ([turn-end], session start/end markers, backup lines)
- Do NOT include "### Session YYYY-MM-DD" — just the grouped bullet content

ARCHIVE:
{archive_content}"""


def get_api_key() -> str | None:
    """Get Anthropic API key from env, falling back to ui/.env."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_file = LUCENT_ROOT / "ui" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def find_unsummarized_dates() -> list[str]:
    """Find daily note stubs (UNSUMMARIZED placeholder) from the last 7 days."""
    unsummarized = []
    today = date.today()
    for i in range(1, 8):
        check_date = today - timedelta(days=i)
        date_str = check_date.strftime("%Y-%m-%d")
        daily_note = MEMORY_DIR / f"{date_str}.md"
        if not daily_note.exists():
            continue
        try:
            if "UNSUMMARIZED" in daily_note.read_text():
                unsummarized.append(date_str)
        except Exception:
            continue
    return unsummarized


def ltmemory_has_session(date_str: str) -> bool:
    """Return True if LTMemory already has a ### Session entry for this date."""
    if not LTMEMORY_PATH.exists():
        return False
    return f"### Session {date_str}" in LTMEMORY_PATH.read_text()


def call_haiku(archive_content: str, api_key: str) -> str | None:
    """Call Haiku API to generate summary. Returns summary text or None on failure."""
    try:
        import anthropic
    except ImportError:
        print("  ✗ anthropic package not installed — run: pip install anthropic")
        return None

    if len(archive_content) > MAX_ARCHIVE_CHARS:
        archive_content = archive_content[:MAX_ARCHIVE_CHARS] + "\n\n[archive truncated — see full file in memory/archive/]"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": SUMMARY_PROMPT.format(archive_content=archive_content)
            }]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"  ✗ Haiku API call failed: {e}")
        return None


def prepend_session_to_ltmemory(date_str: str, summary: str) -> bool:
    """Prepend new session entry to LTMemory.md immediately after ## Recent Sessions."""
    if not LTMEMORY_PATH.exists():
        print("  ✗ LTMemory.md not found")
        return False
    try:
        content = LTMEMORY_PATH.read_text()
        marker = "## Recent Sessions\n"
        idx = content.find(marker)
        if idx == -1:
            print("  ✗ '## Recent Sessions' section not found in LTMemory.md")
            return False
        new_block = f"\n### Session {date_str}\n{summary}\n"
        insert_at = idx + len(marker)
        updated = content[:insert_at] + new_block + content[insert_at:]
        LTMEMORY_PATH.write_text(updated)
        return True
    except Exception as e:
        print(f"  ✗ Failed to update LTMemory.md: {e}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv
    print("→ auto_summarize: checking for unsummarized sessions...")

    unsummarized = find_unsummarized_dates()
    if not unsummarized:
        print("✓ No unsummarized sessions found")
        if UNSUMMARIZED_MARKER.exists():
            UNSUMMARIZED_MARKER.unlink()
        return 0

    print(f"  Found: {', '.join(unsummarized)}")

    api_key = get_api_key()
    if not api_key:
        print("  ✗ ANTHROPIC_API_KEY not found in env or ui/.env — cannot summarize")
        return 1

    success_count = 0
    for date_str in unsummarized:
        if ltmemory_has_session(date_str):
            print(f"  ✓ {date_str}: already in LTMemory, skipping")
            success_count += 1
            continue

        archive_path = ARCHIVE_DIR / f"{date_str}.md"
        if not archive_path.exists():
            print(f"  ✗ {date_str}: archive not found ({archive_path})")
            continue

        size = archive_path.stat().st_size
        print(f"  → {date_str}: reading archive ({size:,} bytes)...")
        archive_content = archive_path.read_text()

        print(f"  → {date_str}: calling Haiku API...")
        summary = call_haiku(archive_content, api_key)
        if not summary:
            print(f"  ✗ {date_str}: API call failed, leaving for manual review")
            continue

        line_count = len(summary.splitlines())
        print(f"  → {date_str}: generated {line_count}-line summary")

        if dry_run:
            print(f"\n--- DRY RUN: would write to LTMemory.md ---")
            print(f"### Session {date_str}")
            print(summary[:800] + ("..." if len(summary) > 800 else ""))
            print("--- END DRY RUN ---\n")
            success_count += 1
            continue

        if prepend_session_to_ltmemory(date_str, summary):
            print(f"  ✓ {date_str}: written to LTMemory.md")
            success_count += 1
        else:
            print(f"  ✗ {date_str}: write failed")

    if not dry_run and success_count == len(unsummarized):
        if UNSUMMARIZED_MARKER.exists():
            UNSUMMARIZED_MARKER.unlink()

    status = f"{success_count}/{len(unsummarized)} sessions summarized"
    print(f"{'✓' if success_count == len(unsummarized) else '⚠'} auto_summarize complete: {status}")
    return 0 if success_count == len(unsummarized) else 1


if __name__ == "__main__":
    sys.exit(main())
