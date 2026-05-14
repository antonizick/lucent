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

> **Recovering or deploying from scratch?** See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the complete step-by-step guide — covers both repos, all services, cron jobs, shell config, Claude Code, Ollama, and OpenCode.

## Key Features

### Voice Feedback (Voice Box)
The Voice Box web UI (port 8001) provides voice acknowledgment for every interaction. When an agent receives input from Nick, it sends a voice confirmation via the `/speak` endpoint. This ensures Nick always knows the system received his input, even when away from keyboard.

- **Server:** `ui/server.py` (FastAPI, port 8001)
- **Startup:** `bash ui/start.sh`
- **Voice Send:** `bash ui/speak.sh "Your message"`

**Features:**
- **Multi-Client Broadcasting:** When multiple browsers have the Voice Box open, all instances receive and speak messages simultaneously via Server-Sent Events (SSE). No more "only one browser speaks" limitation.
- **Voice Mute Option:** Select "None (muted)" from the voice dropdown to see visualizations (scanner animation, avatar animation) without audio output. Useful for presentations or silent monitoring. Selection persists across sessions.
- **Dynamic Refresh Timer:** The daily log displays a countdown timer (left of font controls) showing seconds until the next automatic refresh. Counts down from 30 to 0, resets on each cycle. Styled subtly to avoid visual clutter.
- **Daily Log Tabs:** Switch between Daily (live), Weekly insights, and Long-term memory views
  - **Long-term Memory Tab:** Displays `memory/LTMemory.md` — distilled knowledge and priorities
  - **Daily Tab:** Live view of today's session notes (`memory/YYYY-MM-DD.md`)
- **Font Controls:** Adjust daily log text size with +/− buttons

### Backup Status Monitoring
The Voice Box popup includes real-time backup health monitoring. When you mouseover the voice panel, a popup displays the last push times for both your Lucent codebase and memory repository with visual status indicators.

**Features:**
- **Three-State Indicator Dots:** Color-coded status for each repository
  - 🟢 **Green dot:** Fresh backup (< 2 hours old) — text displays in cyan
  - 🟡 **Yellow dot:** Warning state (2-4 hours old) — text displays in cyan (still operational)
  - 🔴 **Red dot:** Critical state (> 4 hours old) — text displays in grey (unhealthy)
- **Formatted Time Display:** Shows last push time in format `HH:MM today/yesterday (Xh ago)`
- **Repository Labels:**
  - `Lucent Core` — Last push time for the main Lucent repository
  - `Synaptic Clone` — Last push time for your memory repository (github.com/antonizick/LucentMemory)
- **Automated Warning System:** When backups enter warning state (yellow), the system:
  - Sends voice notification: "Warning: Backups are stale. Triggering automated backup now."
  - Automatically runs `backup_memory.py` without waiting for user intervention
  - Continues monitoring and automatically transitions back to healthy when backup completes
- **30-Second Polling:** Backup status updates automatically every 30 seconds while the popup is visible
- **Consistent Styling:** Backup status section uses identical fonts, sizing, and colors as the Services list below it for visual unity

**Backend Endpoints:**
- `GET /backup/status` — Returns last commit times for both repositories with health status
- `POST /run-backup` — Triggers immediate memory folder backup

### Discord Integration
Lucent integrates with Discord for monitoring and async responses. A background monitor watches for messages, forwards them to Ollama, and posts responses back to Discord with intelligent web search integration and emoji feedback.

**Architecture Overview:**
Discord message → `/message/pending` queue → discord_monitor (Ollama processing + web search) → `/response` endpoint → discord_bot (posts to Discord + emoji reactions) → Voice Box (simultaneous voice feedback)

- **Main Components:**
  - `discord_bot.py` — Discord.py bot (message reception + Flask webhook for responses + emoji reactions)
  - `discord_monitor.py` — Background monitor (message fetch, Ollama processing, web search decision, voice feedback)
  - `server.py` — FastAPI backbone (message queue, response routing, all endpoints)
  - `discord_test_client.py` — Automated integration testing tool
  - `discord_message_logger.py` — Full message exchange logging (human-readable + JSON)
