# Lucent Startup Architecture

**Last updated:** 2026-06-07
**Status:** Production — both platforms operational, automatic-hook parity achieved

This document explains how the Lucent startup ritual and per-turn runtime are implemented
across Claude Code and OpenCode, why the architecture is designed the way it is, what was
tried and failed before arriving here, and how to debug it when something goes wrong.

---

## The Core Problem This Architecture Solves

AI assistants have no persistent memory between sessions. Each session starts cold — the
assistant has no knowledge of Nick, the Lucent system, ongoing projects, or the voice box
requirement unless that information is explicitly loaded into context.

The startup ritual is the solution: a defined sequence that loads identity, memory, and
live context before the assistant generates its first response — and a per-turn sequence
that keeps dynamic state (date, recall, reminders, NERO proposals) fresh on every message.
The architectural challenge is making both sequences *reliable* — ensuring they actually
run every session and every turn, never dependent on the model choosing to comply.

The fundamental insight that shapes this architecture:

> **Documentation in context is passive. Platform-level hooks are binding.**

An instruction file saying "execute these steps before responding" is treated as optional
documentation by the model — it can be skipped when the model decides an immediate response
is more appropriate. A hook that the *host platform itself* fires before the model ever sees
a turn cannot be skipped. This distinction drives every design decision below, and it is
the reason the architecture below is now **identical in shape** across both platforms.

---

## Headline Finding (Corrected 2026-06-07)

An earlier version of this document claimed *"OpenCode does not have a `UserPromptSubmit`-
equivalent hook"* and used that premise to justify a fundamentally different (and less
reliable) voluntary-tool design for OpenCode. **That premise was false.** The installed
`@opencode-ai/plugin` (v1.14.x) exposes automatic, platform-level hooks that map ~1:1 onto
Claude Code's hook set:

| Claude Code hook | OpenCode hook (now wired up) | Purpose |
|---|---|---|
| `SessionStart` | first `chat.message` of a session (guarded, once) | Identity bundle + validation gates (`startup.py`) |
| `UserPromptSubmit` | every `chat.message` | Per-turn dynamic state injection (`lucent-init.sh`) |
| `Stop` | `event` → `session.idle` | NERO reflection (`reflect.py`) |
| `PreCompact` | `experimental.session.compacting` | Compaction memory-durability guard (`pre_compact.py`) |
| *(convention-enforced)* | `experimental.text.complete` | Soft voice-box compliance nudge |

The gap that existed was implementation debt — an integration last touched ~2026-05-13,
predating the NERO self-improvement layer — not a platform limitation. Closing it was the
subject of the OpenCode Parity Plan (`docs/OPENCODE_PARITY_PLAN.md`, 4 phases, completed
2026-06-07). The architecture documented below **is** that closed state.

---

## Design Principle: Single-Source Logic

Both platforms run the **exact same Python/bash**. The OpenCode plugin does not reimplement
Lucent's brain in TypeScript — it shells out to the identical scripts Claude Code's hooks
invoke:

```
scripts/startup.py        ← identity bundle + validation gates (SessionStart equivalent)
scripts/lucent-init.sh    ← per-turn dynamic state             (UserPromptSubmit equivalent)
scripts/reflect.py        ← NERO self-improvement reflection   (Stop equivalent)
scripts/pre_compact.py    ← compaction memory-durability guard (PreCompact equivalent)
```

This guarantees behavioral identity and prevents logic forks: a fix or feature added to any
of these scripts is automatically live on both platforms with zero plugin changes. The only
platform-specific code that exists is the *plumbing* that wires the host's automatic hooks
to these scripts (`.opencode/lucent-plugin.ts` on the OpenCode side; `.claude/settings.json`
+ `lucent-init.sh`/`startup.py` directly on the Claude Code side).

Where the two hosts genuinely differ in shape — e.g. OpenCode stores session transcripts in
its own SDK-queryable format, not Claude-Code-shaped JSONL — the plugin uses a **thin
translation shim**: it re-shapes OpenCode's data into the exact format the shared script
already expects, then calls that script unmodified. See "NERO Reflection" below for the
concrete example. Translate the data, never fork the brain.

Automatic **platform detection** (where scripts need to know which host they're running
under — e.g. to print the correct host name in injected text) uses the `$CLAUDECODE`
environment variable, which Claude Code's CLI sets to `1` and which is simply absent under
OpenCode. No special wiring is required on either side; see `lucent-init.sh`'s `HOST_LABEL`
and `startup.py`'s `init_session_logger()`.

