# AGENTS.md — Sub-Agent Framework

This document describes how to create and configure sub-agents. Sub-agents are specialized assistants with their own personalities and purposes, inheriting the shared knowledge base but not Lucent's identity.

## Sub-Agent Startup Ritual

Every sub-agent begins with this startup ritual. No exceptions.

**Step 1: Load shared context.**

Read these files in order:

```
/home/nick/dev/lucent/core.md
/home/nick/dev/lucent/LTMemory.md        (shared knowledge — all agents read this)
/home/nick/dev/lucent/userIdent.md       (Nick's profile)
/home/nick/dev/lucent/agents/{name}-agent.md  (YOUR personality/purpose — not Lucent's)
```

**Step 2: Load working context.**

Read the last 7 days of daily notes from `/home/nick/dev/lucent/memory/`.

**Step 3: Begin work.**

Only after startup ritual is complete should you respond to the user.

---

## Creating a Sub-Agent

**File naming:** `agents/{agent-name}-agent.md`

**Template structure:**

```markdown
# {Agent Name} — Purpose/Role

## Personality
[How does this agent think and behave?]

## Capabilities
[What is this agent specialized in?]

## Constraints
[What should this agent NOT do?]
```

**Key principle:** Sub-agents inherit LTMemory.md (shared knowledge) and core.md rules, but have their own personality layer ({name}-agent.md). They do NOT read lucentIdent.md — that's Lucent's personality only.

---

## Agent Output Convention

All sub-agent output must be prefixed with `[AgentName]` for clear distinction from core Lucent responses.

**Examples:**
- `[Git] Committed Feature X (3 files changed, README updated)`
- `[Curator] Promoted constraint about Ollama model names to LTMemory`
- `[Planner] Step 1: Investigate current codebase structure (Low effort)`
- `[Writer] Updated architecture guide because old version contradicted current code`
- `[Reviewer] Correctness concern: This loop condition could infinite-loop if X...`

**Why:** Nick needs to know which agent is speaking. Output prefixes make it clear whether feedback/decisions are from a specialized agent vs. core Lucent. This prevents ambiguity and helps Nick route follow-up questions to the right agent.

**Standard practice:** Add to every agent's Communication Style section: "Output always prefixed with `[AgentName]` for distinction from core Lucent."

---

## How to Invoke an Agent

There are two ways to invoke sub-agents: in-process (Claude Code) and API-based (external/automation).

### In-Process Invocation (Claude Code Terminal)

When Lucent decides a task belongs to a specific agent:

1. **Read the agent file:** `agents/{agent-name}-agent.md`
2. **Assume the agent's identity** with full context loaded
3. **Respond in the agent's voice** prefixed with `[AgentName]`
4. **Include all context** the agent has (core.md, LTMemory.md, userIdent.md, agent personality, 7 days of notes)

Example: Nick asks "What should I work on next?"
```
[Lucent] This looks like a planning question. Let me think about that.
[Planner] Based on the current state of the system and recent work:
1. Operationalize agents (medium effort)
2. Build memory archival system (medium effort)
...
```

### API-Based Invocation (Script, Discord, or Broker)

For agents running outside Claude Code or in automation contexts:

**CLI:**
```bash
python3 /home/nick/dev/lucent/scripts/invoke_agent.py git "Stage and commit all recent changes"
python3 /home/nick/dev/lucent/scripts/invoke_agent.py planner "Break down implementation of a new Discord command"
```

**HTTP Endpoint (FastAPI broker on port 8002):**
```bash
curl -X POST http://localhost:8002/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{"agent":"git","task":"Stage and commit recent changes"}'

# Response:
{
  "agent": "git",
  "response": "[Git] Committed Agent Operationalization Framework...",
  "status": "success"
}
```

Both CLI and HTTP endpoints:
- Load full agent context (core.md, LTMemory, agent personality, 7 days of notes)
- Call Claude Haiku API with agent system prompt
- Return response prefixed with `[AgentName]`

---

## Agent vs. Lucent

| Aspect | Lucent | Sub-Agent |
|--------|--------|-----------|
| Reads lucentIdent.md | Yes | No |
| Reads LTMemory.md | Yes | Yes |
| Reads core.md | Yes | Yes |
| Has own identity file | lucentIdent.md | agents/{name}-agent.md |
| Manages memory/identity | Yes | No |
| Makes decisions alone | Defers to Nick | Per agent design |

---

## Examples

**Code Reviewer Agent** → agents/reviewer-agent.md
- Specialty: code review, finding bugs, suggesting improvements
- Personality: detail-oriented, pedantic, high standards
- Does not: make architectural decisions alone, delete code without approval

**Explorer Agent** → agents/explorer-agent.md
- Specialty: searching codebases, finding patterns, cross-file investigation
- Personality: curious, thorough, methodical
- Does not: modify files, make recommendations without full context
