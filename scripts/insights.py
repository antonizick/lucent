#!/usr/bin/env python3
"""
NERO Phase 5 — Insights: self-improvement loop health dashboard.

Shows the NERO loop working: memory corpus growth, skill library state,
reflection loop statistics, and curator activity. Gives Nick visibility
into whether the system is learning and staying lean.

Usage:
  python3 scripts/insights.py               # full report
  python3 scripts/insights.py --brief       # one-page summary
  python3 scripts/insights.py --json        # machine-readable JSON
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
SKILLS_DIR = MEMORY_DIR / "skills"
NERO_DIR = MEMORY_DIR / ".nero"
AUTO_MEMORY_DIR = Path.home() / ".claude/projects/-home-nick-dev-lucent/memory"


# ---------------------------------------------------------------------------
# Data collectors
# ---------------------------------------------------------------------------

def _memory_corpus() -> dict:
    """Sizes of each memory tier."""
    def _count(path: Path) -> dict:
        if not path.exists():
            return {"lines": 0, "size_kb": 0}
        try:
            t = path.read_text(encoding="utf-8")
            return {"lines": len(t.splitlines()), "size_kb": round(len(t.encode()) / 1024, 1)}
        except Exception:
            return {"lines": 0, "size_kb": 0}

    # Hard caps for LTMemory (10 sessions = ~240 lines, cap at 500 lines or 100KB)
    ltmemory_line_limit = 500
    ltmemory_size_limit_kb = 100

    lt = _count(MEMORY_DIR / "LTMemory.md")
    lt_arch = _count(MEMORY_DIR / "LTMemory.archive.md")

    # Auto-memory files
    am_count = 0
    am_lines = 0
    if AUTO_MEMORY_DIR.exists():
        for p in AUTO_MEMORY_DIR.glob("*.md"):
            if p.name != "MEMORY.md":
                am_count += 1
                try:
                    am_lines += len(p.read_text().splitlines())
                except Exception:
                    pass

    # Daily notes (last 7)
    daily_count = 0
    daily_lines = 0
    from datetime import date, timedelta
    today = date.today()
    for i in range(7):
        p = MEMORY_DIR / f"{today - timedelta(days=i)}.md"
        if p.exists():
            daily_count += 1
            try:
                daily_lines += len(p.read_text().splitlines())
            except Exception:
                pass

    # Recall index
    index_chunks = 0
    idx = MEMORY_DIR / ".recall_index.json"
    if idx.exists():
        try:
            index_chunks = len(json.loads(idx.read_text()).get("chunks", []))
        except Exception:
            pass

    # Limits (based on curator rules)
    daily_notes_limit_days = 7
    daily_notes_utilization = round(100 * daily_count / daily_notes_limit_days) if daily_notes_limit_days > 0 else 0

    # LTMemory utilization (whichever limit is hit first)
    ltmemory_line_util = round(100 * lt["lines"] / ltmemory_line_limit) if ltmemory_line_limit > 0 else 0
    ltmemory_size_util = round(100 * lt["size_kb"] / ltmemory_size_limit_kb) if ltmemory_size_limit_kb > 0 else 0
    ltmemory_utilization = max(ltmemory_line_util, ltmemory_size_util)  # Take the higher utilization

    return {
        "ltmemory": {
            "lines": lt["lines"],
            "size_kb": lt["size_kb"],
            "path": str(MEMORY_DIR / "LTMemory.md"),
            "line_limit": ltmemory_line_limit,
            "size_limit_kb": ltmemory_size_limit_kb,
            "utilization_pct": ltmemory_utilization
        },
        "ltmemory_archive": {"lines": lt_arch["lines"], "size_kb": lt_arch["size_kb"], "path": str(MEMORY_DIR / "LTMemory.archive.md")},
        "auto_memory_files": am_count,
        "auto_memory_lines": am_lines,
        "auto_memory_path": str(AUTO_MEMORY_DIR),
        "daily_notes_7d": daily_count,
        "daily_lines_7d": daily_lines,
        "daily_notes_path": str(MEMORY_DIR),
        "daily_notes_limit_days": daily_notes_limit_days,
        "daily_notes_utilization_pct": daily_notes_utilization,
        "recall_index_chunks": index_chunks,
    }


def _skill_stats() -> dict:
    sys.path.insert(0, str(LUCENT_ROOT / "scripts"))
    try:
        import skills as sk
        all_skills = sk.list_skills(include_archived=False)
        usage = sk._load_usage()
        protected = sk.load_protected()
        archive_count = 0
        if (SKILLS_DIR / ".archive").exists():
            archive_count = sum(
                1 for p in (SKILLS_DIR / ".archive").iterdir()
                if p.is_dir() and (p / "SKILL.md").exists()
            )
        by_state: dict[str, int] = {}
        for s in all_skills:
            by_state[s["state"]] = by_state.get(s["state"], 0) + 1
        active_slugs = {s["slug"] for s in all_skills}
        top_used = sorted(
            [(slug, u.get("use_count", 0), u.get("last_used", ""))
             for slug, u in usage.items()
             if u.get("use_count", 0) > 0 and slug in active_slugs],
            key=lambda x: x[1], reverse=True
        )[:5]
        # Build full skills list with usage data
        protected_set = set(protected) if isinstance(protected, list) else protected
        skills_list = []
        for skill in all_skills:
            u = usage.get(skill["slug"], {})
            skill_path = SKILLS_DIR / skill["slug"]
            skills_list.append({
                "slug": skill["slug"],
                "name": skill.get("name", skill["slug"]),
                "description": skill.get("description", ""),
                "state": skill.get("state", ""),
                "protected": skill["slug"] in protected_set,
                "use_count": u.get("use_count", 0),
                "last_used": u.get("last_used", ""),
                "path": str(skill_path),
            })
        return {
            "total_live": len(all_skills),
            "by_state": by_state,
            "archived": archive_count,
            "protected_count": len(protected),
            "skills_path": str(SKILLS_DIR),
            "top_used": [{"slug": s, "uses": u, "last": l[:10] if l else ""} for s, u, l in top_used],
            "all_skills": sorted(skills_list, key=lambda s: (-s["use_count"], s["slug"])),
        }
    except Exception as e:
        return {"error": str(e)}


def _reflection_stats() -> dict:
    try:
        proposals_path = NERO_DIR / "proposals.jsonl"
        worker_log = NERO_DIR / "worker.log"
        config_path = NERO_DIR / "config.json"
        state_path = NERO_DIR / "state.json"

        cfg = {}
        if config_path.exists():
            cfg = json.loads(config_path.read_text())
        state = {}
        if state_path.exists():
            state = json.loads(state_path.read_text())

        proposals: list[dict] = []
        if proposals_path.exists():
            for line in proposals_path.read_text().splitlines():
                if line.strip():
                    try:
                        proposals.append(json.loads(line))
                    except Exception:
                        pass

        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for p in proposals:
            s = p.get("status", "?")
            by_status[s] = by_status.get(s, 0) + 1
            t = p.get("action", {}).get("type", "?")
            by_type[t] = by_type.get(t, 0) + 1

        # Parse worker log for gate stats
        gate_yes = gate_no = 0
        if worker_log.exists():
            for ln in worker_log.read_text().splitlines():
                if "gate=NO" in ln:
                    gate_no += 1
                elif "proposed " in ln or "auto " in ln:
                    gate_yes += 1

        total_turns = gate_yes + gate_no
        hit_rate = f"{100*gate_yes//total_turns}%" if total_turns > 0 else "n/a"

        return {
            "enabled": cfg.get("enabled", True),
            "mode": cfg.get("mode", "propose"),
            "last_run": (state.get("last_run_at") or "never")[:19],
            "proposals_total": len(proposals),
            "by_status": by_status,
            "by_type": by_type,
            "gate_yes": gate_yes,
            "gate_no": gate_no,
            "gate_hit_rate": hit_rate,
        }
    except Exception as e:
        return {"error": str(e)}


def _curator_stats() -> dict:
    try:
        report = NERO_DIR / "curator_report.md"
        last_run = "never"
        if report.exists():
            text = report.read_text()
            for line in text.splitlines():
                if line.startswith("# NERO Curator Report"):
                    last_run = line.split("—", 1)[-1].strip()[:19]
                    break
        ltm_arch_sessions = 0
        lta = MEMORY_DIR / "LTMemory.archive.md"
        if lta.exists():
            ltm_arch_sessions = lta.read_text().count("### Session")
        lt_live_sessions = 0
        lt = MEMORY_DIR / "LTMemory.md"
        if lt.exists():
            lt_live_sessions = lt.read_text().count("### Session")

        # Limits and utilization
        ltmemory_session_limit = 10  # KEEP_RECENT_SESSIONS from skill_curator.py
        ltmemory_utilization = round(100 * lt_live_sessions / ltmemory_session_limit) if ltmemory_session_limit > 0 else 0

        daily_notes_limit = 7  # Days tracked

        return {
            "last_run": last_run,
            "ltmemory_live_sessions": lt_live_sessions,
            "ltmemory_live_sessions_limit": ltmemory_session_limit,
            "ltmemory_utilization_pct": ltmemory_utilization,
            "ltmemory_archive_sessions": ltm_arch_sessions,
            "daily_notes_limit_days": daily_notes_limit,
            "ltmemory_path": str(MEMORY_DIR / "LTMemory.md"),
            "ltmemory_archive_path": str(MEMORY_DIR / "LTMemory.archive.md"),
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _bar(val: int, max_val: int = 20) -> str:
    filled = min(val, max_val)
    return "█" * filled + "░" * (max_val - filled)


def format_full(corpus: dict, skills: dict, reflection: dict, curator: dict) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"╔══════════════════════════════════════════════════════╗",
        f"║        NERO Self-Improvement Insights — {now}  ║",
        f"╚══════════════════════════════════════════════════════╝",
        "",
        "━━━ Memory Corpus ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  LTMemory.md        {corpus['ltmemory']['lines']:>5} lines  {corpus['ltmemory']['size_kb']:>6} KB",
        f"  LTMemory.archive   {corpus['ltmemory_archive']['lines']:>5} lines  {corpus['ltmemory_archive']['size_kb']:>6} KB",
        f"  Auto-memory files  {corpus['auto_memory_files']:>5} files  {corpus['auto_memory_lines']:>6} lines",
        f"  Daily notes (7d)   {corpus['daily_notes_7d']:>5} files  {corpus['daily_lines_7d']:>6} lines",
        f"  Recall index       {corpus['recall_index_chunks']:>5} chunks",
        "",
        "━━━ Skill Library ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if "error" not in skills:
        by_state = skills.get("by_state", {})
        lines.append(f"  Live skills        {skills['total_live']:>5}  (protected: {skills['protected_count']})")
        lines.append(f"  Archived           {skills['archived']:>5}")
        if by_state:
            state_str = "  ".join(f"{k}:{v}" for k, v in sorted(by_state.items()))
            lines.append(f"  By state           {state_str}")
        if skills.get("top_used"):
            lines.append("  Top used:")
            for s in skills["top_used"]:
                lines.append(f"    {s['slug']:<30} {s['uses']} uses  last: {s['last']}")
        else:
            lines.append("  (no usage data yet)")
    else:
        lines.append(f"  error: {skills['error']}")
    lines.append("")
    lines.append("━━━ Reflection Loop ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if "error" not in reflection:
        status = "✓ enabled" if reflection["enabled"] else "✗ disabled"
        lines.append(f"  Status             {status}  ({reflection['mode']} mode)")
        lines.append(f"  Last run           {reflection['last_run']}")
        lines.append(f"  Gate hit rate      {reflection['gate_hit_rate']}  ({reflection['gate_yes']} yes / {reflection['gate_no']} no)")
        lines.append(f"  Proposals total    {reflection['proposals_total']}")
        if reflection["by_status"]:
            st_str = "  ".join(f"{k}:{v}" for k, v in sorted(reflection["by_status"].items()))
            lines.append(f"  By status          {st_str}")
        if reflection["by_type"]:
            ty_str = "  ".join(f"{k}:{v}" for k, v in sorted(reflection["by_type"].items()))
            lines.append(f"  By type            {ty_str}")
    else:
        lines.append(f"  error: {reflection['error']}")
    lines.append("")
    lines.append("━━━ Curator ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if "error" not in curator:
        lines.append(f"  Last run           {curator['last_run']}")
        lines.append(f"  LTMemory sessions  {curator['ltmemory_live_sessions']} live  +  {curator['ltmemory_archive_sessions']} archived")
    else:
        lines.append(f"  error: {curator['error']}")
    lines.append("")
    lines.append("━━━ Commands ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("  python3 scripts/reflect.py review          — review pending proposals")
    lines.append("  python3 scripts/skill_curator.py run       — dry-run curator (all jobs)")
    lines.append("  python3 scripts/skill_curator.py run --live— apply curator changes")
    lines.append("  python3 scripts/memory_index.py build      — rebuild recall index")
    lines.append("  python3 scripts/skills.py list             — list skill library")
    return "\n".join(lines)


def format_brief(corpus: dict, skills: dict, reflection: dict, curator: dict) -> str:
    pending = reflection.get("by_status", {}).get("pending", 0)
    hit_rate = reflection.get("gate_hit_rate", "n/a")
    lines = [
        f"NERO snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  memory  : LTMemory {corpus['ltmemory']['lines']}L  index {corpus['recall_index_chunks']} chunks",
        f"  skills  : {skills.get('total_live', '?')} live  {skills.get('archived', 0)} archived",
        f"  reflect : {reflection.get('mode','?')} mode  gate {hit_rate}  {pending} pending",
        f"  curator : last {curator.get('last_run','never')}  {curator.get('ltmemory_live_sessions','?')} live sessions",
    ]
    if pending:
        lines.append(f"  ⚡ {pending} proposal(s) awaiting review — `reflect.py review`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    brief = "--brief" in sys.argv
    as_json = "--json" in sys.argv

    corpus = _memory_corpus()
    skills = _skill_stats()
    reflection = _reflection_stats()
    curator = _curator_stats()

    if as_json:
        print(json.dumps({
            "corpus": corpus,
            "skills": skills,
            "reflection": reflection,
            "curator": curator,
        }, indent=2, default=str))
    elif brief:
        print(format_brief(corpus, skills, reflection, curator))
    else:
        print(format_full(corpus, skills, reflection, curator))


if __name__ == "__main__":
    main()
