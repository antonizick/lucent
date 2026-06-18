---
description: Alias for /newproject — scaffold a new Lucent idea/ project
---

This is an alias for `/newproject`. Run the canonical project-creation workflow in
`memory/skills/project-creation/SKILL.md` (and `.opencode/command/newproject.md`):
collect project info, propose a free port via `python3 scripts/new_project.py ports`,
**wait for Nick to confirm the port**, then scaffold with
`python3 scripts/new_project.py create …` (emits CLAUDE.md + AGENTS.md, dual-platform),
write the planning doc, register the project, and report ready (voice + daily note + text).

User input:

$ARGUMENTS