- **Setup:** Configure `.env` with `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`, and `OLLAMA_URL`
- **Run Monitor:** `python discord_monitor.py` (polls `/message/pending` every 3 seconds)
- **Run Bot:** `python discord_bot.py` (starts bot + Flask webhook on 8003)

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
│   ├── logs/              Voice activity logs (backed up hourly)
│   ├── scripts/           Backup scripts (redundant copies for recovery)
│   └── archive/           Historical notes + compressed logs (never deleted)
├── private/               Sensitive context (git-ignored)
├── scripts/               Backup & maintenance utilities
│   ├── backup_memory.py   Main backup executor (retry + health check)
│   ├── verify_startup.py  Startup ritual enforcement
│   ├── verify_backup_health.py Health check (GitHub connectivity)
│   └── rotate_voice_logs.py Voice log archival (monthly gzip)
├── ui/                    Voice Box web UI & Discord integration
│   ├── server.py          FastAPI server (voice feedback, Discord webhooks, backup status)
│   ├── discord_bot.py     Discord bot client
│   ├── discord_monitor.py Discord message monitor & Mistral response handler
│   ├── discord_logger.py  Logging forwarder to Discord channel
│   ├── speak.sh           Voice feedback endpoint (send to Voice Box)
│   ├── start.sh           Startup script
│   └── static/            Web UI assets (backup status popup integrated)
└── scratchpad/            Temporary workspace (not synced)
```

## Setup

> **Fresh deployment or disaster recovery?** The [Deployment Guide](docs/DEPLOYMENT.md) covers the full process end-to-end: system prerequisites, cloning both repos, Python and Node dependencies, environment variables, installing and enabling all five systemd services, cron jobs, `.bashrc` auto-starts, and step-by-step setup for Claude Code, Ollama, and OpenCode. The quick steps below are for reference only.

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

### Logging System — Complete Reference

Lucent maintains a comprehensive multi-layer logging system for debugging, auditing, and understanding system behavior. This section documents what gets logged, where, and how to use logs for troubleshooting.

#### **Activity Log (Voice Box Speech History)**

**Purpose:** Record every message sent to the Voice Box for voice/text synthesis and track all session events.

**Location:** `memory/logs/activity_YYYY-MM-DD.log`

**Why in memory/:** Activity logs are stored in the memory folder so they're automatically backed up with the hourly memory backup system, ensuring no voice history is lost.

**Content:** Timestamp + message text (one entry per `/speak` endpoint call) + session events (backup triggers, startup rituals, etc.)

**Example:**
```
[2026-05-13T14:23:45.123456] [voice_box] Welcome Nick, it's great to see you again
[2026-05-13T14:24:12.654321] [voice_box] Weather forecast for Austin: Partly cloudy, 78°F
[2026-05-13T19:50:43.000000] [voice_box] Backup triggered via UI (automated warning response)
```

**Access:**
- Web UI: `http://localhost:8001/activity-log-viewer` (auto-refreshing dashboard)
- Direct: `curl http://localhost:8001/activity-log` (JSON response with full content)

**Backup & Archival:**
- **Daily backup:** Included in hourly memory folder backup (every hour at :00)
- **Monthly rotation:** Logs older than 30 days gzipped to `memory/archive/voice-box/YYYY-MM/activity_YYYY-MM-DD.gz`
- **Retention:** Recent logs stay searchable in `memory/logs/`, full history preserved in archive

#### **Discord Monitor Logging**

**Purpose:** Track message receipt, search detection decisions, Ollama processing, and response generation.

**Logging Points:**

| Event | Log Entry | Purpose |
|-------|-----------|---------|
| Message fetch | `[FETCH] Fetched N pending message(s)` | Confirms polling succeeded |
| Search detection (Stage 1) | `[SEARCH] Stage 1 (keywords): MATCH/NO MATCH` | Fast keyword matching result |
| Search detection (Stage 2) | `[SEARCH] Stage 2 (AI): MATCH/NO MATCH - AI says 'yes'/'no'` | AI fallback decision |
| Web search execution | `[SEARCH] Searching DuckDuckGo for: {query}` | Confirms search initiated |
| Web search results | `[SEARCH] Found N results` | Number of results returned |
| Context loading | `[PROCESS] Loaded context (N chars)` | Memory files successfully loaded |
| Ollama call | `[OLLAMA] Calling Ollama with model={model}` | Request sent to Ollama |
| Ollama response | `[OLLAMA] Generated response (N chars): {text[:100]}` | Success + response preview |
| Response posting | `[RESPONSE] Posting to /response with search_used={flag}` | Sending back to server |
| Response success | `[RESPONSE] Successfully posted: {response[:80]}` | Confirmation |

**Log Level:** INFO by default (all events captured), ERROR for failures

