# Lucent Startup Architecture

**Last updated:** 2026-05-13  
**Status:** Production — both platforms operational

This document explains how the Lucent startup ritual is implemented across Claude Code and
OpenCode, why the architecture was designed the way it was, what was tried and failed
before arriving at the current design, and how to debug it when something goes wrong.

---

## The Core Problem This Architecture Solves

AI assistants have no persistent memory between sessions. Each session starts cold — the
assistant has no knowledge of Nick, the Lucent system, ongoing projects, or the voice box
requirement unless that information is explicitly loaded into context.

The startup ritual is the solution: a defined sequence that loads identity, memory, and
live context before the assistant generates its first response. The architectural challenge
is making this sequence *reliable* — ensuring it actually runs every session, not just
when Nick manually triggers it.

The fundamental insight that shaped this architecture:

> **Documentation in context is passive. Tool calls in schema are binding.**

An instruction file saying "execute these steps before responding" is treated as optional
documentation by the model. A tool in the model's schema marked MANDATORY is treated
as a required action. This distinction drives every design decision below.

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    LUCENT SYSTEM FILES                       │
│                                                             │
│  memory/                                                    │
│  ├── core.md              ← Operating manual (all platforms)│
│  ├── lucentIdent.md       ← Who Lucent is                   │
│  ├── userIdent.md         ← Who Nick is                     │
│  ├── LTMemory.md          ← Long-term memory + priorities   │
│  ├── REMINDERS.md         ← Active reminders                │
│  ├── STARTUP_RITUAL.md    ← Ritual specification (ref doc)  │
│  └── YYYY-MM-DD.md        ← Daily session notes             │
│                                                             │
│  scripts/                                                   │
│  ├── session_logger.py    ← Daily note initialization       │
│  └── check_reminders.py   ← Pattern-based reminder checks   │
└─────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌──────────────────────┐
│   CLAUDE CODE   │          │      OPEN CODE        │
│                 │          │                       │
│  CLAUDE.md      │          │  AGENTS.md            │
│  (hooks, steps) │          │  (binding directive)  │
│                 │          │                       │
│  UserPromptSubmit│         │  opencode.json        │
│  hook injects   │          │  (loads memory files, │
│  all context    │          │   registers plugin)   │
│  at turn start  │          │                       │
│                 │          │  .opencode/           │
│                 │          │  ├── lucent-plugin.ts │
│                 │          │  ├── startup-helper.py│
│                 │          │  ├── settings.json    │
│                 │          │  └── package.json     │
└─────────────────┘          └──────────────────────┘
```

---

## Claude Code Implementation

### How it works

Claude Code's `UserPromptSubmit` hook runs a shell script before the model sees any user
message. This gives platform-level enforcement with no dependency on model behavior.

The hook (defined in `.claude/hooks/` or via `settings.json`) runs `lucent-init.sh`, which:
1. Reads and injects all memory files into the conversation context
2. Initializes session logging
3. Checks voice box health

`CLAUDE.md` then provides step-by-step directives the model follows after context is
already loaded. Because the heavy lifting is done by the hook (not the model), CLAUDE.md
directives are executed against a rich, pre-loaded context rather than being ignored as
passive documentation.

### Key files

| File | Role |
|---|---|
| `CLAUDE.md` | Platform config: startup steps, voice box template, response requirements |
| `.claude/settings.json` | Hook registration and permissions |
| `scripts/session_logger.py` | Session init, daily note management |
| `scripts/check_reminders.py` | Pattern-based reminder evaluation |

### Reliability

**High.** The `UserPromptSubmit` hook fires at the OS/framework level before the model
receives any input. The model cannot skip it. Context injection is guaranteed.

---

## OpenCode Implementation

### How it works

OpenCode does not have a `UserPromptSubmit`-equivalent hook. Context loading and execution
enforcement must be accomplished through two mechanisms:

1. **Static context loading** (`opencode.json` instructions) — loads memory files into the
   model's context window before the first turn
2. **Plugin tool enforcement** (`.opencode/lucent-plugin.ts`) — registers `lucent_startup`
   in the model's tool schema, providing a binding execution mechanism

```
Session start
     │
     ▼
opencode.json instructions[] loaded
→ core.md, lucentIdent.md, userIdent.md, LTMemory.md, REMINDERS.md
(model now has identity, memory, priorities, reminders in context)
     │
     ▼
