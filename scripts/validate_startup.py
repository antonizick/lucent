#!/usr/bin/env python3
"""
Startup ritual validation gate.

Orchestrates all startup checks: voice box health, context file existence,
session logger initialization, checkpoint write. Sends a varied pleasantry
before validation runs so Nick knows the system is working.

Usage:
  python3 scripts/validate_startup.py
  python3 scripts/validate_startup.py --json
"""

import sys
import json
import random
import subprocess
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
VOICE_BOX_SPEAK = "http://localhost:8001/speak"
VOICE_BOX_HEALTH = "http://localhost:8001/services/health"

PLEASANTRIES = [
    "Give me just a moment...",
    "Hold on while I get my bearings...",
    "One sec, loading context...",
    "Gathering my thoughts...",
    "Let me get oriented...",
    "Just a moment while I catch up...",
    "Bear with me briefly...",
    "Getting up to speed...",
    "One moment while I sync...",
    "Just pulling things together...",
]

REQUIRED_CONTEXT_FILES = [
    "memory/LTMemory.md",
    "memory/lucentIdent.md",
    "memory/userIdent.md",
    "memory/core.md",
]


def log_to_activity(message: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    log_path = LUCENT_ROOT / "memory" / "logs" / f"activity_{today}.log"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] [startup_validator] {message}\n")
    except Exception:
        pass