**Format:** `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

**Real-Time Monitoring:**
```bash
# Follow Discord monitor logs in real-time
tail -f discord_monitor.py output  # if running in foreground
ps aux | grep discord_monitor  # find the process
```

#### **Discord Bot Logging**

**Purpose:** Track message reception, webhook requests, and emoji reactions.

**Logging Points:**

| Event | Log Entry | Purpose |
|-------|-----------|---------|
| Bot ready | `Logged in as {username}` | Bot successfully connected |
| Webhook received | `[WEBHOOK] Received response: message_id={id}, search_used={flag}` | Response from server arrived |
| Message posted | `[DISCORD] Posted response to message {id} (search_used={flag})` | Discord message sent |
| Emoji added | `[DISCORD] Added newspaper emoji to response` | Newspaper reaction added successfully |
| Emoji error | `[ERROR] Failed to add newspaper emoji: {reason}` | Emoji reaction failed (common: invalid message ID) |

**Log Output:** stdout/stderr (printed to console when running in foreground)

**Flask Webhook Server:** Runs on `http://127.0.0.1:8003` in background thread

#### **Discord Test Client**

**Purpose:** Automated integration testing without manual Discord messages.

**Usage:**
```bash
python discord_test_client.py
```

**Test Results Log:** `/tmp/discord_test_results.log`

**Tests Included:**
- Weather query (triggers web search)
- General knowledge question (no search needed)
- Current events query (news search)
- Store hours query (location-based search)

**Output:**
```
[2026-05-13 14:25:30] Bot connected as Lucent#1234
[2026-05-13 14:25:31] Queued: What's the weather tomorrow?... (ID: abc-123-def)
[2026-05-13 14:25:45] Response received with search_used=true
```

#### **Discord Message Logger**

**Purpose:** Full bidirectional Discord message exchange logging for debugging, auditing, and compliance.

**Usage:**
```bash
python discord_message_logger.py
```

**Log Locations** (moved to memory folder for automatic hourly backup):
- Human-readable: `memory/logs/discord/message_exchange.log`
- Machine-readable (JSON): `memory/logs/discord/messages.jsonl`

**What's Logged:**
- All incoming user messages (author, content, timestamp)
- All outgoing Lucent responses (content, reactions, search_used flag)
- System events (logger startup/ready)
- Discord metadata (message IDs, channel, reactions)

**Message Exchange Log Format:**
```
======================================================================
[2026-05-13T14:25:30.123456] RECEIVED
Message ID: 1234567890
Author: nick
Channel: lucent-commands
Content: What's the weather tomorrow?

======================================================================
[2026-05-13T14:25:45.654321] SENT
Message ID: 1234567890
Author: Lucent
Channel: lucent-commands
Content: The weather tomorrow will be partly cloudy...
Reactions: 📰
Search Used: true
```

**JSON Log Format (line-delimited):**
```json
{"timestamp": "2026-05-13T14:25:30.123456", "direction": "RECEIVED", "message_id": "1234567890", "author": "nick", "content": "What's the weather tomorrow?"}
{"timestamp": "2026-05-13T14:25:45.654321", "direction": "SENT", "message_id": "1234567890", "content": "The weather tomorrow...", "search_used": true, "reactions": ["📰"]}
```

**Backup & Archival:**
- **Daily backup:** Included in hourly memory folder backup (every hour at :00)
- **Monthly rotation:** Logs older than 30 days gzipped to `memory/archive/discord/YYYY-MM/`
- **Retention:** Recent logs stay searchable in `memory/logs/discord/`, full history preserved in archive

**Querying JSON Logs:**
```bash
# Find all messages that used web search
grep '"search_used": true' memory/logs/discord/messages.jsonl

# Extract all responses
jq 'select(.direction == "SENT") | .content' memory/logs/discord/messages.jsonl

# Find messages by author
jq 'select(.author == "nick")' memory/logs/discord/messages.jsonl

# Find messages older than 30 days (archived)
zcat memory/archive/discord/2026-04/*.gz | grep -i "specific search term"
```

#### **Server.py Activity Logging**

**Purpose:** General FastAPI request/response logging for debugging backend issues.

**Setup:** Configured via Python logging module, logs to stdout by default

**Endpoints Logging:**
- `/message/pending` POST → Logs message queued with source
- `/response` POST → Logs response routed to destination
- `/speak` POST → Logs activity entry + queues SSE broadcast
- All health checks logged to activity log

#### **Debugging with Logs**

**Scenario: Newspaper emoji not appearing**
1. Check `discord_bot.py` logs for: `Added newspaper emoji` or `Failed to add newspaper emoji`
2. Check `discord_monitor.py` logs for: `[SEARCH] Stage 1/2: MATCH` → confirms search was detected
3. Check `server.py` logs: Verify `search_used=true` in response payload
4. If emoji error: Message may have been deleted before emoji add, or invalid message_id

