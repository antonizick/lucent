#!/usr/bin/env python3
"""
Validate three-layer response requirement.
Checks that a response includes: daily note entry, voice message, and text response.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

def validate(daily_note_entry: str, voice_message: str, text_response: str) -> dict:
    """Validate all three layers of response requirement."""
    missing = []

    if not daily_note_entry or not daily_note_entry.strip():
        missing.append("daily_note_entry")

    if not voice_message or not voice_message.strip():
        missing.append("voice_message")

    if not text_response or not text_response.strip():
        missing.append("text_response")

    if missing:
        return {
            "status": "INVALID",
            "missing": missing,
            "message": f"Missing layers: {', '.join(missing)}. All three required: daily_note_entry, voice_message, text_response."
        }

    return {
        "status": "OK_TO_SEND",
        "message": "All three layers present. Safe to send response."
    }

def main():
    if len(sys.argv) < 4:
        print(json.dumps({
            "status": "ERROR",
            "message": "Usage: validate_response.py <daily_note_entry> <voice_message> <text_response>"
        }))
        sys.exit(1)

    daily_note_entry = sys.argv[1]
    voice_message = sys.argv[2]
    text_response = sys.argv[3]

    result = validate(daily_note_entry, voice_message, text_response)
    print(json.dumps(result))

    sys.exit(0 if result["status"] == "OK_TO_SEND" else 1)

if __name__ == "__main__":
    main()