All `experimental.*` OpenCode hooks degrade to no-ops if the SDK changes or the call fails
— the same "purely additive, never breaks a turn" contract the shared scripts already honor.

---

## System Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      LUCENT SYSTEM FILES                          │
│                                                                   │
│  memory/                          scripts/                       │
│  ├── core.md          ← manual    ├── startup.py     ← SessionStart│
│  ├── lucentIdent.md               ├── lucent-init.sh ← UserPromptSubmit│
│  ├── userIdent.md                 ├── reflect.py     ← Stop        │
│  ├── LTMemory.md                  ├── pre_compact.py ← PreCompact   │
│  ├── REMINDERS.md                 ├── memory_recall.py             │
│  └── YYYY-MM-DD.md                └── session_logger.py            │
└──────────────────────────────────────────────────────────────────┘
         │                                          │
         │   invoked via .claude/settings.json      │   invoked via
         │   hook registration (direct)             │   .opencode/lucent-plugin.ts
         ▼                                          │   (subprocess shim)
┌─────────────────────┐                             ▼
│     CLAUDE CODE     │                  ┌─────────────────────────┐
│                     │                  │         OPENCODE         │
│  CLAUDE.md          │                  │                          │
│  (platform config)  │                  │  AGENTS.md (identity +   │
│                     │                  │   protocol reference —   │
│  settings.json      │                  │   no startup directive,  │
│  hooks:             │                  │   hooks run automatically)│
│   SessionStart      │ ───┐             │                          │
│   UserPromptSubmit  │    │   parallel  │  opencode.json           │
│   Stop              │    │   structure │  (loads memory files,    │
│   PreCompact        │    │             │   registers plugin)      │
│   SessionEnd        │ ───┘             │                          │
│                     │                  │  .opencode/              │
│                     │                  │  ├── lucent-plugin.ts ◄──┤ automatic hooks:
│                     │                  │  │                       │  chat.message,
│                     │                  │  │                       │  event, experimental.*
│                     │                  │  └── package.json        │
└─────────────────────┘                  └──────────────────────────┘
```

---

## Claude Code Implementation

### How it works

Claude Code's hooks (registered in `.claude/settings.json`) run shell/Python commands at
fixed lifecycle points before the model ever sees the corresponding turn:

| Hook | Command | Fires |
|---|---|---|
| `SessionStart` | `python3 scripts/startup.py` | Once, at session start |
| `UserPromptSubmit` | `scripts/lucent-init.sh` | Every user message |
| `Stop` | `log_turn_end.py` then `reflect.py` | After every assistant turn |
| `PreCompact` | `python3 scripts/pre_compact.py` | Before compaction |
| `SessionEnd` | `log_session_end.py` + voice "Session complete." | Once, at session end |

`startup.py` prints the identity bundle (core rules, identity, LTMemory, NERO skills
listing), runs validation gates (voice box health, session logger, LTMemory completeness),
calls `speak()`, and writes a `.startup_ready_<date>.txt` readiness marker. `lucent-init.sh`
prints dynamic per-turn state (date, rules reminder, semantic recall, reminders, priority
email, daily-note tail, NERO proposal count) and, on the very next turn after startup,
detects and consumes that readiness marker with a one-shot voice acknowledgment.

`CLAUDE.md` then provides step-by-step directives the model follows — but because the heavy
lifting (context injection, validation, logging) is *already done* by the hooks before the
model responds, those directives land against a rich, pre-loaded context rather than being
read as skippable documentation.

### Reliability

**High.** Hooks fire at the OS/framework level before the model receives any input. The
model cannot skip them. Context injection, validation, and logging are guaranteed every
single turn.

---

## OpenCode Implementation

### How it works (current — automatic hooks, since 2026-06-07)

`.opencode/lucent-plugin.ts` registers OpenCode's automatic platform hooks and wires each
one to the matching shared script via a thin subprocess shim — the same single-source
principle as Claude Code, just with TypeScript plumbing instead of native hook registration:

```
First chat.message of a session
     │
     ▼
runStartup(sessionID): once-per-session guard checks /tmp marker + in-memory Set
     │  (cache miss)
     ▼
python3 scripts/startup.py  →  identity bundle + validation gates + readiness marker
     │
     ▼  (SEQUENTIAL — see "Startup/Per-Turn Ordering" below)
runPerTurn(userText): bash scripts/lucent-init.sh  →  dynamic per-turn state
     │
     ▼
Both outputs joined and pushed as a synthetic <lucent-context> text part
     │
     ▼
