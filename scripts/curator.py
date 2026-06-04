#!/usr/bin/env python3
"""
Curator Agent — Promote daily note archives to LTMemory.md

Reads recent day archives (7-14 days), extracts comprehensive summaries,
updates LTMemory.md Recent Sessions with curated content.

Usage:
  python3 scripts/curator.py [--days 7]
  python3 scripts/curator.py --days 14  # Review 14 days
  python3 scripts/curator.py --check    # Verify LTMemory completeness
  python3 scripts/curator.py --prune            # Move old sessions to archive (keep last 20)
  python3 scripts/curator.py --prune --keep 15  # Keep only 15 sessions
  python3 scripts/curator.py --prune --dry-run  # Preview without modifying files

Returns:
  0 on success (summaries written or verified complete)
  1 on error
"""

import re
import sys
import json
from pathlib import Path
from datetime import date, timedelta
from typing import Optional

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
ARCHIVE_DIR = MEMORY_DIR / "archive"
LTMEMORY_PATH = MEMORY_DIR / "LTMemory.md"
LTMEMORY_ARCHIVE_PATH = MEMORY_DIR / "LTMemory.archive.md"

SESSIONS_TO_KEEP = 5  # Default: keep last 5 sessions statically loaded; older sessions
                      # move to LTMemory.archive.md (still recall-indexed, just not loaded
                      # into every conversation). Recall serves older detail on demand.

def get_recent_archives(days: int = 7) -> list[tuple[str, Path]]:
    """Get list of (date_str, path) for recent unsummarized archives."""
    if not ARCHIVE_DIR.exists():
        return []

    archives = []
    today = date.today()

    for i in range(1, days + 1):
        check_date = today - timedelta(days=i)
        date_str = check_date.strftime("%Y-%m-%d")
        archive_path = ARCHIVE_DIR / f"{date_str}.md"

        if archive_path.exists():
            archives.append((date_str, archive_path))

    return sorted(archives, reverse=True)  # Most recent first


def extract_summary_from_archive(archive_path: Path) -> Optional[str]:
    """
    Extract comprehensive summary from archive file.

    Identifies:
    - Major features/fixes (lines starting with ✅)
    - Key decisions/blockers
    - Database/infrastructure changes
    - Commits and tags

    Returns formatted section for LTMemory.md, or None if archive is minimal.
    """
    try:
        with open(archive_path, 'r') as f:
            content = f.read()

        # Extract checkmarked items (major work)
        lines = content.split('\n')
        major_items = [line.strip() for line in lines if '✅' in line]

        if len(major_items) < 5:
            # Archive too minimal to extract meaningful summary
            return None

        # Build summary section
        summary_lines = []

        # Extract first few major items as bullet points
        for item in major_items[:20]:  # Limit to 20 most relevant items
            # Clean up formatting
            item = item.replace('✅', '').strip()
            summary_lines.append(f"- {item}")

        # Extract commits (look for "Commit:" lines)
        commits = [line.strip() for line in lines if 'commit' in line.lower() and ':' in line]
        if commits:
            summary_lines.append("\n**Commits:**")
            for commit in commits[:5]:
                summary_lines.append(f"- {commit}")

        # Extract database/infrastructure work
        db_work = [line.strip() for line in lines if any(
            x in line.lower() for x in ['database', 'port', 'config', 'infrastructure', 'fix', 'migration']
        ) and '✅' in line]
        if db_work:
            summary_lines.append("\n**Infrastructure:**")
            for work in db_work[:5]:
                work = work.replace('✅', '').strip()
                summary_lines.append(f"- {work}")

        return '\n'.join(summary_lines) if summary_lines else None

    except Exception as e:
        print(f"  ✗ Failed to extract summary: {e}")
        return None


