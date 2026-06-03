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

### Voice Feedback (Voice Box + NX Vox)
The Voice Box web UI (port 8001) provides voice acknowledgment for every interaction. When an agent receives input from Nick, it sends a voice confirmation via the `/speak` endpoint. This ensures Nick always knows the system received his input, even when away from keyboard.

- **Server:** `ui/server.py` (FastAPI, port 8001)
- **Startup:** managed by `lucent-voice-box.service` (systemd)
- **Voice Send:** `curl -X POST http://localhost:8001/speak -H "Content-Type: application/json" -d '{"text": "message"}'`

#### NX Vox — Neural TTS Engine

As of 2026-05-14, the Voice Box uses **Piper TTS** for server-side neural speech synthesis. This replaces the browser's built-in `window.speechSynthesis` (which used the OS-native engine — robotic `espeak-ng` on Linux).

- **Engine:** [Piper TTS](https://github.com/OHF-Voice/piper1-gpl) (OHF-Voice, GPL-3.0, v1.4.2)
- **Integration:** In-process Python library — no separate service, no cloud dependency, no API key
- **Audio delivery:** Base64-encoded WAV over the existing SSE pipeline
- **Default voice:** `en_GB-cori-high` (Southern British female, high quality)
- **Voice model directory:** `ui/voices/` (git-ignored — must be downloaded per machine)
- **Full voice guide:** [docs/VOICES.md](docs/VOICES.md)

**Voice API endpoints:**

| Endpoint | Method | Description |
|---|---|---|
| `/vox/voices` | GET | List installed voices and current active voice |
| `/vox/voice` | POST | Switch active voice model (`{"voice": "en_GB-alan-medium"}`) |
| `/vox/status` | GET | Runtime stats: synthesis count, latency, uptime |
| `/vox/speak` | POST | Synthesize audio and return WAV directly (no SSE broadcast) |
| `/vox/config` | GET | Read avatar→voice mapping |
| `/vox/config` | POST | Update a voice assignment (`{"avatar": "Emma", "voice": "en_GB-jenny_dioco-medium"}`) |

**Installed voices (2026-05-14):**

| Voice | Gender | Quality | Default for |
|---|---|---|---|
| `en_GB-cori-high` | Female | High | Lucent, Karen |
| `en_GB-jenny_dioco-medium` | Female | Medium | Emma |
| `en_GB-alan-medium` | Male | Medium | Alex |
| `en_GB-northern_english_male-medium` | Male | Medium | (available) |

**Per-avatar voice assignment** is configured in `ui/voice_config.json`. Switching the avatar in the UI automatically switches the active Piper voice on the server. See [docs/VOICES.md](docs/VOICES.md) for the complete guide to browsing, downloading, and assigning voices.

**Features:**
- **Multi-Client Broadcasting:** When multiple browsers have the Voice Box open, all instances receive and speak messages simultaneously via Server-Sent Events (SSE). No more "only one browser speaks" limitation.
- **Voice Mute Option:** Select "None (muted)" from the voice dropdown to see visualizations (scanner animation, avatar animation) without audio output. Useful for presentations or silent monitoring. Selection persists across sessions.
- **Dynamic Refresh Timer:** The daily log displays a countdown timer (left of font controls) showing seconds until the next automatic refresh. Counts down from 30 to 0, resets on each cycle. Styled subtly to avoid visual clutter.
- **Daily Log Tabs:** Switch between Daily (live), Weekly insights, and Long-term memory views
  - **Long-term Memory Tab:** Displays `memory/LTMemory.md` — distilled knowledge and priorities
  - **Daily Tab:** Live view of today's session notes (`memory/YYYY-MM-DD.md`)
- **Font Controls:** Adjust daily log text size with +/− buttons

### FaceTime Mode
FaceTime mode optimizes the Voice Box for mobile and video conferencing use. Press **Ctrl+Shift+F** (or click the FaceTime button) to toggle.

**Features:**
- **Full-Screen Avatar:** Hides the log panel and side controls, displaying only the avatar character in the center
- **Mobile Responsive:** On phones (≤600px width), the header collapses to show only the FaceTime toggle button, maximizing screen real estate
- **Portrait & Landscape Support:** Avatar scales properly on both orientations; in portrait mode, the avatar expands to fill all available vertical space
- **Always Visible Toggle:** The FaceTime on/off button remains accessible even in the minimal header on narrow screens

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
| `memory/LTMemory.md` | Long-term memory — distilled from daily notes into lasting knowledge (newest 10 sessions; older → `LTMemory.archive.md`) |
| `memory/skills/` | NERO skill library — procedural knowledge packages with lifecycle management |
| `memory/.nero/` | NERO runtime state — config, proposals, curator reports, worker log |
| `memory/.recall_index.json` | NERO semantic recall index (Ollama `nomic-embed-text` embeddings, 392+ chunks) |

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
│   ├── LTMemory.archive.md Older LTMemory sessions (capped at 10 live; still recall-indexed)
│   ├── skills/            NERO skill library (procedural knowledge packages)
│   │   ├── .protected     Slugs the curator never archives
│   │   ├── .usage.json    Per-skill use counters
│   │   ├── .archive/      Archived skills (recoverable)
│   │   └── <slug>/SKILL.md+ references/ templates/ scripts/
│   ├── .nero/             NERO runtime state (config, proposals, curator reports, worker log)
│   ├── .recall_index.json Semantic recall index (Ollama nomic-embed-text embeddings)
│   ├── nero_inbox.md      Pending self-improvement proposals (propose mode)
│   ├── logs/              Voice activity logs (backed up hourly)
│   ├── scripts/           Backup scripts (redundant copies for recovery)
│   └── archive/           Historical notes + compressed logs (never deleted)
├── private/               Sensitive context (git-ignored)
├── scripts/               Backup & maintenance utilities
│   ├── startup.py         IGNITION Phase 2: Robust startup orchestrator (parallel checks, auto-restart, /tmp fallback)
│   ├── acknowledge_startup.py Proactive acknowledgement: sends random confirmation after startup.py completes
│   ├── validate_startup.py IGNITION Phase 1: Sequential validation gate (preserved for backward compat)
│   ├── verify_startup.py  Checkpoint utilities (ritual enforcement, hash validation)
│   ├── backup_memory.py   Main backup executor (retry + health check)
│   ├── verify_backup_health.py Health check (GitHub connectivity)
│   ├── session_logger.py  Session logging initialization
│   ├── rotate_voice_logs.py Voice log archival (monthly gzip)
│   ├── memory_index.py    NERO: semantic recall index (build/query/status)
│   ├── memory_recall.py   NERO: UserPromptSubmit hook entry (embeds prompt, injects recall)
│   ├── reflect.py         NERO: per-turn reflection loop (Stop hook + worker + proposal inbox)
│   ├── skills.py          NERO: skill library management (list/view/bump/lifecycle)
│   ├── skill_curator.py   NERO: weekly curator (lifecycle + consolidation + memory hygiene)
│   ├── pre_compact.py     NERO: PreCompact hook (injects must-keep context before compaction)
│   └── insights.py        NERO: self-improvement health dashboard
├── ui/                    Voice Box web UI & Discord integration
│   ├── server.py          FastAPI server (voice, Piper TTS, Discord, backup status)
│   ├── piper_manager.py   Piper TTS wrapper (thread-safe synthesis, voice switching)
│   ├── voice_config.json  Avatar→voice mapping (edit or use POST /vox/config)
│   ├── discord_bot.py     Discord bot client
│   ├── discord_monitor.py Discord message monitor & Mistral response handler
│   ├── discord_logger.py  Logging forwarder to Discord channel
│   ├── speak.sh           Voice feedback endpoint (send to Voice Box)
│   ├── start.sh           Startup script
│   ├── voices/            Piper TTS model files (git-ignored, ~290MB total)
│   │   ├── en_GB-cori-high.onnx(.json)
│   │   ├── en_GB-jenny_dioco-medium.onnx(.json)
│   │   ├── en_GB-alan-medium.onnx(.json)
│   │   └── en_GB-northern_english_male-medium.onnx(.json)
│   └── static/            Web UI assets (audio-player.js, app.js, avatars)
└── docs/                  Documentation
    ├── DEPLOYMENT.md      Full deployment/recovery guide
    ├── NX_VOX_PLAN.md     Piper TTS integration design document
    └── VOICES.md          Voice browsing, download, and assignment guide
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

**IGNITION Phase 3** makes the startup ritual **fully automatic** via Claude Code's `SessionStart` hook. The ritual runs once when the session opens — before any user interaction — with no manual execution required.

#### **What Happens at Startup (Automatic Flow)**

1. **SessionStart Hook Fires** (automatic)
   - Triggers when Claude Code session opens, before any user message
   - Executes `python3 scripts/startup.py` with 60-second timeout
   - Runs silently in background, writes checkpoint file

2. **IGNITION Phase 2 Orchestrator Runs** (`scripts/startup.py`)
   - Sends varied initial pleasantry immediately (voice + text) — Nick knows system is responsive
   - **Parallel checks** (concurrent via ThreadPoolExecutor):
     - **Voice Box Health:** Checks both ports 8001 (local) and 8002 (authenticated)
     - **Context Files:** Verifies memory/core.md, memory/lucentIdent.md, memory/userIdent.md, memory/LTMemory.md exist
     - **Compression Trigger:** Fires backup_memory.py to archive previous session's notes (non-blocking)
   - **Auto-Restart Fallback:** If voice box offline, automatically runs `bash ui/start.sh` and polls for up to 20 seconds
   - **Logger Initialization:** Runs `session_logger.py init` with /tmp fallback if primary logger fails
   - **Checkpoint Write:** Stores ritual completion in `memory/.ritual_checkpoint.json`
   - **Exit Status:** Returns STARTUP_OK, STARTUP_DEGRADED, or ALREADY_COMPLETE

3. **UserPromptSubmit Hook Injects Context** (automated)
   - `lucent-init.sh` runs when user types first message
   - Injects memory files: memory/LTMemory.md, core.md, lucentIdent.md, userIdent.md, today's note, REMINDERS.md
   - Shows checkpoint status: "✓ Startup validated for today (auto-triggered via SessionStart hook)" if successful
   - Shows fallback warning if checkpoint is stale, with manual `startup.py` command

4. **Load priorities and reminders** (automated)
   - Read Current Priorities section in LTMemory.md (injected by hook)
   - Read REMINDERS.md (injected by hook alongside LTMemory.md)
   - Review pattern-based reminders (due today), context-triggered reminders, opportunistic reminders

5. **Ready for Interaction**
   - Ritual complete; voice box online, context loaded, checkpoint valid
   - Ready to respond to Nick

6. **Respond using three-layer requirement**
   - Log to daily note (append to memory/YYYY-MM-DD.md)
   - Send voice (curl to localhost:8001/speak)
   - Send text (response in Claude Code)
   - All three, every time. Framework validates.

#### **IGNITION — Startup Ritual Architecture**

The startup ritual is built on **IGNITION**, a three-phase system that ensures reliable, automatic, resilient initialization:

| Phase | Component | Status | Function |
|---|---|---|---|
| **Phase 1** | `validate_startup.py` | Complete | Sequential validation gate: voice box + context files + session logger + checkpoint |
| **Phase 2** | `scripts/startup.py` | Complete | Robust orchestrator: parallel checks, dual voice box (8001 + 8002), auto-restart fallback, /tmp logger fallback, comprehensive logging |
| **Phase 3** | `SessionStart` hook in `.claude/settings.json` | Complete | Automatic execution: fires at session open before any user interaction, no manual execution required |

**Phase 2 Features (Robust Orchestrator):**
- **Parallel Execution:** Voice box + context + compression run concurrently (ThreadPoolExecutor)
- **Dual Voice Box Support:** Both ports 8001 (local) and 8002 (authenticated) validated together
- **Auto-Restart Fallback:** If either port offline, automatically restarts Piper and polls up to 20 seconds
- **Session Logger Fallback:** If primary logger fails, writes to `/tmp/lucent_session_YYYYMMDD.log`
- **Per-Step Timeouts:** 3s health check, 20s restart window, 5s logger, 10s compression
- **Graceful Degradation:** Returns STARTUP_OK, STARTUP_DEGRADED, or ALREADY_COMPLETE with detailed logging
- **Idempotency Guard:** Same-day reruns short-circuit to ALREADY_COMPLETE instantly
- **Comprehensive Logging:** All events logged to activity log and daily note with timestamps

**Phase 3 Automation:**
- `SessionStart` hook in `.claude/settings.json` fires `startup.py` automatically when session opens
- Runs before any user interaction — guaranteed initialization
- Silent execution (output to log, not context) — checkpoint verified via lucent-init.sh output
- Per-session-once mechanism via checkpoint file (`memory/.ritual_checkpoint.json`)
- Fallback: If checkpoint stale, `lucent-init.sh` prints warning with manual `startup.py` command

#### **Proactive Startup Acknowledgement (100% Automatic)**

When startup completes successfully, the system sends a **proactive acknowledgement** before the user needs to send a message. This ensures Nick gets immediate confirmation that all systems are initialized and ready.

**Complete Flow:**

1. **Startup Validation** (SessionStart hook → `scripts/startup.py`)
   - Runs parallel checks (voice box, context files, compression)
   - Sends initial pleasantry: "Give me just a moment..." (voice + text)
   - Writes readiness marker: `memory/.startup_ready_YYYY-MM-DD.txt`
   - Returns: STARTUP_OK, STARTUP_DEGRADED, or ALREADY_COMPLETE
   - Sends readiness pleasantry: "Ready when you are" (voice + text from READINESS_PLEASANTRIES pool)

2. **Proactive Acknowledgement** (SessionStart hook → `scripts/acknowledge_startup.py`)
   - Runs immediately after `startup.py` completes (same hook, chained execution)
   - Reads startup marker to confirm STARTUP_OK status
   - Selects random message from 20-message acknowledgement pool
   - Sends voice + text: "Startup ritual complete. Standing by." (example; varies each time)
   - Logs to daily note: `[HH:MM:SS] **Startup acknowledgement sent:** <message>`
   - Exits cleanly

**Key Properties:**
- **100% Reliable:** No Claude agent invocation — direct Python script in SessionStart hook
- **Proactive (Not Reactive):** Sends acknowledgement before user sends first message
- **Unpredictable:** 20-message pool rotates randomly — never robotic or repetitive
- **Fast:** ~1-2 seconds total (startup.py + acknowledge_startup.py)
- **Logged:** Every acknowledgement recorded with timestamp in daily note
- **Zero Latency:** Runs in hook context, doesn't block user input

**Acknowledgement Message Pool (20 variations):**
- "Startup ritual complete. Standing by."
- "Context loaded. Ready for your command."
- "Initialization sequence finished. Awaiting instruction."
- "All systems initialized. Let's begin."
- ...and 16 more unique phrases

**SessionStart Hook Configuration:**
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/nick/dev/lucent/scripts/startup.py && python3 /home/nick/dev/lucent/scripts/acknowledge_startup.py",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

**User Experience:**
- Session opens → SessionStart hook fires automatically
- Hears: Initial pleasantry (voice) → Startup checks run in parallel → Readiness pleasantry (voice) → Proactive acknowledgement (voice)
- All before user types anything
- Ready to accept commands immediately

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

### NERO — Self-Improvement System (2026-06-03)

Lucent now learns continuously from conversations. Project **NERO** added five interlocked capabilities inspired by the [Hermes Agent](https://github.com/oborounov/hermes-agent) framework, adapted to run inside Claude Code via hooks and the Anthropic API.

#### 1. Semantic Memory Recall (Phase 1)
Before every turn, the `UserPromptSubmit` hook embeds the incoming message with local Ollama `nomic-embed-text` and injects the top-5 most relevant memory chunks as a fenced `<memory-context>` block — fully local, zero API cost, 100% reliable (graceful no-op if Ollama is unavailable).

```bash
python3 scripts/memory_index.py build        # rebuild index (auto on changes)
python3 scripts/memory_index.py query "text" # test a query
python3 scripts/memory_index.py status       # show chunk counts by source
```

**Sources indexed:** `memory/LTMemory.md`, `~/.claude/.../memory/*.md` (auto-memory), last 7 daily notes, all `memory/skills/**/*.md`, plus their archives.

#### 2. Skill Library (Phase 2)
Procedural knowledge packages in `memory/skills/` — *how to do a class of task for Nick*. Distinct from `agents/` (personas) and `memory/` (facts). Four core seed skills are shipped and protected; the reflection loop adds more over time.

```
memory/skills/
├── .protected              # slugs the curator never touches
├── .usage.json             # per-skill use counters + last_used
├── .archive/               # archived skills (recoverable, never deleted)
├── voice-protocol/         # mandatory dual-channel communication
├── daily-note-protocol/    # what/how to log
├── memory-reference-lookup/# read source files before answering lookups
└── project-creation/       # scaffold workflow + CLAUDE.md template
```

Each skill: `SKILL.md` (description, triggers, instructions, pitfalls) + optional `references/`, `templates/`, `scripts/` subdirectories.

```bash
python3 scripts/skills.py list            # list all skills
python3 scripts/skills.py view <name>     # read a skill (bumps use counter)
python3 scripts/skills.py status          # usage stats
```

Skills are listed in the `SessionStart` identity bundle (progressive disclosure — names and descriptions only; bodies load on demand).

#### 3. Per-Turn Reflection Loop (Phase 3)
After every turn, the `Stop` hook spawns a **detached background worker** in ~25ms (zero turn latency). The worker runs:

1. **Stage 0 — trivial filter:** exchanges under 200 chars → skip (no API cost)
2. **Stage 1 — Haiku gate:** "is there anything worth durably saving here?" YES/NO
3. **Stage 2 — Sonnet writer:** decides exactly what to save, emits structured JSON actions

Ported from Hermes' `background_review.py` — including the critical **anti-pattern list**: never capture environment-dependent failures, negative tool claims ("X is broken"), transient errors, or one-off narratives.

Starts in **propose mode**: suggestions land in `memory/nero_inbox.md` for review before anything is written. Switch to `auto` once trusted.

```bash
python3 scripts/reflect.py status              # state + pending count
python3 scripts/reflect.py review              # read pending proposals
python3 scripts/reflect.py apply <id>          # apply a proposal
python3 scripts/reflect.py reject <id>         # reject a proposal
python3 scripts/reflect.py mode propose|auto   # switch mode
python3 scripts/reflect.py enable|disable      # toggle the loop
```

Config lives in `memory/.nero/config.json`.

#### 4. Curator (Phase 4)
Weekly skill lifecycle management + memory hygiene. Dry-run by default; `--live` applies changes with a pre-run snapshot. **Archive-only** — never deletes.

**4a — Skill curation:**
- Lifecycle transitions: `active → stale (30d) → archived (90d)`, reactivates on use. Protected/pinned skills exempt.
- LLM umbrella-building pass (Sonnet): clusters narrow reflection-created skills and merges them into broad class-level umbrellas.

**4b — Memory hygiene:**
- `LTMemory.md` Recent Sessions capped at 10 — older sessions moved to `memory/LTMemory.archive.md` (still recall-indexed).
- Auto-memory stale archive: completed project files untouched for 90+ days → `archive/`.

```bash
python3 scripts/skill_curator.py run             # dry-run (report only)
python3 scripts/skill_curator.py run --live      # apply (with snapshot)
python3 scripts/skill_curator.py memory-hygiene --live
python3 scripts/skill_curator.py snapshot        # manual snapshot
python3 scripts/skill_curator.py report          # print last report
```

Report written to `memory/.nero/curator_report.md`.

#### 5. Compaction Guard + Insights (Phase 5)
- **`PreCompact` hook:** before Claude Code compacts the transcript, injects current priorities, NERO state, skills listing, and today's daily note tail into the compaction context — so compaction never silently drops durable knowledge.
- **Insights dashboard:** one-command view of the entire self-improvement loop.

```bash
python3 scripts/insights.py         # full report
python3 scripts/insights.py --brief # one-page summary
```

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

### Security Auditing (Gibson Agent)

Gibson is a specialized security auditor agent that scans code for vulnerabilities, secrets exposure, and infrastructure security issues. It categorizes findings by type (custom code, external libraries, dependencies) and provides actionable remediation guidance.

**Components:**
- `agents/gibson-agent.md` — Agent personality and capabilities
- `scripts/security_auditor.py` — Core scanning logic (400+ lines)
- `scripts/run-security-audit.py` — Entry point for running audits
- `scripts/pre-commit-security-hook.py` — Git pre-commit integration

**Vulnerability Categories Detected:**
1. **Custom Code** — Security issues you authored and can fix directly
   - XSS vulnerabilities (innerHTML with untrusted data)
   - Command injection (eval, exec in Python)
   - SQL injection patterns
   - Missing CORS headers on endpoints
   - Hardcoded credentials or API keys

2. **External Code** — Patterns in external/minified libraries (cannot be modified)
   - Identifies vulnerabilities in dependency code
   - Explains why no fix is possible (upgrade library instead)
   - Guides toward dependency updates

3. **Dependencies** — npm/pip package vulnerabilities with available patches
   - CVE numbers and official titles
   - Current vs. upgrade versions
   - Major version upgrade warnings
   - Exact npm/pip upgrade commands

4. **Secrets** — Visibility into secret handling
   - References to secrets in code (config files, env variables)
   - Protected secrets (.gitignore validation)
   - Clarifies: code references ≠ exposed secrets

**Running an Audit:**
```bash
# Manual scan of a project
python3 scripts/run-security-audit.py /path/to/project

# Output:
# 1. Markdown report: memory/security-audits/YYYY-MM-DD/{project}-HH-MM-SS.md
# 2. JSON summary (to stdout)
# 3. Voice summary with critical/high items listed first
```

**Report Structure:**
```
# Security Audit: {project}

## Summary
- Vulnerability counts by severity and category
- Secret reference patterns found (code references)
- Protected secrets (.gitignore status)

## Vulnerability Categories

--------------------------------------------------

## Custom Code — Issues you authored and can fix directly

### 🟠 HIGH
- Finding title
- File affected
- Detailed issue description
- How to Fix: Specific remediation steps

### 🟡 MEDIUM
[Similar format]

--------------------------------------------------

## External Code — Patterns in external, third-party, or minified code

### 🟠 HIGH
[External code findings with explanation of why no direct fix]

--------------------------------------------------

## Dependencies — npm, pip, or other package vulnerabilities

### 🔴 CRITICAL
- Package name + CVE/Advisory ID + official title
- Location: package.json file
- Current version → Upgrade to version (⚠️ Major version warning if applicable)
- How to Fix: `npm upgrade package@version` (exact command)

### 🟠 HIGH
[Similar format]

--------------------------------------------------

## 🔑 Secrets Analysis
- Code references found (not actual secrets)
- Protected secrets (.gitignore validated)
```

**Voice Summary:**
Gibson provides voice feedback with all findings categorized by severity and type:
```
"Gibson audit of lucent: 1 critical (1 fixable deps), 6 high (1 in code, 5 fixable deps), 
4 medium (1 in code, 3 fixable deps) findings. Code issues: innerHTML assignment. 
3 secret reference patterns found (not actual secrets). Full report saved to security-audits folder."
```

**Git Pre-Commit Integration:**
```bash
# Installed to .git/hooks/pre-commit (automatic on commit attempt)

# Behavior:
- Critical vulnerabilities: BLOCK push (requires explicit override: --no-verify)
- High vulnerabilities: WARN + block (requires explicit override)
- Medium/Low: WARN + auto-proceed after 60 seconds
```

**Example Workflow:**
```bash
# 1. Make changes to code
git add changes.js

# 2. Attempt commit (hook runs automatically)
git commit -m "Fix feature X"

# 3. If vulnerabilities found:
[Gibson] Found 1 critical vulnerability in custom code (innerHTML)
[Gibson] Critical issues must be fixed or overridden explicitly.
[Gibson] Use: git commit --no-verify to override (not recommended)

# 4. Fix the vulnerability or override
# Fix: Replace innerHTML with safe createElement()
# Then commit again

git commit -m "Fix feature X + security: Replace innerHTML with createElement"
```

**Scheduling Audits:**
```bash
# One-off audit
python3 scripts/run-security-audit.py /home/nick/dev/lucent

# Result appears in memory/security-audits/ folder
# Reports are archived and can be reviewed over time
```

**Integration with Claude Code / OpenCode:**
```bash
# Invoke Gibson directly via agent framework
python3 scripts/lucent.py agent gibson "Audit /home/nick/dev/lucent"
```

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
       + NERO self-improvement loop

                    ┌─────────────────────────────────────────┐
                    │  Claude Code session                    │
                    │                                         │
  UserPromptSubmit  │  ┌──────────────┐   ┌───────────────┐  │
  ──────────────── ►│  │ Recall hook  │   │  SessionStart │  │
  (user message)    │  │ (semantic    │   │  identity     │  │
                    │  │  embed+fetch)│   │  bundle       │  │
                    │  └──────┬───────┘   └───────────────┘  │
                    │         │ <memory-context>              │
                    │         ▼                               │
                    │  ┌──────────────────────────────────┐  │
                    │  │  Claude (Opus / Sonnet / Haiku)  │  │
                    │  └──────────────────┬───────────────┘  │
                    │                     │ response          │
  Stop hook         │  ◄──────────────────┘                  │
  ────────────────► │  ┌──────────────┐                      │
  (detached)        │  │ reflect.py   │  Haiku gate           │
                    │  │ worker       │→ Sonnet writer        │
                    │  └──────┬───────┘→ proposals inbox     │
                    │         │                               │
                    └─────────┼───────────────────────────── ┘
                              │ writes (propose-mode: inbox first)
                              ▼
              ┌───────────────────────────────────────────┐
              │  memory/  (three-tier + skill library)    │
              │  ├── LTMemory.md    (live, capped at 10)  │
              │  ├── LTMemory.archive.md  (older sessions)│
              │  ├── YYYY-MM-DD.md  (daily notes)         │
              │  ├── archive/       (compressed notes)    │
              │  ├── skills/        (NERO skill library)  │
              │  └── .recall_index.json  (embeddings)     │
              └───────────────────────────────────────────┘
                              │
                    Monday curator (skill_curator.py)
                    lifecycle + umbrella consolidation
                    + LTMemory hygiene  (dry-run → live)

Everything lives in lucent/ root and syncs to GitHub via lucent-sync.sh.
Per-project .lucentrc files wire any dev session into the system.
```

## Web UI

<img src="docs/images/WebUI.png" alt="Lucent Voice Box Web UI" width="100%" />

## License

Private repository. All rights reserved.

