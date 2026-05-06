# AGENTS.md

## Repo geometry

```
lucent/
├── ai-shared-brain/    — Git submodule: AI shared brain (Lucent's architecture)
│   ├── core.md          Startup ritual, core rules (NOT personality)
│   ├── lucentIdent.md   Lucent's identity (personality, actions, habits)
│   ├── userIdent.md     Nick's identity (facts, expectations, preferences)
│   ├── LTMemory.md      Long-term memory (agent-curated from daily notes)
│   ├── agents/          Sub-agent definitions: {name}-agent.md
│   └── memory/          Daily episodic notes: YYYY-MM-DD.md
└── idea/                Working directory — create project here
```

## Constraints

- **`ai-shared-brain/` is a submodule.** Edit its files via `git -C ai-shared-brain` or `cd ai-shared-brain && <cmd>`, not through the parent repo.
- **`idea/` is where you work.** Everything goes here.
- **Every AI agent reads `core.md`** — it's the universal operating manual before anything else.
- **Personality per agent** — each agent has its own identity file, not shared.
