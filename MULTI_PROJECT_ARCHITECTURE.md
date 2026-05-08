# Multi-Project Architecture (Hybrid Model)

## Overview

Lucent supports concurrent work across multiple projects in `idea/` folder using a **hybrid context model**: per-project daily notes for focus + shared LTMemory for knowledge transfer.

## Context Loading Strategy

### Project Activation (via .lucentrc)

Each project has a `.lucentrc` file in its root:

```
LUCENT_PROJECT=cyphertek
LUCENT_PROJECT_PATH=/home/nick/dev/lucent/idea/cyphertek
```

On session start, startup ritual reads `.lucentrc` and loads:

1. **Shared across all projects** (always loaded):
   - `core.md` (operating manual)
   - `lucentIdent.md` (Lucent personality)
   - `userIdent.md` (Nick profile)
   - `LTMemory.md` (cross-project knowledge, lessons, patterns)
   - Last 7 days of **root-level** daily notes from `memory/`

2. **Project-specific** (when in a project):
   - `idea/{project}/memory/YYYY-MM-DD.md` (today's project note)
   - `idea/{project}/README.md` (project context)
   - `idea/{project}/.lucentrc` (project config)

### Context Window Hierarchy

**Always present:**
- core.md (operating manual)
- lucentIdent.md (personality)
- userIdent.md (profile)
- LTMemory.md (shared knowledge)

**When in a project:**
- Project README (overview, current state)
- Today's project daily note (working log)
- Last N days of project daily notes (if needed for context)

**When in Lucent root:**
- Lucent-level daily notes
- System architecture notes (CLAUDE.md, AGENTS.md, etc.)

## Memory Structure

```
lucent/
├── core.md
├── lucentIdent.md
├── userIdent.md
├── LTMemory.md                    # Shared across all projects
├── memory/
│   ├── YYYY-MM-DD.md             # Lucent session notes (root-level)
│   └── archive/                   # Old compressed notes
├── idea/
│   ├── cyphertek/
│   │   ├── .lucentrc              # Project config
│   │   ├── README.md              # Project overview
│   │   ├── memory/
│   │   │   ├── YYYY-MM-DD.md     # Project daily notes
│   │   │   └── archive/
│   │   └── [project files]
│   ├── moviemaj/
│   │   ├── .lucentrc
│   │   ├── README.md
│   │   ├── memory/
│   │   └── [project files]
│   └── [9 other projects...]
```

## Daily Note Convention

**Root-level daily notes** (`memory/YYYY-MM-DD.md`):
- Lucent system work (Voice Box updates, agent design, framework changes)
- Cross-project observations and decisions
- Session summaries that affect all projects

**Project-level daily notes** (`idea/{project}/memory/YYYY-MM-DD.md`):
- Work specific to that project
- Technical decisions for the project
- Progress and blockers
- NOT synced to shared LTMemory (unless pattern is relevant across projects)

## Agent Scope

Agents read context based on current project:

- **In Lucent root:** Agents see shared knowledge, Lucent architecture, system-level work
- **In a project:** Agents see shared knowledge + project-specific README + project daily notes

**Example:** Git agent in cyphertek:
1. Loads shared LTMemory (decisions, patterns)
2. Loads cyphertek README (what the project is)
3. Loads today's cyphertek daily note (current progress)
4. Reads core.md, identity files
5. Commits with proper context for that project

Agents can reference shared LTMemory for cross-project patterns without being distracted by other projects' working logs.

## Workflow: Context Switching

**Scenario:** Nick finishes work in cyphertek, switches to moviemaj.

```bash
cd /home/nick/dev/lucent/idea/moviemaj
# .lucentrc is auto-detected by Claude Code
# Next Lucent session automatically loads:
# - Shared: core.md, identities, LTMemory
# - Project: moviemaj README, moviemaj daily note
```

No manual context reset. .lucentrc wires the switch automatically.

## Implementation Details

### Startup Ritual (Updated)

1. Read core.md, lucentIdent.md, userIdent.md
2. Detect current project via `.lucentrc` (if exists)
3. Load shared context: LTMemory.md, last 7 days of root daily notes
4. If in a project: load project README, today's project daily note
5. Compress yesterday's note if new day
6. Begin work

### .lucentrc Template

```
# Project identity
LUCENT_PROJECT=projectname
LUCENT_PROJECT_PATH=/home/nick/dev/lucent/idea/projectname

# Optional: Project-specific settings
LUCENT_PROJECT_MODEL=mistral:latest
LUCENT_PROJECT_FOCUS=backend
```

### Project README Format

**Minimal structure** (each project populates as needed):

```markdown
# ProjectName

**Current status:** [1-2 sentences on what's happening]
**Next steps:** [Prioritized list]
**Key files:** [Paths to critical code/config]
**Recent decisions:** [Architecture or direction decisions]
```

## Knowledge Transfer: LTMemory Maintenance

**Rule:** Patterns that appear in 2+ projects → promote to LTMemory.

**Examples of cross-project patterns:**
- Authentication approach that worked in Project A, useful in Project B
- Deployment strategy learned in Project C
- Common architectural mistakes to avoid
- Lessons about Nick's development patterns

**Process:** Curator agent (or Lucent) periodically reviews project notes and promotes recurring insights to LTMemory.

## Benefits of Hybrid Model

1. **Focus:** Project context loads only project-relevant work
2. **Knowledge reuse:** Patterns and lessons shared via LTMemory
3. **Isolation:** Projects don't clutter each other's daily notes
4. **Scalability:** Can add projects without context explosion
5. **Flexibility:** Agents can cross-project (via shared memory) when needed
6. **Low friction:** .lucentrc already exists; minimal setup per project

## Future Extensions

- **Project teams:** Support multiple sub-projects under one umbrella
- **Shared project memory:** Some projects might share a `.shared_memory.md`
- **Cross-project agents:** Agents that coordinate work across projects
- **Project archival:** Move completed projects to memory/archive with snapshot
