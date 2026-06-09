#!/usr/bin/env python3
"""
Context-triggered TODO surface.

Reads the user prompt from stdin JSON ({"prompt": "..."}),
checks for project/work/idea keywords, and prints open TODO items
when triggered. Designed to run in lucent-init.sh before each response.
Fails silently on any error — never blocks the hook.
"""

import json
import sys
from datetime import date
from pathlib import Path

LUCENT_DIR = Path(__file__).parent.parent
TODO_PATH = LUCENT_DIR / "memory" / "TODO.json"

TRIGGER_KEYWORDS = [
    "project", "projects", "work on", "working on", "idea", "ideas",
    "todo", "to-do", "to do", "task", "tasks", "backlog",
    "priority", "priorities", "what should", "what can", "what next",
    "next up", "what to", "ambitions", "goals", "build something",
    "coding", "implement", "feature", "things to do", "things we can",
]


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        prompt = payload.get("prompt", "").lower()
    except Exception:
        return

    if not any(kw in prompt for kw in TRIGGER_KEYWORDS):
        return

    if not TODO_PATH.exists():
        return

    try:
        data = json.loads(TODO_PATH.read_text())
    except Exception:
        return

    today = date.today().isoformat()
    open_items = []
    for item in data.get("items", []):
        status = item.get("status", "open")
        cryo_until = item.get("cryo_until") or ""
        if status in ("archived", "done"):
            continue
        if status == "cryo" and cryo_until and cryo_until > today:
            continue
        open_items.append(item)

    if not open_items:
        return

    pri_order = {"H": 0, "M": 1, "L": 2, None: 3}
    open_items.sort(key=lambda i: (pri_order.get(i.get("priority"), 3), i.get("created", "")))

    print("[Lucent] === TODO — OPEN ITEMS (context-triggered) ===")
    for item in open_items:
        pri = item.get("priority") or "—"
        tags = item.get("tags", [])
        tag_str = f" [{', '.join(tags[:2])}]" if tags else ""
        thawed = " (thawed)" if item.get("status") == "cryo" else ""
        print(f"  [{pri}] {item['title']}{tag_str}{thawed}")


if __name__ == "__main__":
    main()
