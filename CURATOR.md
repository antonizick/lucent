# Curator Agent — Memory Curation & Promotion

**Purpose:** Extract comprehensive session summaries from daily note archives and promote them to LTMemory.md Recent Sessions, ensuring the startup context bundle always contains substantive, up-to-date session documentation.

---

## Quick Start

```bash
# Review past 7 days and promote summaries to LTMemory
python3 scripts/curator.py --days 7

# Deeper review: 14 days
python3 scripts/curator.py --days 14

# Verify current LTMemory completeness
python3 scripts/curator.py --check

# Dry-run (review only, don't modify)
python3 scripts/curator.py --days 7 --preview
```

---

## The Problem It Solves

**Before Curator:** Auto-compression wrote minimal stubs (6 lines from 1000+ lines) to LTMemory.md, causing sessions to be missing from the startup context. Archives preserved full details, but they were never promoted to active memory.

**Result:** Startup context was incomplete, Claude would restart each session with missing knowledge about recent work.

**Solution:** Curator reads archives, extracts real summaries, and updates LTMemory to match actual work done.

---

## How It Works

### 1. Find Recent Unsummarized Archives
```python
get_recent_archives(days=7)  # Get all archives from past N days
```
- Scans `memory/archive/` for YYYY-MM-DD.md files
- Returns list of (date, path) tuples, sorted newest first
- Skips files that don't exist

### 2. Extract Summaries from Each Archive
```python
extract_summary_from_archive(archive_path)
```

For each archive, Curator:

**Identifies major work:**
- Scans for lines starting with `✅` (checkmarked items)
- Collects up to 20 most relevant items

**Extracts commits:**
- Finds lines matching "commit" (case-insensitive)
- Lists top 5 commits with messages

**Extracts infrastructure changes:**
- Database migrations, config changes, port assignments, fixes
- Filters to relevant lines only

**Builds formatted summary:**
- Returns markdown section with bullets
- Minimum 100 characters to be considered meaningful
- Returns `None` if archive too minimal

### 3. Update LTMemory.md Recent Sessions
```python
update_ltmemory_recent_sessions(summaries)
```

For each extracted summary:
- Creates new `### Session YYYY-MM-DD` section
- Inserts summary content
- Maintains reverse chronological order (newest at top)
- Replaces any existing stub with comprehensive version

---

## Integration with Startup Validation

**At startup:**
```python
check_ltmemory_completeness()  # Called by startup.py
```

This validation:
- Detects stub markers: "UNSUMMARIZED", "to be filled in", "See full details"
- Counts bullets per session
- Flags any session with <3 bullet points as incomplete
- **Blocks startup** if stubs found

**If stubs detected:**
```
STARTUP FAILURE: LTMemory has incomplete summaries...
→ Run: python3 scripts/curator.py --days 14
```

---

## Archive Requirements

For Curator to extract meaningful summaries, archives should contain:

### ✅ Checkmarked Items (Key indicator)
```
✅ Fixed white opening move bug — race condition in board sync
✅ Implemented move note editor with auto-save
✅ Added Tailscale HMR configuration for WebSocket protocol
```

### Commits
```
- Commit: c0029f3 "feat: Add Move Note persistence"
- Commit: 0d7ef36 "fix: Resolve Tailscale WebSocket errors"
```

### Database/Infrastructure
```
- Consolidated 15 public libraries under seedbot account
- Reconfigured NX-Citadel to port 9123
- Fixed cascade deletion for ReviewLog → PracticePosition → Line
```

---

## Validation Modes

### `--check` Mode (Verify Only)
```bash
python3 scripts/curator.py --check
```

**Output:**
```
✓ LTMemory.md is complete (all sessions documented)
  OR
✗ LTMemory.md has incomplete summaries:
  ⚠️  Found stub marker: 'UNSUMMARIZED'
  ⚠️  Incomplete session: 2026-05-25 has <3 items
```

No modifications to files. Safe to run anytime.

### Normal Mode (Extract & Promote)
```bash
python3 scripts/curator.py --days 7
```

**Output:**
```
→ Curator reviewing 7 days of archives...
  Found 5 archive(s) to review
  → Reviewing 2026-05-27...
    ✓ Extracted 42 lines
  → Reviewing 2026-05-26...
    ✓ Extracted 38 lines
  ...
✓ Curator complete: 5 sessions promoted to LTMemory.md
```

Updates LTMemory.md with new summaries.

---

## Daily Note Format Guidelines

To maximize what Curator can extract, structure daily notes with:

### Major Items (Checkmarked)
```
## [HH:MM] Feature Name

✅ Completed feature X
✅ Fixed bug Y
✅ Implemented Z
```

Curator looks for `✅` to identify key work.

### Commits
```
**Commit:** abc1234 "feat: Add new feature"
**Commit:** def5678 "fix: Resolve issue"
```

Curator extracts commit section automatically.

### Infrastructure
```
**Database:** Added new migration for user accounts
**Port:** Changed NX-Citadel from 8000 to 9123
**Config:** Updated Vite HMR configuration
```

Curator recognizes these headers.

---

## Scheduled Operation (Recommended)

Add to crontab for weekly curation:
```bash
# Weekly curation: Mondays at 8am
0 8 * * 1 cd /home/nick/dev/lucent && python3 scripts/curator.py --days 14
```

Or run manually at day-end before committing:
```bash
python3 scripts/curator.py --days 7
git add memory/LTMemory.md
git commit -m "chore: Curator promoted 7 days to LTMemory"
```

---

## Return Values

- **0:** Success (summaries promoted or verified complete)
- **1:** Error (file not found, update failed, no archives)

---

## Implementation Notes

**Why separate from startup.py:**
- Compression happens automatically (hourly backup)
- Curation is intentional (weekly manual or scheduled)
- Allows Curator to run on its own schedule without blocking startup

**Why archives as source:**
- Full detail preserved forever
- Compression doesn't lose information
- Curator reads complete picture, not stubs

**Why validation blocks startup:**
- Prevents sessions starting with incomplete context
- Forces real curation before work resumes
- Clear remedy command provided on failure

**Why reverse chronological order:**
- Most recent work first in startup context
- Readers scan top of Recent Sessions, not bottom
- Aligns with how memory is consumed

---

## Troubleshooting

**Q: Curator found no summaries to extract**
A: Archives may be too minimal. Check if daily notes have `✅` checkmarks. Curator needs at least 5 major items per session.

**Q: LTMemory doesn't update**
A: Verify `memory/LTMemory.md` exists and is writable. Check script output for errors.

**Q: Startup still blocks after running Curator**
A: Verify Curator ran successfully (look for "✓ promoted" message). Run `curator.py --check` to verify completeness.

**Q: Archive is missing or incomplete**
A: `backup_memory.py` auto-archives hourly. If archive missing, ensure backup_memory.py is running and has git permissions.

---

## Related Systems

- **backup_memory.py** — Auto-archives daily notes hourly, compresses at day boundary
- **startup.py** — Validates LTMemory completeness at session start
- **check_ltmemory_completeness()** — Detects stubs and blocks startup if found
- **core.md** — Note Summary Protocol defines daily note structure
- **CLAUDE.md** — Memory Management section documents three-tier system
