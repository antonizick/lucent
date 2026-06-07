#!/usr/bin/env python3
"""
Track skill usage when Claude reads a SKILL.md directly via the Read tool.

CLAUDE.md documents loading skill bodies by reading memory/skills/<name>/SKILL.md
with the Read tool — which bypasses skills.py's bump_use() counter (only wired to
the `skills.py view` CLI path). This hook closes that gap so the Insights "Top
used" stats reflect real consultations, not just CLI test runs.

Called by PostToolUse hook (matcher: Read). Reads the tool call JSON from stdin,
and if the file read was a memory/skills/<slug>/SKILL.md, bumps that skill's
usage counter directly (bypassing view_skill's full-text read).

Usage: python3 scripts/skill_read_tracker.py   (stdin: hook JSON payload)
"""

import json
import re
import sys
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent

SKILL_PATH_RE = re.compile(r"memory/skills/([^/]+)/SKILL\.md$")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    if payload.get("tool_name") != "Read":
        return

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    match = SKILL_PATH_RE.search(file_path.replace("\\", "/"))
    if not match:
        return

    slug = match.group(1)

    sys.path.insert(0, str(LUCENT_ROOT / "scripts"))
    try:
        import skills as sk
    except Exception:
        return

    if not (LUCENT_ROOT / "memory" / "skills" / slug / "SKILL.md").exists():
        return

    try:
        sk.bump_use(slug)
    except Exception:
        pass  # Silent fail — never block the read


if __name__ == "__main__":
    main()
