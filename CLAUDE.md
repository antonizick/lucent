# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## What This Repo Is

A personal AI assistant framework based on the ai-shared-brain starter kit. Lucent manages persistent memory through markdown files that AI agents read and write. See `ai-shared-brain/` submodule for the shared brain architecture.

## File Structure

```
lucent/
├── ai-shared-brain/    — Git submodule: AI shared brain architecture
│   ├── core.md         Startup ritual, core rules (NOT personality)
│   ├── lucentIdent.md  Lucent's identity (personality, actions, habits)
│   ├── userIdent.md    Nick's identity (facts, expectations, preferences)
│   ├── LTMemory.md     Long-term memory (agent-curated from daily notes)
│   ├── agents/         Sub-agent definitions: {name}-agent.md
│   └── memory/         Daily episodic notes: YYYY-MM-DD.md
├── idea/               Working directory
└── AGENTS.md           Top-level instructions
```

## How the System Works

The key mechanism is the **startup ritual** in `core.md`: before doing anything, the agent reads lucentIdent.md, userIdent.md, LTMemory.md, and today's/yesterday's daily note. This creates session-to-session continuity.

- **core.md** — Operating manual with startup ritual, memory rules, safety guidelines
- **lucentIdent.md** — Lucent's identity (personality, behaviors, habits)
- **userIdent.md** — Nick's profile (facts, expectations, preferences)
- **LTMemory.md** — Distilled long-term knowledge (agent curates from daily notes)
- **agents/** — Sub-agent definition files ({name}-agent.md) with their own personalities
- **memory/YYYY-MM-DD.md** — Daily episodic notes (never deleted, accumulate over time)

## Working With This Repo

Changes are typically:
- Editing identity/memory files
- Adding or modifying sub-agents in agents/
- Creating daily memory notes during active work
- Working on projects in idea/
