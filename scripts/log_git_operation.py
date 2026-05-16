#!/usr/bin/env python3
"""
Log Git operations to activity log.

Usage:
  python3 scripts/log_git_operation.py "commit message" [repo_path]

Arguments:
  commit_message: The commit message (or operation description)
  repo_path: Optional path to repo (defaults to current directory)

Examples:
  python3 scripts/log_git_operation.py "fix: Update auth proxy"
  python3 scripts/log_git_operation.py "backup" /home/nick/dev/lucent/memory
"""

import sys
from pathlib import Path
from datetime import datetime, date
import subprocess

LUCENT_ROOT = Path(__file__).parent.parent

def get_git_info(repo_path: str) -> tuple:
    """Get current Git branch and latest commit hash."""
    try:
        result = subprocess.run(
            "git rev-parse --abbrev-ref HEAD",
            shell=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        branch = result.stdout.strip() or "unknown"

        result = subprocess.run(
            "git rev-parse --short HEAD",
            shell=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        commit = result.stdout.strip() or "unknown"

        return branch, commit
    except Exception:
        return "unknown", "unknown"

def log_to_activity(message: str) -> None:
    """Append timestamped message to activity log."""
    today = date.today().strftime("%Y-%m-%d")
    log_path = LUCENT_ROOT / "ui" / "logs" / f"activity_{today}.log"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] [git] {message}\n")
    except Exception as e:
        print(f"Warning: Failed to log to activity log: {e}", file=sys.stderr)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/log_git_operation.py 'commit message' [repo_path]")
        sys.exit(1)

    commit_msg = sys.argv[1]
    repo_path = sys.argv[2] if len(sys.argv) > 2 else str(LUCENT_ROOT)

    # Get Git info
    branch, commit = get_git_info(repo_path)

    # Log to activity log
    repo_name = Path(repo_path).name or "lucent"
    log_to_activity(f"{repo_name} ({branch} {commit}): {commit_msg}")

    print(f"Logged: {repo_name} ({branch} {commit}): {commit_msg}")

if __name__ == "__main__":
    main()