def check_ltmemory_completeness() -> bool:
    """
    Verify that LTMemory.md Recent Sessions contains comprehensive summaries.

    Returns True if all sessions are well-documented, False if stubs detected.
    """
    if not LTMEMORY_PATH.exists():
        print("✗ LTMemory.md not found")
        return False

    with open(LTMEMORY_PATH, 'r') as f:
        content = f.read()

    # Check for stub markers
    stub_markers = [
        "to be filled in",
        "See full details",
        "UNSUMMARIZED",
        "*Summary",
    ]

    issues = []
    for marker in stub_markers:
        if marker.lower() in content.lower():
            issues.append(f"  ⚠️  Found stub marker: '{marker}'")

    # Check for session entries with < 3 bullet points (sign of incompleteness)
    import re
    session_pattern = r'### Session \d{4}-\d{2}-\d{2}(.*?)(?=### Session|$)'
    sessions = re.findall(session_pattern, content, re.DOTALL)

    for session_content in sessions:
        bullet_count = session_content.count('\n-') + session_content.count('\n1.')
        if bullet_count < 3:
            date_match = re.search(r'Session (\d{4}-\d{2}-\d{2})', content)
            if date_match:
                issues.append(f"  ⚠️  Incomplete session: {date_match.group(1)} has <3 items")

    if issues:
        print("✗ LTMemory.md has incomplete summaries:")
        for issue in issues:
            print(issue)
        return False

    print("✓ LTMemory.md is complete (all sessions documented)")
    return True


def update_ltmemory_recent_sessions(summaries: dict[str, str]) -> bool:
    """
    Update LTMemory.md Recent Sessions with new summaries.

    Replaces stub entries with comprehensive summaries.
    Maintains reverse chronological order (newest first).
    """
    if not summaries:
        return False

    if not LTMEMORY_PATH.exists():
        print("✗ LTMemory.md not found")
        return False

    try:
        with open(LTMEMORY_PATH, 'r') as f:
            content = f.read()

        # Find Recent Sessions section
        import re
        recent_sessions_pattern = r'## Recent Sessions\n\n(.*?)(?=## |$)'
        match = re.search(recent_sessions_pattern, content, re.DOTALL)

        if not match:
            print("✗ Recent Sessions section not found in LTMemory.md")
            return False

        # Build new Recent Sessions section (reverse chronological order)
        new_sessions = []
        for date_str in sorted(summaries.keys(), reverse=True):
            summary = summaries[date_str]
            new_sessions.append(f"\n### Session {date_str}\n{summary}\n")

        new_recent_section = "## Recent Sessions\n" + ''.join(new_sessions)

        # Replace old section with new
        updated_content = content[:match.start()] + new_recent_section + content[match.end():]

        with open(LTMEMORY_PATH, 'w') as f:
            f.write(updated_content)

        print(f"✓ Updated LTMemory.md with {len(summaries)} session summaries")
        return True

    except Exception as e:
        print(f"✗ Failed to update LTMemory.md: {e}")
        return False


def parse_recent_sessions(content: str) -> tuple[str, list[tuple[str, str]], str]:
    """
    Split LTMemory.md into (preamble, sessions, postamble).

    sessions: list of (date_str, full_block_text) in the order found (newest first).
    preamble: everything up to and including "## Recent Sessions\n".
    postamble: any ## sections after Recent Sessions (usually empty).
    """
    match = re.search(r'^## Recent Sessions\s*\n', content, re.MULTILINE)
    if not match:
        return content, [], ""

    section_start = match.start()
    preamble = content[:section_start] + "## Recent Sessions\n"
    body_start = match.end()

    # Recent Sessions is always the last top-level section.
    # Don't search for the next "## " — session bodies contain "## Bold Heading"
    # lines that would be misidentified as top-level section boundaries.
    body = content[body_start:]
    postamble = ""

    session_re = re.compile(r'^### Session (\d{4}-\d{2}-\d{2})\n', re.MULTILINE)
    matches = list(session_re.finditer(body))
    sessions = []
    for i, m in enumerate(matches):
        date_str = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sessions.append((date_str, body[start:end]))

    return preamble, sessions, postamble


