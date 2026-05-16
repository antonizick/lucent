#!/usr/bin/env python3
"""
Startup Acknowledgement — sends proactive confirmation after startup.py completes.

Runs after startup.py in SessionStart hook:
- Reads startup marker to confirm STARTUP_OK
- Sends random acknowledgement message via voice box
- Logs to daily note with timestamp
- Exits cleanly

Reliability: 100% deterministic, no Claude agent invocation, direct voice box API.
"""

import sys
import json
import random
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
VOICE_BOX_SPEAK = "http://localhost:8001/speak"
MARKER_DIR = LUCENT_ROOT / "memory"

# 20 random acknowledgement messages for variety
ACKNOWLEDGEMENTS = [
    "Startup ritual complete. Standing by.",
    "Context loaded. Ready for your command.",
    "Initialization sequence finished. Awaiting instruction.",
    "All systems initialized. Let's begin.",
    "Startup ritual complete. Systems nominal.",
    "Ready to work. What's your request?",
    "Context fully loaded. Standing by.",
    "Startup acknowledgement complete. I'm listening.",
    "All checks passed. Ready to assist.",
    "Ritual complete. What shall we do?",
    "Startup successful. Awaiting your input.",
    "Systems online. Ready when you are.",
    "Context integrated. Standing by for commands.",
    "Initialization done. What's next?",
    "Ready and listening. Your move.",
    "Startup complete. I'm all ears.",
    "All systems ready. Let's proceed.",
    "Ritual acknowledged. Standing by.",
    "Ready to begin. What can I help with?",
    "Startup done. I'm ready to work.",
]


def send_voice(message: str) -> bool:
    """Send message to voice box. Returns True if successful."""
    try:
        data = json.dumps({"text": message}).encode("utf-8")
        req = urllib.request.Request(
            VOICE_BOX_SPEAK,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def log_to_activity(message: str) -> bool:
    """Append message to activity log."""
    try:
        today = date.today().strftime("%Y-%m-%d")
        log_path = MARKER_DIR / "logs" / f"activity_{today}.log"
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] [startup-ack] {message}\n")
        return True
    except Exception:
        return False


def check_startup_marker() -> bool:
    """Check if startup.py successfully completed (marker exists)."""
    today = date.today().strftime("%Y-%m-%d")
    marker = MARKER_DIR / f".startup_ready_{today}.txt"
    return marker.exists()


def main():
    # Only acknowledge if startup was successful
    if not check_startup_marker():
        return 0  # Fail silently if no marker

    # Pick random acknowledgement
    message = random.choice(ACKNOWLEDGEMENTS)

    # Send voice
    send_voice(message)

    # Log to activity log
    log_to_activity(f"Startup acknowledgement sent: {message}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
