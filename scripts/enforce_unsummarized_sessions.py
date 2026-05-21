#!/usr/bin/env python3
"""
Enforce STEP 4.5: Generate summaries for unsummarized sessions.

Reads .unsummarized_sessions.json, generates 2-3 paragraph summaries
for each session from archive files, inserts into LTMemory.md,
and cleans up the marker file.

This eliminates the discipline gap by making summary generation automatic
at startup, removing manual check requirement.
"""

import json
import re
from pathlib import Path
from datetime import datetime

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
UNSUMMARIZED_FILE = MEMORY_DIR / ".unsummarized_sessions.json"
LTMEMORY_FILE = MEMORY_DIR / "LTMemory.md"


def extract_summary_from_archive(date_str: str) -> str:
    """
    Extract a 2-3 paragraph summary from archive file.
    Reads archive and intelligently extracts:
    - What was built/completed (Paragraph 1)
    - Technical decisions/implementations (Paragraph 2)
    - Blockers/constraints/deferred work (Paragraph 3, if any)
    """
    archive_path = MEMORY_DIR / "archive" / f"{date_str}.md"

    if not archive_path.exists():
        return f"**Archive file not found for {date_str}. See memory/archive/{date_str}.md**"

    try:
        with open(archive_path, 'r') as f:
            content = f.read()
    except Exception as e:
        return f"**Error reading archive: {e}**"

    # Extract key sections and information
    outcomes = extract_section(content, "WORK COMPLETED|COMPLETION|IMPLEMENTATION COMPLETE")
    technical = extract_technical_decisions(content)
    blockers = extract_blockers(content)
    commits = extract_commits(content)

    # Build summary
    paragraphs = []

    # Paragraph 1: Outcomes + deliverables
    if outcomes or commits:
        p1 = build_outcomes_paragraph(date_str, outcomes, commits)
        if p1:
            paragraphs.append(p1)

    # Paragraph 2: Technical decisions + implementations
    if technical:
        p2 = build_technical_paragraph(technical)
        if p2:
            paragraphs.append(p2)

    # Paragraph 3: Blockers/constraints/deferred work
    if blockers:
        p3 = build_blockers_paragraph(blockers)
        if p3:
            paragraphs.append(p3)

    # Fallback: if no structured data found, extract raw log
    if not paragraphs:
        paragraphs.append(extract_fallback_summary(content))

    return "\n".join(paragraphs)


def extract_section(content: str, pattern: str) -> list:
    """Extract section content by heading pattern."""
    sections = []
    lines = content.split('\n')

    capturing = False
    current_section = []

    for line in lines:
        if re.search(pattern, line, re.IGNORECASE):
            capturing = True
            continue

        if capturing:
            # Stop at next heading or end
            if line.startswith('##') or line.startswith('---'):
                if current_section:
                    sections.append('\n'.join(current_section))
                current_section = []
                capturing = False
            elif line.strip():
                current_section.append(line)

    if current_section:
        sections.append('\n'.join(current_section))

    return sections


def extract_technical_decisions(content: str) -> list:
    """Extract technical decisions and implementation patterns."""
    decisions = []

    # Look for decision patterns
    patterns = [
        r'DECISION:.*?\n(.*?)(?=\n\n|\n[A-Z]|$)',
        r'Created.*?:\s*(.*?)(?=\n|$)',
        r'Modified.*?:\s*(.*?)(?=\n|$)',
        r'Added.*?:\s*(.*?)(?=\n|$)',
        r'Implemented.*?:\s*(.*?)(?=\n|$)',
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)
        for match in matches:
            text = match.group(1).strip()
            if text and len(text) > 10:
                decisions.append(text[:200])  # Limit length

    return decisions[:5]  # Keep top 5


