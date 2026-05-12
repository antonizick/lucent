# Lucent

A personal AI assistant framework built on persistent memory. Lucent maintains continuity across sessions through a curated system of identity files, long-term memory, and daily notes — so your AI assistant remembers who you are, what matters, and what happened last time.

## How It Works

```
+-------------+       reads        +-----------+
|  Claude     | ──────────────────> |  Memory   |
|  Code /     |                     |  Files    |
|  OpenCode   | <───────────────── | (.md)     |
|  Agent      |       writes        +-----------+
+-------------+                    ^
        |                          |  reads
        v                          |
+-------------+       writes       +-----------+
|  Daily     | ──────────────────> |  LTMemory  |
|  Notes     |                     |  (distilled)
+-------------+       promotes ──> |  knowledge |
                                   +-----------+
```

Lucent is a personal AI assistant framework with a private GitHub repository as the single source of truth.

## Key Features

### Voice Feedback (Voice Box)
The Voice Box web UI (port 8001) provides voice acknowledgment for every interaction. When an agent receives input from Nick, it sends a voice confirmation via the `/speak` endpoint. This ensures Nick always knows the system received his input, even when away from keyboard.

- **Server:** `ui/server.py` (FastAPI, port 8001)
- **Startup:** `bash ui/start.sh`
- **Voice Send:** `bash ui/speak.sh "Your message"`

**Features:**
- **Dynamic Refresh Timer:** The daily log displays a countdown timer (left of font controls) showing seconds until the next automatic refresh. Counts down from 30 to 0, resets on each cycle. Styled subtly to avoid visual clutter.
- **Daily Log Tabs:** Switch between Daily (live), Weekly insights, and Long-term memory views
- **Font Controls:** Adjust daily log text size with +/− buttons

### Discord Integration
Lucent integrates with Discord for monitoring and async responses. A background monitor watches for messages, forwards them to Claude, and posts responses back to Discord.

- **Components:**
  - `discord_bot.py` — Bot client (webhook responses)
  - `discord_monitor.py` — Message monitor & Claude response handler
  - `discord_logger.py` — Logging forwarder
  - `discord_poller.py` — Polling engine
- **Setup:** Configure `.env` with `DISCORD_WEBHOOK_URL` and `DISCORD_CHANNEL_ID`
- **Run:** `python discord_monitor.py`

## Core Files

All core memory files are consolidated in the `memory/` directory:

| File | Purpose |
|------|---------|
| `memory/core.md` | Operating manual — startup ritual, rules, safety guidelines |
| `memory/lucentIdent.md` | Lucent's identity — personality, behaviors, habits |
| `memory/userIdent.md` | Nick's identity — facts, preferences, working style |
| `memory/LTMemory.md` | Long-term memory — distilled from daily notes into lasting knowledge |

## Directory Structure

```
lucent/
├── CLAUDE.md              Claude Code guidance
├── README.md              This file
├── .lucentrc              Per-project config for session loading
├── lucent-sync.sh         Sync script — commit + push to GitHub
├── lucentrc               Sync config (remote URL, log dedup)
├── .sync.log              Sync history (30-day auto-cleanup)
├── agents/                Sub-agent definitions: {name}-agent.md
├── idea/                  Working directory for projects
├── memory/                Core memory + daily notes
│   ├── core.md            Startup ritual, rules, safety
│   ├── lucentIdent.md     Lucent's identity
│   ├── userIdent.md       Nick's identity
│   ├── LTMemory.md        Long-term memory (agent-curated)
│   ├── REMINDERS.md       Active reminders
│   ├── AGENTS.md          Top-level instructions
│   ├── AGENT_ASSIGNMENTS.md Agent task ownership
│   ├── YYYY-MM-DD.md      Daily episodic notes
│   └── archive/           Historical notes (never deleted)
├── private/               Sensitive context (git-ignored)
├── ui/                    Voice Box web UI & Discord integration
│   ├── server.py          FastAPI server (voice feedback, Discord webhooks)
│   ├── discord_bot.py     Discord bot client
│   ├── discord_monitor.py Discord message monitor & Lucent response handler
│   ├── discord_logger.py  Logging forwarder to Discord channel
│   ├── discord_poller.py  Polling engine for channel messages
│   ├── speak.sh           Voice feedback endpoint (send to Voice Box)
│   ├── start.sh           Startup script
│   └── static/            Web UI assets
└── scratchpad/            Temporary workspace (not synced)
```

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/antonizick/lucent.git
cd lucent
```

### 2. Configure your AI agent

#### Claude Code

Add to `~/.claude/settings.json` or use the config command:

```json
{
  "systemPrompt": "You are Lucent, a personal AI assistant. Before doing anything, read the startup ritual: memory/core.md, memory/lucentIdent.md, memory/userIdent.md, memory/LTMemory.md, and today's daily note."
}
```

Or set it via CLI:

```bash
claude config set --key system-prompt "You are Lucent, a personal AI assistant. Before doing anything, read memory/core.md, memory/lucentIdent.md, memory/userIdent.md, memory/LTMemory.md, and today's daily note."
```

#### OpenCode

The `lucentrc` file at the repo root contains the full configuration. Copy it to your project's `.opencode/` directory:

```bash
cp lucentrc ~/.opencode/settings.json
```

### 3. Set up aliases

Add to `~/.bash_aliases` (or `~/.zsh_aliases`):

```bash
# Launcher aliases (select platform & model)
alias lucent='bash /home/nick/dev/lucent/scripts/ai-launcher.sh'
alias luc='bash /home/nick/dev/lucent/scripts/ai-launcher.sh'

