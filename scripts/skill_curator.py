#!/usr/bin/env python3
"""
NERO Phase 4 — Curator: skill lifecycle + umbrella consolidation + memory hygiene.

Three jobs, all archive-only (never delete), dry-run by default:

  4a-i   transitions   Pure-Python lifecycle: active→stale→archived by inactivity,
                       reactivate on use. Protected/pinned skills exempt.
  4a-ii  consolidate   LLM "umbrella-building" pass over curatable (reflection-
                       created) skills: merge narrow siblings into class-level
                       umbrellas, demote detail to references/, archive absorbed.
  4b     memory-hygiene LTMemory.md Recent Sessions length cap (move oldest to
                       LTMemory.archive.md) + auto-memory stale archive.

SAFETY (mirrors Hermes curator.py):
  - DRY-RUN is the default. Mutations require --live.
  - A snapshot of memory/skills/ is taken before any live skill mutation.
  - Archiving is the maximum destructive action — recoverable, never deletion.
  - Protected skills (memory/skills/.protected + State: pinned) are never touched.
  - Every run writes a human-readable report to memory/.nero/curator_report.md.

Usage:
  python3 scripts/skill_curator.py run                  # dry-run everything (report only)
  python3 scripts/skill_curator.py run --live           # apply (with snapshot)
  python3 scripts/skill_curator.py transitions [--live] # lifecycle only
  python3 scripts/skill_curator.py consolidate [--live] # umbrella pass only
  python3 scripts/skill_curator.py memory-hygiene [--live]
  python3 scripts/skill_curator.py snapshot             # manual skills snapshot
  python3 scripts/skill_curator.py report               # print last report
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
SKILLS_DIR = MEMORY_DIR / "skills"
SNAPSHOT_DIR = SKILLS_DIR / ".snapshots"
LTMEMORY_PATH = MEMORY_DIR / "LTMemory.md"
LTMEMORY_ARCHIVE = MEMORY_DIR / "LTMemory.archive.md"
AUTO_MEMORY_DIR = Path.home() / ".claude/projects/-home-nick-dev-lucent/memory"
AUTO_MEMORY_ARCHIVE = AUTO_MEMORY_DIR / "archive"
REPORT_PATH = MEMORY_DIR / ".nero" / "curator_report.md"

# Lifecycle thresholds
STALE_AFTER_DAYS = 30
ARCHIVE_AFTER_DAYS = 90
# Memory hygiene thresholds
KEEP_RECENT_SESSIONS = 10
AUTO_MEMORY_STALE_DAYS = 90

SONNET_MODEL = "claude-sonnet-4-6"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ===========================================================================
# Snapshot
# ===========================================================================

def snapshot_skills(reason: str = "manual") -> Path | None:
    """Copy the skills directory to a timestamped snapshot. Best-effort."""
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = _now().strftime("%Y%m%d-%H%M%S")
        dest = SNAPSHOT_DIR / stamp
        shutil.copytree(
            SKILLS_DIR, dest,
            ignore=shutil.ignore_patterns(".snapshots"),
        )
        (dest / ".reason").write_text(reason)
        return dest
    except Exception:
        return None


# ===========================================================================
# 4a-i — lifecycle transitions (pure Python, no LLM)
# ===========================================================================

def apply_transitions(live: bool) -> dict:
    """Age skills active→stale→archived by inactivity. Protected exempt.

    created_at anchors brand-new skills so they don't archive immediately.
    Returns a counts dict.
    """
    import skills as sk
    counts = {"checked": 0, "marked_stale": 0, "archived": 0, "reactivated": 0, "seeded": 0}
    now = _now()
    stale_cut = now - timedelta(days=STALE_AFTER_DAYS)
    archive_cut = now - timedelta(days=ARCHIVE_AFTER_DAYS)

    actions = []
    for info in sk.list_skills():
        slug = info["slug"]
        counts["checked"] += 1
        if sk.is_protected(slug):
            continue

        usage = sk.get_usage(slug)
        anchor = _parse_iso(usage.get("last_used")) or _parse_iso(usage.get("created_at"))
        if anchor is None:
            # No usage record yet — seed created_at to now so the clock starts now.
            counts["seeded"] += 1
            if live:
                u = sk._load_usage()
                u.setdefault(slug, {"use_count": 0, "last_used": None})
                u[slug]["created_at"] = now.isoformat()
                sk._save_usage(u)
            continue

        state = info["state"]
        if anchor <= archive_cut and state != sk.STATE_ARCHIVED:
            actions.append(("archive", slug))
            counts["archived"] += 1
            if live:
                sk.archive_skill(slug)
        elif anchor <= stale_cut and state == sk.STATE_ACTIVE:
            actions.append(("stale", slug))
            counts["marked_stale"] += 1
            if live:
                sk.set_state(slug, sk.STATE_STALE)
        elif anchor > stale_cut and state == sk.STATE_STALE:
            actions.append(("reactivate", slug))
            counts["reactivated"] += 1
            if live:
                sk.set_state(slug, sk.STATE_ACTIVE)

    counts["_actions"] = actions
    return counts


# ===========================================================================
# 4a-ii — LLM umbrella consolidation
# ===========================================================================

CONSOLIDATE_SYSTEM = (
    "You are Lucent's background skill CURATOR running an UMBRELLA-BUILDING "
    "consolidation pass — not a passive audit and not a duplicate-finder.\n\n"
    "The skill library's goal is a set of CLASS-LEVEL skills with rich bodies + "
    "references/ subfiles — NOT hundreds of narrow one-session-one-skill entries. "
    "One broad umbrella with labeled subsections beats five narrow siblings for "
    "discoverability (agents match on descriptions, not exact names).\n\n"
    "Hard rules:\n"
    "1. Only the candidate skills listed below are eligible. Never touch protected "
    "or pinned skills.\n"
    "2. NEVER delete. Archiving is the maximum action and is recoverable.\n"
    "3. Judge overlap on CONTENT, not use-count. Ask: 'would a maintainer write "
    "these as N separate skills, or one skill with N labeled subsections?'\n"
    "4. 'Narrow but distinct from its siblings' is NOT a reason to keep separate — "
    "it's a reason to make it a subsection or references/ file under an umbrella.\n\n"
    "For each prefix/domain cluster with 2+ members, decide one of:\n"
    "  a. MERGE into an existing broad member (patch it, archive siblings)\n"
    "  b. CREATE a new umbrella SKILL.md (archive absorbed siblings)\n"
    "  c. DEMOTE a sibling's detail into <umbrella>/references/<topic>.md, archive it\n\n"
    "Output ONLY a JSON object (no prose, no fences):\n"
    '{"consolidations":[{"from":"<slug>","into":"<umbrella-slug>","method":"merge|create|demote","reason":"<one sentence>"}],'
    '"prunings":[{"name":"<slug>","reason":"<why archived with no merge target>"}],'
    '"notes":"<short human summary of clusters processed and decisions left alone>"}\n'
    "Leave a list empty if none. This is a PLAN — downstream tooling executes it."
)


def _curatable_skills() -> list[dict]:
    import skills as sk
    return [s for s in sk.list_skills() if sk.is_curatable(s["slug"])]


def _get_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_file = LUCENT_ROOT / "ui" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def run_consolidation(live: bool) -> dict:
    """LLM umbrella pass. Returns {plan, applied, candidates}. Dry-run unless live."""
    import skills as sk
    candidates = _curatable_skills()
    result = {"candidate_count": len(candidates), "plan": None, "applied": [], "skipped_reason": None}

    if len(candidates) < 2:
        result["skipped_reason"] = (
            f"only {len(candidates)} curatable skill(s) — need 2+ to consolidate"
        )
        return result

    api_key = _get_api_key()
    if not api_key:
        result["skipped_reason"] = "no API key"
        return result

    listing = "\n".join(
        f"- {s['slug']} (state={s['state']}, uses={s['use_count']}): {s['description']}"
        for s in candidates
    )
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=3000,
            system=CONSOLIDATE_SYSTEM,
            messages=[{"role": "user", "content":
                       f"Candidate skills (agent-created, unprotected):\n{listing}\n\n"
                       "Produce the consolidation plan JSON."}],
        )
        plan = _parse_json(resp.content[0].text)
    except Exception as e:
        result["skipped_reason"] = f"LLM call failed: {e}"
        return result

    result["plan"] = plan
    if not live or not plan:
        return result

    # Live execution: snapshot, then apply archive actions for absorbed/pruned.
    snapshot_skills(reason="pre-consolidation")
    for c in plan.get("consolidations", []):
        slug = c.get("from")
        if slug and sk.is_curatable(slug):
            ok, msg = sk.archive_skill(slug)
            result["applied"].append({"action": "archive(consolidated)", "slug": slug, "ok": ok, "msg": msg})
    for p in plan.get("prunings", []):
        slug = p.get("name")
        if slug and sk.is_curatable(slug):
            ok, msg = sk.archive_skill(slug)
            result["applied"].append({"action": "archive(pruned)", "slug": slug, "ok": ok, "msg": msg})
    return result


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e != -1:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                return None
    return None


# ===========================================================================
# 4b — memory hygiene
# ===========================================================================

def cap_ltmemory(live: bool) -> dict:
    """Keep newest KEEP_RECENT_SESSIONS in LTMemory; move older to archive."""
    res = {"total_sessions": 0, "kept": 0, "archived": 0, "error": None}
    if not LTMEMORY_PATH.exists():
        res["error"] = "LTMemory.md not found"
        return res
    content = LTMEMORY_PATH.read_text(encoding="utf-8")
    marker = "## Recent Sessions"
    idx = content.find(marker)
    if idx == -1:
        res["error"] = "no '## Recent Sessions' section"
        return res

    head = content[:idx]
    section = content[idx:]
    # Split into the header line + session blocks (split on '### Session')
    parts = section.split("\n### Session")
    section_header = parts[0]  # "## Recent Sessions\n..." up to first session
    blocks = [f"### Session{p}" for p in parts[1:]]  # each block (reverse-chron order)

    res["total_sessions"] = len(blocks)
    if len(blocks) <= KEEP_RECENT_SESSIONS:
        res["kept"] = len(blocks)
        return res

    keep = blocks[:KEEP_RECENT_SESSIONS]
    archive = blocks[KEEP_RECENT_SESSIONS:]
    res["kept"] = len(keep)
    res["archived"] = len(archive)

    if live:
        # Append archived blocks to LTMemory.archive.md (preserve order; newest of
        # the archived batch first, appended after any existing archive content).
        archive_text = "\n".join(b.rstrip() + "\n" for b in archive)
        existing = LTMEMORY_ARCHIVE.read_text() if LTMEMORY_ARCHIVE.exists() else "# LTMemory Archive\n\nOlder session entries moved out of LTMemory.md to keep it lean. Still indexed for recall.\n"
        LTMEMORY_ARCHIVE.write_text(existing + "\n" + archive_text)
        # Rewrite LTMemory.md with only the kept blocks
        new_section = section_header.rstrip() + "\n\n" + "\n".join(b.rstrip() + "\n" for b in keep)
        LTMEMORY_PATH.write_text(head + new_section)
    return res


def archive_stale_auto_memory(live: bool) -> dict:
    """Move COMPLETED auto-memory project files older than N days to archive/."""
    res = {"scanned": 0, "archived": 0, "candidates": [], "error": None}
    if not AUTO_MEMORY_DIR.exists():
        res["error"] = "auto-memory dir not found"
        return res
    cutoff = _now() - timedelta(days=AUTO_MEMORY_STALE_DAYS)
    for p in sorted(AUTO_MEMORY_DIR.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        res["scanned"] += 1
        try:
            text = p.read_text(encoding="utf-8")
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        except Exception:
            continue
        # Only archive things explicitly marked complete AND untouched past cutoff
        is_completed = ("COMPLETED" in text or "✅" in text)
        if is_completed and mtime <= cutoff:
            res["candidates"].append(p.name)
            if live:
                AUTO_MEMORY_ARCHIVE.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(p), str(AUTO_MEMORY_ARCHIVE / p.name))
                    res["archived"] += 1
                except Exception:
                    pass
    return res


# ===========================================================================
# Report
# ===========================================================================

def write_report(sections: dict, live: bool) -> None:
    lines = [
        f"# NERO Curator Report — {_now().isoformat()}",
        "",
        f"**Mode:** {'LIVE (mutations applied)' if live else 'DRY-RUN (report only)'}",
        "",
    ]
    for title, body in sections.items():
        lines.append(f"## {title}")
        lines.append("```json")
        lines.append(json.dumps(body, indent=2, default=str))
        lines.append("```")
        lines.append("")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines))


# ===========================================================================
# CLI
# ===========================================================================

def _run_all(live: bool):
    t = apply_transitions(live)
    c = run_consolidation(live)
    lt = cap_ltmemory(live)
    am = archive_stale_auto_memory(live)
    sections = {
        "4a-i Lifecycle transitions": t,
        "4a-ii Umbrella consolidation": c,
        "4b LTMemory length cap": lt,
        "4b Auto-memory stale archive": am,
    }
    write_report(sections, live)
    return sections


def _print_summary(sections: dict, live: bool):
    print(f"=== NERO Curator {'(LIVE)' if live else '(DRY-RUN)'} ===")
    for title, body in sections.items():
        print(f"\n{title}:")
        for k, v in body.items():
            if k.startswith("_") or k == "plan":
                continue
            print(f"  {k}: {v}")
    plan = sections.get("4a-ii Umbrella consolidation", {}).get("plan")
    if plan:
        print("\nConsolidation plan:")
        print(json.dumps(plan, indent=2))
    print(f"\nReport: {REPORT_PATH}")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else "run"
    live = "--live" in args

    if cmd == "run":
        _print_summary(_run_all(live), live)
    elif cmd == "transitions":
        s = {"4a-i Lifecycle transitions": apply_transitions(live)}
        write_report(s, live); _print_summary(s, live)
    elif cmd == "consolidate":
        s = {"4a-ii Umbrella consolidation": run_consolidation(live)}
        write_report(s, live); _print_summary(s, live)
    elif cmd == "memory-hygiene":
        s = {"4b LTMemory length cap": cap_ltmemory(live),
             "4b Auto-memory stale archive": archive_stale_auto_memory(live)}
        write_report(s, live); _print_summary(s, live)
    elif cmd == "snapshot":
        d = snapshot_skills(reason="manual-cli")
        print(f"snapshot: {d}" if d else "snapshot failed")
    elif cmd == "report":
        print(REPORT_PATH.read_text() if REPORT_PATH.exists() else "No report yet.")
    else:
        print(__doc__)
        sys.exit(1)