def extract_blockers(content: str) -> list:
    """Extract blockers, constraints, or deferred work."""
    blockers = []

    patterns = [
        r'BLOCKED:.*?\n(.*?)(?=\n\n|\n[A-Z]|$)',
        r'BLOCKER:.*?\n(.*?)(?=\n\n|\n[A-Z]|$)',
        r'Blocked.*?:\s*(.*?)(?=\n|$)',
        r'FAILED:.*?\n(.*?)(?=\n\n|\n[A-Z]|$)',
        r'deferred.*?:\s*(.*?)(?=\n|$)',
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            text = match.group(1).strip()
            if text and len(text) > 10:
                blockers.append(text[:200])

    return blockers[:3]


def extract_commits(content: str) -> list:
    """Extract Git commits mentioned in archive."""
    commits = []

    # Look for commit patterns: [commit-hash] message or "Commit: message"
    patterns = [
        r'\[([a-f0-9]{7})\]\s+"([^"]+)"',
        r'Commit.*?:\s*"([^"]+)"',
        r'feat:.*?(\w+.*?)(?=\n|$)',
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) >= 1:
                msg = match.group(1) if len(match.groups()) == 1 else match.group(2)
                if msg and msg not in commits:
                    commits.append(msg)

    return commits[:3]


def build_outcomes_paragraph(date: str, outcomes: list, commits: list) -> str:
    """Build paragraph 1: what was built/completed."""
    parts = []

    if outcomes:
        parts.append(" ".join(outcomes[:2]))

    if commits:
        parts.append(f"Committed: {', '.join(commits[:2])}")

    if parts:
        return " ".join(parts) + "."

    return None


def build_technical_paragraph(decisions: list) -> str:
    """Build paragraph 2: technical decisions and implementations."""
    if not decisions:
        return None

    parts = ["Technical implementation:"] + decisions[:3]
    return " ".join(parts) + "."


def build_blockers_paragraph(blockers: list) -> str:
    """Build paragraph 3: blockers/constraints/deferred work."""
    if not blockers:
        return None

    parts = ["Blockers or deferred work:"] + blockers[:2]
    return " ".join(parts) + "."


def extract_fallback_summary(content: str) -> str:
    """Fallback: extract first meaningful lines from archive."""
    lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('[')]

    # Take first 3-5 non-empty, non-timestamp lines
    summary_lines = []
    for line in lines[:10]:
        if line and len(line) > 20 and not line.startswith('##'):
            summary_lines.append(line)
        if len(summary_lines) >= 3:
            break

    if summary_lines:
        return " ".join(summary_lines) + " (Archive: full details at memory/archive/.md)"

    return "Session completed. See archive for full details."


def insert_summary_into_ltmemory(date_str: str, summary: str):
    """
    Insert summary into LTMemory.md Recent Sessions section.
    Inserts as: ### Session YYYY-MM-DD\n{summary}\n
    """
    if not LTMEMORY_FILE.exists():
        return False

    try:
        with open(LTMEMORY_FILE, 'r') as f:
            content = f.read()

        # Check if session already exists
        if f"### Session {date_str}" in content:
            return True  # Already summarized

        # Find "## Recent Sessions" section
        if "## Recent Sessions" not in content:
            return False

        # Find insertion point: right after "## Recent Sessions" header
        parts = content.split("## Recent Sessions")
        before = parts[0] + "## Recent Sessions"
        after = "## Recent Sessions" + parts[1] if len(parts) > 1 else ""

        # Find the first existing "### Session" entry to insert before it
        after_lines = after.split('\n')
        insert_idx = 0
        for i, line in enumerate(after_lines):
            if line.startswith("### Session"):
                insert_idx = i
                break

        # Build new entry
        new_entry = f"\n### Session {date_str}\n{summary}\n"

        # Insert
        if insert_idx > 0:
            after_lines.insert(insert_idx, new_entry)
            after = '\n'.join(after_lines)
        else:
            after = '\n' + new_entry + after

        new_content = before + after

        with open(LTMEMORY_FILE, 'w') as f:
            f.write(new_content)

        return True

    except Exception as e:
        print(f"Error inserting summary: {e}")
        return False


def log_to_daily_note(message: str):
    """Log action to today's daily note."""
    today = datetime.now().strftime("%Y-%m-%d")
    note_path = MEMORY_DIR / f"{today}.md"

    timestamp = datetime.now().strftime("[%H:%M:%S]")
    entry = f"{timestamp} [memory] {message}\n"

    try:
        with open(note_path, 'a') as f:
            f.write(entry)
    except Exception:
        pass


def enforce_unsummarized_sessions():
    """Main enforcement logic."""
    if not UNSUMMARIZED_FILE.exists():
        # No unsummarized sessions
        return {"status": "NO_UNSUMMARIZED", "count": 0}

    try:
        with open(UNSUMMARIZED_FILE, 'r') as f:
            data = json.load(f)
    except Exception:
        return {"status": "ERROR_READING_FILE", "count": 0}

    if not isinstance(data, list):
        return {"status": "INVALID_FORMAT", "count": 0}

    processed = []

    for session_data in data:
        if isinstance(session_data, dict):
            date_str = session_data.get("date")
        else:
            date_str = session_data

        if not date_str:
            continue

        # Extract summary from archive
        summary = extract_summary_from_archive(date_str)

        # Insert into LTMemory
        if insert_summary_into_ltmemory(date_str, summary):
            processed.append(date_str)

    # Delete marker file
    try:
        UNSUMMARIZED_FILE.unlink()
    except Exception:
        pass

    # Log to daily note
    if processed:
        message = f"Enforced unsummarized sessions: {', '.join(processed)}. Summaries generated and inserted into LTMemory.md Recent Sessions. Archive references preserved."
        log_to_daily_note(message)

    return {
        "status": "SUMMARIES_COMPLETE",
        "count": len(processed),
        "sessions": processed
    }


if __name__ == "__main__":
    result = enforce_unsummarized_sessions()
    print(json.dumps(result))
