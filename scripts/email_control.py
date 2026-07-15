#!/usr/bin/env python3
"""
Email monitoring control — suspend/resume monitoring + kill active processes.

Usage:
    python3 scripts/email_control.py suspend      # Suspend email monitoring completely
    python3 scripts/email_control.py resume       # Resume email monitoring
    python3 scripts/email_control.py status       # Check current status
    python3 scripts/email_control.py kill         # Kill any running email monitor processes
    python3 scripts/email_control.py quick-off    # Suspend + kill (fastest)
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime

SUSPEND_FLAG = Path.home() / "dev/lucent/memory/email/.suspended"
SUSPEND_LOG = Path.home() / "dev/lucent/memory/email/.suspend.log"


def ensure_dir():
    """Ensure email directory exists."""
    SUSPEND_FLAG.parent.mkdir(parents=True, exist_ok=True)


def suspend():
    """Suspend email monitoring (set flag)."""
    ensure_dir()
    SUSPEND_FLAG.touch()
    log_action("SUSPENDED", "Email monitoring suspended via flag file")
    print("✓ Email monitoring suspended")
    return True


def resume():
    """Resume email monitoring (remove flag)."""
    ensure_dir()
    if SUSPEND_FLAG.exists():
        SUSPEND_FLAG.unlink()
    log_action("RESUMED", "Email monitoring resumed")
    print("✓ Email monitoring resumed")
    return True


def status():
    """Check current suspension status."""
    suspended = SUSPEND_FLAG.exists()
    state = "SUSPENDED" if suspended else "RUNNING"
    print(f"Email monitoring: {state}")

    # Check for running processes
    try:
        result = subprocess.run(
            ["pgrep", "-f", "email_monitor.py|sync_and_score.py"],
            capture_output=True
        )
        if result.returncode == 0:
            pids = result.stdout.decode().strip().split('\n')
            print(f"  Active processes: {len(pids)}")
            for pid in pids:
                if pid:
                    print(f"    - PID {pid}")
        else:
            print("  Active processes: none")
    except Exception as e:
        print(f"  Could not check processes: {e}")

    return suspended


def kill_processes():
    """Kill any running email monitor processes."""
    try:
        result = subprocess.run(
            ["pkill", "-f", "email_monitor.py|sync_and_score.py"],
            capture_output=True,
            timeout=5
        )
        log_action("KILLED", "Email monitor processes terminated")
        print("✓ Email monitor processes killed")
        return True
    except Exception as e:
        print(f"✗ Failed to kill processes: {e}")
        return False


def quick_off():
    """Suspend + kill (fastest way to stop email monitoring)."""
    suspend()
    kill_processes()
    log_action("QUICK_OFF", "Email monitoring suspended and processes killed")
    print("✓ Email monitoring disabled (suspended + killed)")
    return True


def log_action(action, message):
    """Log suspension/resume actions."""
    ensure_dir()
    timestamp = datetime.now().isoformat()
    try:
        with open(SUSPEND_LOG, "a") as f:
            f.write(f"[{timestamp}] {action}: {message}\n")
    except Exception:
        pass


def main():
    ensure_dir()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "suspend":
        suspend()
    elif command == "resume":
        resume()
    elif command == "status":
        status()
    elif command == "kill":
        kill_processes()
    elif command == "quick-off":
        quick_off()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
