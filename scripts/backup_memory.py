#!/usr/bin/env python3
"""
Backup memory folder to private Git repository.

Commits all changes with message "Automated backup by Lucent" and pushes to origin.
Safe to run multiple times — if no changes, commit is skipped.

Usage:
  python3 scripts/backup_memory.py
  Returns 0 on success (commit + push, or nothing to commit)
  Returns 1 on failure (git error)
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime, date

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"

def log_to_daily_note(message: str) -> None:
    """Append timestamped message to today's daily note."""
    today = date.today().strftime("%Y-%m-%d")
    note_path = LUCENT_ROOT / "memory" / f"{today}.md"
    timestamp = datetime.now().strftime("%H:%M:%S")

    try:
        with open(note_path, "a") as f:
            f.write(f"\n[{timestamp}] {message}")
    except Exception:
        pass  # Fail silently

def run_cmd(cmd, cwd=None, check=True):
    """Run shell command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False
    )
    return result.returncode, result.stdout, result.stderr

def backup_memory() -> int:
    """
    Backup memory folder to Git.

    Returns:
        0 on success, 1 on failure
    """
    if not MEMORY_DIR.exists():
        print(f"✗ Memory directory not found: {MEMORY_DIR}")
        return 1

    print(f"→ Backing up memory folder...")

    # Check if memory/ is a git repository
    code, _, _ = run_cmd("git status", cwd=str(MEMORY_DIR))
    if code != 0:
        print(f"✗ Memory folder is not a Git repository: {MEMORY_DIR}")
        return 1

    # Add all changes
    code, stdout, stderr = run_cmd("git add -A", cwd=str(MEMORY_DIR))
    if code != 0:
        print(f"✗ Failed to stage files: {stderr}")
        return 1

    # Check if there are changes to commit
    code, status, _ = run_cmd("git status --porcelain", cwd=str(MEMORY_DIR))
    if not status.strip():
        print(f"✓ No changes to commit (memory already up-to-date)")
        return 0

    # Commit
    code, stdout, stderr = run_cmd(
        'git commit -m "Automated backup by Lucent"',
        cwd=str(MEMORY_DIR)
    )
    if code != 0:
        print(f"✗ Commit failed: {stderr}")
        log_to_daily_note(f"Backup FAILED: commit error")
        return 1

    print(f"✓ Committed: Automated backup by Lucent")

    # Push to origin
    code, stdout, stderr = run_cmd("git push origin", cwd=str(MEMORY_DIR))
    if code != 0:
        print(f"✗ Push failed: {stderr}")
        log_to_daily_note(f"Backup FAILED: push error")
        return 1

    print(f"✓ Pushed to origin (memory backed up)")
    log_to_daily_note(f"Backup: Committed and pushed (Automated backup by Lucent)")
    return 0

def main():
    exit_code = backup_memory()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
