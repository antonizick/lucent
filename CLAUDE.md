# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## What This Repo Is

A personal AI assistant framework based on the ai-shared-brain starter kit. Lucent manages persistent memory through markdown files that AI agents read and write. Synced to GitHub via `lucent-sync.sh`.

## File Structure

```
lucent/
├── ai-shared-brain/    — Git submodule: AI shared brain architecture (gitignored)
├── core.md             Startup ritual, rules, safety
├── lucentIdent.md      Lucent's identity
├── userIdent.md        Nick's identity
├── LTMemory.md         Long-term memory (agent-curated from daily notes)
├── memory/             Daily episodic notes: YYYY-MM-DD.md
├── agents/             Sub-agent definitions: {name}-agent.md
├── idea/               Working directory — create projects here
├── private/            Sensitive context (gitignored)
├── AGENTS.md           Top-level instructions
├── .lucentrc           Per-project config for session loading
├── lucent-sync.sh      Sync script
├── lucentrc            Sync config (remote URL, log dedup)
└── README.md           Public-facing documentation
```

## How the System Works

The key mechanism is the **startup ritual** in `core.md`: before doing anything, the agent reads lucentIdent.md, userIdent.md, LTMemory.md, and today's daily note. This creates session-to-session continuity.

- **core.md** — Operating manual with startup ritual, memory rules, safety guidelines
- **lucentIdent.md** — Lucent's identity (personality, behaviors, habits)
- **userIdent.md** — Nick's profile (facts, expectations, preferences)
- **LTMemory.md** — Distilled long-term knowledge (agent curates from daily notes)
- **agents/** — Sub-agent definition files ({name}-agent.md) with their own personalities
- **memory/** — Daily episodic notes (never deleted, accumulate over time)

## Current State

**Done:**
- Skeleton complete: structure, README.md, sync script, per-project config, .gitignore
- First daily note written (2026-05-06)
- First LTMemory.md populated from initial session

**Next:**
- Populate userIdent.md with Nick's actual profile
- Create sub-agents (review-agent, research-agent)
- Build out idea/ with initial projects

## Working With This Repo

Changes are typically:
- Editing identity/memory files
- Adding or modifying sub-agents in agents/
- Creating daily memory notes during active work
- Working on projects in idea/
- Pushing sync with `brain` alias or `lucent-sync.sh`