**Scenario: Web search not triggering**
1. Check `discord_monitor.py` logs for: `[SEARCH] Stage 1 (keywords): NO MATCH`
2. Check `[SEARCH] Stage 2 (AI): NO MATCH` → AI didn't think search needed
3. Add keyword or adjust Stage 2 AI prompt if legitimate search case not detected
4. Current keywords: weather, news, hours, trending, location-based queries, years (2025/2026)

**Scenario: Ollama not responding**
1. Check `discord_monitor.py` logs for: `[OLLAMA] Calling Ollama with model=...`
2. If followed by `[OLLAMA] Ollama error: 504` → Ollama service down, try: `curl http://localhost:11434/api/tags`
3. If no Ollama log → Message never reached processing (check fetch logs)

**Scenario: Response never posted to Discord**
1. Check `discord_monitor.py` logs for: `[RESPONSE] Successfully posted`
2. Check `discord_bot.py` logs for: `[DISCORD] Posted response to message`
3. If missing: Check Flask webhook is running (`curl http://127.0.0.1:8003/`)
4. Verify BACKEND_URL in `discord_monitor.py` matches server port (8001 for server.py)

---

### Daily Notes & Archival

The agent writes a daily note to `memory/YYYY-MM-DD.md` at the end of each session. Notes are never deleted — they accumulate over time. Every 7 days the agent reviews recent notes and promotes lasting knowledge to LTMemory.md.

**Archival & Cleanup Process:**
1. Before compression: Daily notes are copied to `memory/archive/` (permanent backup)
2. After compression: Notes are compressed to 1-2 paragraphs in place
3. Root cleanup: Notes older than 7 days are deleted from `memory/` root (full versions preserved in archive)

This ensures the startup context window stays fresh (7 recent days) while maintaining complete historical records in the archive.

### Memory Backup System

Lucent maintains a three-layer backup strategy ensuring zero data loss:

**Layer 1: Startup Backup**
- Runs automatically at session start via `verify_startup.py`
- Ensures memory changes are pushed before session begins
- Includes health verification (GitHub connectivity check)

**Layer 2: Post-Compression Backup**
- Runs after daily note compression
- Backs up newly compressed notes immediately
- Guarantees compressed knowledge is persisted

**Layer 3: Hourly Backup Cron**
- `0 * * * *` (every hour on the hour)
- Catches any changes between sessions
- Provides continuous protection throughout the day

**Backup Components:**
- `scripts/backup_memory.py` — Main backup executor (3-attempt retry with exponential backoff)
- `scripts/verify_backup_health.py` — Health check (GitHub connectivity, recent push verification)
- `scripts/verify_startup.py` — Startup ritual and backup enforcement
- `scripts/rotate_voice_logs.py` — Weekly voice activity log rotation and archival
- `scripts/rotate_discord_logs.py` — Weekly Discord message log rotation and archival

**Activity Log Backups:**
- Voice activity logs in `memory/logs/` — Included in hourly backup, rotated monthly
- Discord message logs in `memory/logs/discord/` — Included in hourly backup, rotated monthly
- Both gzipped and archived to `memory/archive/` by month for long-term preservation
- Both stay searchable in memory/logs/ for the recent 30 days

**Failure Handling:**
- Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s)
- Health checks: Verify GitHub push via `git rev-parse origin/main`
- Failure notifications: All issues logged to daily note with timestamps
- Automated backup trigger: When backup status enters warning state (>2 hours old), system automatically runs backup + voice notification

### Sub-Agents

Create focused sub-agents in `agents/{name}-agent.md`. Each has its own identity and is loaded with `core.md` for context. Use for:

- **Routine analysis** (code review, debugging, searching)
- **Cross-file investigations**
- **Single-task, narrow-scope work**

### Discord Integration — Detailed Architecture

#### **Message Flow (Complete Pipeline)**

```
1. Discord User Message
   ↓
2. discord_bot.py (on_message event)
   - Listens to configured DISCORD_CHANNEL_ID
   - Posts to http://localhost:8001/message/pending
   - Adds ✅ reaction (confirm receipt)
   ↓
3. server.py (/message/pending endpoint)
   - Accepts MessageRequest with source="discord_command"
   - Stores in memory queue (deque)
   ↓
4. discord_monitor.py (polling loop, 3-second interval)
   - Fetches from /message/pending
   - Detects if web search needed (two-stage: keywords + AI)
   - Calls Ollama with system prompt (including search results if applicable)
   - Generates response
   ↓
5. discord_monitor.py (post_response)
   - Sends voice feedback to Voice Box (/speak)
   - POSTs response to server.py (/response endpoint)
   - Includes search_used flag
   ↓
6. server.py (/response endpoint)
   - Routes response to discord_bot via Flask webhook
   - Forwards to http://127.0.0.1:8003/webhook/response
   ↓
7. discord_bot.py (webhook_response)
   - Receives from Flask
   - Calls post_response() async function
   - Posts message to Discord (reply or thread)
   - If search_used=true, adds 📰 emoji reaction
   ↓
8. Voice Box broadcasts simultaneously
   - User hears voice + sees text transcription
```

