#!/usr/bin/env python3
"""
OpenCode startup helper: Executes bash-level startup ritual steps.
Called by AGENTS.md to perform voice box check and session logging init.
Returns JSON status for the model to verify and proceed.
"""

import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime

def get_lucent_root():
    """Detect lucent root from script location."""
    return Path(__file__).parent.parent

def check_voice_box():
    """Check if voice box is online on port 8001."""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:8001/services/health"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                for service in data.get("services", []):
                    if service.get("name") == "Voice box":
                        return service.get("status") == "online"
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    return False

def init_session_logger():
    """Initialize session logger."""
    lucent_root = get_lucent_root()
    try:
        result = subprocess.run(
            ["python3", str(lucent_root / "scripts" / "session_logger.py"), "init"],
            cwd=str(lucent_root),
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False

def main():
    """Execute startup steps and return status."""
    lucent_root = get_lucent_root()

    # Run checks
    voice_box_ok = check_voice_box()
    session_init_ok = init_session_logger()

    status = {
        "timestamp": datetime.now().isoformat(),
        "voice_box_online": voice_box_ok,
        "session_logger_init": session_init_ok,
        "ritual_ready": voice_box_ok and session_init_ok,
        "lucent_root": str(lucent_root)
    }

    print(json.dumps(status, indent=2))
    return 0 if status["ritual_ready"] else 1

if __name__ == "__main__":
    sys.exit(main())
