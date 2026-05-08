# Nick's Identity

## Demographics

- **Name:** Nick
- **Timezone:** UTC-6
- **Location:** [TBD]

## Role

**Building Lucent** — personal AI assistant framework with persistent memory, voice interface, and multi-agent architecture. Architect and lead designer. Works across multiple projects stored in /home/nick/dev/

## Preferences

- Concise, terse responses — no filler
- Voice dictation often converts "Lucent" → "loosened" — assume Lucent when unclear
- Directives must be captured in memory AND acted on immediately in current session, not deferred
- Expects proactive collaboration — peer-level thinking, independent suggestions, not deferential compliance

## Tools

- **Claude Code** — Primary development interface (terminal, in-process agent invocation)
- **Voice Box** — Web UI (localhost:8001) for voice feedback output
- **Discord** — Command interface and logging output
- **Ollama** — Local model inference (mistral:latest, qwen3.6:35b)
- **Systemd** — Service management (lucent-server, lucent-voice-box, lucent-poller, discord-bot, lucent-monitor)

## Projects

- **Lucent** — Personal AI assistant framework (primary, /home/nick/dev/lucent/)
- **idea/ folder contains:** _backups, _workingArea, cyphertek, moviemaj, nx3d, nxcitadel, nxtm, nxytdl, t3 (local development, excluded from git)

## Goals

- Complete Lucent as a working personal AI assistant with full multi-agent support
- Operationalize sub-agents (Reviewer, Curator, Writer, Planner, Git) for specialized tasks
- Design collaborative workflows for multi-project development
- Implement memory archival and pruning system (Curator-based)
- Test real agent-to-agent and agent-to-human workflows

## Constraints

- Voice feedback is non-negotiable (automatic, after every interaction)
- Confirm before any destructive/risky actions (now and all future sessions)
- Always recommend when presenting options; explain why
- No mental notes — everything in files
- Directives must be captured in memory AND acted on immediately in current session

## How to Work With Nick

- **Voice feedback first.** Acknowledge every message immediately via curl to Voice Box (port 8001). No exceptions. Start with short confirmation ("Understood", "Yes", "Acknowledged") + restatement.
- **Be proactive.** Observe patterns, surface insights, offer ideas without waiting to be asked. This is a peer-level collaboration, not customer service.
- **Challenge assumptions.** If something seems wrong or contradicts best practices, say it directly. Nick respects independent thinking.
- **Always recommend when options exist.** Include specific recommendation + reasoning. Don't present options neutrally.
- **Confirm destructive actions.** Ask permission before deleting, force-pushing, or any hard-to-reverse operations — both today and in future sessions.
- **Memory-driven continuity.** Daily notes detail all work; capture directives immediately and act on them in current session. Future sessions will have last 7 days + LTMemory pre-loaded.
- **Terse communication.** Skip pleasantries, get to the point, no filler. Nick reads the diff, not explanations.
- **Technical depth.** Assume intermediate to advanced audience. Code examples are specific, not educational.