Model sees full Lucent context before generating its first token. No tool call,
no model discretion, nothing to skip.
```

Every subsequent `chat.message` short-circuits `runStartup` (guard hit) and runs only
`runPerTurn` — exactly mirroring Claude Code's SessionStart-once / UserPromptSubmit-every-
turn shape.

### Startup/Per-Turn Ordering (race-condition fix, Phase 3)

Claude Code guarantees `SessionStart` fully completes — including writing the
`.startup_ready_<date>.txt` marker — before the first `UserPromptSubmit` ever runs (which
checks for that marker and fires the one-shot voice acknowledgment). The first cut of the
OpenCode plugin ran `runStartup()` and `runPerTurn()` in `Promise.all` (parallel), which
broke that guarantee: `lucent-init.sh` could check for the marker before `startup.py` had
written it, silently delaying the acknowledgment by a full turn.

Fix: both the `chat.message` hook and the `lucent_startup` manual-recovery tool now run
them **sequentially** — `await runStartup(...)` then `await runPerTurn(...)`. On the first
turn this costs a small amount of wall-clock time (correctness > speed for a one-time
event); on every later turn `runStartup` short-circuits via the guard, so the sequencing
costs nothing in steady state.

### NERO Reflection (Stop equivalent — translation shim pattern)

Claude Code's Stop hook pipes `{"transcript_path": "<jsonl>"}` to `reflect.py`, which parses
Claude-Code-shaped JSONL (`{"type": "user"|"assistant", "message": {"content": ...},
"uuid": ...}`) to extract the last exchange and decide whether to propose a memory/skill
update.

OpenCode stores session transcripts in its own SDK format (`client.session.messages`), not
as that JSONL. Rather than fork `reflect.py`'s gate/writer/proposal logic — the actual
"single source" that matters — the plugin's `buildClaudeShapedTranscript()` is a thin
**translation shim**: it re-shapes OpenCode's message history into the exact JSONL shape
`reflect.py` already knows how to read, writes it to `/tmp/lucent_oc_transcript_<id>.jsonl`,
and invokes `reflect.py` exactly as Claude Code's Stop hook does — same stdin contract, same
`hook_entry()`, same detached background worker, same dedup-by-uuid. Zero logic fork. The
trigger is OpenCode's `event` → `session.idle`, the closest equivalent to "the assistant has
finished responding and gone quiet."

### PreCompact (compaction guard)

`experimental.session.compacting` is OpenCode's **direct** documented equivalent of
`PreCompact` — same idea (inject must-keep context before the summarizer runs), just a
different append point (`output.context[]` vs. stdout). The plugin runs `pre_compact.py`
unmodified and appends its "must-keep" block to the compaction context.

### Soft voice-box enforcement (Phase 3)

Neither platform has a *blocking* mechanism for the three-layer voice rule — it's enforced
by convention (`CLAUDE.md` / `core.md`), and `validate_response.py` exists but isn't wired
into any hook on either side. The OpenCode plugin adds a **soft, additive** backstop using
`experimental.text.complete`: it records when each turn started, and at text-completion
time checks `ui/logs/activity_<date>.log` for a `[voice_box]` entry timestamped after that
moment (the same evidence trail the `/speak` endpoint already writes via `log_activity`).
If none is found, it appends a brief on-screen reminder to the response — deduped per
`messageID` so a multi-part response is never nagged twice, and **fails open** (assumes
compliance) if the log can't be read. It never blocks a response; it only nudges.

### `lucent_startup` tool — retained as manual recovery only

The historical voluntary `lucent_startup` tool still exists, but it is **no longer the
primary enforcement mechanism** — the `chat.message` hook now runs startup automatically,
removing the model-discretion failure mode entirely (see "Design History" for why the old
voluntary-tool design existed and what replaced it). The tool remains as the documented
recovery path: if a session ever looks "generic" (no Lucent context, no voice), Nick can
say *"run your lucent_startup tool"* to force a full re-init with `force=true` (bypasses
the once-per-session guard).

### Key files

| File | Role |
|---|---|
| `opencode.json` | Static instructions list (memory files) + plugin registration |
| `AGENTS.md` | Identity + protocol reference (no longer a startup *directive* — see Design History) |
| `.opencode/lucent-plugin.ts` | The plugin: registers automatic hooks + manual-recovery tool |
| `.opencode/package.json` | Declares `@opencode-ai/plugin` dependency, `"type": "module"` |
| `.opencode/settings.json` | Workspace env vars |

### Reliability

**High — now structurally equal to Claude Code.** The `chat.message` hook fires at the
platform level before the model sees any input, exactly like `UserPromptSubmit`. Context
injection, validation-gate output, NERO reflection, and the compaction guard are all
guaranteed every session/turn with no dependency on model behavior. The remaining
differences from Claude Code are matters of hook *plumbing* (TypeScript shim vs. native
registration), not reliability.

---

## Context Loading: What Each File Provides and Why

| File | Loaded by | What it provides | Why it's needed |
|---|---|---|---|
| `memory/core.md` | `opencode.json` instructions / `startup.py` bundle | Voice box requirement, three-layer protocol, sub-agent delegation, note protocol | The operating manual. If missing, the model doesn't know about voice box or logging requirements. |
| `memory/lucentIdent.md` | `opencode.json` instructions / `startup.py` bundle | Lucent's identity, personality, role | Without this, the model behaves as a generic assistant, not as Lucent. |
| `memory/userIdent.md` | `opencode.json` instructions / `startup.py` bundle | Nick's profile, preferences, working style | Enables personalized responses rather than generic assistance. |
| `memory/LTMemory.md` | `opencode.json` instructions / `startup.py` bundle | Projects, priorities, standing decisions, lessons | The persistent knowledge base. Tells the model what's being worked on and why. |
| `memory/REMINDERS.md` | `opencode.json` instructions / `lucent-init.sh` (filtered) | Active deadlines, recurring tasks, context triggers | Ensures the model surfaces time-sensitive information proactively. |
| `AGENTS.md` | Auto-discovered by OpenCode | Identity context + protocol reference | Platform-discovered system-prompt addendum. |
| Today's daily note (tail) | `lucent-init.sh`, every turn | What happened today, work in progress, recent decisions | Live session context; changes every turn. |
| Recent memories (semantic recall) | `lucent-init.sh` → `memory_recall.py`, every turn | Top-5 relevant memories via local Ollama embeddings | Surfaces exactly the context relevant to *this* message, not a fixed window. |

**What is deliberately NOT loaded into model context:**

- `memory/STARTUP_RITUAL.md` — Reference specification document. The hooks execute the
  ritual; the model doesn't need to read the spec.
- Archive files, old daily notes — Historical context is summarized in `LTMemory.md`.
- `docs/STARTUP_ARCHITECTURE.md` (this file), `docs/OPENCODE_PARITY_PLAN.md` — Developer
  documentation. Not needed in model context.

---

## Failure Modes and Debugging

### Mode 1: Plugin fails to load / hooks don't fire

**Symptom:** No `<lucent-context>` block appears in the conversation; the model behaves
generically with no voice, no recall, no reminders.

**Diagnosis:**
```bash
cd /home/nick/dev/lucent/.opencode
node --experimental-strip-types -e "import('./lucent-plugin.ts').then(m => console.log(Object.keys(m)))"
```
Check for TypeScript syntax errors. (OpenCode runs the plugin via its bundled Bun runtime —
standalone `bun` is *not* on PATH; `node --experimental-strip-types` is the verification
path that resolves the real `@opencode-ai/plugin` package from `.opencode/node_modules`.)

Check the package is installed:
```bash
ls /home/nick/dev/lucent/.opencode/node_modules/@opencode-ai/plugin
```
If missing, reinstall per the OpenCode plugin docs for this version.

**Recovery:** Say **"run your lucent_startup tool"** — the manual-recovery path still works
even if the automatic hooks are degraded (it's a separate registration in the same plugin).

---

### Mode 2: Startup ritual seems to run twice / voice acknowledgment delayed

**Symptom:** Two startup bundles inject in the same session, or the "Startup complete" voice
acknowledgment lands a turn late.

**Root cause (historical, fixed 2026-06-07):** `runStartup()` and `runPerTurn()` racing in
`Promise.all` let `lucent-init.sh` check the readiness marker before `startup.py` wrote it.
Now run sequentially — see "Startup/Per-Turn Ordering" above. If this resurfaces after a
plugin edit, check that the sequential `await` ordering wasn't reverted to parallel.

**Diagnosis:** Check `/tmp/lucent_oc_session_<sessionID>` exists after the first turn (the
once-per-session marker) and that `memory/.startup_ready_<date>.txt` is consumed (deleted)
by the very next `lucent-init.sh` run, not a turn later.

---

### Mode 3: Voice box fails / health check fails

**Symptom:** `startup.py`'s validation gate reports `voice_box=false`, or the soft
voice-box-compliance nudge fires even though you did call `/speak`.

**Diagnosis:**
```bash
curl -s http://localhost:8001/services/health
```
If no response, the voice box is down.

**Recovery:**
```bash
cd /home/nick/dev/lucent/ui && nohup bash start.sh > /tmp/lucent-voice-box.log 2>&1 &
```
Wait ~5 seconds, then retry. (If the soft-nudge false-positives despite a successful
`/speak` call, check that `ui/logs/activity_<date>.log` is being written — the nudge's
evidence source is the `[voice_box]`-tagged `log_activity()` line the `/speak` handler
writes on every successful call.)

---

### Mode 4: NERO reflection never fires under OpenCode

**Symptom:** `memory/nero_inbox.md` never accumulates proposals during OpenCode sessions,
even though the same conversations would generate them under Claude Code.

**Diagnosis:**
1. Confirm `event` → `session.idle` is actually firing (log inside `triggerReflection` if
   needed — it's wrapped in a silent `try/catch` by design).
2. Confirm `buildClaudeShapedTranscript()` is producing a non-null path — check for
   `/tmp/lucent_oc_transcript_<sessionID>.jsonl` after a turn completes.
3. Run `python3 scripts/reflect.py status` — same command works on both platforms (single
   source); if it reports healthy gate hit-rates from Claude Code sessions but nothing from
   OpenCode ones, the shim's translation step is the suspect.

---

### Mode 5: Compaction loses context

**Symptom:** After a long OpenCode session compacts, priorities/NERO state/skills that
should have been preserved are missing from the summary.

**Diagnosis:** `experimental.session.compacting` is an `experimental.*` API — confirm it
still exists in the installed `@opencode-ai/plugin` version and that `runPreCompactGuard()`
is returning non-empty output (`python3 scripts/pre_compact.py` should print a populated
"[NERO PreCompact — must-keep context...]" block when run directly).

---

## Design History: What Was Tried Before (2026-05 era — superseded)

This section is preserved because the lessons it documents remain true in general — they
just no longer describe *this system's* OpenCode integration, which moved to automatic
hooks on 2026-06-07.

### Attempt 1: Inline instructions in opencode.json
**What:** Placed ritual steps as inline text in `opencode.json` `instructions[]` array.
**Why it failed:** OpenCode's `instructions[]` only accepts file paths, not inline strings.
Inline text was silently ignored.

### Attempt 2: AGENTS.md with execution directives
**What:** Placed step-by-step execution instructions in AGENTS.md with "BEFORE FIRST
RESPONSE" language.
**Why it failed:** AGENTS.md is passive context. The model reads it as documentation and
decides whether to follow it. Result: model often said "Hello!" before attempting the ritual.

### Attempt 3: memory/STARTUP_RITUAL.md as execution guide
**What:** Extracted the ritual to a separate file, referenced from instructions, with
"EXECUTE BEFORE FIRST RESPONSE" as the first line.
**Why it failed:** Same root cause as Attempt 2 — loading a file as an instruction makes it
context, not a command.

### Attempt 4: Bash tool directive
**What:** Instructed the model to run `bash verify_startup.py check` as its first action.
**Why it failed:** `bash` is a generic tool; the model's decision to call it is discretionary
and gets skipped when it judges an immediate text response more appropriate.

### Attempt 5 → the voluntary `lucent_startup` tool era (2026-05-13 → 2026-06-07)
**What:** Registered `lucent_startup` (and, briefly, `startup_ritual_check` /
`startup_ritual_markComplete`) as MANDATORY-described tools in the plugin schema, with
AGENTS.md directing the model to call it as its first action, backed by a now-deleted
helper script (`startup-helper.py`) for the actual infrastructure checks.
**Result:** A real improvement over pure text instructions — tool-schema framing measurably
raised compliance. **But it was still fundamentally discretionary**: a model that decided to
respond before calling any tool skipped it entirely, and recovery required Nick to
explicitly say "run your lucent_startup tool."
**What replaced it:** The 2026-06-07 OpenCode Parity Plan discovered that `@opencode-ai/
plugin` had grown automatic hooks (`chat.message`, `event`, `experimental.*`) that didn't
exist — or weren't documented — when this design was chosen. Those hooks remove the
discretion entirely, the same way Claude Code's hooks always have. The voluntary tool is
retained only as a manual-recovery fallback (see "lucent_startup tool" above).

### Key Lesson (still true)
The passive-context problem is fundamental: *any rule that lives only as text in a context
file, or behind a tool the model can choose not to call, is at the model's discretion.*
Platform-level, automatically-firing hooks are the only fully reliable mechanism. As of
2026-06-07, **both** platforms now achieve this the same way.

---

## The Fallback Trigger: How to Recover a Broken Session

Automatic hooks make this rare, but if an OpenCode session somehow starts without Lucent
context (no voice, no `<lucent-context>` block, generic behavior):

### Option 1 (Most Reliable): Name the recovery tool directly
Say: **"Run your lucent_startup tool"**

Naming a specific tool by its exact name in the schema leaves no ambiguity. It forces a
full re-init (`force=true`, bypasses the once-per-session guard) and returns both the
identity bundle and current dynamic state directly in its tool result.

### Option 2 (Natural language): Use the mapped trigger phrase
Say: **"lucent init"**

`AGENTS.md` and the tool's own description map this phrase (and "run startup") to the
`lucent_startup` call.

---

## Maintenance Notes

### `startup-helper.py` was removed (2026-06-07)
`.opencode/startup-helper.py` was the infrastructure-check script the *old* voluntary
`lucent_startup` tool ran (voice box health + session logger init, returned as JSON). The
rewritten plugin (Phase 1, 2026-06-07) shells directly to `scripts/startup.py` instead —
the same single-source script Claude Code's `SessionStart` hook runs — so the helper had
become orphaned (`grep -n startup-helper .opencode/lucent-plugin.ts` returned nothing).
Confirmed dead and deleted via `git rm` the same day, on Nick's go-ahead. If you're reading
old commits or docs that still reference it, that's why it's gone — `scripts/startup.py`
is the live infrastructure-check path on both platforms now.

### When adding a new memory file
1. Add it to `opencode.json` `instructions[]` if it should be in static context, **and**
   to `startup.py`'s identity-bundle assembly (`print_identity_bundle`) so Claude Code gets
   it too — single source means both platforms should load the same files the same way.
2. If it's dynamic (changes per-session/turn), it belongs in `lucent-init.sh`'s per-turn
   output, not static instructions — that's what makes it show up on both platforms for free.

### When the @opencode-ai/plugin package needs updating
```bash
cd /home/nick/dev/lucent/.opencode && bun update @opencode-ai/plugin
```
Re-run the verification command from "Mode 1" above and check `lucent-plugin.ts` for any
hook-signature changes — especially the `experimental.*` hooks, which carry no stability
guarantee and must keep their no-op fallback behavior.

### When OpenCode version changes
Re-verify that all five hooks the plugin registers (`chat.message`, `event`,
`experimental.session.compacting`, `experimental.text.complete`, `tool.lucent_startup`)
still exist and fire as expected. The graceful-degradation wrappers mean a missing or
renamed `experimental.*` hook will silently no-op rather than crash — but a silent no-op
also means reduced parity, so this is worth checking explicitly after upgrades, not just
trusting it "didn't break."

---

## File Ownership Summary

| File | Owner | Change frequency | Notes |
|---|---|---|---|
| `scripts/startup.py` | Architecture / single-source | Occasional | SessionStart equivalent on both platforms — edit once, both benefit |
| `scripts/lucent-init.sh` | Architecture / single-source | Occasional | UserPromptSubmit equivalent on both platforms |
| `scripts/reflect.py` | Architecture / single-source | Occasional | Stop equivalent on both platforms (OpenCode via translation shim) |
| `scripts/pre_compact.py` | Architecture / single-source | Rare | PreCompact equivalent on both platforms |
| `.opencode/lucent-plugin.ts` | Architecture | Occasional | The only platform-specific "brain" file — pure plumbing, no logic forks |
| `opencode.json` | Architecture | Infrequent | Static instructions + plugin registration |
| `AGENTS.md` | Architecture | Infrequent | Identity + protocol reference (not a startup directive anymore) |
| `.claude/settings.json` | Architecture | Infrequent | Claude Code hook registration |
| `CLAUDE.md` | Claude Code config | Occasional | Platform-specific summary/pointer to the shared architecture |
| `memory/STARTUP_RITUAL.md` | Reference | Rare | Spec doc — update when ritual changes |
| `memory/core.md` | Operations | Occasional | Operating manual — central source of truth for voice/protocol rules |
| `docs/OPENCODE_PARITY_PLAN.md` | Architecture | Done (historical) | The plan that produced this architecture; keep for context on *why* |

---

*This document is developer/architecture reference. It is not loaded into model context.*
