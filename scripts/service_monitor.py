#!/usr/bin/env python3
"""
Lucent Service Monitor — checks all systemd-managed services every 5 minutes
and auto-restarts any that are failed or inactive.

Services monitored:
  lucent-voice-box  — voice box UI (port 8001), HTTP health check
  lucent-monitor    — Discord instruction monitor
  discord-bot       — Discord bot
  ollama            — Local inference engine (port 11434)

Recovery strategy: systemctl restart <service> via sudo (passwordless).
Logs to activity log and stdout (captured by cron).
"""

import os
import subprocess
import sys
import time
from datetime import datetime

import requests

# ── Config ────────────────────────────────────────────────────

SERVICES = [
    {
        "unit": "lucent-voice-box",
        "label": "Voice Box",
        "health_url": "http://localhost:8001/services/health",
    },
    {
        "unit": "lucent-monitor",
        "label": "Discord Monitor",
    },
    {
        "unit": "discord-bot",
        "label": "Discord Bot",
    },
    {
        "unit": "ollama",
        "label": "Ollama",
        "health_url": "http://localhost:11434/api/tags",
    },
]

ACTIVITY_LOG_DIR = "/home/nick/dev/lucent/ui/logs"
MAX_RESTART_WAIT = 8   # seconds to wait after restart before re-checking

# ── Logging ───────────────────────────────────────────────────

def _log(component: str, level: str, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{component}] {level}: {msg}"
    print(line, flush=True)
    try:
        os.makedirs(ACTIVITY_LOG_DIR, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_path = os.path.join(ACTIVITY_LOG_DIR, f"activity_{today}.log")
        with open(log_path, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Service checks ────────────────────────────────────────────

def is_active(unit: str) -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def is_healthy_http(url: str) -> bool:
    try:
        r = requests.get(url, timeout=3)
        return r.status_code < 500
    except Exception:
        return False


def restart_unit(unit: str, label: str) -> bool:
    _log("service-monitor", "NOTICE", f"Restarting {label} ({unit})…")
    try:
        r = subprocess.run(
            ["sudo", "-n", "systemctl", "restart", unit],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            _log("service-monitor", "ERROR",
                 f"systemctl restart {unit} failed: {r.stderr.strip()}")
            return False
        time.sleep(MAX_RESTART_WAIT)
        if is_active(unit):
            _log("service-monitor", "NOTICE", f"{label} restarted successfully")
            return True
        else:
            _log("service-monitor", "ERROR",
                 f"{label} still not active after restart")
            return False
    except Exception as e:
        _log("service-monitor", "ERROR", f"Exception restarting {unit}: {e}")
        return False


# ── Main check loop ───────────────────────────────────────────

def check_all() -> bool:
    all_ok = True
    repaired = []
    failed = []

    for svc in SERVICES:
        unit = svc["unit"]
        label = svc["label"]
        health_url = svc.get("health_url")

        # Step 1: systemd state
        if not is_active(unit):
            _log("service-monitor", "ALERT", f"{label} ({unit}) is not active — restarting")
            ok = restart_unit(unit, label)
            (repaired if ok else failed).append(label)
            all_ok = all_ok and ok
            continue

        # Step 2 (optional): HTTP health check for services that expose one
        if health_url and not is_healthy_http(health_url):
            _log("service-monitor", "WARN",
                 f"{label} is running but not responding at {health_url} — restarting")
            ok = restart_unit(unit, label)
            (repaired if ok else failed).append(label)
            all_ok = all_ok and ok

    if repaired:
        _log("service-monitor", "NOTICE", f"Auto-repaired: {', '.join(repaired)}")
    if failed:
        _log("service-monitor", "ERROR", f"Could not repair: {', '.join(failed)}")

    return all_ok


if __name__ == "__main__":
    try:
        ok = check_all()
        sys.exit(0 if ok else 1)
    except Exception as e:
        _log("service-monitor", "FATAL", f"Unexpected error: {e}")
        sys.exit(1)