# Sync alias
alias brain='/home/nick/dev/lucent/lucent-sync.sh'
```

Source your aliases and run `brain` to perform the initial push, or `lucent` to launch your chosen AI platform.

## Usage

### The Startup Ritual — Complete Reference

Every agent session executes an 8-step startup ritual that ensures continuity and reliable operation. This section documents what happens, what context is available, and what may be missing.

#### **What Happens at Startup (Step-by-Step)**

1. **Hook injects context** (automated)
   - memory/LTMemory.md (long-term knowledge)
   - Last 7 days of daily notes (compressed to 1-2 paragraphs each, except today in full)
   - memory/core.md, memory/lucentIdent.md, memory/userIdent.md (identity and rules)
   - These files appear in system context automatically

2. **Compress yesterday's note** (mandatory)
   - If yesterday's daily note exists, invoke Curator to compress it to 1-2 paragraphs (outcomes + key decisions only)
   - Verify "Compressed [date]" marker in today's note
   - Update ritual checkpoint

3. **Load priorities and reminders** (automated)
   - Read Current Priorities section in LTMemory.md (injected by hook)
   - Read REMINDERS.md (now injected by hook alongside LTMemory.md)
   - Review pattern-based reminders (due today), context-triggered reminders, opportunistic reminders

4. **Verify Voice Box** (mandatory for Claude Code)
   - Check `curl -s http://localhost:8001/health`
   - Start if missing: `cd /home/nick/dev/lucent/ui && nohup bash start.sh &`
   - **STOP if voice box fails** — cannot proceed

5. **Initialize session logging** (mandatory for Claude Code)
   - Run `python3 scripts/session_logger.py /home/nick/dev/lucent`
   - Creates session marker in daily note
   - **STOP if this fails** — cannot proceed

6. **Send proactive greeting** (mandatory for Claude Code)
   - Greet Nick warmly via voice + text (Lucent speaks first, no waiting)
   - Include current priorities, active reminders, open-ended invitation

7. **Wait for Nick's input** (ready state)
   - Ritual complete; ready to respond

8. **Respond using three-layer requirement**
   - Log to daily note (append to memory/YYYY-MM-DD.md)
   - Send voice (curl to localhost:8001/speak)
   - Send text (response in Claude Code)
   - All three, every time. Framework validates.

#### **Context Available at Startup**

**Automatically injected by hook:**
- `memory/LTMemory.md` — Distilled long-term knowledge (3-5 active priorities, preferences, lessons learned, archival policy)
- Last 7 days of daily notes: `memory/2026-05-XX.md` (compressed, except today in full)
- `memory/core.md` — Operating rules (voice box requirement, three-layer response, core rules, archival policy)
- `memory/lucentIdent.md` — Lucent's personality and core operating principles
- `memory/userIdent.md` — Nick's role, preferences, constraints, how to work with him

**Must be read manually (not auto-injected):**
- `memory/AGENTS.md` — Top-level agent instructions (when to invoke which agent)
- `memory/AGENT_ASSIGNMENTS.md` — Detailed task ownership (what each agent owns)

**Available but not loaded at startup:**
- Individual agent files: `agents/{name}-agent.md` (Curator, Git, Writer, Reviewer, Planner)
- Archived notes: `memory/archive/` (historical reference only, not active)
- Project-local notes: `idea/*/` (working area, not core memory)

#### **Memory Files by Category**

