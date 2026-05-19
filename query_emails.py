#!/usr/bin/env python3
"""
Query emails from the Lucent email database.

Usage:
    python3 query_emails.py              # Show all emails
    python3 query_emails.py --limit 10   # Show last 10 emails
    python3 query_emails.py --sender abc@example.com  # Filter by sender
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path so we can import email module
parent_dir = str(Path(__file__).parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from src.lucent_email.config import load_config
from src.lucent_email.db import EmailDatabase


def format_table(emails):
    """Format emails as an ASCII table."""
    if not emails:
        print("No emails found.")
        return

    # Column widths
    ts_width = 19  # "YYYY-MM-DD HH:MM"
    sender_width = 30
    subject_width = 40
    sample_width = 50

    # Header
    header = f"{'TIMESTAMP':<{ts_width}} {'SENDER':<{sender_width}} {'SUBJECT':<{subject_width}} {'SAMPLE':<{sample_width}}"
    divider = "=" * (ts_width + sender_width + subject_width + sample_width + 3)

    print(divider)
    print(header)
    print(divider)

    # Rows
    for email in emails:
        # Format timestamp
        if email.timestamp:
            ts = email.timestamp.strftime("%Y-%m-%d %H:%M")
        else:
            ts = "Unknown"

        # Truncate and pad columns
        sender = (email.from_addr or "Unknown")[:sender_width - 1]
        sender = sender.ljust(sender_width)

        subject = (email.subject or "(no subject)")[:subject_width - 1]
        subject = subject.ljust(subject_width)

        # Get sample from snippet (first part of body)
        snippet = email.snippet or ""
        sample = snippet[:sample_width - 1]
        sample = sample.ljust(sample_width)

        print(f"{ts:<{ts_width}} {sender} {subject} {sample}")

    print(divider)
    print(f"Total: {len(emails)} email(s)")


def main():
    parser = argparse.ArgumentParser(description="Query emails from Lucent database")
    parser.add_argument("--limit", type=int, default=100, help="Maximum emails to return (default: 100)")
    parser.add_argument("--sender", type=str, help="Filter by sender email address")
    parser.add_argument("--folder", type=str, help="Filter by folder (e.g., Inbox, INBOX.Sent)")
    parser.add_argument("--unread", action="store_true", help="Show only unread emails")
    args = parser.parse_args()

    try:
        config = load_config()
        db = EmailDatabase(config.database.path)

        # Get all emails
        all_emails = db.list_emails(limit=args.limit * 2)  # Get more to filter

        # Apply filters
        filtered = all_emails

        if args.sender:
            filtered = [e for e in filtered if args.sender.lower() in (e.from_addr or "").lower()]

        if args.folder:
            filtered = [e for e in filtered if e.folder == args.folder]

        if args.unread:
            filtered = [e for e in filtered if not e.read]

        # Limit results
        filtered = filtered[:args.limit]

        # Display
        format_table(filtered)

        db.close()

    except FileNotFoundError as e:
        print(f"Error: Email database not found at {config.database.path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
