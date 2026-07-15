#!/usr/bin/env python3
"""
Auto-summarizer: calls local Ollama to write LTMemory session summaries.

Runs hourly via cron (2 minutes after backup_memory.py). Finds daily notes
marked UNSUMMARIZED, reads their archives, calls the local Ollama writer
model, and writes comprehensive summaries to LTMemory.md Recent Sessions.

Safe to run manually:
  python3 scripts/auto_summarize.py
  python3 scripts/auto_summarize.py --dry-run  # show what would be written
"""

import sys
from pathlib import Path
from datetime import date, timedelta

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
ARCHIVE_DIR = MEMORY_DIR / "archive"
LTMEMORY_PATH = MEMORY_DIR / "LTMemory.md"
UNSUMMARIZED_MARKER = MEMORY_DIR / ".unsummarized_sessions.json"

sys.path.insert(0, str(Path(__file__).parent))
from ollama_client import call_ollama, check_ollama_health, WRITER_MODEL

MAX_ARCHIVE_CHARS = 60_000  # ~15K tokens — comfortably within mistral-small's 32K context
SUMMARY_TIMEOUT = 180       # seconds — long input, local inference on a 3090 Ti

SUMMARY_PROMPT = """You are summarizing a day's work log for Nick's personal productivity system (Lucent).

This summary is loaded into Lucent's context at the START of every future conversation,
so it must be SHORT and carry only what stays relevant beyond today. Fine-grained detail
(specific bug fixes, commit hashes, line numbers) is already preserved in the daily archive
and is retrievable on demand via semantic recall — do NOT duplicate it here.

Read the archive below and write a TIGHT summary for LTMemory.md.

FORMAT RULES:
- Group items by project using **Project Name:** headers (only projects with real progress)
- Each item is a bullet: - ✅ One durable outcome — what shipped, what was decided, what was learned
- 5-8 bullets TOTAL across all projects (hard cap — fewer for quiet days)
- Altitude test for each bullet: "Will this still matter to a future session a week from now?"
  If it's a one-off fix with no lasting lesson, OMIT it — recall will surface it if needed.
- Prefer: features shipped, architecture/design decisions, lasting lessons, project status changes
- OMIT: routine bug fixes, commit hashes, file/line references, raw log lines, blow-by-blow detail
- Do NOT include "### Session YYYY-MM-DD" — just the grouped bullet content

ARCHIVE:
{archive_content}"""


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


def call_summarizer(archive_content: str) -> str | None:
    """Call the local Ollama writer model to generate a summary. Returns
    summary text, or None on failure (logged to stdout — cron redirects
    this to /tmp/auto-summarize.log)."""
    if len(archive_content) > MAX_ARCHIVE_CHARS:
        archive_content = archive_content[:MAX_ARCHIVE_CHARS] + "\n\n[archive truncated — see full file in memory/archive/]"

    content, err = call_ollama(
        WRITER_MODEL,
        system="",
        user=SUMMARY_PROMPT.format(archive_content=archive_content),
        num_predict=700,  # ~5-8 tight bullets; hard ceiling reinforcing the prompt's brevity rule
        num_ctx=20000,    # covers the 60K-char archive cap (~15K tokens) plus prompt + response
        timeout=SUMMARY_TIMEOUT,
    )
    if err:
        print(f"  ✗ Ollama call failed: {err}")
        return None
    return content


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

    if not check_ollama_health():
        print("  ✗ Ollama unreachable at localhost:11434 — cannot summarize (is `ollama serve` / systemd unit running?)")
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

        print(f"  → {date_str}: calling local Ollama ({WRITER_MODEL})...")
        summary = call_summarizer(archive_content)
        if not summary:
            print(f"  ✗ {date_str}: Ollama call failed, leaving for manual review")
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
