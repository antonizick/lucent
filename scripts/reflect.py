#!/usr/bin/env python3
"""
NERO Phase 3 — Per-turn self-improvement loop.

After every assistant turn — Claude Code's Stop hook, or OpenCode's
session.idle event feeding a translated transcript (see lucent-plugin.ts's
buildClaudeShapedTranscript) — Lucent reflects on the exchange and asks:
"did I just learn something about Nick, or how to do this class of task?"
If yes, it proposes a memory write or skill update. Both hosts feed this
script the identical stdin contract: {"transcript_path": "<jsonl file>"}.

ARCHITECTURE (zero-latency + 100% reliability):
  - The hook entry (no args, reads Stop JSON on stdin) does almost nothing:
    it validates config, dedups the turn, and spawns a DETACHED background
    worker, then exits 0 immediately. Nick's next turn is never delayed.
  - The worker (--worker <transcript_path>) does the LLM work out-of-band:
      Stage 0  local trivial-turn filter (no API cost)
      Stage 1  Haiku GATE — "is there anything worth saving here?" (cheap)
      Stage 2  Sonnet WRITER — decides exact action(s), emits structured JSON
  - All actions are APPEND/CREATE only — never overwrite or delete. This makes
    even auto-mode safe.

MODES (memory/.nero/config.json → "mode"):
  - "propose" (default): actions are written to the inbox for Nick's approval.
  - "auto": actions are applied immediately (still append/create only).

RELIABILITY CONTRACT:
  - Hook entry never blocks (spawns detached worker, exits 0 in <100ms).
  - Worker swallows every exception; a failed reflection is a no-op.
  - Disabled or misconfigured → silent no-op.
  - No API key → silent no-op (logged to worker.log only).

CLI:
  python3 scripts/reflect.py                      # hook entry (reads stdin)
  python3 scripts/reflect.py --worker <path>      # internal: run reflection
  python3 scripts/reflect.py status               # show config + pending count
  python3 scripts/reflect.py review               # print pending proposals
  python3 scripts/reflect.py apply <id>           # apply a pending proposal
  python3 scripts/reflect.py apply-all            # apply all pending proposals at once
  python3 scripts/reflect.py reject <id>          # reject a pending proposal
  python3 scripts/reflect.py mode propose|auto    # set mode (auto applies pending retroactively)
  python3 scripts/reflect.py enable|disable       # toggle the loop
"""

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

LUCENT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_ROOT / "memory"
SKILLS_DIR = MEMORY_DIR / "skills"
AUTO_MEMORY_DIR = Path.home() / ".claude/projects/-home-nick-dev-lucent/memory"

NERO_DIR = MEMORY_DIR / ".nero"
CONFIG_PATH = NERO_DIR / "config.json"
STATE_PATH = NERO_DIR / "state.json"
PROPOSALS_PATH = NERO_DIR / "proposals.jsonl"
WORKER_LOG = NERO_DIR / "worker.log"
INBOX_PATH = MEMORY_DIR / "nero_inbox.md"
ACTIVITY_LOG_DIR = MEMORY_DIR / "logs"

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

MIN_EXCHANGE_CHARS = 200   # Stage 0: skip trivial turns below this combined size
MAX_EXCHANGE_CHARS = 24000  # cap context sent to the models


# ===========================================================================
# Config / state
# ===========================================================================

def _load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return dict(default)


def load_config() -> dict:
    return _load_json(CONFIG_PATH, {"enabled": True, "mode": "propose"})


def save_config(cfg: dict) -> None:
    NERO_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def load_state() -> dict:
    return _load_json(STATE_PATH, {"last_leaf_uuid": None, "last_run_at": None})