AGENTS.md appended to system prompt (auto-discovered)
→ "Call lucent_startup before first response"
     │
     ▼
Model sees lucent_startup in tool schema
→ Tool description: "MANDATORY: Call before first response"
     │
     ▼
Model calls lucent_startup
→ startup-helper.py runs (voice box + session logger)
→ today's daily note injected into conversation
→ protocol reminder returned
     │
     ▼
Model has full context. Session proceeds as Lucent.
```

### What `lucent_startup` does

The tool (`.opencode/lucent-plugin.ts`) executes three steps when called:

**Step 1 — Infrastructure check**  
Runs `.opencode/startup-helper.py`, which:
- Calls `GET localhost:8001/services/health` to verify voice box is online
- Runs `scripts/session_logger.py init` to initialize today's daily note
- Returns JSON status with `voice_box_online`, `session_logger_init`, `ritual_ready`

**Step 2 — Dynamic context injection**  
Reads the last 3 daily notes and injects them into the conversation:
- **Today** (`memory/YYYY-MM-DD.md`): last 3000 chars — most detail, current in-progress work
- **Yesterday**: last 1500 chars — recent context; already Curator-compressed to 1–2 paragraphs
- **Two days ago**: last 1000 chars — background context; already compressed

This is the part that cannot be static — daily notes change every session and day. Previous
notes are compressed by Curator at session start, so token cost is low. This mirrors Claude
Code's 7-day window but scoped to 3 days to avoid excessive context in the tool return value.

**Step 3 — Protocol assertion**  
Returns a protocol reminder: voice curl command format, daily note path for today, and
three-layer requirement. This re-asserts compliance at session start.

### Key files

| File | Role |
|---|---|
| `opencode.json` | Instructions list (static memory files) + plugin registration |
| `AGENTS.md` | Startup directive + three-layer requirement + key rules |
| `.opencode/lucent-plugin.ts` | Plugin: registers `lucent_startup` tool |
| `.opencode/startup-helper.py` | Infrastructure check: voice box + session logger |
| `.opencode/settings.json` | Workspace config: env vars, OpenCode-specific settings |
| `.opencode/package.json` | Declares `@opencode-ai/plugin` dependency |

### Why the plugin tool approach works

The model's reasoning about tool use differs fundamentally from its reasoning about text
instructions. When a tool appears in the schema with MANDATORY in its description, the
model's tool-use decision-making prioritizes it as a required pre-step. Text instructions
in AGENTS.md saying "execute these steps" are read as documentation and can be skipped
by the model when it decides that an immediate text response is more appropriate.

A named tool with "MANDATORY: Call before first response" in its description is not skipped
in the same way. The model's tool-use reasoning treats it as an obligation.

**This is not 100% guaranteed** — no text-based enforcement mechanism is. But it
dramatically improves reliability compared to instruction-only approaches, which have
historically failed in production sessions.

### Reliability

**Medium-High.** Substantially more reliable than pure instruction-file approaches. The
binding failure mode is a model that decides to generate text before calling any tools.
This is rare with capable models (Claude via Anthropic, strong cloud models) but more
common with weaker local models. See Failure Modes below.

---

## Context Loading: What Each File Provides and Why

| File | Loaded by | What it provides | Why it's needed |
|---|---|---|---|
| `memory/core.md` | opencode.json instructions | Voice box requirement, three-layer protocol, sub-agent delegation, note protocol | The operating manual. If missing, model doesn't know about voice box or logging requirements. |
| `memory/lucentIdent.md` | opencode.json instructions | Lucent's identity, personality, role | Without this, model behaves as a generic assistant, not as Lucent. |
| `memory/userIdent.md` | opencode.json instructions | Nick's profile, preferences, working style | Enables personalized responses rather than generic assistance. |
| `memory/LTMemory.md` | opencode.json instructions | Projects, priorities, standing decisions, lessons | The persistent knowledge base. Tells the model what's being worked on and why. |
| `memory/REMINDERS.md` | opencode.json instructions | Active deadlines, recurring tasks, context triggers | Ensures the model surfaces time-sensitive information proactively. |
| `AGENTS.md` | Auto-discovered by OpenCode | Startup directive, three-layer requirement, key rules | Platform-specific binding directive for OpenCode. |
| Today's daily note | `lucent_startup` tool | What happened today, work in progress, recent decisions | Live session context. Changes every day — cannot be in static instructions. |
| Yesterday's note | `lucent_startup` tool | Most recent completed session summary (Curator-compressed) | Continuity from previous session. |
| Two days ago note | `lucent_startup` tool | Background context (Curator-compressed) | Recent history without going too far back. |

**What is deliberately NOT loaded:**

- `memory/STARTUP_RITUAL.md` — This is a reference specification document. The model doesn't
  need to read the spec to execute the ritual; the tool and AGENTS.md provide execution
  directives. Loading it would add context bloat without behavioral value.
- Archive files, old daily notes — Historical context is summarized in LTMemory.md.
  Loading raw old notes would flood context unnecessarily.
- `docs/STARTUP_ARCHITECTURE.md` (this file) — Developer documentation. Not needed in
  model context.

---

## Failure Modes and Debugging

### Mode 1: Model responds before calling lucent_startup

**Symptom:** OpenCode says "Hello!" or gives a generic response without using the voice box.

**Root cause:** The model chose to generate text before calling any tools. This is the
primary failure mode for the tool-enforcement approach.

**Diagnosis:**
1. Check if the `lucent_startup` tool appeared in OpenCode's tool list. If not, the plugin
   failed to register. Check `.opencode/lucent-plugin.ts` for syntax errors.
2. If the tool is registered but wasn't called, the model skipped it. More common with
   weaker models.

**Recovery:** Nick says **"run your lucent_startup tool"** — naming the tool explicitly
forces the model to call it.

**Long-term fix:** Use a more capable model for sessions where Lucent compliance matters.

---

### Mode 2: lucent_startup called but voice box fails

**Symptom:** Tool returns `voice_box_online: false` or `ritual_ready: false`.

**Diagnosis:**
```bash
curl -s http://localhost:8001/services/health
```
If no response: voice box is down.

**Recovery:**
```bash
cd /home/nick/dev/lucent/ui && nohup bash start.sh > /tmp/lucent-voice-box.log 2>&1 &
```
Wait 5 seconds, then call `lucent_startup` again.

---

### Mode 3: Session logger fails

**Symptom:** Tool returns `session_logger_init: false`.

**Diagnosis:**
```bash
python3 /home/nick/dev/lucent/scripts/session_logger.py init
```
Check for Python errors. Common causes: missing `memory/` directory, permissions issue.

---

### Mode 4: Context loaded but model ignores voice box requirement

**Symptom:** Model responds with text only, no voice curl.

**Root cause:** `core.md` is loaded but the model is treating the voice box requirement
as advisory documentation rather than a mandatory protocol.

**Recovery:** Nick says **"use the voice box"** — explicit instruction overrides passive
context. Once corrected in-session, the model usually maintains compliance.

**Long-term:** The `lucent_startup` tool returns a protocol assertion at the end of its
output, which re-activates compliance. Calling the tool again resets protocol compliance.

---

### Mode 5: Plugin fails to load

**Symptom:** `lucent_startup` tool does not appear in OpenCode's tool list at session start.

**Diagnosis:** Check for TypeScript syntax errors in `.opencode/lucent-plugin.ts`. OpenCode
uses Bun to execute the plugin — Bun will fail silently if the file has errors.

```bash
cd /home/nick/dev/lucent && bun .opencode/lucent-plugin.ts 2>&1
```

Check that `@opencode-ai/plugin` is installed:
```bash
ls /home/nick/dev/lucent/.opencode/node_modules/@opencode-ai/plugin
```

If missing: `cd .opencode && bun install`

---

## Design History: What Was Tried Before

This architecture is the result of multiple failed approaches. Understanding the failures
explains why the current design is structured the way it is.

### Attempt 1: Inline instructions in opencode.json
**What:** Placed ritual steps as inline text in `opencode.json` `instructions[]` array.  
**Why it failed:** OpenCode's `instructions[]` only accepts file paths, not inline strings.
Inline text was silently ignored.

### Attempt 2: AGENTS.md with execution directives
**What:** Placed step-by-step execution instructions in AGENTS.md with "BEFORE FIRST RESPONSE"
language.  
**Why it failed:** AGENTS.md is passive context. The model reads it as documentation and
decides whether to follow it based on what it considers most immediately appropriate.
Result: model often said "Hello!" before attempting the ritual.

### Attempt 3: memory/STARTUP_RITUAL.md as execution guide
**What:** Extracted ritual to a separate file, referenced from instructions. Included
"EXECUTE BEFORE FIRST RESPONSE" as the first line.  
**Why it failed:** Same root cause as Attempt 2. Loading a file as an instruction makes
it context, not a command. The model treated it as documentation.

### Attempt 4: Bash tool directive
**What:** Instructed model to run `bash verify_startup.py check` as its first action.  
**Why it failed:** `bash` is a generic tool. The model's decision to call it is discretionary.
When it decided a text response was immediately appropriate, the bash call was skipped.

### Attempt 5: Custom TypeScript tools (startup-ritual.ts)
**What:** Created `.opencode/tools/startup-ritual.ts` registering `startup_ritual_check`
and `startup_ritual_markComplete` tools with MANDATORY descriptions.  
**Result:** **This worked.** The tool approach was functional.  
**What happened:** These files were created by a session that later had its commits
reverted as part of a `.opencode` directory recovery operation (the session had
accidentally deleted `settings.json` and added corrupted files). The tool files, which
were working correctly, were removed as collateral damage.

**Current implementation (`.opencode/lucent-plugin.ts`) is the direct successor to
Attempt 5** — same approach, proper plugin SDK, better documented, with a combined
startup tool that also injects daily note context.

### Key Lesson
The passive-context problem is fundamental: *any rule that lives only as text in a context
file is at the model's discretion*. Platform-level enforcement (hooks, registered tools)
is the only reliable mechanism. Claude Code achieves this via hooks. OpenCode achieves it
via plugin-registered tools.

---

## The Fallback Trigger: How to Recover a Broken Session

If an OpenCode session starts without running the startup ritual (model behaves generically,
no voice, no context), Nick has two recovery options:

### Option 1 (Most Reliable): Name the tool directly
Say: **"Run your lucent_startup tool"**

This is the most reliable recovery. Naming a specific tool by its exact name in the schema
leaves no ambiguity for the model. It will call it.

### Option 2 (Natural language): Use the mapped trigger phrase
Say: **"lucent init"**

AGENTS.md maps this phrase to the lucent_startup tool call. Works with capable models.
May require rephrasing with weaker models.

### Why these work better than "run the startup ritual"
The phrase "run the startup ritual" is natural language that the model might interpret
as "tell me about the startup ritual" or "proceed as if you ran it." Naming the tool
directly — `lucent_startup` — produces an unambiguous action: call that specific function.

---

## Maintenance Notes

### When adding a new memory file
1. Add it to `opencode.json` `instructions[]` if it should be in static context
2. Assess whether it should also appear in Claude Code's hook context (CLAUDE.md STEP 1)
3. If it's dynamic (changes per-session), consider having `lucent_startup` read it

### When the @opencode-ai/plugin package needs updating
```bash
cd /home/nick/dev/lucent/.opencode && bun update @opencode-ai/plugin
```
Check `.opencode/lucent-plugin.ts` for any API changes after updating.

### When OpenCode version changes
OpenCode may change how AGENTS.md is discovered or how plugins are registered. If startup
reliability degrades after an OpenCode upgrade, check:
1. Is AGENTS.md still auto-discovered? (Check if its content appears in system prompt)
2. Is the plugin still loading? (Check if lucent_startup appears in tool list)
3. Has the `instructions[]` format changed in opencode.json?

---

## File Ownership Summary

| File | Owner | Change frequency | Notes |
|---|---|---|---|
| `opencode.json` | Architecture | Infrequent | Add plugins or instructions here |
| `AGENTS.md` | Architecture | Infrequent | Directive file — keep concise |
| `.opencode/lucent-plugin.ts` | Architecture | Rare | Only change if tool behavior needs updating |
| `.opencode/startup-helper.py` | Architecture | Rare | Change if startup checks change |
| `memory/STARTUP_RITUAL.md` | Reference | Rare | Spec doc — update when ritual changes |
| `memory/core.md` | Operations | Occasional | Operating manual — central source of truth |
| `CLAUDE.md` | Claude Code config | Occasional | Platform-specific steps for Claude Code |

---

*This document is developer/architecture reference. It is not loaded into model context.*
