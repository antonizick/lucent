#!/usr/bin/env python3
"""
Scan for uncompressed daily notes.

A note is considered uncompressed if it exceeds COMPRESS_THRESHOLD lines.
Compressed notes are short (1-2 paragraphs); uncompressed notes are raw session
logs and can be thousands of lines.

Usage:
  python3 scripts/scan_uncompressed.py           # scan last 7 days
  python3 scripts/scan_uncompressed.py --days 14  # scan last 14 days
  python3 scripts/scan_uncompressed.py --json     # JSON output

Exit: 0 if nothing to compress, 1 if compression needed
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import date, timedelta

LUCENT_ROOT = Path(__file__).parent.parent
COMPRESS_THRESHOLD = 200  # lines; below this = already compressed


def scan(days: int = 7) -> list:
    today = date.today()
    needs_work = []

    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        note_path = LUCENT_ROOT / "memory" / f"{d.isoformat()}.md"
        if not note_path.exists():
            continue
        content = note_path.read_text()
        lines = content.count('\n')
        if lines > COMPRESS_THRESHOLD:
            archive_path = LUCENT_ROOT / "memory" / "archive" / f"{d.isoformat()}.md"
            needs_work.append({
                "date": d.isoformat(),
                "lines": lines,
                "archived": archive_path.exists(),
                "is_yesterday": (i == 1),
            })

    return needs_work


def main():
    parser = argparse.ArgumentParser(description="Scan for uncompressed daily notes")
    parser.add_argument("--days", type=int, default=7, help="Days to scan (default: 7)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    results = scan(args.days)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print(f"✓ All notes compressed (last {args.days} days)")
        else:
            for item in results:
                archived = "archived" if item["archived"] else "no archive yet"
                yesterday = " (yesterday)" if item["is_yesterday"] else ""
                print(f"⚠ {item['date']}: {item['lines']} lines | {archived}{yesterday}")

    sys.exit(1 if results else 0)


if __name__ == "__main__":
    main()
