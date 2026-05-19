#!/usr/bin/env python3
"""
Log startup readiness acknowledgment to activity log.

Called by lucent-init.sh hook when startup completes.
Logs to activity log only (not daily note) to keep daily notes focused on substantive work.
"""

from pathlib import Path
from datetime import datetime, date


def log_to_activity(message: str) -> None:
    """Append timestamped message to activity log."""
    lucent_root = Path(__file__).parent.parent
    today = date.today().strftime("%Y-%m-%d")
    log_path = lucent_root / "memory" / "logs" / f"activity_{today}.log"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] [startup-readiness] {message}\n")
    except Exception:
        pass  # Fail silently


if __name__ == "__main__":
    log_to_activity("Startup readiness acknowledged (auto via UserPromptSubmit hook)")
