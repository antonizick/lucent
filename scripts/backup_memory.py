#!/usr/bin/env python3
"""
Backup memory folder to private Git repository.

Commits all changes with message "Automated backup by Lucent" and pushes to origin.
Safe to run multiple times — if no changes, commit is skipped.

Usage:
  python3 scripts/backup_memory.py
  Returns 0 on success (commit + push, or nothing to commit)
  Returns 1 on failure (git error)
"""

import subprocess
import sys
import json
import os
import re
from pathlib import Path
from datetime import datetime, date, timedelta

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
HEALTH_CHECK_FILE = LUCENT_ROOT / ".backup_health"

def write_health_check(backup_type: str) -> None:
    """Write health check timestamp for backup verification."""
    try:
        health_data = {}
        if HEALTH_CHECK_FILE.exists():
            with open(HEALTH_CHECK_FILE, "r") as f:
                health_data = json.load(f)

        health_data[backup_type] = datetime.now().isoformat()

        with open(HEALTH_CHECK_FILE, "w") as f:
            json.dump(health_data, f)
    except Exception:
        pass  # Fail silently

def log_to_daily_note(message: str) -> None:
    """Append timestamped message to today's daily note."""
    today = date.today().strftime("%Y-%m-%d")
    note_path = LUCENT_ROOT / "memory" / f"{today}.md"
    timestamp = datetime.now().strftime("%H:%M:%S")

    try:
        with open(note_path, "a") as f:
            f.write(f"\n[{timestamp}] {message}")
    except Exception:
        pass  # Fail silently

def log_to_activity(message: str) -> None:
    """Append timestamped message to activity log."""
    today = date.today().strftime("%Y-%m-%d")
    log_path = LUCENT_ROOT / "ui" / "logs" / f"activity_{today}.log"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] [backup] {message}\n")
    except Exception:
        pass  # Fail silently

def run_cmd(cmd, cwd=None, check=True):
    """Run shell command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False
    )
    return result.returncode, result.stdout, result.stderr

def compress_yesterday_if_needed() -> None:
    """
    Auto-compress yesterday's daily note if it exists and is uncompressed.

    Triggered at day boundary (first backup after midnight UTC).
    Uses archive validation to ensure completeness before compression.
    """
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    daily_note = MEMORY_DIR / f"{yesterday}.md"
    archive_path = MEMORY_DIR / "archive" / f"{yesterday}.md"

    # Check if yesterday's note exists
    if not daily_note.exists():
        return

    # Count lines to determine if compressed (compressed notes are typically < 10 lines)
    try:
        with open(daily_note, 'r') as f:
            note_lines = sum(1 for _ in f)

        # Skip if already compressed (< 10 lines indicates summary)
        if note_lines < 10:
            return

        # Validate archive exists and is complete
        if not archive_path.exists():
            log_to_daily_note(f"[Compression] ERROR: Archive missing for {yesterday}, cannot compress")
            return

        with open(archive_path, 'r') as f:
            archive_lines = sum(1 for _ in f)

        # Ensure archive is complete
        if archive_lines < note_lines:
            # Re-archive first
            import shutil
            shutil.copy2(daily_note, archive_path)
            log_to_daily_note(f"[Compression] Re-archived {yesterday}: {note_lines} lines")

        # Create placeholder that references archive (no manual summary needed)
        summary = f"""## Session {yesterday}

**⚠️ UNSUMMARIZED** — See full details in `memory/archive/{yesterday}.md`

