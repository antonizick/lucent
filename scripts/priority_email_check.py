#!/usr/bin/env python3
"""
Priority email check for Lucent.

Queries email database for high-priority messages and outputs alert if any found.
- Checks emails with priority_score >= 7.0
- Filters to last 8 days
- Outputs top 3 with sender + subject
- Silent if no priority emails found

Usage: python3 scripts/priority_email_check.py
Output: Goes to stdout for hook injection (or silent)
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
EMAIL_DB = LUCENT_ROOT / "ui" / "data" / "emails.db"


def get_priority_emails():
    """Query database for priority emails from last 8 days."""
    if not EMAIL_DB.exists():
        return []

    try:
        conn = sqlite3.connect(str(EMAIL_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Calculate cutoff date (8 days ago)
        cutoff_date = (datetime.now() - timedelta(days=8)).isoformat()

        # Query for priority emails (score >= 7.0)
        # Assuming table: emails, columns: received_at, priority_score, sender, subject
        query = """
            SELECT sender, subject, priority_score, received_at
            FROM emails
            WHERE priority_score >= 7.0
            AND received_at >= ?
            ORDER BY priority_score DESC, received_at DESC
            LIMIT 3
        """

        cursor.execute(query, (cutoff_date,))
        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    except Exception:
        # Silent fail — if database doesn't exist or query fails, output nothing
        return []


def format_output(emails):
    """Format priority emails for output."""
    if not emails:
        # No priority emails — output nothing
        return ""

    # Format alert
    count = len(emails)
    output = f"[Lucent] ⚠ PRIORITY EMAILS ({count}):\n"

    for email in emails:
        sender = email.get("sender", "Unknown")
        subject = email.get("subject", "(No subject)")
        score = email.get("priority_score", "?")
        output += f"  - {sender} | {subject[:60]} (score: {score})\n"

    return output.rstrip()


def main():
    """Main entry point."""
    emails = get_priority_emails()
    output = format_output(emails)

    if output:
        print(output)


if __name__ == "__main__":
    main()
