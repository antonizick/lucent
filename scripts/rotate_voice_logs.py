#!/usr/bin/env python3
"""
Voice box activity log rotation and archival.

Moves activity logs older than 30 days to gzipped monthly archives in memory/archive/voice-box/.
Keeps recent logs (< 30 days) in memory/logs/ for easy searching and automatic backup.

Usage:
  python3 scripts/rotate_voice_logs.py
  Returns 0 on success, 1 on failure
"""

import sys
import gzip
import shutil
from pathlib import Path
from datetime import datetime, date, timedelta

LUCENT_ROOT = Path(__file__).parent.parent
LOGS_DIR = LUCENT_ROOT / "memory" / "logs"
ARCHIVE_DIR = LUCENT_ROOT / "memory" / "archive" / "voice-box"
KEEP_DAYS = 30

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

def rotate_voice_logs() -> int:
    """
    Rotate voice box logs older than KEEP_DAYS to gzipped archives.

    Returns:
        0 on success, 1 on failure
    """
    if not LOGS_DIR.exists():
        error_msg = f"Logs directory not found: {LOGS_DIR}"
        log_to_daily_note(f"Voice log rotation FAILED: {error_msg}")
        print(f"✗ {error_msg}")
        return 1

    # Calculate cutoff date
    cutoff = date.today() - timedelta(days=KEEP_DAYS)

    archived_count = 0
    archived_list = []

    try:
        # Find all activity_YYYY-MM-DD.log files
        for log_file in sorted(LOGS_DIR.glob("activity_????-??-??.log")):
            try:
                # Extract date from filename
                date_str = log_file.stem.replace("activity_", "")
                log_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                # Skip if recent (within KEEP_DAYS)
                if log_date >= cutoff:
                    continue

                # Determine archive directory (YYYY-MM structure)
                year_month = log_date.strftime("%Y-%m")
                archive_subdir = ARCHIVE_DIR / year_month
                archive_subdir.mkdir(parents=True, exist_ok=True)

                # Create gzipped archive
                archive_path = archive_subdir / f"{log_file.stem}.gz"
                with open(log_file, "rb") as f_in:
                    with gzip.open(archive_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)

                # Delete original
                log_file.unlink()

                archived_count += 1
                archived_list.append(date_str)

            except (ValueError, OSError) as e:
                # Skip files that don't match pattern or fail
                print(f"⚠ Skipped {log_file.name}: {e}")
                continue

        if archived_count == 0:
            message = f"✓ No logs to rotate (all within {KEEP_DAYS} days)"
            print(message)
            return 0

        message = f"✓ Rotated {archived_count} log(s) to memory/archive/voice-box/: {', '.join(archived_list)}"
        print(message)
        log_to_daily_note(f"Voice log rotation: {message}")
        return 0

    except Exception as e:
        error_msg = f"Log rotation failed: {e}"
        log_to_daily_note(f"Voice log rotation ERROR: {error_msg}")
        print(f"✗ {error_msg}")
        return 1

def main():
    exit_code = rotate_voice_logs()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