Curator agent must review archive and write comprehensive summary to LTMemory.md Recent Sessions.
**Archive validation:** ✓ Complete ({archive_lines} lines preserved)
"""

        # Overwrite daily note with summary
        with open(daily_note, 'w') as f:
            f.write(summary)

        # Log to activity log (not daily note, to avoid recursive growth)
        log_to_activity(f"Compression: Auto-compressed {yesterday}: {note_lines} → {sum(1 for line in summary.split(chr(10)))} lines. Archive preserved. Awaiting Curator review.")

    except Exception as e:
        log_to_daily_note(f"[Compression] WARNING: Failed to auto-compress {yesterday}: {e}")


def archive_accumulating_daily_note() -> None:
    """
    Archive the current day's accumulating daily note.

    This runs every backup cycle (hourly) to ensure the archive captures
    the growing daily note throughout the day. When compression happens,
    the archive will already be complete, preventing data loss.
    """
    import shutil
    today = date.today().strftime("%Y-%m-%d")
    daily_note = MEMORY_DIR / f"{today}.md"
    archive_path = MEMORY_DIR / "archive" / f"{today}.md"

    if not daily_note.exists():
        return  # No daily note yet

    try:
        # Create archive directory if needed
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy current daily note to archive (overwrites old version)
        shutil.copy2(daily_note, archive_path)

        # Log only if this is a new/growing note (not already archived)
        # Check if archive is being updated (note lines > archive lines)
        try:
            with open(daily_note, 'r') as f:
                daily_lines = sum(1 for _ in f)
            with open(archive_path, 'r') as f:
                archive_lines = sum(1 for _ in f)

            # If archive just became complete or grew, log it
            if daily_lines == archive_lines:
                # Archive now matches daily note—it's complete
                # Silently maintain the invariant: archive_lines >= daily_lines
                pass

        except Exception:
            pass  # Don't fail backup on logging errors

    except Exception as e:
        # Log error but don't fail the backup
        log_to_daily_note(f"Archive update failed: {e}")

def maybe_prune_ltmemory() -> None:
    """
    Auto-prune LTMemory.md if session count exceeds the keep limit.
    Runs on every backup cycle; no-ops when within limit.
    Old sessions move to LTMemory.archive.md (non-destructive).
    """
    ltmemory_path = MEMORY_DIR / "LTMemory.md"
    if not ltmemory_path.exists():
        return
    try:
        import re
        content = ltmemory_path.read_text()
        session_count = len(re.findall(r'^### Session \d{4}-\d{2}-\d{2}', content, re.MULTILINE))

        # Import keep constant from curator
        sys.path.insert(0, str(Path(__file__).parent))
        from curator import SESSIONS_TO_KEEP, prune_sessions

        if session_count > SESSIONS_TO_KEEP:
            kept, archived = prune_sessions(keep_n=SESSIONS_TO_KEEP, dry_run=False)
            log_to_activity(f"LTMemory auto-prune: {session_count} sessions → kept {kept}, archived {archived}")
    except Exception as e:
        log_to_activity(f"LTMemory auto-prune: failed ({e})")


# ---------------------------------------------------------------------------
# Secret-scan guard
# ---------------------------------------------------------------------------
# Root cause of the 2026-05-17 leak: a credential typed into a daily note was
# committed + pushed to the private LucentMemory repo by this very script. This
# guard scans the STAGED diff (newly added lines only) for credential-shaped
# content and refuses to commit/push if any is found. High precision by design —
# it matches secret *values* (high-entropy strings assigned to secret-named keys,
# or known token formats), NOT the mere word "password" — so it won't silently
# block the unattended hourly backup on ordinary note text. Fails OPEN on its own
# errors (defense-in-depth, not the primary control). Override for emergencies:
# LUCENT_BACKUP_ALLOW_SECRETS=1.

_SECRET_KEY_RE = re.compile(
    r'(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|'
    r'private[_-]?key|client[_-]?secret|credential)'
    r'\s*[:=(]\s*[\'"`(]?([^\s\'"`)]{12,})'
)
_KNOWN_TOKEN_RE = re.compile(
    r'(AKIA[0-9A-Z]{16}'                      # AWS access key id
    r'|sk-[A-Za-z0-9]{20,}'                   # OpenAI/Anthropic-style key
    r'|ghp_[A-Za-z0-9]{30,}'                  # GitHub PAT
    r'|xox[baprs]-[A-Za-z0-9-]{10,}'          # Slack token
    r'|-----BEGIN [A-Z ]*PRIVATE KEY-----)'   # private key block
)


def _shannon_entropy(s: str) -> float:
    from collections import Counter
    import math as _m
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * _m.log2(c / n) for c in Counter(s).values())


def _looks_like_secret(value: str) -> bool:
    """High-entropy, mixed-class token — not a word, not a redaction placeholder."""
    v = value.strip().strip('`\'"()')
    if len(v) < 12:
        return False
    if set(v) <= set('*x•.-_'):          # asterisk/placeholder redactions
        return False
    classes = sum([
        any(c.isupper() for c in v),
        any(c.islower() for c in v),
        any(c.isdigit() for c in v),
    ])
    return classes >= 2 and _shannon_entropy(v) >= 3.0


def _mask_for_log(line: str) -> str:
    """Redact long tokens so the alert itself never re-exposes the secret."""
    masked = re.sub(r'[A-Za-z0-9/+=_\-]{10,}',
                    lambda m: m.group(0)[:2] + '…' + '*' * 6, line)
    return masked.strip()[:160]


def scan_staged_for_secrets(cwd: str) -> list:
    """Return masked descriptions of credential-shaped content in the staged diff."""
    code, diff, _ = run_cmd("git diff --cached --unified=0", cwd=cwd)
    if code != 0:
        return []
    findings = []
    for line in diff.splitlines():
        if not line.startswith('+') or line.startswith('+++'):
            continue
        content = line[1:]
        if _KNOWN_TOKEN_RE.search(content):
            findings.append(_mask_for_log(content))
            continue
        m = _SECRET_KEY_RE.search(content)
        if m and _looks_like_secret(m.group(2)):
            findings.append(_mask_for_log(content))
    return findings


def backup_memory() -> int:
    """
    Backup memory folder to Git.

    Returns:
        0 on success, 1 on failure
    """
    if not MEMORY_DIR.exists():
        print(f"✗ Memory directory not found: {MEMORY_DIR}")
        return 1

    print(f"→ Backing up memory folder...")

    # Check if memory/ is a git repository
    code, _, _ = run_cmd("git status", cwd=str(MEMORY_DIR))
    if code != 0:
        print(f"✗ Memory folder is not a Git repository: {MEMORY_DIR}")
        return 1

    # Add all changes
    code, stdout, stderr = run_cmd("git add -A", cwd=str(MEMORY_DIR))
    if code != 0:
        print(f"✗ Failed to stage files: {stderr}")
        return 1

    # Check if there are changes to commit
    code, status, _ = run_cmd("git status --porcelain", cwd=str(MEMORY_DIR))
    if not status.strip():
        print(f"✓ No changes to commit (memory already up-to-date)")
        log_to_activity(f"Backup: No changes (memory already up-to-date)")
        # Still write health check timestamp (verified, no changes needed)
        write_health_check("memory")
        return 0

    # Secret-scan guard — never commit/push credentials to the backup repo.
    if os.environ.get("LUCENT_BACKUP_ALLOW_SECRETS") != "1":
        try:
            findings = scan_staged_for_secrets(str(MEMORY_DIR))
        except Exception as e:
            findings = []  # fail open — a broken scanner must not block backups
            log_to_activity(f"Backup: secret-scan errored, proceeding (fail-open): {e}")
        if findings:
            run_cmd("git reset", cwd=str(MEMORY_DIR))  # unstage; leave files in place
            print(f"✗ ABORTED: {len(findings)} possible secret(s) in staged memory changes — not committing/pushing.")
            for f in findings[:5]:
                print(f"   ⚠ {f}")
            print("   Remove the credential from the offending file, then the next backup resumes.")
            print("   Emergency override: LUCENT_BACKUP_ALLOW_SECRETS=1 (use only if it's a false positive).")
            log_to_activity(f"Backup: ABORTED — {len(findings)} possible secret(s) detected; commit/push skipped")
            return 1

    # Commit
    code, stdout, stderr = run_cmd(
        'git commit -m "Automated backup by Lucent"',
        cwd=str(MEMORY_DIR)
    )
    if code != 0:
        print(f"✗ Commit failed: {stderr}")
        log_to_daily_note(f"Backup FAILED: commit error")
        log_to_activity(f"Backup: FAILED (commit error)")
        return 1

    print(f"✓ Committed: Automated backup by Lucent")
    log_to_activity(f"Backup: Committed (Automated backup by Lucent)")

    # Push to origin
    code, stdout, stderr = run_cmd("git push origin", cwd=str(MEMORY_DIR))
    if code != 0:
        print(f"✗ Push failed: {stderr}")
        log_to_daily_note(f"Backup FAILED: push error")
        log_to_activity(f"Backup: Commit OK, push FAILED")
        return 1

    print(f"✓ Pushed to origin (memory backed up)")
    log_to_activity(f"Backup: Pushed to origin")
    write_health_check("memory")
    return 0

def check_lucent_core() -> None:
    """Check Lucent core repo status and write health check timestamp."""
    print(f"→ Checking Lucent core repo...")
    code, _, _ = run_cmd("git status", cwd=str(LUCENT_ROOT))
    if code == 0:
        print(f"✓ Lucent core repo verified")
        write_health_check("lucent_core")
    else:
        print(f"✗ Lucent core repo check failed")

def main():
    # Step 1: Auto-compress yesterday's note if day boundary crossed (no-op otherwise)
    compress_yesterday_if_needed()

    # Step 2: Archive the accumulating daily note (maintains live archive)
    archive_accumulating_daily_note()

    # Step 3: Auto-prune LTMemory.md if over session limit
    maybe_prune_ltmemory()

    # Step 4: Backup memory folder to git
    exit_code = backup_memory()

    # Step 5: Verify lucent core repo
    check_lucent_core()

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
