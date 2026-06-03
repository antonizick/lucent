#!/usr/bin/env python3
"""
NERO Phase 2 — Skill library management.

Skills are procedural knowledge packages: class-level instructions for how
to do categories of work for Nick. Distinct from agents/ (personas) and
memory/ (facts/preferences).

Structure:
  memory/skills/
    .usage.json          # usage tracking
    .archive/            # archived skills (never deleted)
    <skill-name>/
      SKILL.md           # required — name, description, instructions, pitfalls
      references/        # session-specific detail, knowledge banks
      templates/         # starter files to copy+modify
      scripts/           # re-runnable actions

Usage:
  python3 scripts/skills.py list              # list all with descriptions
  python3 scripts/skills.py view <name>       # show full skill + support files
  python3 scripts/skills.py bump <name>       # increment use counter
  python3 scripts/skills.py status            # usage + library stats
  python3 scripts/skills.py summary           # compact listing for SessionStart bundle
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LUCENT_DIR = Path(__file__).parent.parent
SKILLS_DIR = LUCENT_DIR / "memory" / "skills"
USAGE_FILE = SKILLS_DIR / ".usage.json"
PROTECTED_FILE = SKILLS_DIR / ".protected"
ARCHIVE_DIR = SKILLS_DIR / ".archive"

STATE_ACTIVE = "active"
STATE_STALE = "stale"
STATE_ARCHIVED = "archived"
STATE_PINNED = "pinned"


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def _skill_dirs() -> list[Path]:
    """Return all non-archived skill directories, sorted alphabetically."""
    if not SKILLS_DIR.exists():
        return []
    return sorted(
        p for p in SKILLS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name != "archive"
    )


def _parse_frontmatter(skill_md: str) -> dict:
    """
    Extract name, description, class, state from a SKILL.md body.
    Falls back to empty strings if fields are absent.
    """
    info = {"name": "", "description": "", "class": "", "state": STATE_ACTIVE}
    for line in skill_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not info["name"]:
            info["name"] = stripped[2:].strip()
        elif stripped.startswith("**Description:**"):
            info["description"] = stripped[len("**Description:**"):].strip()
        elif stripped.startswith("**Class:**"):
            info["class"] = stripped[len("**Class:**"):].strip()
        elif stripped.startswith("**State:**"):
            info["state"] = stripped[len("**State:**"):].strip().lower()
    return info


def _read_skill_dir(skill_dir: Path) -> dict | None:
    """
    Parse a skill directory. Returns info dict or None if malformed.
    """
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        return None
    try:
        body = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    info = _parse_frontmatter(body)
    info["slug"] = skill_dir.name
    if not info["name"]:
        info["name"] = skill_dir.name

    # Support files
    support = {}
    for subdir in ("references", "templates", "scripts"):
        sub = skill_dir / subdir
        if sub.exists():
            files = sorted(f.name for f in sub.iterdir() if f.is_file())
            if files:
                support[subdir] = files
    info["support"] = support

    return info


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------

def _load_usage() -> dict:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_usage(data: dict) -> None:
    USAGE_FILE.write_text(json.dumps(data, indent=2, sort_keys=True))


def bump_use(skill_slug: str) -> None:
    """Increment the use counter and update last_used timestamp for a skill."""
    usage = _load_usage()
    entry = usage.get(skill_slug, {"use_count": 0, "last_used": None, "created_at": None})
    entry["use_count"] = int(entry.get("use_count", 0)) + 1
    entry["last_used"] = datetime.now(timezone.utc).isoformat()
    if not entry.get("created_at"):
        entry["created_at"] = entry["last_used"]
    usage[skill_slug] = entry
    _save_usage(usage)


def _get_usage(skill_slug: str) -> dict:
    return _load_usage().get(skill_slug, {"use_count": 0, "last_used": None})


def get_usage(skill_slug: str) -> dict:
    """Public accessor — use_count, last_used, created_at for a skill."""
    return _load_usage().get(
        skill_slug, {"use_count": 0, "last_used": None, "created_at": None}
    )


# ---------------------------------------------------------------------------
# Protection + lifecycle (used by the curator — never deletes)
# ---------------------------------------------------------------------------

def load_protected() -> set:
    """Slugs that the curator must never archive or consolidate.

    Protected = listed in .protected OR State: pinned in SKILL.md. Core seed
    skills live in .protected; reflection-created skills are curatable by default.
    """
    protected = set()
    if PROTECTED_FILE.exists():
        for line in PROTECTED_FILE.read_text().splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                protected.add(s)
    return protected


def is_protected(skill_slug: str) -> bool:
    if skill_slug in load_protected():
        return True
    info = _read_skill_dir(SKILLS_DIR / skill_slug)
    return bool(info and info.get("state") == STATE_PINNED)


def is_curatable(skill_slug: str) -> bool:
    """A skill the curator may act on: exists, not protected, not pinned."""
    return (SKILLS_DIR / skill_slug / "SKILL.md").exists() and not is_protected(skill_slug)


def set_state(skill_slug: str, state: str) -> bool:
    """Rewrite the **State:** line in a skill's SKILL.md. Returns success."""
    skill_md = SKILLS_DIR / skill_slug / "SKILL.md"
    if not skill_md.exists():
        return False
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines()
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith("**State:**"):
                lines[i] = f"**State:** {state}"
                found = True
                break
        if not found:
            return False
        skill_md.write_text("\n".join(lines) + "\n")
        return True
    except Exception:
        return False


