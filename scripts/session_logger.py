#!/usr/bin/env python3
"""
Session logging enforcement for Lucent.

Ensures that every session initializes a daily note entry at startup
and validates that logging happens during the session.

Usage:
  from session_logger import initialize_session_log, validate_session_log_updated

  # At startup
  session_start = initialize_session_log(lucent_root, topic="Voice box enforcement")

  # Before each response (optional, for validation)
  validate_session_log_updated(lucent_root, session_start)
"""

import json
from pathlib import Path
from datetime import datetime, date
import sys

def initialize_session_log(lucent_root, topic=""):
    """
    Initialize a session log entry in today's daily note.

    Creates or appends to memory/YYYY-MM-DD.md with a session start marker.
    Returns the timestamp of session start for later validation.

    Args:
        lucent_root: Path to Lucent root directory
        topic: Brief description of what's being worked on

    Returns:
        dict with session_start timestamp and note file path
    """
    memory_dir = Path(lucent_root) / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()
    note_path = memory_dir / f"{today.strftime('%Y-%m-%d')}.md"

    session_start = datetime.now()
    timestamp = session_start.strftime("%H:%M:%S")

    # Append session start marker
    marker = f"\n## [{timestamp}] Session start"
    if topic:
        marker += f" — {topic}"
    marker += "\n"

    # Append to file (create if doesn't exist)
    with open(note_path, "a") as f:
        f.write(marker)

    # Return session metadata for later validation
    return {
        "start_time": session_start.timestamp(),
        "note_path": str(note_path),
        "date": str(today),
        "timestamp": timestamp
    }

def validate_session_log_updated(lucent_root, session_start):
    """
    Validate that the daily note has been updated since session start.

    Checks that the file was modified after the session started.
    Raises RuntimeError if validation fails.

    Args:
        lucent_root: Path to Lucent root directory
        session_start: dict returned by initialize_session_log()

    Raises:
        RuntimeError if daily note was not updated
    """
    note_path = Path(session_start["note_path"])

    if not note_path.exists():
        raise RuntimeError(
            f"Daily note missing: {note_path}\n"
            f"Session logging failed. Cannot proceed."
        )

    # Get file modification time
    file_mtime = note_path.stat().st_mtime
    session_start_time = session_start["start_time"]

    # Check if file was modified after session started
    # Allow 1 second grace period for the initial write
    if file_mtime < session_start_time + 1:
        raise RuntimeError(
            f"Daily note not updated since session start.\n"
            f"Session started: {session_start['timestamp']}\n"
            f"File modified: {datetime.fromtimestamp(file_mtime).strftime('%H:%M:%S')}\n"
            f"Logging failed. Cannot proceed."
        )

def require_session_log_entry(lucent_root, session_start, content=""):
    """
    Require and validate a session log entry with content.

    Appends content to the daily note and validates it was written.
    This is called before each response to ensure logging happens.

    Args:
        lucent_root: Path to Lucent root directory
        session_start: dict returned by initialize_session_log()
        content: Text to append to the daily note

    Raises:
        RuntimeError if logging fails
    """
    note_path = Path(session_start["note_path"])

    if not note_path.exists():
        raise RuntimeError(
            f"Daily note missing: {note_path}\n"
            f"Cannot append session log."
        )

    if content.strip():
        # Append content to note
        with open(note_path, "a") as f:
            f.write(f"{content}\n")

    # Validate file was updated
    file_mtime = note_path.stat().st_mtime
    now = datetime.now().timestamp()

    # File should have been modified very recently (within last 5 seconds)
    if now - file_mtime > 5:
        raise RuntimeError(
            f"Daily note update failed.\n"
            f"Expected recent modification, but file is stale.\n"
            f"Cannot proceed without session logging."
        )

def check_session_log_checkpoint(lucent_root):
    """
    Check if today's daily note has been initialized for the session.

    Used at startup to verify session logging has been started.
    Raises RuntimeError if session hasn't been initialized.

    Args:
        lucent_root: Path to Lucent root directory

    Raises:
        RuntimeError if session log not initialized
    """
    today = date.today()
    note_path = Path(lucent_root) / "memory" / f"{today.strftime('%Y-%m-%d')}.md"

    if not note_path.exists():
        raise RuntimeError(
            f"Daily note not initialized: {note_path}\n"
            f"Run initialize_session_log() during startup ritual."
        )

    # Check that note contains a session start marker
    content = note_path.read_text()
    if "## [" not in content or "Session start" not in content:
        raise RuntimeError(
            f"Daily note missing session start marker.\n"
            f"File: {note_path}\n"
            f"Initialize session logging at startup."
        )

if __name__ == "__main__":
    # Test mode
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
        try:
            session = initialize_session_log(root, "Test session")
            print(f"✓ Session initialized: {session}")
            check_session_log_checkpoint(root)
            print("✓ Checkpoint verified")
        except Exception as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            sys.exit(1)