| File | Category | Startup | Purpose |
|------|----------|---------|---------|
| memory/LTMemory.md | Core | ✓ Injected | Distilled knowledge, priorities, lessons, archival policy |
| memory/core.md | Core | ✓ Injected | Operating rules, startup ritual, core guidelines |
| memory/lucentIdent.md | Core | ✓ Injected | Lucent's identity and operating principles |
| memory/userIdent.md | Core | ✓ Injected | Nick's identity, preferences, working style |
| memory/YYYY-MM-DD.md | Daily | ✓ Injected (last 7) | Session logs, decisions, progress (compressed except today) |
| memory/REMINDERS.md | Active | ✓ Injected | Pattern, context, and opportunistic reminders |
| memory/AGENTS.md | Reference | — Manual read | Agent invocation guidance |
| memory/AGENT_ASSIGNMENTS.md | Reference | — Manual read | Task ownership matrix |
| agents/*.md | Reference | — On-demand | Individual agent definitions |
| memory/archive/ | Archive | — On-demand | Historical reference (never deleted, not active) |

#### **Platform-Specific Details**

**Claude Code** (`CLAUDE.md`):
- Startup ritual includes voice box check and session logging initialization (mandatory)
- Hook handles context injection automatically
- Checkpoint system tracks ritual completion

**OpenCode and others**:
- Read the same memory files (memory/core.md, memory/lucentIdent.md, memory/userIdent.md, memory/LTMemory.md)
- Platform-agnostic rules apply identically
- Voice box requirement may differ (OpenCode doesn't have port 8001 integration)
- See memory/AGENTS.md for platform-agnostic invocation patterns

#### **Potential Gaps in Startup Context**

**Currently NOT auto-injected (by design):**
- `memory/AGENTS.md` — Not loaded at startup. Manual read needed to determine when to invoke other agents.
- Agent files (`agents/*.md`) — Not loaded at startup. Read on-demand when invoking a specific agent.
- `memory/AGENT_ASSIGNMENTS.md` — Not auto-injected. Manual read when designing new task delegation.

---

### Daily Notes

The agent writes a daily note to `memory/YYYY-MM-DD.md` at the end of each session. Notes are never deleted — they accumulate over time. Every 7 days the agent reviews recent notes and promotes lasting knowledge to LTMemory.md.

### Daily Notes

The agent writes a daily note to `memory/YYYY-MM-DD.md` at the end of each session. Notes are never deleted — they accumulate over time. Every 7 days the agent reviews recent notes and promotes lasting knowledge to LTMemory.md.

### Sub-Agents

Create focused sub-agents in `agents/{name}-agent.md`. Each has its own identity and is loaded with `core.md` for context. Use for:

- **Routine analysis** (code review, debugging, searching)
- **Cross-file investigations**
- **Single-task, narrow-scope work**

### Multi-AI Platform Launcher

The `ai-launcher.py` Python launcher provides a polished, interactive interface for launching Claude or OpenCode with your choice of AI model — Anthropic models (Opus, Sonnet, Haiku), local Ollama models, or OpenCode's free online models.

**Aliases:**
```bash
lucent             # Interactive launcher menu (recommended)
luc                # Same as lucent (short form)
```

Both aliases run the Python launcher: `python3 /home/nick/dev/lucent/scripts/ai-launcher.py`

**Usage:**

Interactive menu (select platform and model):
```bash
lucent
```

Quick-launch (skip menu, direct to Claude or OpenCode):
```bash
lucent claude opus                      # Claude + Opus
lucent claude sonnet                    # Claude + Sonnet
lucent opencode big-pickle              # OpenCode + Big Pickle
lucent opencode deepseek-v4-flash-free  # OpenCode + DeepSeek V4
```

**Features:**
- **Polished UI:** Built with Questionary and Rich for a sharp, professional look
- **Clean navigation:** Arrow keys to move through menus, back button to navigate back
- **Graceful exit:** Exit option on every menu with confirmation message
- **Color-coded models:** Magenta for Anthropic, Blue for Ollama, Green for OpenCode free models
- **Clean screen:** Terminal clears before each menu for focused, uncluttered display
- **Auto-launch:** Sessions start in `/home/nick/dev/lucent` with your chosen platform and model
- **Model detection:** Automatically determines model type (Anthropic/Ollama/OpenCode free) based on selection
- **Quick-launch mode:** Skip the menu entirely with CLI arguments

**Available Models:**

*Claude:*
- `opus` (Claude Opus 4.7)
- `sonnet` (Claude Sonnet 4.6)
- `haiku` (Claude Haiku 4.5)
- Any local Ollama model

*OpenCode:*
- `big-pickle`
- `deepseek-v4-flash-free`
- `minimax-m2.5-free`
- `nemotron-3-super-free`
- `ring-2.6-1t-free`
- Any local Ollama model

### Syncing

```bash
brain              # Sync the entire repo to GitHub
```

The sync script:
- Checks if already synced today (dedup via `.sync.log`)
- Stages all changes with `git add -A`
- Commits with timestamp
- Pushes to the configured remote
- Auto-cleans `.sync.log` (30-day retention)

### Per-Project Config

Each project under `/home/nick/dev/` gets its own `.lucentrc` pointing to the shared brain files. This lets any agent session load Lucent's context without changing repos.

## Core Rules

- **Write it down.** Nothing lives in mental notes. The file system is memory.
- **Never delete daily notes.** They accumulate and inform memory promotion.
- **Don't surface private info.** Nick's details stay inside the files unless explicitly asked.
- **Ask before destructive actions.** Deleting files, clearing memory, or modifying core config requires explicit approval.

## Architecture

```
Lucent = memory files + daily notes + agent config + GitHub sync

Everything lives in lucent/ root and syncs to GitHub via lucent-sync.sh.
Per-project .lucentrc files wire any dev session into the system.
```

## Web UI

<img src="docs/images/WebUI.png" alt="Lucent Voice Box Web UI" width="100%" />

## License

Private repository. All rights reserved.
