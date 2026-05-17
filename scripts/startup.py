#!/usr/bin/env python3
"""
IGNITION Phase 2 — Robust startup orchestrator.

Runs all startup checks in parallel with timeouts and fallbacks:
- Context file validation (parallel with voice box check)
- Voice box health check on ports 8001 + 8002 (with auto-restart fallback)
- Session logger initialization (with /tmp fallback)
- Compression trigger (with timeout)
- Checkpoint write

Usage:
  python3 scripts/startup.py
  python3 scripts/startup.py --json
"""

import sys
import json
import random
import subprocess
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

LUCENT_ROOT = Path(__file__).parent.parent
VOICE_BOX_SPEAK_LOCAL = "http://localhost:8001/speak"
VOICE_BOX_SPEAK_AUTH = "http://localhost:8002/speak"
VOICE_BOX_HEALTH_LOCAL = "http://localhost:8001/services/health"
VOICE_BOX_HEALTH_AUTH = "http://localhost:8002/services/health"
VOICE_BOX_START_CMD = ["bash", "start.sh"]
VOICE_BOX_START_LOG = Path("/tmp/lucent-voice-box.log")

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

READINESS_PLEASANTRIES = [
    "Ready when you are.",
    "All set.",
    "Let's go.",
    "Standing by.",
    "Ready to roll.",
    "What's next?",
    "All systems go.",
    "I'm listening.",
    "What can I do for you?",
    "Fire away.",
    "Ready to work.",
    "At your service.",
    "Fully online.",
    "Locked and loaded.",
    "Ready to assist.",
    "What's on your mind?",
    "I'm ready.",
    "All clear.",
    "Standing at attention.",
    "Good to go.",
    "Systems nominal.",
    "Ready for action.",
    "What shall we tackle?",
    "Await your command.",
    "Ready as ever.",
    "All pistons firing.",
    "Count me in.",
    "Let's make some magic.",
    "Primed and ready.",
    "What's the mission?",
]

REQUIRED_CONTEXT_FILES = [
    "memory/LTMemory.md",
    "memory/lucentIdent.md",
    "memory/userIdent.md",
    "memory/core.md",
]

UNSUMMARIZED_MARKER = LUCENT_ROOT / "memory" / ".unsummarized_sessions.json"


class CheckResult(NamedTuple):
    ok: bool
    reason: str
    fallback_used: bool = False


def log_to_activity(message: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    log_path = LUCENT_ROOT / "memory" / "logs" / f"activity_{today}.log"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] [startup] {message}\n")
    except Exception:
        pass


def log_to_daily_note(message: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    note_path = LUCENT_ROOT / "memory" / f"{today}.md"
    timestamp = datetime.now().strftime("%H:%M:%S")
    try:
        with open(note_path, "a") as f:
            f.write(f"\n[{timestamp}] [startup] {message}")
    except Exception:
        pass


def speak(text: str, timeout: float = 5.0) -> bool:
    """Send text to both voice boxes (8001 + 8002). Returns True if either succeeds."""
    success = False
    for url in [VOICE_BOX_SPEAK_LOCAL, VOICE_BOX_SPEAK_AUTH]:
        try:
            payload = json.dumps({"text": text, "source": "startup"}).encode()
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout):
                success = True
        except Exception:
            pass
    return success


def check_voice_box(port: int = 8001, timeout: float = 3.0) -> CheckResult:
    """Check voice box health on a specific port. Returns (ok, reason)."""
    url = f"http://localhost:{port}/services/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            if "Voice box" in body or resp.status == 200:
                return CheckResult(True, f"Voice box online (port {port})")
            return CheckResult(False, f"Health endpoint returned unexpected response (port {port}, status {resp.status})")
    except urllib.error.URLError as e:
        return CheckResult(False, f"Voice box unreachable on port {port}: {e.reason}")
    except Exception as e:
        return CheckResult(False, f"Voice box check failed on port {port}: {e}")


