# Long-Term Memory

## Projects

- **Lucent** — Personal AI assistant framework. Skeleton complete: README.md, directory structure, sync script, per-project config (.lucentrc), .gitignore. Next: populate memory files, create sub-agents.

## Preferences

- Concise, terse responses preferred. No filler. One-line summaries over paragraphs.
- Aliases over long commands — "brain" for sync, "lucent" as alias.
- Ruthless about pruning — prefer under ~150-200 lines for summaries. Drop low-value or stale info.
- Timezone UTC-6.

## Decisions

- README.md is the only public-facing file — concise, covers architecture, setup, usage, not a tutorial.
- .gitignore excludes private/, IDE files, .DS_Store.
- Daily notes accumulate forever — no deletion of completed notes. Daily notes can and should be edited, refined, and summarized during their day. Once the day is over, the note is never deleted — only its content promoted to LTMemory.md.

## Lessons Learned

- Start sessions with a clean README before populating memory. A framework with no content is still a template.
- .lucentrc config is the bridge between any project and Lucent's context.
- **Ollama model names:** Always use full names with version tags (e.g., "qwen3.6:35b", "mistral:latest"), not short names. Short names fail when passed to Ollama API.
- **Qwen model capabilities:** Qwen3.6 is more capable than mistral but may attempt tool_use syntax (Claude feature). Needs system prompt constraint + response cleaning.
- **Response timeouts:** Qwen3.6 is ~30x slower than mistral. Discord monitor needs 15-minute timeout for generate endpoint.
- **Debug logging:** Don't use print() for debugging when discord_logger broadcasts to Discord. Use logger.info/error instead (or remove debug output entirely).

## Context

- Repo at /home/nick/dev/lucent/.
- Sync: lucent-sync.sh + aliases (brain/lucent) to GitHub remote.
- Per-project .lucentrc files wire dev sessions into the system.

## Archival & Maintenance Policy

**Philosophy:** Retain what's load-bearing, archive what's outdated.

**Keep in LTMemory:** Decisions that still hold. Preferences that still apply. Lessons that inform future work. Architecture decisions. Recurring patterns.

**Archive to `memory/archive/`:** Outdated context. Completed initiatives (unless they're principles). Historical notes that don't affect future work. Decisions superseded by newer ones.

**Decision rule:** "If a new sub-agent reads this, does it help them work with Nick?" Yes → keep. No → archive.

**Process:** Monthly review (or quarterly). Scan LTMemory, ask the question above, move stale entries to `memory/archive/YYYY-MM.md` with a brief note on why it was archived.

**Format:** Archived entries stay readable. Archive files are numbered by month: `archive/2026-Q2.md`, `archive/2026-Q3.md`, etc.
