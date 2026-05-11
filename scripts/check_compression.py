#!/usr/bin/env python3
"""
Compression status utility for Lucent startup ritual.

Usage:
  python3 scripts/check_compression.py status       # Check if compression is needed
  python3 scripts/check_compression.py mark-done    # Mark compression as complete (after Curator finishes)
"""

import sys
from pathlib import Path
from verify_startup import needs_compression, mark_compression_complete, compression_marker_exists, read_checkpoint

LUCENT_ROOT = Path(__file__).parent.parent

def cmd_status():
    """Check if compression is needed."""
    yesterday = needs_compression(LUCENT_ROOT)

    if yesterday:
        print(f"⚠ Compression needed for: {yesterday}.md")
        print(f"  Invoke Curator: python3 scripts/invoke_agent.py curator 'Compress {yesterday}.md'")
        print(f"  Or in Claude: invoke Curator agent to compress")
        sys.exit(1)
    else:
        print("✓ No compression needed (yesterday already compressed or first day)")
        sys.exit(0)

def cmd_mark_done():
    """Mark compression as complete."""
    yesterday = needs_compression(LUCENT_ROOT)

    if yesterday:
        if compression_marker_exists(LUCENT_ROOT, yesterday):
            mark_compression_complete(LUCENT_ROOT)
            print(f"✓ Compression marked complete for {yesterday}.md")
            sys.exit(0)
        else:
            print(f"✗ Compression marker not found in today's note")
            print(f"  Expected: 'Compressed {yesterday} at session start'")
            sys.exit(1)
    else:
        # No compression needed; just mark it
        mark_compression_complete(LUCENT_ROOT)
        print("✓ Compression status updated (no compression needed)")
        sys.exit(0)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/check_compression.py [status|mark-done]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        cmd_status()
    elif cmd == "mark-done":
        cmd_mark_done()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
