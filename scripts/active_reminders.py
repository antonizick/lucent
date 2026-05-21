#!/usr/bin/env python3
"""
Smart reminder filtering for Lucent.

Reads REMINDERS.md and filters to show ONLY active reminders for today.
- Evaluates day-of-week patterns (e.g., "Every Monday")
- Evaluates dated reminders (e.g., "2026-05-21")
- Checks "Every session starting" patterns
- Context-triggered reminders always output (they're relevant when context appears)
- Auto-archives expired dated reminders
- Silent if no active reminders found

Usage: python3 scripts/active_reminders.py
Output: Goes to stdout for hook injection
"""

import re
from datetime import datetime, date
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
REMINDERS_FILE = LUCENT_ROOT / "memory" / "REMINDERS.md"

WEEKDAYS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday"
}


def get_today():
    """Return today's date and day of week."""
    today = date.today()
    day_name = WEEKDAYS[today.weekday()]
    return today, day_name


def extract_section(content, section_name):
    """Extract a section from REMINDERS.md by section name."""
    # Find section header
    pattern = rf"## {section_name}.*?\n(.*?)(?=##|$)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return ""
    return match.group(1)


def parse_pattern_reminders(section_text, today, today_name):
    """Parse and filter pattern-based reminders."""
    active = []

    for line in section_text.split('\n'):
        line = line.strip()
        if not line or not line.startswith('- **'):
            continue

        # Parse line: - **Every Monday**: reminder text
        # or: - **2026-05-14 at 09:00**: reminder text
        # or: - **Every session starting 2026-05-20**: reminder text

        match = re.match(r'- \*\*(.+?)\*\*: (.+)$', line)
        if not match:
            continue

        trigger, reminder_text = match.groups()

        # Check if active
        if is_pattern_active(trigger, today, today_name):
            active.append(f"**{trigger}**: {reminder_text}")

    return active


def is_pattern_active(trigger, today, today_name):
    """Determine if a pattern-based reminder is active today."""

    # Every Monday, Tuesday, etc.
    if trigger.startswith("Every "):
        # Extract day name
        match = re.match(r"Every (\w+)", trigger)
        if match:
            day = match.group(1)
            return day == today_name
        return False

    # Specific dates: "2026-05-14 at 09:00" or "2026-05-15"
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", trigger)
    if date_match:
        reminder_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
        # Show on the date AND any day after (overdue until manually archived)
        return today >= reminder_date

    # Every session starting: "Every session starting 2026-05-20"
    if "Every session starting" in trigger:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", trigger)
        if date_match:
            start_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
            return today >= start_date

    return False


def parse_context_reminders(section_text):
    """Extract context-triggered reminders."""
    reminders = []

    for line in section_text.split('\n'):
        line = line.strip()
        if not line or not line.startswith('- **'):
            continue

        # Parse: - **When: [context] → Remind**: [reminder text]
        match = re.match(r'- \*\*When: ([^→]+) → Remind\*\*: (.+)$', line)
        if match:
            context, reminder_text = match.groups()
            reminders.append(f"**When: {context.strip()} → Remind**: {reminder_text}")

    return reminders


def format_output(active_pattern_reminders, context_reminders):
    """Format reminders for output."""
    all_reminders = active_pattern_reminders + context_reminders

    if not all_reminders:
        return ""

    # Format as bulleted list
    output = "[Lucent] === ACTIVE REMINDERS ===\n"
    for reminder in all_reminders:
        output += f"- {reminder}\n"

    return output.rstrip()


def main():
    """Main entry point."""
    today, today_name = get_today()

    if not REMINDERS_FILE.exists():
        return

    try:
        with open(REMINDERS_FILE, 'r') as f:
            content = f.read()
    except Exception:
        return

    # Parse pattern-based reminders
    pattern_section = extract_section(content, "Pattern-Based Reminders")
    active_patterns = parse_pattern_reminders(pattern_section, today, today_name)

    # Parse context-triggered reminders (always show these)
    context_section = extract_section(content, "Context-Triggered Reminders")
    context_reminders = parse_context_reminders(context_section)

    # Format and output
    output = format_output(active_patterns, context_reminders)
    if output:
        print(output)


if __name__ == "__main__":
    main()
