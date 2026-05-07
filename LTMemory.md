# Long-Term Memory

## Projects

- **Lucent** — Personal AI assistant framework. Skeleton complete: README.md, directory structure, sync script, per-project config (.lucentrc), .gitignore. Based on ai-shared-brain starter kit. Next: populate memory files, create sub-agents.

## Preferences

- Concise, terse responses preferred. No filler. One-line summaries over paragraphs.
- Aliases over long commands — "brain" for sync, "lucent" as alias.
- Ruthless about pruning — prefer under ~150-200 lines for summaries. Drop low-value or stale info.
- Timezone UTC-6.

## Decisions

- README.md is the only public-facing file — concise, covers architecture, setup, usage, not a tutorial.
- .gitignore excludes ai-shared-brain/ submodule, private/, IDE files, .DS_Store.
- Daily notes accumulate forever — no deletion. Promoted to LTMemory on review.

## Lessons Learned

- Start sessions with a clean README before populating memory. A framework with no content is still a template.
- .lucentrc config is the bridge between any project and Lucent's context.

## Context

- Repo at /home/nick/dev/lucent/ with ai-shared-brain/ as git submodule.
- Sync: lucent-sync.sh + aliases (brain/lucent) to GitHub remote.
- Per-project .lucentrc files wire dev sessions into the system.