def prune_sessions(keep_n: int = SESSIONS_TO_KEEP, dry_run: bool = False) -> tuple[int, int]:
    """
    Move the oldest sessions from LTMemory.md Recent Sessions to LTMemory.archive.md.
    Sessions are kept sorted newest-first; only the tail beyond keep_n is archived.
    Returns (kept_count, archived_count).
    """
    if not LTMEMORY_PATH.exists():
        print("✗ LTMemory.md not found")
        return 0, 0

    content = LTMEMORY_PATH.read_text()
    preamble, sessions, postamble = parse_recent_sessions(content)

    if not sessions:
        print("✓ No sessions found in Recent Sessions section.")
        return 0, 0

    # Ensure newest-first order before splitting
    sessions.sort(key=lambda x: x[0], reverse=True)

    if len(sessions) <= keep_n:
        print(f"✓ {len(sessions)} sessions present — within limit ({keep_n}). Nothing to prune.")
        return len(sessions), 0

    keep = sessions[:keep_n]
    archive = sessions[keep_n:]

    print(f"  Sessions found: {len(sessions)}  |  Keeping: {len(keep)}  |  Archiving: {len(archive)}")
    for date_str, _ in archive:
        print(f"    → Archive: {date_str}")

    if dry_run:
        print("  (dry-run — no files modified)")
        return len(keep), len(archive)

    # Rewrite LTMemory.md with only the kept sessions
    new_content = preamble + "\n" + "".join(b for _, b in keep) + postamble
    LTMEMORY_PATH.write_text(new_content)

    # Prepend archived sessions into LTMemory.archive.md (after file header)
    archived_block = "".join(b for _, b in archive)
    if LTMEMORY_ARCHIVE_PATH.exists():
        existing = LTMEMORY_ARCHIVE_PATH.read_text()
        # Insert new sessions after the header paragraph (before first ### Session)
        first_session = re.search(r'^### Session', existing, re.MULTILINE)
        if first_session:
            insert_at = first_session.start()
            new_archive = existing[:insert_at] + archived_block + existing[insert_at:]
        else:
            new_archive = existing.rstrip() + "\n\n" + archived_block
    else:
        header = "# LTMemory Archive\n\nOlder session entries moved out of LTMemory.md to keep it lean.\n\n"
        new_archive = header + archived_block

    LTMEMORY_ARCHIVE_PATH.write_text(new_archive)

    size_kb = LTMEMORY_PATH.stat().st_size // 1000
    print(f"✓ Prune complete: {len(keep)} sessions kept ({size_kb}KB), {len(archive)} archived to LTMemory.archive.md")
    return len(keep), len(archive)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Curator: promote daily archives to LTMemory")
    parser.add_argument('--days', type=int, default=7, help='Number of days to review (default: 7)')
    parser.add_argument('--check', action='store_true', help='Check LTMemory completeness, do not modify')
    parser.add_argument('--prune', action='store_true', help='Move oldest sessions to LTMemory.archive.md')
    parser.add_argument('--keep', type=int, default=SESSIONS_TO_KEEP, help=f'Sessions to keep when pruning (default: {SESSIONS_TO_KEEP})')
    parser.add_argument('--dry-run', action='store_true', help='Preview prune without modifying files')
    args = parser.parse_args()

    if args.prune:
        print(f"→ Pruning LTMemory.md to last {args.keep} sessions...")
        kept, archived = prune_sessions(keep_n=args.keep, dry_run=args.dry_run)
        return 0

    print(f"→ Curator reviewing {args.days} days of archives...")

    if args.check:
        # Just verify completeness
        return 0 if check_ltmemory_completeness() else 1

    # Get recent unsummarized archives
    archives = get_recent_archives(days=args.days)
    if not archives:
        print("✓ No recent archives found (LTMemory may already be up-to-date)")
        return 0

    print(f"  Found {len(archives)} archive(s) to review")

    # Extract summaries from each archive
    summaries = {}
    for date_str, archive_path in archives:
        print(f"  → Reviewing {date_str}...")
        summary = extract_summary_from_archive(archive_path)
        if summary:
            summaries[date_str] = summary
            print(f"    ✓ Extracted {len(summary.split(chr(10)))} lines")
        else:
            print(f"    ⊘ Archive too minimal, skipping")

    if not summaries:
        print("✗ No substantial archives to promote")
        return 0

    # Update LTMemory
    if update_ltmemory_recent_sessions(summaries):
        print(f"✓ Curator complete: {len(summaries)} sessions promoted to LTMemory.md")
        return 0
    else:
        print("✗ Curator failed to update LTMemory.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())