#### **Web Search Integration (Two-Stage Detection)**

**Stage 1 — Keyword Matching (Fast, Zero Overhead)**
Checks text against regex patterns for obvious search-needing queries:
- Time-sensitive: "today", "latest", "current", "tomorrow", "next week", "weekend"
- News/events: "news", "happening", "event", "what's on"
- Specific domains: "weather", "forecast", "hours", "open", "restaurant"
- Location-based: "what in", "things to do", "visit"
- Trending: "viral", "trending", "popular"

**Stage 2 — AI Fallback (Smart, 1-2 second latency)**
If Stage 1 doesn't match, asks Ollama:
```
"Does this require real-time information from the internet?"
```
Examples: "How does photosynthesis work?" → No. "What's the weather?" → Yes.

**Search Engine:** DuckDuckGo via `ddgs` library (v9.14.2)
- Returns 3 results per query by default
- Results formatted as: Title + body snippet
- Included in system prompt context for Ollama to reference

**Triggering Search:**
```python
if needs_web_search(instruction_text):
    search_results = search_duckduckgo(instruction_text)
    # Search results added to system prompt
    # search_used flag set to True
```

#### **Newspaper Emoji Feature (📰)**

**Purpose:** Visual indicator that a response used real-time web search

**When it appears:** Added as reaction to Lucent's response message when `search_used=true`

**Root Cause (Fixed in commit 184a48e):** Three-layer bug that prevented emoji from appearing:
1. `server.py /response` endpoint was dropping `search_used` field when forwarding
2. `ResponseRequest` Pydantic model didn't define `search_used` field
3. `discord_bot.py` had emoji code but never received the flag

**Current Implementation (Works):**
```python
# discord_bot.py post_response()
if search_used:
    try:
        await msg.add_reaction("📰")
        print(f"[DISCORD] Added newspaper emoji to response")
    except Exception as emoji_error:
        print(f"[ERROR] Failed to add newspaper emoji: {emoji_error}")
```

#### **Testing and Debugging Tools**

**discord_test_client.py — Automated Integration Testing**
- Posts test messages programmatically
- Simulates weather, news, and knowledge queries
- Logs results to `/tmp/discord_test_results.log`
- Useful for validating web search without manual Discord interaction

**discord_message_logger.py — Full Exchange Visibility**
- Logs every Discord message received and sent
- Two formats: human-readable + machine-readable JSON
- Enables post-mortem analysis of message exchanges
- Useful for debugging: "Why didn't my message get a response?"

#### **Environment Configuration**

Required `.env` variables for Discord integration:
```bash
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_SERVER_ID=your_server_id
DISCORD_CHANNEL_ID=your_command_channel_id
DISCORD_LOG_CHANNEL_ID=your_log_channel_id  # Optional
DISCORD_LOG_WEBHOOK_URL=your_webhook_url    # Optional
BACKEND_URL=http://localhost:8002           # discord_monitor talks to this
OLLAMA_URL=http://localhost:11434
LUCENT_ROOT=/home/nick/dev/lucent
```

Note: `BACKEND_URL` for discord_monitor defaults to `http://localhost:8002` but server.py runs on 8001. Check actual configuration in `discord_monitor.py`.

#### **Service Lifecycle**

**Starting Discord Integration:**
```bash
# Terminal 1: Start Voice Box (includes server.py)
cd /home/nick/dev/lucent/ui && bash start.sh

# Terminal 2: Start Discord Bot
cd /home/nick/dev/lucent/ui && python discord_bot.py

# Terminal 3: Start Discord Monitor
cd /home/nick/dev/lucent/ui && python discord_monitor.py
```

**Health Check:**
```bash
curl http://localhost:8001/services/health | jq .
# Returns status of: Ollama, Voice Box, Discord Bot, Discord Monitor, Lucent Server
```

**Stopping:**
- Monitor: `Ctrl+C` in monitor terminal
- Bot: `Ctrl+C` in bot terminal
- Voice Box: `Ctrl+C` in start.sh terminal

---

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

