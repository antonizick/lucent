#!/usr/bin/env python3
"""
NERO Phase 5 — PreCompact hook: memory durability guard.

Fires before Claude Code compacts the transcript. Injects a concise
block of must-keep facts into the compaction context so compaction
never silently drops durable knowledge.

Prints to stdout → Claude Code injects it into the compaction summary prompt.
Exits 0 always (failures are silent no-ops — compaction must never block).

What we preserve:
  - Current priorities from LTMemory.md
  - Active NERO state (pending proposals, mode, reflection health)
  - Available skills listing
  - Today's daily note key entries (last 30 lines)
  - Active reminders (via existing script)
"""

import sys
from datetime import datetime
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"


def _read_section(path: Path, start_marker: str, end_markers: list[str], max_lines: int = 30) -> str:
    """Extract lines from a file between start_marker and the next end_marker."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return ""
    idx = text.find(start_marker)
    if idx == -1:
        return ""
    section = text[idx:]
    for em in end_markers:
        stop = section.find(em, len(start_marker))
        if stop != -1:
            section = section[:stop]
    lines = section.strip().splitlines()
    return "\n".join(lines[:max_lines])


def main():
    try:
        lines = ["[NERO PreCompact — must-keep context for compaction summary]", ""]

        # 1. Current priorities
        lt = MEMORY_DIR / "LTMemory.md"
        priorities = _read_section(lt, "## Current Priorities", ["## ", "### "], max_lines=25)
        if priorities:
            lines.append("=== Current Priorities ===")
            lines.append(priorities)
            lines.append("")

        # 2. NERO self-improvement state
        try:
            sys.path.insert(0, str(LUCENT_ROOT / "scripts"))
            from reflect import pending_count, load_config, load_state
            cfg = load_config()
            st = load_state()
            nero_lines = [
                "=== NERO Self-Improvement State ===",
                f"reflection: {'enabled' if cfg.get('enabled') else 'disabled'}, mode={cfg.get('mode','propose')}",
                f"pending proposals: {pending_count()}",
                f"last reflection: {(st.get('last_run_at') or 'never')[:19]}",
            ]
            # Skill count
            from skills import list_skills
            skills = list_skills()
            nero_lines.append(f"skill library: {len(skills)} skills")
            lines.extend(nero_lines)
            lines.append("")
        except Exception:
            pass

        # 3. Skills listing (names only)
        try:
            from skills import get_skills_summary
            summary = get_skills_summary()
            if summary:
                lines.append("=== Available Skills ===")
                # Just the names, not the long form
                for ln in summary.splitlines():
                    if ln.startswith("  ") and not ln.startswith("   "):
                        lines.append(ln)
                lines.append("")
        except Exception:
            pass

        # 4. Today's daily note tail (last 25 lines)
        today = datetime.now().strftime("%Y-%m-%d")
        note = MEMORY_DIR / f"{today}.md"
        if note.exists():
            try:
                tail = note.read_text(encoding="utf-8").splitlines()[-25:]
                lines.append("=== Today's Session Log (last 25 lines) ===")
                lines.extend(tail)
                lines.append("")
            except Exception:
                pass

        output = "\n".join(lines).strip()
        if output:
            print(output)
    except Exception:
        pass  # Never block compaction


if __name__ == "__main__":
    main()
