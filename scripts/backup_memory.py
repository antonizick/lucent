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
import json
from pathlib import Path
from datetime import datetime, date

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
HEALTH_CHECK_FILE = LUCENT_ROOT / ".backup_health"

def write_health_check(backup_type: str) -> None:
    """Write health check timestamp for backup verification."""
    try:
        health_data = {}
        if HEALTH_CHECK_FILE.exists():
            with open(HEALTH_CHECK_FILE, "r") as f:
                health_data = json.load(f)

        health_data[backup_type] = datetime.now().isoformat()

        with open(HEALTH_CHECK_FILE, "w") as f:
            json.dump(health_data, f)
    except Exception:
        pass  # Fail silently

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

def archive_accumulating_daily_note() -> None:
    """
    Archive the current day's accumulating daily note.

    This runs every backup cycle (hourly) to ensure the archive captures
    the growing daily note throughout the day. When compression happens,
    the archive will already be complete, preventing data loss.
    """
    import shutil
    today = date.today().strftime("%Y-%m-%d")
    daily_note = MEMORY_DIR / f"{today}.md"
    archive_path = MEMORY_DIR / "archive" / f"{today}.md"

    if not daily_note.exists():
        return  # No daily note yet

    try:
        # Create archive directory if needed
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy current daily note to archive (overwrites old version)
        shutil.copy2(daily_note, archive_path)

        # Log only if this is a new/growing note (not already archived)
        # Check if archive is being updated (note lines > archive lines)
        try:
            with open(daily_note, 'r') as f:
                daily_lines = sum(1 for _ in f)
            with open(archive_path, 'r') as f:
                archive_lines = sum(1 for _ in f)

            # If archive just became complete or grew, log it
            if daily_lines == archive_lines:
                # Archive now matches daily note—it's complete
                # Silently maintain the invariant: archive_lines >= daily_lines
                pass

        except Exception:
            pass  # Don't fail backup on logging errors

    except Exception as e:
        # Log error but don't fail the backup
        log_to_daily_note(f"Archive update failed: {e}")

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
        # Still write health check timestamp (verified, no changes needed)
        write_health_check("memory")
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
    write_health_check("memory")
    return 0

def check_lucent_core() -> None:
    """Check Lucent core repo status and write health check timestamp."""
    print(f"→ Checking Lucent core repo...")
    code, _, _ = run_cmd("git status", cwd=str(LUCENT_ROOT))
    if code == 0:
        print(f"✓ Lucent core repo verified")
        write_health_check("lucent_core")
    else:
        print(f"✗ Lucent core repo check failed")

def main():
    # Step 1: Archive the accumulating daily note (maintains live archive)
    archive_accumulating_daily_note()

    # Step 2: Backup memory folder to git
    exit_code = backup_memory()

    # Step 3: Verify lucent core repo
    check_lucent_core()

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