def check_all_voice_boxes() -> CheckResult:
    """Check both voice box ports (8001 + 8002) in parallel. Both must be online."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(check_voice_box, 8001): 8001,
            executor.submit(check_voice_box, 8002): 8002,
        }
        results = {}
        for future in as_completed(futures, timeout=6):
            port = futures[future]
            results[port] = future.result()

    port_8001_ok = results.get(8001, CheckResult(False, "Timeout")).ok
    port_8002_ok = results.get(8002, CheckResult(False, "Timeout")).ok

    if port_8001_ok and port_8002_ok:
        return CheckResult(True, "Voice boxes online (both 8001 + 8002)")
    reasons = []
    if not port_8001_ok:
        reasons.append(results.get(8001, CheckResult(False, "Unknown")).reason)
    if not port_8002_ok:
        reasons.append(results.get(8002, CheckResult(False, "Unknown")).reason)
    return CheckResult(False, "Voice box offline: " + "; ".join(reasons))


def restart_voice_box(max_wait: float = 20.0) -> CheckResult:
    """Start Piper via ui/start.sh, wait up to max_wait for both ports to come online."""
    try:
        with open(VOICE_BOX_START_LOG, "a") as log_file:
            subprocess.Popen(
                VOICE_BOX_START_CMD,
                cwd=str(LUCENT_ROOT / "ui"),
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
    except Exception as e:
        return CheckResult(False, f"Failed to start voice box: {e}", fallback_used=True)

    deadline = time.time() + max_wait
    while time.time() < deadline:
        result = check_all_voice_boxes()
        if result.ok:
            return CheckResult(True, "Voice boxes restarted successfully (both online)", fallback_used=True)
        time.sleep(1)

    return CheckResult(
        False,
        f"Voice boxes failed to come online within {max_wait}s",
        fallback_used=True,
    )


def ensure_voice_box() -> CheckResult:
    """Check voice boxes; if either offline, try to restart both."""
    result = check_all_voice_boxes()
    if result.ok:
        return result
    log_to_activity("Voice boxes offline — attempting restart")
    restart_result = restart_voice_box()
    return restart_result


def check_context_files() -> CheckResult:
    """Check required context files exist. Returns (ok, missing)."""
    missing = []
    today = date.today().strftime("%Y-%m-%d")
    files = REQUIRED_CONTEXT_FILES + [f"memory/{today}.md"]
    for rel in files:
        if not (LUCENT_ROOT / rel).exists():
            missing.append(rel)
    if len(missing) == 0:
        return CheckResult(True, f"All context files present ({len(files)} files)")
    return CheckResult(False, f"Missing context files: {', '.join(missing)}")


def init_session_logger(timeout: float = 5.0) -> CheckResult:
    """Initialize session logger with /tmp fallback."""
    try:
        result = subprocess.run(
            [sys.executable, str(LUCENT_ROOT / "scripts" / "session_logger.py"), "init"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return CheckResult(True, "Session logger initialized")
        raise RuntimeError(result.stderr.strip() or f"session_logger.py exited {result.returncode}")
    except (subprocess.TimeoutExpired, Exception) as e:
        fallback_log = Path(f"/tmp/lucent_session_{date.today().strftime('%Y%m%d')}.log")
        try:
            with open(fallback_log, "a") as f:
                ts = datetime.now().strftime("%H:%M:%S")
                f.write(f"[{ts}] Session started (fallback log — primary logger failed)\n")
            msg = f"Logger failed, using /tmp fallback: {fallback_log}"
            log_to_activity(f"WARNING: {msg}")
            return CheckResult(False, msg, fallback_used=True)
        except Exception as e2:
            return CheckResult(False, f"Logger and /tmp fallback both failed: {e2}")


def trigger_compression(timeout: float = 10.0) -> CheckResult:
    """Fire backup_memory.py with timeout; non-fatal on failure."""
    try:
        result = subprocess.run(
            [sys.executable, str(LUCENT_ROOT / "scripts" / "backup_memory.py")],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return CheckResult(True, "Compression triggered")
        return CheckResult(False, f"Compression exited {result.returncode} (non-fatal)", fallback_used=False)
    except subprocess.TimeoutExpired:
        return CheckResult(False, f"Compression timed out after {timeout}s (non-fatal)", fallback_used=False)
    except Exception as e:
        return CheckResult(False, f"Compression failed: {e} (non-fatal)", fallback_used=False)


def check_unsummarized_sessions() -> CheckResult:
    """Check for daily notes missing from LTMemory Recent Sessions."""
    try:
        result = subprocess.run(
            ["python3", str(LUCENT_ROOT / "scripts" / "check_unsummarized_sessions.py")],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return CheckResult(True, "Unsummarized check completed")

        data = json.loads(result.stdout)
        count = data.get("count", 0)

        if count > 0:
            # Write marker file for Claude to handle
            unsummarized = data.get("unsummarized", [])
            with open(UNSUMMARIZED_MARKER, "w") as f:
                json.dump(unsummarized, f)
            return CheckResult(True, f"{count} session(s) need summarization")
        else:
            # Clean up marker if no unsummarized sessions
            if UNSUMMARIZED_MARKER.exists():
                UNSUMMARIZED_MARKER.unlink()
            return CheckResult(True, "All sessions summarized")

    except Exception as e:
        return CheckResult(True, f"Unsummarized check: {str(e)}")


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


def write_readiness_marker() -> None:
    """Write marker file to signal startup completion to Claude."""
    try:
        today = date.today().strftime("%Y-%m-%d")
        marker_path = LUCENT_ROOT / "memory" / f".startup_ready_{today}.txt"
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with open(marker_path, "w") as f:
            f.write(f"{timestamp}\nSTARTUP_OK\n")
    except Exception as e:
        log_to_activity(f"Failed to write readiness marker: {e}")


def run(json_mode: bool = False) -> dict:
    """Main orchestrator. Returns dict with status, checks, and diagnostics."""
    if is_already_complete():
        result = {"status": "ALREADY_COMPLETE", "message": "Startup already validated for this session."}
        if json_mode:
            print(json.dumps(result))
        else:
            print("✓ Startup already complete for this session.")
        return result

    pleasantry = random.choice(PLEASANTRIES)
    speak_thread = threading.Thread(target=speak, args=(pleasantry,), daemon=True)
    speak_thread.start()
    print(f"Lucent: {pleasantry}")

    checks = {}
    failures = []
    warnings = []
    fallbacks_used = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        voicebox_future = executor.submit(ensure_voice_box)
        context_future = executor.submit(check_context_files)
        compression_future = executor.submit(trigger_compression)

        try:
            vb_result = voicebox_future.result(timeout=25)
        except FuturesTimeoutError:
            vb_result = CheckResult(False, "Voice box check timed out after 25s")

        try:
            context_result = context_future.result(timeout=5)
        except FuturesTimeoutError:
            context_result = CheckResult(False, "Context file check timed out")

        try:
            compression_result = compression_future.result(timeout=12)
        except FuturesTimeoutError:
            compression_result = CheckResult(False, "Compression timed out")

    logger_result = init_session_logger()
    unsummarized_result = check_unsummarized_sessions()

    speak_thread.join(timeout=6)

    checks["voice_box"] = {"ok": vb_result.ok, "reason": vb_result.reason}
    checks["context_files"] = {"ok": context_result.ok, "reason": context_result.reason}
    checks["compression"] = {"ok": compression_result.ok, "reason": compression_result.reason}
    checks["session_logger"] = {"ok": logger_result.ok, "reason": logger_result.reason}
    checks["unsummarized_sessions"] = {"ok": unsummarized_result.ok, "reason": unsummarized_result.reason}

    if vb_result.fallback_used:
        fallbacks_used.append("voice_box_restart")
    if logger_result.fallback_used:
        fallbacks_used.append("session_logger_tmp")
    if compression_result.fallback_used:
        fallbacks_used.append("compression_timeout")

    if not vb_result.ok:
        failures.append(f"Voice box: {vb_result.reason}")
        log_to_activity(f"FAILURE: {vb_result.reason}")
        log_to_daily_note(f"STARTUP FAILURE: {vb_result.reason}")

    if not context_result.ok:
        warnings.append(f"Context: {context_result.reason}")
        log_to_activity(f"WARNING: {context_result.reason}")
        log_to_daily_note(f"STARTUP WARNING: {context_result.reason}")

    if not compression_result.ok:
        if not compression_result.ok and "timed out" in compression_result.reason:
            warnings.append(f"Compression: {compression_result.reason}")
            log_to_activity(f"WARNING: {compression_result.reason}")
        else:
            log_to_activity(f"Compression: {compression_result.reason}")

    if not logger_result.ok and not logger_result.fallback_used:
        failures.append(f"Logger: {logger_result.reason}")
        log_to_activity(f"FAILURE: {logger_result.reason}")
        log_to_daily_note(f"STARTUP FAILURE: {logger_result.reason}")
    elif logger_result.fallback_used:
        log_to_activity(f"FALLBACK: {logger_result.reason}")
        log_to_daily_note(f"STARTUP FALLBACK: {logger_result.reason}")

    if "need" in unsummarized_result.reason.lower():
        log_to_activity(f"NOTICE: {unsummarized_result.reason}")

    degraded = bool(failures or warnings or fallbacks_used)
    status = "STARTUP_DEGRADED" if degraded else "STARTUP_OK"

    write_checkpoint_today(degraded)

    result = {
        "status": status,
        "checks": checks,
        "pleasantry": pleasantry,
    }
    if failures:
        result["failures"] = failures
    if warnings:
        result["warnings"] = warnings
    if fallbacks_used:
        result["fallbacks"] = fallbacks_used

    status_line = f"{status} — voice_box={vb_result.ok}, context={context_result.ok}, logger={logger_result.ok}, compression={compression_result.ok}"
    log_to_activity(status_line)

    if json_mode:
        print(json.dumps(result, indent=2))
    else:
        if status == "STARTUP_OK":
            print("✓ Startup validation complete — all checks passed.")
            print()  # Blank line for visual separation
            readiness = random.choice(READINESS_PLEASANTRIES)
            speak_thread_ready = threading.Thread(target=speak, args=(readiness,), daemon=True)
            speak_thread_ready.start()
            print(f"→ {readiness}")  # Arrow prefix to signal readiness
            write_readiness_marker()
        else:
            print(f"⚠ Startup validation complete with issues.")
            if failures:
                for f in failures:
                    print(f"  ✗ {f}")
            if warnings:
                for w in warnings:
                    print(f"  ⚠ {w}")
            if fallbacks_used:
                for fb in fallbacks_used:
                    print(f"  → {fb}")
            print(f"  Continuing in degraded mode. Check activity log for details.")

    return result


def main():
    json_mode = "--json" in sys.argv
    result = run(json_mode=json_mode)
    sys.exit(0 if result["status"] in ("STARTUP_OK", "ALREADY_COMPLETE") else 1)


if __name__ == "__main__":
    main()
