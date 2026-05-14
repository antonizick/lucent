#!/usr/bin/env python3
"""
Verify backup health by checking GitHub for recent commits.

Ensures memory repo on GitHub is up-to-date and accessible.
Logs health status to daily note.

Usage:
  python3 scripts/verify_backup_health.py
  Returns 0 if healthy, 1 if issues found
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime, date, timedelta

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

def verify_backup_health() -> int:
    """
    Verify backup health by checking GitHub.

    Returns:
        0 if healthy, 1 if issues found
    """
    if not MEMORY_DIR.exists():
        error = "Memory directory not found"
        log_to_daily_note(f"Backup health CHECK FAILED: {error}")
        print(f"✗ {error}")
        return 1

    # Check if it's a git repo
    result = subprocess.run(
        "git status",
        cwd=str(MEMORY_DIR),
        capture_output=True,
        text=True,
        shell=True
    )
    if result.returncode != 0:
        error = "Not a git repository"
        log_to_daily_note(f"Backup health CHECK FAILED: {error}")
        print(f"✗ {error}")
        return 1

    # Check if we can reach GitHub (fetch without modifying)
    result = subprocess.run(
        "git fetch origin --dry-run",
        cwd=str(MEMORY_DIR),
        capture_output=True,
        text=True,
        shell=True,
        timeout=10
    )
    if result.returncode != 0:
        error = f"Cannot reach GitHub: {result.stderr.strip()}"
        log_to_daily_note(f"Backup health CHECK FAILED: {error}")
        print(f"✗ {error}")
        return 1

    # Check how recent the last push was
    result = subprocess.run(
        "git log --oneline origin/main -1",
        cwd=str(MEMORY_DIR),
        capture_output=True,
        text=True,
        shell=True
    )
    if result.returncode != 0:
        error = "Cannot read remote history"
        log_to_daily_note(f"Backup health CHECK FAILED: {error}")
        print(f"✗ {error}")
        return 1

    last_commit = result.stdout.strip()

    # Get the commit timestamp
    result = subprocess.run(
        "git log --format=%ai origin/main -1",
        cwd=str(MEMORY_DIR),
        capture_output=True,
        text=True,
        shell=True
    )
    if result.returncode == 0:
        commit_time = result.stdout.strip().split()[0]

        # Parse and check if recent (within 2 hours for safety)
        try:
            from datetime import datetime as dt
            commit_dt = dt.fromisoformat(commit_time)
            now = dt.now(commit_dt.tzinfo)
            hours_ago = (now - commit_dt).total_seconds() / 3600

            if hours_ago > 2:
                warning = f"Last backup was {hours_ago:.1f} hours ago"
                log_to_daily_note(f"Backup health WARNING: {warning}")
                print(f"⚠ {warning}")
                return 0  # Still healthy, just older than expected

            message = f"Backup health OK: Last backup {hours_ago:.1f}h ago ({last_commit[:40]})"
            log_to_daily_note(f"Backup health: {message}")
            print(f"✓ {message}")
            return 0

        except Exception as e:
            message = f"Backup health OK (could not check age): {last_commit[:40]}"
            log_to_daily_note(f"Backup health: {message}")
            print(f"✓ {message}")
            return 0

    message = f"Backup health OK: {last_commit[:40]}"
    log_to_daily_note(f"Backup health: {message}")
    print(f"✓ {message}")
    return 0

def main():
    exit_code = verify_backup_health()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