def archive_skill(skill_slug: str) -> tuple[bool, str]:
    """Move a skill directory into .archive/ (recoverable). Never deletes."""
    import shutil
    if is_protected(skill_slug):
        return False, f"{skill_slug} is protected — refusing to archive"
    src = SKILLS_DIR / skill_slug
    if not (src / "SKILL.md").exists():
        return False, f"skill not found: {skill_slug}"
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dest = ARCHIVE_DIR / skill_slug
    if dest.exists():
        dest = ARCHIVE_DIR / f"{skill_slug}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    try:
        set_state(skill_slug, STATE_ARCHIVED)
        shutil.move(str(src), str(dest))
        return True, f"archived {skill_slug} → .archive/{dest.name}"
    except Exception as e:
        return False, f"archive failed: {e}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_skills(include_archived: bool = False) -> list[dict]:
    """
    Return list of skill info dicts for all non-archived skills.
    Each dict: slug, name, description, class, state, use_count, last_used, support.
    """
    results = []
    usage = _load_usage()
    for skill_dir in _skill_dirs():
        info = _read_skill_dir(skill_dir)
        if not info:
            continue
        if not include_archived and info["state"] == STATE_ARCHIVED:
            continue
        u = usage.get(skill_dir.name, {})
        info["use_count"] = u.get("use_count", 0)
        info["last_used"] = u.get("last_used")
        results.append(info)
    return results


def view_skill(skill_slug: str) -> str | None:
    """
    Return the full text content of a skill (SKILL.md + any support files listed).
    Returns None if skill not found.
    """
    skill_dir = SKILLS_DIR / skill_slug
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        return None

    parts = [skill_md_path.read_text(encoding="utf-8")]

    for subdir in ("references", "templates", "scripts"):
        sub = skill_dir / subdir
        if sub.exists():
            for f in sorted(sub.iterdir()):
                if f.is_file():
                    try:
                        content = f.read_text(encoding="utf-8")
                        parts.append(f"\n--- {subdir}/{f.name} ---\n{content}")
                    except OSError:
                        pass

    bump_use(skill_slug)
    return "\n\n".join(parts)


def get_skills_summary() -> str:
    """
    Compact listing of all active skills for the SessionStart identity bundle.
    Shows name + description only (progressive disclosure — full bodies load on demand).
    """
    skills = list_skills()
    if not skills:
        return ""

    lines = ["[Lucent] === SKILLS LIBRARY ===",
             "[Lucent] Procedural knowledge packages. Read SKILL.md on demand for full instructions.",
             ""]
    for s in skills:
        state_tag = f" [{s['state']}]" if s["state"] != STATE_ACTIVE else ""
        lines.append(f"  {s['slug']}{state_tag}")
        if s["description"]:
            lines.append(f"    {s['description']}")
    lines.append("")
    lines.append(f"[Lucent] {len(skills)} skill(s). Load any with: read memory/skills/<name>/SKILL.md")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_list():
    skills = list_skills()
    if not skills:
        print("No skills found in memory/skills/")
        return
    for s in skills:
        state_tag = f" [{s['state']}]" if s["state"] != STATE_ACTIVE else ""
        support_tag = f" ({', '.join(s['support'].keys())})" if s["support"] else ""
        print(f"\n{s['slug']}{state_tag}{support_tag}")
        print(f"  {s['description'] or '(no description)'}")
        if s["use_count"]:
            print(f"  uses: {s['use_count']}  last: {s['last_used'][:10] if s['last_used'] else 'never'}")


def _cmd_view(slug: str):
    content = view_skill(slug)
    if content is None:
        print(f"Skill not found: {slug}", file=sys.stderr)
        sys.exit(1)
    print(content)


def _cmd_bump(slug: str):
    skill_dir = SKILLS_DIR / slug
    if not (skill_dir / "SKILL.md").exists():
        print(f"Skill not found: {slug}", file=sys.stderr)
        sys.exit(1)
    bump_use(slug)
    usage = _get_usage(slug)
    print(f"Bumped {slug}: use_count={usage['use_count']}")


def _cmd_status():
    skills = list_skills()
    usage = _load_usage()
    print(f"Skills total  : {len(skills)}")
    print(f"Skills dir    : {SKILLS_DIR}")
    if skills:
        print("\nUsage:")
        for s in sorted(skills, key=lambda x: x["use_count"], reverse=True):
            bar = "█" * min(s["use_count"], 20)
            last = s["last_used"][:10] if s["last_used"] else "never"
            print(f"  {s['slug']:<32} {bar:<20} {s['use_count']} uses  last: {last}")


def _cmd_summary():
    print(get_skills_summary())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        _cmd_list()
    elif cmd == "view":
        if len(sys.argv) < 3:
            print("Usage: skills.py view <slug>", file=sys.stderr)
            sys.exit(1)
        _cmd_view(sys.argv[2])
    elif cmd == "bump":
        if len(sys.argv) < 3:
            print("Usage: skills.py bump <slug>", file=sys.stderr)
            sys.exit(1)
        _cmd_bump(sys.argv[2])
    elif cmd == "status":
        _cmd_status()
    elif cmd == "summary":
        _cmd_summary()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
