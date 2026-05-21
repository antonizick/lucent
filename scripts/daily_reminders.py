#!/usr/bin/env python3
"""
Twice-daily bundled announcements: overdue/due reminders + priority emails.

Rate-limited to one announcement per window (morning 6am–noon, afternoon noon–8pm).
Overdue reminders repeat every window until archived in REMINDERS.md.
Priority emails (score >= 7.0, last 8 days) are included in the same announcement.
"""

import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
REMINDERS_FILE = LUCENT_ROOT / "memory" / "REMINDERS.md"
EMAIL_DB = LUCENT_ROOT / "ui" / "data" / "emails.db"
LOG_FILE = LUCENT_ROOT / "memory" / ".daily_announcement_log.json"
VOICE_BOX_URL = "http://localhost:8001/speak"

MORNING_START = 6
AFTERNOON_START = 12
EVENING_END = 20


def get_current_window():
    """Return 'morning', 'afternoon', or None if outside announcement windows."""
    hour = datetime.now().hour
    if MORNING_START <= hour < AFTERNOON_START:
        return "morning"
    elif AFTERNOON_START <= hour < EVENING_END:
        return "afternoon"
    return None


def load_log():
    try:
        if LOG_FILE.exists():
            return json.loads(LOG_FILE.read_text())
    except Exception:
        pass
    return {}


def save_log(log):
    LOG_FILE.write_text(json.dumps(log, indent=2))


def should_fire(window):
    """Return True if this window slot hasn't fired today."""
    today = date.today().isoformat()
    return load_log().get(today, {}).get(f"{window}_fired") is None


def mark_fired(window):
    today = date.today().isoformat()
    log = load_log()
    if today not in log:
        log[today] = {}
    log[today][f"{window}_fired"] = datetime.now().isoformat()
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    save_log({k: v for k, v in log.items() if k >= cutoff})


def parse_due_reminders():
    """Parse REMINDERS.md; return list of overdue/due-within-24h items."""
    if not REMINDERS_FILE.exists():
        return []

    content = REMINDERS_FILE.read_text()
    archive_idx = content.find("## Archive")
    if archive_idx != -1:
        content = content[:archive_idx]

    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_weekday = today.strftime("%A").lower()
    items = []

    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("- **"):
            continue

        # Specific date: **2026-05-15**: or **2026-05-15 at 09:00**:
        m = re.match(r'- \*\*(\d{4}-\d{2}-\d{2})(?:\s+at\s+\d{1,2}:\d{2})?\*\*:\s*(.+)', line)
        if m:
            try:
                reminder_date = date.fromisoformat(m.group(1))
                text = m.group(2).strip()
                if reminder_date < today:
                    days = (today - reminder_date).days
                    items.append(f"Overdue by {days} day{'s' if days != 1 else ''}: {text}")
                elif reminder_date == today:
                    items.append(f"Due today: {text}")
                elif reminder_date == tomorrow:
                    items.append(f"Due tomorrow: {text}")
            except ValueError:
                pass
            continue

        # Every session starting DATE
        m = re.match(r'- \*\*Every session starting (\d{4}-\d{2}-\d{2})\*\*:\s*(.+)', line)
        if m:
            try:
                start = date.fromisoformat(m.group(1))
                text = m.group(2).strip()
                if today >= start:
                    items.append(f"Ongoing: {text}")
            except ValueError:
                pass
            continue

        # Every DAY [at HH:MM]
        m = re.match(r'- \*\*Every (\w+)(?:\s+at\s+\d{1,2}:\d{2})?\*\*:\s*(.+)', line)
        if m:
            day = m.group(1).lower()
            text = m.group(2).strip()
            if day == today_weekday:
                items.append(f"Scheduled today: {text}")
            continue

    return items


def get_priority_emails():
    """Return formatted strings for priority emails (score >= 7, last 8 days)."""
    try:
        if not EMAIL_DB.exists():
            return []
        conn = sqlite3.connect(str(EMAIL_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=8)).isoformat()
        cursor.execute(
            "SELECT sender, subject, priority_score FROM emails "
            "WHERE priority_score >= 7.0 AND received_at >= ? "
            "ORDER BY priority_score DESC, received_at DESC LIMIT 3",
            (cutoff,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            f"Priority email from {r['sender']}: {r['subject'][:60]} (score {r['priority_score']:.1f})"
            for r in rows
        ]
    except Exception:
        return []


def speak(text):
    try:
        subprocess.run(
            ["curl", "-s", "-X", "POST", VOICE_BOX_URL,
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"text": text})],
            check=False,
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def run():
    """Fire bundled announcement if a window slot is available. Returns status dict."""
    window = get_current_window()
    if window is None:
        return {"fired": False, "reason": "Outside announcement windows (6am–8pm)"}

    if not should_fire(window):
        return {"fired": False, "reason": f"{window} slot already fired today"}

    reminder_items = parse_due_reminders()
    email_items = get_priority_emails()
    all_items = reminder_items + email_items

    if not all_items:
        mark_fired(window)  # Mark slot used so we don't retry until next window
        return {"fired": False, "reason": "No due reminders or priority emails"}

    # Build speech from sections
    parts = []
    if reminder_items:
        n = len(reminder_items)
        parts.append(
            f"{'One reminder' if n == 1 else f'{n} reminders'}: "
            + ". ".join(reminder_items)
        )
    if email_items:
        n = len(email_items)
        parts.append(
            f"{'One priority email' if n == 1 else f'{n} priority emails'}: "
            + ". ".join(email_items)
        )

    speech = ". Also, ".join(parts) + "."
    speak(speech)
    mark_fired(window)

    return {
        "fired": True,
        "window": window,
        "reminder_count": len(reminder_items),
        "email_count": len(email_items),
        "items": all_items,
    }


if __name__ == "__main__":
    result = run()
    if result.get("fired"):
        print(
            f"✓ Daily announcements spoken ({result['window']} slot): "
            f"{result['reminder_count']} reminder(s), {result['email_count']} email(s)"
        )
        for item in result.get("items", []):
            print(f"  • {item}")
    else:
        print(f"— Daily announcements: {result.get('reason', 'skipped')}")
    sys.exit(0)
