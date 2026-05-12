#!/usr/bin/env python3
"""
Startup ritual verification and enforcement.

Ensures the startup ritual has fired (context loaded, identity established).
Sets/checks a checkpoint to verify ritual completion. If checkpoint is missing
or stale, forces a full ritual execution before proceeding.

Usage:
  from verify_startup import ensure_startup_ritual
  context = ensure_startup_ritual(project_root="/home/nick/dev/lucent")
"""

import sys
import json
import hashlib
import os
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, Tuple

def compute_context_hash(lucent_root: Path) -> str:
    """Compute hash of all context files to detect changes."""
    hasher = hashlib.sha256()

    files_to_hash = [
        "core.md",
        "lucentIdent.md",
        "userIdent.md",
        "LTMemory.md",
    ]

    # Add today's daily note
    today = date.today().strftime("%Y-%m-%d")
    files_to_hash.append(f"memory/{today}.md")

    for filename in files_to_hash:
        path = lucent_root / filename
        if path.exists():
            hasher.update(path.read_bytes())

    return hasher.hexdigest()

def get_checkpoint_path(lucent_root: Path) -> Path:
    """Get path to the ritual checkpoint file."""
    return lucent_root / "memory" / ".ritual_checkpoint.json"

def read_checkpoint(lucent_root: Path) -> Optional[dict]:
    """Read the ritual checkpoint. Returns None if doesn't exist or is invalid."""
    checkpoint_path = get_checkpoint_path(lucent_root)
    if not checkpoint_path.exists():
        return None

    try:
        return json.loads(checkpoint_path.read_text())
    except (json.JSONDecodeError, IOError):
        return None

def needs_compression(lucent_root: Path) -> Optional[str]:
    """
    Check if yesterday's daily note exists and needs compression.

    Returns:
        Date string (YYYY-MM-DD) if compression is needed, None otherwise
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    yesterday_path = lucent_root / "memory" / f"{yesterday.strftime('%Y-%m-%d')}.md"

    return yesterday.strftime("%Y-%m-%d") if yesterday_path.exists() else None

def compression_marker_exists(lucent_root: Path, yesterday_date: str) -> bool:
    """Check if today's note contains the compression marker for yesterday."""
    today = date.today().strftime("%Y-%m-%d")
    today_path = lucent_root / "memory" / f"{today}.md"

    if not today_path.exists():
        return False

    content = today_path.read_text()
    marker = f"Compressed {yesterday_date} at session start"
    return marker in content

def is_checkpoint_valid(checkpoint: dict, current_hash: str, current_model: Optional[str] = None, lucent_root: Optional[Path] = None) -> bool:
    """Check if checkpoint is valid and not stale."""
    if not checkpoint:
        return False

    # Check hash matches (context files unchanged)
    if checkpoint.get("context_hash") != current_hash:
        return False

    # Check if model changed (if tracking model)
    if current_model and checkpoint.get("model") != current_model:
        return False

    # Check if checkpoint is from today (per-day validity)
    checkpoint_date = checkpoint.get("date")
    today = date.today().isoformat()
    if checkpoint_date != today:
        return False

    # NEW: Check if compression was done (if needed)
    if lucent_root:
        yesterday_date = needs_compression(lucent_root)
        if yesterday_date:
            # Compression was needed; verify it was done
            if not checkpoint.get("compressed_yesterday"):
                return False
            # Double-check the marker exists in today's note
            if not compression_marker_exists(lucent_root, yesterday_date):
                return False

    return True

def write_checkpoint(lucent_root: Path, context_hash: str, model: Optional[str] = None, compressed_yesterday: bool = False) -> None:
    """Write/update the ritual checkpoint."""
    checkpoint_path = get_checkpoint_path(lucent_root)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "date": date.today().isoformat(),
        "context_hash": context_hash,
        "model": model,
        "compressed_yesterday": compressed_yesterday,
        "version": 2
    }

    checkpoint_path.write_text(json.dumps(checkpoint, indent=2))

def load_context_files(lucent_root: Path) -> str:
    """Load all context files needed for startup ritual."""
    context_parts = []

    # Core identity files
    for filename in ["core.md", "lucentIdent.md", "userIdent.md", "LTMemory.md"]:
        path = lucent_root / filename
        if path.exists():
            content = path.read_text()
            context_parts.append(f"=== {filename} ===\n{content}")

    # Today's daily note
    today = date.today().strftime("%Y-%m-%d")
    daily_note_path = lucent_root / "memory" / f"{today}.md"
    if daily_note_path.exists():
        content = daily_note_path.read_text()
        context_parts.append(f"=== TODAY'S DAILY NOTE ({today}) ===\n{content}")

    return "\n\n".join(context_parts)

