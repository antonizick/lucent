#!/usr/bin/env python3
"""
Data-driven reminder checker that parses REMINDERS.md for pattern-based reminders.
Fires reminders based on schedule with idempotency tracking per reminder per day.

Supported formats in REMINDERS.md:
  - Every [day]: [text]
  - Every [day] at [HH:MM]: [text]
  - [YYYY-MM-DD]: [text]
"""
import json
import os
import sys
import re
from datetime import datetime, date, timedelta
import subprocess

CHECKPOINT_FILE = os.path.expanduser("~/dev/lucent/memory/reminders_checkpoint.json")
REMINDERS_FILE = os.path.expanduser("~/dev/lucent/memory/REMINDERS.md")
VOICE_BOX_URL = "http://localhost:8001/speak"

DAYS_OF_WEEK = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}

def save_checkpoint(data):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, indent=2)

def parse_reminders_file():
    """Parse REMINDERS.md and extract pattern-based reminders."""
    reminders = []
    if not os.path.exists(REMINDERS_FILE):
        return reminders

    with open(REMINDERS_FILE) as f:
        content = f.read()

    # Extract pattern-based reminders section
    section_match = re.search(
        r"## Pattern-Based Reminders.*?(?=##|\Z)",
        content,
        re.DOTALL
    )
    if not section_match:
        return reminders

    section = section_match.group(0)

    # Parse each reminder line (starts with "- **")
    for line in section.split('\n'):
        if not line.strip().startswith('- '):
            continue

        # Extract format: - **[pattern]**: [text]
        match = re.search(r'- \*\*(.+?)\*\*:\s*(.+?)(?:\s*\(|$)', line)
        if not match:
            continue

        pattern = match.group(1).strip()
        text = match.group(2).strip()

        # Parse pattern: "Every [day]" or "Every [day] at [HH:MM]" or "[YYYY-MM-DD]"

        # Specific date
        if re.match(r'\d{4}-\d{2}-\d{2}', pattern):
            reminders.append({
                'type': 'date',
                'date': pattern,
                'text': text,
                'key': f"date_{pattern}"
            })
            continue

        # Every [day] or Every [day] at [HH:MM]
        every_match = re.match(r'Every\s+(\w+)(?:\s+at\s+(\d{2}):(\d{2}))?', pattern, re.IGNORECASE)
        if every_match:
            day_name = every_match.group(1).lower()
            hour = every_match.group(2)
            minute = every_match.group(3)

            if day_name not in DAYS_OF_WEEK:
                continue

            reminder = {
                'type': 'weekly',
                'day': DAYS_OF_WEEK[day_name],
                'day_name': day_name,
                'text': text,
                'key': f"weekly_{day_name}"
            }

            if hour and minute:
                reminder['time'] = f"{hour}:{minute}"
                reminder['key'] = f"weekly_{day_name}_{hour}_{minute}"

            reminders.append(reminder)

    return reminders

def send_voice_reminder(text):
    """Send reminder via voice box."""
    try:
        subprocess.run(
            ["curl", "-s", "-X", "POST", VOICE_BOX_URL,
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"text": text})],
            check=False,
            timeout=5
        )
        return True
    except Exception as e:
        print(f"Warning: Failed to send voice reminder: {e}", file=sys.stderr)
        return False

def should_fire_reminder(reminder, today, now_time):
    """Check if a reminder should fire based on current date/time."""

    if reminder['type'] == 'date':
        # Specific date reminder
        return str(today) == reminder['date']

    elif reminder['type'] == 'weekly':
        # Weekly reminder
        if today.weekday() != reminder['day']:
            return False

        # If time specified, check if current time >= reminder time
        if 'time' in reminder:
            reminder_time = datetime.strptime(reminder['time'], "%H:%M").time()
            if now_time < reminder_time:
                return False

        return True

    return False

def check_reminders():
    """Check and fire due reminders."""
    checkpoint = load_checkpoint()
    today = date.today()
    now = datetime.now()
    today_str = today.isoformat()

    reminders = parse_reminders_file()
    if not reminders:
        return False

    fired_any = False

    for reminder in reminders:
        key = reminder['key']
        last_fired_date = checkpoint.get(key)

        # Check if reminder should fire today/now
        if should_fire_reminder(reminder, today, now.time()):
            # Only fire if we haven't already fired this reminder today
            if last_fired_date != today_str:
                send_voice_reminder(reminder['text'])
                checkpoint[key] = today_str
                fired_any = True
                print(f"✓ Reminder fired: {reminder['key']} — {reminder['text']}")

    # Save updated checkpoint
    save_checkpoint(checkpoint)
    return fired_any

if __name__ == "__main__":
    check_reminders()