def log_to_daily_note(message: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    note_path = LUCENT_ROOT / "memory" / f"{today}.md"
    timestamp = datetime.now().strftime("%H:%M:%S")
    try:
        with open(note_path, "a") as f:
            f.write(f"\n[{timestamp}] [startup_validator] {message}")
    except Exception:
        pass


def speak(text: str) -> bool:
    """Send text to voice box. Returns True on success."""
    try:
        payload = json.dumps({"text": text, "source": "startup_validator"}).encode()
        req = urllib.request.Request(
            VOICE_BOX_SPEAK,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


def check_voice_box() -> tuple[bool, str]:
    """Check voice box health. Returns (ok, reason)."""
    try:
        req = urllib.request.Request(VOICE_BOX_HEALTH, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode()
            if "Voice box" in body or resp.status == 200:
                return True, "Voice box online"
            return False, f"Health endpoint returned unexpected response (status {resp.status})"
    except urllib.error.URLError as e:
        return False, f"Voice box unreachable: {e.reason}"
    except Exception as e:
        return False, f"Voice box check failed: {e}"


def check_context_files() -> tuple[bool, list[str]]:
    """Check required context files exist. Returns (all_ok, list_of_missing)."""
    missing = []
    today = date.today().strftime("%Y-%m-%d")
    files = REQUIRED_CONTEXT_FILES + [f"memory/{today}.md"]
    for rel in files:
        if not (LUCENT_ROOT / rel).exists():
            missing.append(rel)
    return len(missing) == 0, missing


def run_session_logger() -> tuple[bool, str]:
    """Run session_logger.py init. Returns (ok, reason)."""
    try:
        result = subprocess.run(
            [sys.executable, str(LUCENT_ROOT / "scripts" / "session_logger.py"), "init"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True, "Session logger initialized"
        reason = (result.stderr.strip() or result.stdout.strip() or "non-zero exit")
        return False, f"session_logger.py exited {result.returncode}: {reason}"
    except subprocess.TimeoutExpired:
        return False, "session_logger.py timed out after 15s"
    except Exception as e:
        return False, f"session_logger.py failed to run: {e}"


def write_checkpoint_today(degraded: bool) -> None:
    """Write today's checkpoint via verify_startup helpers."""
    try:
        sys.path.insert(0, str(LUCENT_ROOT / "scripts"))
        from verify_startup import compute_context_hash, write_checkpoint
        h = compute_context_hash(LUCENT_ROOT)
        write_checkpoint(LUCENT_ROOT, h, model=None, compressed_yesterday=not degraded)
    except Exception as e:
        log_to_activity(f"Checkpoint write failed: {e}")
        log_to_daily_note(f"Checkpoint write failed: {e}")


def is_already_complete() -> bool:
    """Return True if today's startup checkpoint is still valid."""
    try:
        sys.path.insert(0, str(LUCENT_ROOT / "scripts"))
        from verify_startup import (
            compute_context_hash,
            read_checkpoint,
            is_checkpoint_valid,
        )
        h = compute_context_hash(LUCENT_ROOT)
        cp = read_checkpoint(LUCENT_ROOT)
        return is_checkpoint_valid(cp, h, lucent_root=LUCENT_ROOT)
    except Exception:
        return False


def run(json_mode: bool = False) -> dict:
    # Short-circuit if already validated this session
    if is_already_complete():
        result = {"status": "ALREADY_COMPLETE", "message": "Startup already validated for this session."}
        if json_mode:
            print(json.dumps(result))
        else:
            print("✓ Startup already complete for this session.")
        return result

    # Send pleasantry immediately (voice + stdout) before any checks
    pleasantry = random.choice(PLEASANTRIES)
    voice_ok = speak(pleasantry)
    print(f"Lucent: {pleasantry}")

    checks = {}
    failures = []
    warnings = []

    # --- Voice box check (blocking gate) ---
    vb_ok, vb_reason = check_voice_box()
    checks["voice_box"] = {"ok": vb_ok, "reason": vb_reason}
    if not vb_ok:
        msg = f"Voice box OFFLINE — {vb_reason}"
        failures.append(msg)
        log_to_activity(f"DEGRADED: {msg}")
        log_to_daily_note(f"STARTUP DEGRADED: {msg}")
        print(f"⚠ {msg}")
    else:
        log_to_activity(vb_reason)

    # --- Context file check ---
    files_ok, missing_files = check_context_files()
    checks["context_files"] = {"ok": files_ok, "missing": missing_files}
    if not files_ok:
        msg = f"Missing context files: {', '.join(missing_files)}"
        warnings.append(msg)
        log_to_activity(f"WARNING: {msg}")
        log_to_daily_note(f"STARTUP WARNING: {msg}")
        print(f"⚠ {msg}")

    # --- Session logger ---
    sl_ok, sl_reason = run_session_logger()
    checks["session_logger"] = {"ok": sl_ok, "reason": sl_reason}
    if not sl_ok:
        msg = f"Session logger failed — {sl_reason}"
        warnings.append(msg)
        log_to_activity(f"WARNING: {msg}")
        log_to_daily_note(f"STARTUP WARNING: {msg}")
        print(f"⚠ {msg}")
    else:
        log_to_activity(sl_reason)

    # --- Determine overall status ---
    degraded = bool(failures or warnings)
    status = "STARTUP_DEGRADED" if degraded else "STARTUP_OK"

    # Write checkpoint (degraded or not)
    write_checkpoint_today(degraded)

    # Build result
    result = {
        "status": status,
        "checks": checks,
        "pleasantry": pleasantry,
        "voice_sent": voice_ok,
    }
    if failures:
        result["failures"] = failures
    if warnings:
        result["warnings"] = warnings

    # Log final status
    status_line = f"{status} — checks: voice_box={vb_ok}, context_files={files_ok}, session_logger={sl_ok}"
    log_to_activity(status_line)
    if degraded:
        log_to_daily_note(f"STARTUP {status}: {status_line}")

    # Print summary
    if json_mode:
        print(json.dumps(result, indent=2))
    else:
        if status == "STARTUP_OK":
            print("✓ Startup validation complete — all checks passed.")
        else:
            print(f"⚠ Startup validation complete with issues — see warnings above.")
            print(f"  Continuing in degraded mode. Check activity log for details.")

    return result


def main():
    json_mode = "--json" in sys.argv
    result = run(json_mode=json_mode)
    sys.exit(0 if result["status"] in ("STARTUP_OK", "ALREADY_COMPLETE") else 1)


if __name__ == "__main__":
    main()
