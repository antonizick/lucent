---
description: Scaffold a new Lucent idea/ project (port-deconflicted, voice+note enforced)
---

You are creating a new Lucent project. Follow this workflow exactly — it is the
canonical project-creation procedure (full spec: `memory/skills/project-creation/SKILL.md`).

User input (may be empty — if so, ask for the missing fields conversationally):

$ARGUMENTS

## Workflow

**1. Collect project info.** You need: `name`, `purpose`, `type` (lightweight/full),
`tech`, `scope-in`, `scope-out`, `features` (list), `reference` (optional). If the
user gave a free-form description, parse what you can and ask only for what's missing.

**2. Propose a port — DO NOT pick silently.** Run:
```
python3 scripts/new_project.py ports
```
Show Nick the proposed free ports and any DRIFT warning. **Wait for him to confirm
which port to use.** Port deconfliction is a hard mandate; he confirms every time.
If drift is reported, mention it — those ports should be added to `idea/PORTS.md`.

**3. Scaffold with the confirmed port:**
```
python3 scripts/new_project.py create --name "<Name>" --port <confirmed> \
  --purpose "<...>" --type <lightweight|full> --tech "<...>" \
  --scope-in "<...>" --scope-out "<...>" \
  --features "Feat A||Feat B||Feat C" --reference "<...>"
```
This creates the dir, CLAUDE.md (with the port baked in), planning.md, README.md,
.gitignore, .lucentrc, appends the ledger row, and registers the port in
`idea/project-health.sh`. Both port files stay in sync — this is mandatory.

**4. Write a real planning doc** if the project is non-trivial — create
`memory/<name>_planning.md` (the path the CLAUDE.md already declares) with goals,
tech stack, phases, and key decisions. Recommend a model per phase.

**5. Register the project** in `memory/LTMemory.md` (Projects section) and add a
project memory so NERO recall indexes it.

**6. Report ready** — voice + daily note + text. Tell Nick the project is scaffolded,
what port it got, and the launch command: `cd idea/<Name> && claude`.

Remember the per-response protocol throughout: voice box + daily note + text.
