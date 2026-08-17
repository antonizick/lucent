#!/usr/bin/env python3
"""
Shared notify/marker helpers for auto_summarize.py and skill_curator.py.

Voice + daily-note entries only fire when a curator process actually did
something — no noise on silent hourly no-ops.
"""

import json
import urllib.request
from datetime import date, datetime
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
LTMEMORY_PATH = MEMORY_DIR / "LTMemory.md"
VOICE_URL = "http://localhost:8001/speak"


def speak(text: str) -> None:
    try:
        req = urllib.request.Request(
            VOICE_URL,
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # voice box down shouldn't break the curator run


def append_daily_note(text: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    daily_note = MEMORY_DIR / f"{today}.md"
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"\n[{ts}] {text}\n"
    try:
        with open(daily_note, "a") as f:
            f.write(entry)
    except Exception:
        pass


def last_curator_run() -> date | None:
    if not LTMEMORY_PATH.exists():
        return None
    for line in LTMEMORY_PATH.read_text().splitlines():
        if "Last Curator Run:" in line:
            try:
                d = line.split("Last Curator Run:")[1].strip().split("*")[0].split("—")[0].strip()
                return datetime.strptime(d, "%Y-%m-%d").date()
            except Exception:
                return None
    return None


def bump_last_curator_run() -> None:
    if not LTMEMORY_PATH.exists():
        return
    content = LTMEMORY_PATH.read_text()
    today = date.today().strftime("%Y-%m-%d")
    lines = content.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if "Last Curator Run:" in line:
            prefix, _, rest = line.partition("Last Curator Run:")
            # keep everything after the date (e.g. " — updated by...") intact
            after_date = rest.strip().split(" ", 1)
            tail = " " + after_date[1] if len(after_date) > 1 else ""
            lines[i] = f"{prefix}Last Curator Run: {today}**{tail}\n" if rest.strip().startswith("2") else line
            # simplest safe rewrite: replace just the date token
            import re
            lines[i] = re.sub(r"Last Curator Run: \d{4}-\d{2}-\d{2}", f"Last Curator Run: {today}", line)
            break
    LTMEMORY_PATH.write_text("".join(lines))


def check_staleness_and_alarm(max_days: int = 9) -> None:
    """Loud alert if it's been too long since a real curator write. Call this
    from the hourly auto_summarize cron so a broken dependency (missing Ollama
    model, Ollama down, etc.) surfaces instead of failing silently into /tmp."""
    last = last_curator_run()
    if last is None:
        return
    days = (date.today() - last).days
    if days > max_days:
        msg = (
            f"Curator alert: LTMemory hasn't had a real update in {days} days "
            f"(last: {last.isoformat()}, threshold: {max_days}). "
            f"Automated summarization or curation is likely broken — check "
            f"/tmp/auto-summarize.log and Ollama health."
        )
        speak(msg)
        append_daily_note(f"⚠ {msg}")