def save_state(state: dict) -> None:
    NERO_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _log(msg: str) -> None:
    try:
        NERO_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        with open(WORKER_LOG, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _log_to_activity(msg: str) -> None:
    """Log to the daily activity log (memory/logs/activity_YYYY-MM-DD.log)."""
    try:
        ACTIVITY_LOG_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now()
        log_path = ACTIVITY_LOG_DIR / f"activity_{today.strftime('%Y-%m-%d')}.log"
        ts = today.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a") as f:
            f.write(f"[{ts}] [nero-reflection] {msg}\n")
    except Exception:
        pass


# ===========================================================================
# API key + LLM calls
# ===========================================================================

def get_api_key() -> str | None:
    """Match auto_summarize.py: env first, then ui/.env."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_file = LUCENT_ROOT / "ui" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _call_model(model: str, system: str, user: str, api_key: str, max_tokens: int) -> str | None:
    try:
        import anthropic
    except ImportError:
        _log("anthropic SDK not installed")
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        _log(f"{model} call failed: {e}")
        return None


# ===========================================================================
# Prompts — ported from Hermes agent/background_review.py
# ===========================================================================

GATE_SYSTEM = (
    "You are a fast classifier for Lucent, Nick's personal AI assistant. "
    "You decide whether a finished conversation turn contains anything worth "
    "durably saving — either a fact about Nick (persona, preference, "
    "expectation, situation) or a reusable lesson about how to do a class of "
    "task. Answer with a single token: YES or NO, optionally followed by a "
    "short reason. Be conservative: most turns are NO."
)

GATE_USER_TEMPLATE = (
    "Here is the latest exchange between Nick and Lucent:\n\n"
    "{exchange}\n\n"
    "Does this exchange contain something worth durably saving to memory or a "
    "skill? Consider: did Nick reveal a preference/expectation/personal detail? "
    "Did he correct Lucent's style, workflow, or approach? Did a reusable "
    "technique, fix, or pitfall emerge? Answer YES or NO with a one-line reason."
)

WRITER_SYSTEM = (
    "You are Lucent's self-improvement reviewer. You decide exactly what to "
    "save after a conversation turn, and emit structured actions.\n\n"
    "Two stores:\n"
    "  • MEMORY captures WHO Nick is and the current state of operations — "
    "persona, preferences, expectations, ongoing project state, decisions.\n"
    "  • SKILLS capture HOW to do a class of task for Nick — procedures, "
    "pitfalls, corrections embedded so the next session starts already knowing.\n\n"
    "Preference order — prefer the EARLIEST action that fits:\n"
    "  1. PATCH a skill that governs the task in play (append a labeled "
    "subsection or pitfall). If Nick corrected style/workflow, the governing "
    "skill needs the lesson — not just memory.\n"
    "  2. ADD A SUPPORT FILE (references/<topic>.md) under an existing skill "
    "for session-specific detail or a knowledge bank.\n"
    "  3. CREATE A NEW CLASS-LEVEL SKILL only when no existing skill covers "
    "the class. The name MUST be class-level — never a specific date, error "
    "string, PR number, or one-session codename.\n"
    "  4. WRITE A MEMORY fact when the learning is about Nick or operational "
    "state rather than a task procedure.\n\n"
    "Target shape of the skill library: CLASS-LEVEL skills, each with a rich "
    "body and a references/ directory — NOT a flat list of narrow "
    "one-session-one-skill entries.\n\n"
    "Do NOT capture (these harden into self-imposed constraints that bite "
    "later when the environment changes):\n"
    "  • Environment-dependent failures: missing binaries, fresh-install "
    "errors, path mismatches, 'command not found', unconfigured credentials, "
    "uninstalled packages. Nick can fix these — they are not durable rules.\n"
    "  • Negative claims about tools/features ('X is broken', 'cannot use Y'). "
    "These harden into refusals Lucent cites against itself for months after "
    "the actual problem was fixed.\n"
    "  • Session-specific transient errors that resolved before the turn ended. "
    "If retrying worked, the lesson is the retry pattern, not the failure.\n"
    "  • One-off task narratives. 'Summarize today's market' is not a class of "
    "work that warrants a skill.\n"
    "  • Secrets, credentials, or sensitive personal data.\n\n"
    "If a tool failed because of setup state, capture the FIX (how to "
    "configure it), never the failure itself.\n\n"
    "Output: a JSON object with a single key \"actions\" — a list (possibly "
    "empty). Each action is one of:\n"
    '  {"type":"skill_patch","skill":"<slug>","section":"<## heading>","content":"<markdown>","reason":"<why>"}\n'
    '  {"type":"skill_support_file","skill":"<slug>","path":"references/<name>.md","content":"<markdown>","reason":"<why>"}\n'
    '  {"type":"skill_create","slug":"<class-level-slug>","name":"<Title>","description":"<one line>","skill_class":"<category>","content":"<full SKILL.md body>","reason":"<why>"}\n'
    '  {"type":"memory_note","slug":"<kebab-slug>","title":"<Title>","mem_type":"user|feedback|project|reference","content":"<the fact>","reason":"<why>"}\n'
    "Emit {\"actions\": []} when nothing durable should be saved. Output ONLY "
    "the JSON object, no prose, no code fences."
)

WRITER_USER_TEMPLATE = (
    "Existing skills (slug — description):\n{skills}\n\n"
    "Recent memory note slugs:\n{memory_slugs}\n\n"
    "Gate said this turn is worth reviewing because: {gate_reason}\n\n"
    "Here is the exchange:\n\n{exchange}\n\n"
    "Decide what (if anything) to durably save. Honor the preference order and "
    "the do-NOT-capture list. Emit the JSON actions object."
)


# ===========================================================================
# Transcript extraction
# ===========================================================================

def _text_from_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""

def _is_tool_result(content) -> bool:
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in content
        )
    return False


def extract_last_exchange(transcript_path: str) -> tuple[str, str | None]:
    """
    Return (exchange_text, last_assistant_uuid) for the most recent
    user-prompt → assistant-response pair. exchange_text is "" if none found.
    """
    try:
        from memory_index import sanitize_context
    except Exception:
        def sanitize_context(x):  # fallback
            return x

    p = Path(transcript_path)
    if not p.exists():
        return "", None

    turns = []  # list of (role, text, uuid)
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("type")
            if t not in ("user", "assistant"):
                continue
            msg = d.get("message")
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", "")
            if t == "user":
                # Skip tool-result user entries — those aren't Nick's prompts
                if _is_tool_result(content):
                    continue
                text = sanitize_context(_text_from_content(content)).strip()
                # Skip hook-injected context echoes
                if not text or text.startswith("[Lucent]"):
                    continue
                turns.append(("Nick", text, d.get("uuid")))
            else:  # assistant
                text = _text_from_content(content).strip()
                if text:
                    turns.append(("Lucent", text, d.get("uuid")))
    except Exception:
        return "", None

    if not turns:
        return "", None

    # Walk back to find the last assistant turn and the user prompt before it.
    last_assistant_idx = None
    for i in range(len(turns) - 1, -1, -1):
        if turns[i][0] == "Lucent":
            last_assistant_idx = i
            break
    if last_assistant_idx is None:
        return "", None

    last_assistant_uuid = turns[last_assistant_idx][2]

    # Gather the exchange: nearest preceding Nick prompt + this assistant turn.
    start = last_assistant_idx
    for j in range(last_assistant_idx - 1, -1, -1):
        if turns[j][0] == "Nick":
            start = j
            break

    chosen = turns[start:last_assistant_idx + 1]
    lines = [f"{role}: {text}" for role, text, _ in chosen]
    exchange = "\n\n".join(lines)
    if len(exchange) > MAX_EXCHANGE_CHARS:
        exchange = exchange[:MAX_EXCHANGE_CHARS] + "\n\n[truncated]"
    return exchange, last_assistant_uuid


# ===========================================================================
# Proposal storage + inbox rendering
# ===========================================================================

def _append_proposal(record: dict) -> None:
    NERO_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROPOSALS_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def _read_proposals() -> list[dict]:
    if not PROPOSALS_PATH.exists():
        return []
    out = []
    for line in PROPOSALS_PATH.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _rewrite_proposals(records: list[dict]) -> None:
    with open(PROPOSALS_PATH, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def pending_count() -> int:
    return sum(1 for r in _read_proposals() if r.get("status") == "pending")


def _render_inbox() -> None:
    """Regenerate the human-readable inbox from pending proposals."""
    records = _read_proposals()
    pending = [r for r in records if r.get("status") == "pending"]
    lines = [
        "# NERO Inbox — Pending Self-Improvement Proposals",
        "",
        "Reflection (Phase 3) proposes these memory/skill updates after turns. "
        "Review and apply with `python3 scripts/reflect.py apply <id>` or reject "
        "with `reject <id>`. Switch to auto-apply with `reflect.py mode auto`.",
        "",
        f"**Pending: {len(pending)}**",
        "",
    ]
    if not pending:
        lines.append("_No pending proposals._")
    for r in pending:
        a = r.get("action", {})
        lines.append(f"## [{r.get('id','?')}] {a.get('type','?')}")
        lines.append(f"- **When:** {r.get('ts','?')}")
        lines.append(f"- **Reason:** {a.get('reason','')}")
        target = a.get("skill") or a.get("slug") or a.get("path") or "—"
        lines.append(f"- **Target:** {target}")
        content = a.get("content", "")
        preview = content if len(content) < 1200 else content[:1200] + "…"
        lines.append(f"- **Content:**\n\n```\n{preview}\n```")
        lines.append("")
    try:
        INBOX_PATH.write_text("\n".join(lines))
    except Exception:
        pass


# ===========================================================================
# Action application (append/create only — never overwrite/delete)
# ===========================================================================

def apply_action(action: dict) -> tuple[bool, str]:
    atype = action.get("type")
    try:
        if atype == "memory_note":
            return _apply_memory_note(action)
        if atype == "skill_patch":
            return _apply_skill_patch(action)
        if atype == "skill_support_file":
            return _apply_skill_support_file(action)
        if atype == "skill_create":
            return _apply_skill_create(action)
        if atype == "email_rule_update":
            return _apply_email_rule_update(action)
        return False, f"unknown action type: {atype}"
    except Exception as e:
        return False, f"apply failed: {e}"


def _apply_memory_note(a: dict) -> tuple[bool, str]:
    slug = a.get("slug", "").strip()
    if not slug:
        return False, "missing slug"
    path = AUTO_MEMORY_DIR / f"{slug}.md"
    if path.exists():
        return False, f"memory note already exists: {slug} (skipped to avoid overwrite)"
    fm = (
        f"---\nname: {slug}\n"
        f"description: {a.get('title', slug)}\n"
        f"metadata:\n  type: {a.get('mem_type', 'project')}\n---\n\n"
    )
    path.write_text(fm + a.get("content", "").strip() + "\n")
    # Add MEMORY.md index pointer (append under a NERO heading)
    idx = AUTO_MEMORY_DIR / "MEMORY.md"
    try:
        if idx.exists():
            line = f"- [{a.get('title', slug)}]({slug}.md) — added by NERO reflection\n"
            with open(idx, "a") as f:
                f.write(line)
    except Exception:
        pass
    return True, f"created memory note {slug}.md"


def _apply_skill_patch(a: dict) -> tuple[bool, str]:
    slug = a.get("skill", "").strip()
    skill_md = SKILLS_DIR / slug / "SKILL.md"
    if not skill_md.exists():
        return False, f"skill not found: {slug}"
    section = a.get("section", "").strip() or "## Notes (added by reflection)"
    if not section.startswith("#"):
        section = f"## {section}"
    block = f"\n\n{section}\n\n{a.get('content','').strip()}\n"
    with open(skill_md, "a") as f:
        f.write(block)
    return True, f"patched skill {slug}"


def _apply_skill_support_file(a: dict) -> tuple[bool, str]:
    slug = a.get("skill", "").strip()
    skill_dir = SKILLS_DIR / slug
    if not (skill_dir / "SKILL.md").exists():
        return False, f"skill not found: {slug}"
    rel = a.get("path", "").strip()
    if not rel.startswith(("references/", "templates/", "scripts/")):
        return False, f"unsafe support path: {rel}"
    dest = skill_dir / rel
    if dest.exists():
        return False, f"support file already exists: {rel} (skipped)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(a.get("content", "").strip() + "\n")
    return True, f"added {slug}/{rel}"


def _apply_skill_create(a: dict) -> tuple[bool, str]:
    slug = a.get("slug", "").strip()
    if not slug or "/" in slug:
        return False, f"invalid slug: {slug}"
    skill_dir = SKILLS_DIR / slug
    if skill_dir.exists():
        return False, f"skill already exists: {slug}"
    skill_dir.mkdir(parents=True, exist_ok=True)
    body = a.get("content", "").strip()
    # Ensure required header fields are present; prepend if the model omitted them.
    if "**Description:**" not in body:
        header = (
            f"# {a.get('name', slug)}\n\n"
            f"**Description:** {a.get('description','')}\n"
            f"**Class:** {a.get('skill_class','General')}\n"
            f"**State:** active\n"
            f"**Created:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
        )
        body = header + body
    (skill_dir / "SKILL.md").write_text(body + "\n")
    return True, f"created skill {slug}"


def _apply_email_rule_update(a: dict) -> tuple[bool, str]:
    """Append a feedback-derived correction note to priority_guidelines.md."""
    guidelines = MEMORY_DIR / "email" / "priority_guidelines.md"
    if not guidelines.exists():
        return False, "priority_guidelines.md not found"
    content = a.get("content", "").strip()
    if not content:
        return False, "missing content"
    block = f"\n\n### Feedback Correction — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{content}\n"
    with open(guidelines, "a") as f:
        f.write(block)
    return True, "appended correction to priority_guidelines.md"


# ===========================================================================
# Worker — the actual reflection (runs detached)
# ===========================================================================

def _skills_listing() -> str:
    try:
        from skills import list_skills
        rows = list_skills()
        return "\n".join(f"  {s['slug']} — {s['description']}" for s in rows) or "  (none)"
    except Exception:
        return "  (unavailable)"


def _memory_slugs() -> str:
    try:
        names = sorted(p.stem for p in AUTO_MEMORY_DIR.glob("*.md") if p.name != "MEMORY.md")
        return ", ".join(names[:60]) or "(none)"
    except Exception:
        return "(unavailable)"


def run_worker(transcript_path: str) -> None:
    cfg = load_config()
    if not cfg.get("enabled", True):
        return

    exchange, leaf_uuid = extract_last_exchange(transcript_path)
    if not exchange:
        return

    # Dedup — don't reprocess the same assistant turn.
    state = load_state()
    if leaf_uuid and leaf_uuid == state.get("last_leaf_uuid"):
        return

    # Stage 0 — local trivial filter (no API cost).
    if len(exchange) < MIN_EXCHANGE_CHARS:
        state["last_leaf_uuid"] = leaf_uuid
        save_state(state)
        return

    api_key = get_api_key()
    if not api_key:
        _log("no API key — skipping")
        return

    # Stage 1 — Haiku gate.
    gate = _call_model(
        HAIKU_MODEL, GATE_SYSTEM,
        GATE_USER_TEMPLATE.format(exchange=exchange),
        api_key, max_tokens=128,
    )
    state["last_leaf_uuid"] = leaf_uuid
    state["last_run_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    if not gate or not gate.lstrip().upper().startswith("YES"):
        _log(f"gate=NO ({(gate or '').strip()[:80]})")
        return
    gate_reason = gate.strip()[:300]

    # Stage 2 — Sonnet writer.
    writer_out = _call_model(
        SONNET_MODEL, WRITER_SYSTEM,
        WRITER_USER_TEMPLATE.format(
            skills=_skills_listing(),
            memory_slugs=_memory_slugs(),
            gate_reason=gate_reason,
            exchange=exchange,
        ),
        api_key, max_tokens=4096,
    )
    if not writer_out:
        return

    actions = _parse_actions(writer_out)
    if not actions:
        _log("writer produced no actions")
        return

    mode = cfg.get("mode", "propose")
    for action in actions:
        if mode == "auto":
            ok, msg = apply_action(action)
            _append_proposal({
                "id": uuid.uuid4().hex[:8],
                "ts": datetime.now(timezone.utc).isoformat(),
                "status": "applied" if ok else "failed",
                "action": action,
                "apply_msg": msg,
                "gate_reason": gate_reason,
            })
            _log(f"auto {action.get('type')}: {ok} {msg}")
        else:
            _append_proposal({
                "id": uuid.uuid4().hex[:8],
                "ts": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
                "action": action,
                "gate_reason": gate_reason,
            })
            _log(f"proposed {action.get('type')} ({action.get('reason','')[:60]})")

    _render_inbox()


def _parse_actions(text: str) -> list[dict]:
    """Robustly extract the actions list from the writer's JSON output."""
    text = text.strip()
    # Strip accidental code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    # Find the first {...} object
    try:
        obj = json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return []
        try:
            obj = json.loads(text[start:end + 1])
        except Exception:
            return []
    actions = obj.get("actions", []) if isinstance(obj, dict) else []
    return [a for a in actions if isinstance(a, dict) and a.get("type")]


# ===========================================================================
# Hook entry — spawn detached worker, exit fast
# ===========================================================================

def hook_entry() -> None:
    """Read Stop payload from stdin, spawn detached worker, return immediately."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

    transcript_path = data.get("transcript_path", "")
    if not transcript_path:
        return

    cfg = load_config()
    if not cfg.get("enabled", True):
        return

    # Spawn the worker fully detached so the hook never blocks the session.
    try:
        log_fh = open(WORKER_LOG, "a")
    except Exception:
        log_fh = subprocess.DEVNULL
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--worker", transcript_path],
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=log_fh,
            start_new_session=True,  # detach from the host's process group (Claude Code or OpenCode)
            cwd=str(LUCENT_ROOT),
        )
    except Exception:
        pass  # never raise from a hook


# ===========================================================================
# CLI
# ===========================================================================

def _cmd_status():
    cfg = load_config()
    st = load_state()
    print(f"enabled : {cfg.get('enabled', True)}")
    print(f"mode    : {cfg.get('mode', 'propose')}")
    print(f"pending : {pending_count()} proposal(s)")
    print(f"last run: {st.get('last_run_at', 'never')}")


def _cmd_review():
    pending = [r for r in _read_proposals() if r.get("status") == "pending"]
    if not pending:
        print("No pending proposals.")
        return
    for r in pending:
        a = r.get("action", {})
        print(f"\n=== [{r['id']}] {a.get('type')} ===")
        print(f"reason: {a.get('reason','')}")
        target = a.get("skill") or a.get("slug") or a.get("path") or "—"
        print(f"target: {target}")
        print(f"content:\n{a.get('content','')[:1500]}")


def _cmd_apply(pid: str):
    records = _read_proposals()
    found = False
    for r in records:
        if r.get("id") == pid and r.get("status") == "pending":
            ok, msg = apply_action(r["action"])
            r["status"] = "applied" if ok else "failed"
            r["apply_msg"] = msg
            found = True
            print(("✓ " if ok else "✗ ") + msg)
            break
    if not found:
        print(f"No pending proposal with id {pid}")
        return
    _rewrite_proposals(records)
    _render_inbox()


def _cmd_reject(pid: str):
    records = _read_proposals()
    for r in records:
        if r.get("id") == pid and r.get("status") == "pending":
            r["status"] = "rejected"
            print(f"Rejected {pid}")
            break
    _rewrite_proposals(records)
    _render_inbox()


def _apply_all_pending() -> None:
    """Apply all pending proposals and log to activity log."""
    records = _read_proposals()
    pending = [r for r in records if r.get("status") == "pending"]
    if not pending:
        print("No pending proposals.")
        return

    for r in pending:
        ok, msg = apply_action(r["action"])
        r["status"] = "applied" if ok else "failed"
        r["apply_msg"] = msg
        action_type = r.get("action", {}).get("type", "unknown")
        _log_to_activity(f"Applied {action_type}: {msg}")
        print(("✓ " if ok else "✗ ") + f"[{r['id']}] {msg}")

    _rewrite_proposals(records)
    _render_inbox()
    print(f"\nApplied {len(pending)} proposal(s)")


def _cmd_mode(mode: str):
    if mode not in ("propose", "auto"):
        print("mode must be 'propose' or 'auto'", file=sys.stderr)
        sys.exit(1)
    cfg = load_config()
    cfg["mode"] = mode
    save_config(cfg)

    # When switching to auto mode, apply all pending proposals retroactively
    if mode == "auto":
        pending_count = sum(1 for r in _read_proposals() if r.get("status") == "pending")
        if pending_count > 0:
            print(f"Switching to auto mode and applying {pending_count} pending proposal(s)...")
            _apply_all_pending()
        else:
            print("mode set to auto")
    else:
        print(f"mode set to {mode}")


def _cmd_toggle(enabled: bool):
    cfg = load_config()
    cfg["enabled"] = enabled
    save_config(cfg)
    print(f"reflection {'enabled' if enabled else 'disabled'}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        hook_entry()
    elif args[0] == "--worker":
        if len(args) >= 2:
            try:
                run_worker(args[1])
            except Exception as e:
                _log(f"worker crashed: {e}")
    elif args[0] == "status":
        _cmd_status()
    elif args[0] == "review":
        _cmd_review()
    elif args[0] == "apply" and len(args) >= 2:
        _cmd_apply(args[1])
    elif args[0] == "reject" and len(args) >= 2:
        _cmd_reject(args[1])
    elif args[0] == "apply-all":
        _apply_all_pending()
    elif args[0] == "mode" and len(args) >= 2:
        _cmd_mode(args[1])
    elif args[0] == "enable":
        _cmd_toggle(True)
    elif args[0] == "disable":
        _cmd_toggle(False)
    else:
        print(__doc__)
        sys.exit(1)