def ensure_startup_ritual(
    lucent_root: Optional[Path] = None,
    model_name: Optional[str] = None,
    force: bool = False
) -> Tuple[str, bool, Optional[str]]:
    """
    Verify startup ritual has fired. If not, load context and return it.

    Args:
        lucent_root: Root directory of Lucent project (auto-detected if None)
        model_name: Current model name (for checkpoint comparison)
        force: Force ritual execution even if checkpoint is valid

    Returns:
        Tuple of (context_string, ritual_was_executed, yesterday_date_if_compression_needed)
        If ritual was executed, prepend context_string to system prompt.
        If ritual already ran, context_string is empty.
        If compression is needed, third element contains yesterday's date.
    """
    # Auto-detect Lucent root if not provided
    if lucent_root is None:
        script_dir = Path(__file__).parent
        lucent_root = script_dir.parent

    lucent_root = Path(lucent_root)

    # Check if compression is needed
    yesterday_date = needs_compression(lucent_root)

    # Compute current context hash
    current_hash = compute_context_hash(lucent_root)

    # Check existing checkpoint
    checkpoint = read_checkpoint(lucent_root)
    checkpoint_valid = is_checkpoint_valid(checkpoint, current_hash, model_name, lucent_root)

    if checkpoint_valid and not force:
        # Ritual already fired and is still valid
        return "", False, None

    # Ritual needs to fire (checkpoint missing, stale, or forced)
    context = load_context_files(lucent_root)

    # Mark compression as done if no compression needed, or let caller handle it
    compressed = not bool(yesterday_date)  # Mark as done if no compression needed
    write_checkpoint(lucent_root, current_hash, model_name, compressed_yesterday=compressed)

    return context, True, yesterday_date

def mark_compression_complete(lucent_root: Path) -> None:
    """
    Mark yesterday's compression as complete in the checkpoint.

    Call this after Curator finishes compressing yesterday's note.
    Verifies the compression marker exists in today's note before updating checkpoint.
    """
    lucent_root = Path(lucent_root)
    yesterday_date = needs_compression(lucent_root)

    if yesterday_date and compression_marker_exists(lucent_root, yesterday_date):
        # Marker exists; update checkpoint
        checkpoint = read_checkpoint(lucent_root)
        if checkpoint:
            checkpoint["compressed_yesterday"] = True
            checkpoint_path = get_checkpoint_path(lucent_root)
            checkpoint_path.write_text(json.dumps(checkpoint, indent=2))
    elif not yesterday_date:
        # No compression needed; mark as done anyway
        checkpoint = read_checkpoint(lucent_root)
        if checkpoint:
            checkpoint["compressed_yesterday"] = True
            checkpoint_path = get_checkpoint_path(lucent_root)
            checkpoint_path.write_text(json.dumps(checkpoint, indent=2))

def augment_system_prompt(system_prompt: str, additional_context: str) -> str:
    """Prepend additional context to system prompt."""
    if not additional_context:
        return system_prompt

    return f"{additional_context}\n\n---\n\n{system_prompt}"

def cli_check(lucent_root: Path) -> None:
    """Check-only mode: validate checkpoint, write nothing. Exit 1 if ritual needed."""
    from pathlib import Path

    current_hash = compute_context_hash(lucent_root)
    checkpoint = read_checkpoint(lucent_root)
    checkpoint_valid = is_checkpoint_valid(checkpoint, current_hash, lucent_root=lucent_root)

    yesterday = needs_compression(lucent_root)

    if checkpoint_valid:
        print("RITUAL OK")
        if yesterday and not compression_marker_exists(lucent_root, yesterday):
            print(f"⚠ Needs compression: {yesterday}")
        sys.exit(0)
    else:
        print("RITUAL NEEDED")
        print("Execute startup ritual steps before responding:")
        print(f"  lucent_root={lucent_root}")
        if yesterday:
            print(f"  compression_needed={yesterday}")
        if not checkpoint:
            print("  reason=no_checkpoint")
        elif checkpoint.get("date") != date.today().isoformat():
            print(f"  reason=stale_checkpoint ({checkpoint.get('date')})")
            print(f"  today={date.today().isoformat()}")
        elif checkpoint.get("context_hash") != current_hash:
            print("  reason=context_changed")
        elif not checkpoint.get("compressed_yesterday", False) and yesterday:
            print("  reason=compression_pending")
        sys.exit(1)


def cli_mark_complete(lucent_root: Path, model: Optional[str] = None) -> None:
    """Mark the startup ritual as complete in the checkpoint."""
    import hashlib

    current_hash = compute_context_hash(lucent_root)
    yesterday = needs_compression(lucent_root)
    compressed = not bool(yesterday)

    if yesterday:
        if compression_marker_exists(lucent_root, yesterday):
            compressed = True
        else:
            print(f"⚠ Warning: {yesterday} compression marker not found in today's note")

    write_checkpoint(lucent_root, current_hash, model, compressed_yesterday=compressed)
    print(f"✓ Ritual checkpoint written (compressed_yesterday={compressed})")
    sys.exit(0)


def main():
    """CLI entry point with argparse."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Startup ritual verification and enforcement.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["check", "mark-complete", "run"],
        default="run",
        help="Command to run (default: run)",
    )
    parser.add_argument(
        "-p", "--project-root",
        type=Path,
        default=None,
        help="Root of the Lucent project (default: auto-detect)",
    )
    parser.add_argument(
        "-m", "--model",
        type=str,
        default=os.environ.get("OPENCODE_MODEL"),
        help="Model name for checkpoint tracking (default: $OPENCODE_MODEL)",
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force ritual execution even if checkpoint is valid",
    )

    args = parser.parse_args()

    lucent_root = args.project_root
    if lucent_root is None:
        lucent_root = Path(__file__).parent.parent

    if args.command == "check":
        cli_check(lucent_root)
    elif args.command == "mark-complete":
        cli_mark_complete(lucent_root, args.model)
    else:
        # run (default)
        context, executed, compression_needed = ensure_startup_ritual(
            lucent_root, args.model, force=args.force
        )
        if executed:
            print("✓ Startup ritual executed")
            if compression_needed:
                print(f"⚠ Compression needed for: {compression_needed}")
            print("✓ Ready to proceed")
        else:
            print("✓ Startup ritual already valid (checkpoint OK)")
        sys.exit(0)


if __name__ == "__main__":
    main()
