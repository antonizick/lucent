# Lucent — Deployment Guide

> **Audience:** Someone deploying Lucent from scratch on a fresh Linux instance (Ubuntu 22.04 LTS or WSL2).
> **Recovery sources:** Two GitHub repositories — Lucent Core and Lucent Memory.
> **Primary AI platform:** Claude Code. Ollama + OpenCode are covered in dedicated sections after the core deployment.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Prerequisites](#2-prerequisites)
3. [Repository Setup](#3-repository-setup)
4. [Python Environment](#4-python-environment)
5. [Environment Variables](#5-environment-variables)
6. [Systemd Services](#6-systemd-services)
7. [Cron Jobs](#7-cron-jobs)
8. [Shell Configuration — .bashrc](#8-shell-configuration--bashrc)
9. [Claude Code — Primary Platform](#9-claude-code--primary-platform)
10. [Ollama — Local AI Backend](#10-ollama--local-ai-backend)
11. [OpenCode — Alternative Platform](#11-opencode--alternative-platform)
12. [Docker & Open WebUI](#12-docker--open-webui)
13. [Discord Integration](#13-discord-integration)
14. [Port Reference](#14-port-reference)
15. [Verification Checklist](#15-verification-checklist)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. System Overview

Lucent is a persistent AI assistant framework that runs across two Git repositories and multiple interconnected services. Here is the high-level architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                      AI Platforms                           │
│  Claude Code (primary) │ OpenCode (alternative)             │
└───────────────┬─────────────────────┬───────────────────────┘
                │                     │
                ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Hook / Plugin Layer                             │
│  .claude/settings.json hooks │ .opencode/lucent-plugin.ts  │
│  scripts/lucent-init.sh      │ .opencode/startup-helper.py │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Voice Box (port 8001)                        │
│  ui/server.py — FastAPI — TTS queue, SSE broadcast,         │
│  service health, backup status, agent invocation            │
└──────────────┬────────────────────┬────────────────────────┘
               │                    │
     ┌─────────▼──────┐   ┌─────────▼──────┐
     │ Discord Bot     │   │  Ollama         │
     │ port 8003       │   │  port 11434     │
     │ discord_bot.py  │   │  Local LLM      │
     └────┬───────────┘   └─────────────────┘
          │
  ┌───────▼──────────────────────────────┐
  │ Discord Monitor + Poller              │
  │ discord_monitor.py / discord_poller.py│
  └───────────────────────────────────────┘

Memory:
  /home/nick/dev/lucent/memory/   ← separate git repo (LucentMemory)
  Daily notes, LTMemory.md, agent files, logs
```

### Two Git Repositories

| Repo | GitHub URL | Local Path |
|------|-----------|-----------|
| Lucent Core | `https://github.com/antonizick/lucent.git` | `~/dev/lucent` |
| Lucent Memory | `https://github.com/antonizick/LucentMemory.git` | `~/dev/lucent/memory` |

The Memory repo is a **git submodule-style nested repo** inside the core repo. It has its own independent origin and is committed/pushed separately by the automated backup script.

---

## 2. Prerequisites

### 2.1 System Packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    git \
    python3 \
    python3-pip \
    curl \
    wget \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev
```

### 2.2 Required Software Versions

| Software | Minimum Version | Notes |
|----------|----------------|-------|
| Python | 3.10+ | Ubuntu 22.04 ships 3.10.12 |
| Node.js | 20+ | Required for OpenCode plugin |
| npm | 10+ | Ships with Node.js |
| Git | Any recent | For repo operations |
| Docker | Any recent | For Open WebUI only |

### 2.3 Install Node.js (if not present)

```bash
# Via NodeSource (recommended)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# Verify
node --version   # should be v22+
npm --version    # should be 10+
```

---

## 3. Repository Setup

### 3.1 Create Project Directory

```bash
mkdir -p ~/dev
cd ~/dev
```

### 3.2 Clone Lucent Core

```bash
git clone https://github.com/antonizick/lucent.git lucent
cd lucent
```

### 3.3 Clone Lucent Memory (nested inside core)

The memory repo lives at `~/dev/lucent/memory/` and is its own independent git repository. The `memory/` directory already exists in the core repo (it has a `.gitkeep`), so you need to handle this carefully:

```bash
# Remove the placeholder directory that exists in the core repo
rm -rf ~/dev/lucent/memory

# Clone the memory repo into that location
git clone https://github.com/antonizick/LucentMemory.git ~/dev/lucent/memory
```

Verify both repos are set up:

```bash
git -C ~/dev/lucent remote -v       # should show antonizick/lucent.git
git -C ~/dev/lucent/memory remote -v # should show antonizick/LucentMemory.git
```

### 3.4 Verify Directory Structure

After cloning, your structure should look like:

```
~/dev/lucent/
├── .claude/                  # Claude Code hooks and settings
│   ├── settings.json
│   └── settings.local.json
├── .opencode/                # OpenCode plugin and config
│   ├── lucent-plugin.ts
│   ├── startup-helper.py
│   ├── package.json
│   └── settings.json
├── agents/                   # Sub-agent personality files
│   ├── curator-agent.md
│   ├── git-agent.md
│   ├── planner-agent.md
│   ├── reviewer-agent.md
│   └── writer-agent.md
├── memory/                   # ← Separate git repo (LucentMemory)
│   ├── .git/
│   ├── core.md
│   ├── lucentIdent.md
│   ├── userIdent.md
│   ├── LTMemory.md
│   ├── REMINDERS.md
│   ├── logs/
│   ├── scripts/
│   └── YYYY-MM-DD.md         # Daily notes
├── scripts/                  # Utility and automation scripts
│   ├── lucent-init.sh
│   ├── backup_memory.py
│   ├── session_logger.py
│   ├── invoke_agent.py
│   ├── ai-launcher.sh
│   ├── rotate_voice_logs.py
│   ├── verify_startup.py
│   └── check_reminders.py
├── ui/                       # Voice Box FastAPI server
│   ├── server.py
│   ├── discord_bot.py
│   ├── discord_monitor.py
│   ├── discord_poller.py
│   ├── discord_logger.py
│   ├── requirements.txt
│   ├── start.sh
│   ├── .env
│   └── static/               # Web UI (HTML/CSS/JS)
├── *.service                 # systemd service unit files
├── CLAUDE.md                 # Claude Code instructions
├── opencode.json             # OpenCode config
└── restart-services.sh       # Service restart utility
```

---

## 4. Python Environment

### 4.1 Install Python Dependencies

All Python packages install system-wide via pip3. No virtualenv is used.

```bash
cd ~/dev/lucent/ui
pip3 install -r requirements.txt
```

The `requirements.txt` contains:

```
fastapi==0.136.1
uvicorn==0.46.0
anthropic>=0.28.0
python-dotenv>=1.0.0
httpx>=0.24.0
requests>=2.31.0
```

### 4.2 Install Discord Bot Additional Dependencies

The Discord bot (`ui/discord_bot.py`) requires packages not in `requirements.txt`:

```bash
pip3 install "discord.py>=2.3.0" aiohttp flask
```

### 4.3 Full Pip Install Command (All at Once)

```bash
pip3 install \
    "fastapi==0.136.1" \
    "uvicorn==0.46.0" \
    "anthropic>=0.28.0" \
    "python-dotenv>=1.0.0" \
    "httpx>=0.24.0" \
    "requests>=2.31.0" \
    "discord.py>=2.3.0" \
    "aiohttp>=3.13.0" \
    "flask>=3.0.0"
```

### 4.4 Verify Python Path

The Claude Code hook and scripts rely on `python3` being available. Confirm:

```bash
which python3         # /usr/bin/python3
python3 --version     # Python 3.10.x or higher
```

---

## 5. Environment Variables

### 5.1 Create the .env File

The Voice Box server and Discord bot both read from `ui/.env`.

```bash
cp ~/dev/lucent/ui/.env.example ~/dev/lucent/ui/.env
```

Edit `~/dev/lucent/ui/.env` and fill in all values:

```bash
# Anthropic API — required for Claude-powered agent invocation
ANTHROPIC_API_KEY=sk-ant-...

# Discord Bot Configuration
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_SERVER_ID=your_discord_server_id
DISCORD_CHANNEL_ID=channel_id_where_lucent_reads_commands
DISCORD_LOG_CHANNEL_ID=channel_id_for_lucent_logs
DISCORD_LOG_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Backend URL (Voice Box routes Discord responses to this)
BACKEND_URL=http://localhost:8002

# Lucent root path (used by some scripts)
LUCENT_ROOT=/home/nick/dev/lucent
```

> **Note:** `BACKEND_URL` is set to `http://localhost:8002` by default in the example but the Voice Box runs on `8001`. The Discord bot's webhook receiver runs on `8003`. Review and adjust per your active service configuration.

### 5.2 Secure the .env File

```bash
chmod 600 ~/dev/lucent/ui/.env
```

---

## 6. Systemd Services

### 6.1 Service Architecture

Five Lucent-specific services must be installed and enabled. The service unit files live in the repo root and must be **copied** (not symlinked) to `/etc/systemd/system/`.

| Service File | Description | Port |
|-------------|-------------|------|
| `lucent-voice-box.service` | FastAPI Voice Box — core TTS/API hub | 8001 |
| `lucent-server.service` | Discord Integration Server | — |
| `lucent-monitor.service` | Discord Instruction Monitor | — |
| `lucent-poller.service` | Discord Message Poller | — |
| `discord-bot.service` | Discord Bot (webhook receiver) | 8003 |

Service dependency order: `lucent-voice-box` → `lucent-server` → `lucent-monitor` and `lucent-poller`

### 6.2 Install All Service Files

```bash
cd ~/dev/lucent

sudo cp lucent-voice-box.service /etc/systemd/system/
sudo cp lucent-server.service    /etc/systemd/system/
sudo cp lucent-monitor.service   /etc/systemd/system/
sudo cp lucent-poller.service    /etc/systemd/system/
sudo cp discord-bot.service      /etc/systemd/system/

sudo systemctl daemon-reload
```

### 6.3 Enable and Start Services

Enable all services to start on boot, then start them now:

```bash
sudo systemctl enable --now lucent-voice-box.service
sudo systemctl enable --now lucent-server.service
sudo systemctl enable --now lucent-monitor.service
sudo systemctl enable --now lucent-poller.service
sudo systemctl enable --now discord-bot.service
```

### 6.4 Verify Services Are Running

```bash
sudo systemctl status lucent-voice-box lucent-server lucent-monitor lucent-poller discord-bot --no-pager
```

Or use the included restart script which also shows status:

```bash
bash ~/dev/lucent/restart-services.sh
```

### 6.5 Service File Reference

**lucent-voice-box.service** — The core hub. Must be running before any other service.
```ini
[Unit]
Description=Lucent Voice Box
After=network-online.target

[Service]
Type=simple
User=nick
WorkingDirectory=/home/nick/dev/lucent/ui
ExecStart=/bin/bash start.sh
Restart=on-failure
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

**lucent-server.service** — Routes Discord commands through the system.
```ini
[Unit]
Description=Lucent Discord Integration Server
After=network-online.target

[Service]
Type=simple
User=nick
WorkingDirectory=/home/nick/dev/lucent/ui
ExecStart=/usr/bin/python3 /home/nick/dev/lucent/ui/server.py
Restart=on-failure
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

**lucent-monitor.service** — Watches for Discord instructions, depends on `lucent-server`.
```ini
[Unit]
Description=Lucent Discord Instruction Monitor
After=network.target lucent-server.service
Wants=lucent-server.service

[Service]
Type=simple
User=nick
WorkingDirectory=/home/nick/dev/lucent/ui
ExecStart=/usr/bin/python3 /home/nick/dev/lucent/ui/discord_monitor.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**lucent-poller.service** — Polls Discord messages, requires `lucent-server`.
```ini
[Unit]
Description=Lucent Discord Message Poller
After=network-online.target lucent-server.service
Requires=lucent-server.service

[Service]
Type=simple
User=nick
WorkingDirectory=/home/nick/dev/lucent/ui
ExecStart=/usr/bin/python3 /home/nick/dev/lucent/ui/discord_poller.py
Restart=on-failure
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

**discord-bot.service** — The Discord bot itself (Flask webhook on port 8003).
```ini
[Unit]
Description=Lucent Discord Bot
After=network-online.target

[Service]
Type=simple
User=nick
WorkingDirectory=/home/nick/dev/lucent/ui
ExecStart=/usr/bin/python3 /home/nick/dev/lucent/ui/discord_bot.py
Restart=on-failure
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

### 6.6 Service Management Reference

```bash
# Restart all Lucent services at once
bash ~/dev/lucent/restart-services.sh

# View live logs for a service
sudo journalctl -fu lucent-voice-box.service

# Stop a service
sudo systemctl stop lucent-voice-box.service

# Check status
sudo systemctl status discord-bot.service
```

---

## 7. Cron Jobs

Two cron jobs keep memory backed up and logs rotated.

### 7.1 Install Cron Jobs

```bash
crontab -e
```

Add these two lines:

```cron
# Lucent: Backup memory repo to GitHub every hour
0 * * * * python3 /home/nick/dev/lucent/scripts/backup_memory.py >> /tmp/memory-backup-cron.log 2>&1

# Lucent: Rotate voice/activity logs every Monday at 2am
0 2 * * 1 python3 /home/nick/dev/lucent/scripts/rotate_voice_logs.py >> /tmp/voice-log-rotation.log 2>&1
```

Save and exit.

### 7.2 What Each Job Does

**Memory Backup (hourly)**
- Runs `git add -A && git commit && git push` inside `memory/`
- Skips commit if there are no changes (safe to run repeatedly)
- Logs results to `/tmp/memory-backup-cron.log`
- Also appends backup events to today's daily note

**Voice Log Rotation (weekly)**
- Compresses previous month's activity logs into `ui/logs/archives/activity_YYYY-MM.tar.gz`
- Mirrors the same behavior triggered at Voice Box startup for monthly compression
- Logs results to `/tmp/voice-log-rotation.log`

### 7.3 Verify Cron Jobs Are Installed

```bash
crontab -l
```

---

## 8. Shell Configuration — .bashrc

These blocks must be present in `~/.bashrc` for Lucent to function correctly on every shell session.

### 8.1 PATH Additions

Add these exports near the bottom of `~/.bashrc`:

```bash
# pip user-installed binaries (includes claude CLI)
export PATH=$PATH:~/.local/bin

# OpenCode binary
export PATH=/home/nick/.opencode/bin:$PATH
```

### 8.2 Auto-Start Services on WSL Launch

These blocks start Ollama, Docker, and Open WebUI automatically when a WSL shell opens:

```bash
# === AUTO-START OLLAMA & OPEN WEBUI ON WSL LAUNCH ===

# Start Ollama if not already running
if ! pgrep -x "ollama" > /dev/null; then
    echo "[auto] Starting Ollama..."
    ollama serve &>/dev/null &
fi

# Ensure Docker daemon is running
sudo service docker start &>/dev/null || true

# Start Open WebUI container if not already running
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qw "open-webui"; then
    echo "[auto] Starting Open WebUI..."
    sudo docker run -d \
        -p 8088:8080 \
        --add-host=host.docker.internal:host-gateway \
        -v open-webui-data:/app/backend/data \
        --name open-webui \
        --restart always \
        ghcr.io/open-webui/open-webui:latest
fi
```

> **Note:** The `sudo service docker start` command requires passwordless sudo for the `service` command, or you must configure `/etc/sudoers` appropriately. On WSL2, this is standard.

### 8.3 Apply .bashrc Changes

```bash
source ~/.bashrc
```

---

## 9. Claude Code — Primary Platform

### 9.1 Install Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
```

Verify:

```bash
claude --version
which claude   # should be ~/.local/bin/claude or /usr/local/bin/claude
```

> If `claude` is not found after install, ensure `~/.local/bin` is in your PATH (see Section 8.1).

### 9.2 Authenticate with Anthropic

```bash
claude login
```

This opens a browser for OAuth authentication with your Anthropic account. Follow the prompts. Your API key is stored in `~/.claude/` after login.

Alternatively, set the API key directly in `ui/.env` (used by the Voice Box server for agent invocation):

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." >> ~/dev/lucent/ui/.env
```

### 9.3 Project-Level Claude Code Hooks

The Claude Code hooks are already committed to the repo at `.claude/settings.json`. They run automatically when Claude Code is launched from the `~/dev/lucent` directory. No additional setup is required — just clone the repo and the hooks are there.

**What the hooks do:**

| Hook Event | Command | Purpose |
|-----------|---------|---------|
| `UserPromptSubmit` | `scripts/lucent-init.sh` | Injects full Lucent context before every response |
| `SessionEnd` | `curl .../speak` | Sends "Session complete." voice message when session ends |

**`lucent-init.sh` injects:**
- Today's date
- `memory/core.md` — operating rules
- `memory/lucentIdent.md` — Lucent's identity
- `memory/userIdent.md` — Nick's profile
- `memory/LTMemory.md` — long-term memory
- `memory/REMINDERS.md` — active reminders
- Last 7 days of daily notes (chronological)

This runs on **every** prompt submission, giving Claude Code full context on every turn without requiring manual startup steps.

### 9.4 Launch Claude Code as Lucent

Always launch from the lucent project root:

```bash
cd ~/dev/lucent
claude
```

Or use the AI launcher (see Section 9.5).

### 9.5 AI Launcher

The `scripts/ai-launcher.sh` provides an interactive menu for choosing platform and model:

```bash
bash ~/dev/lucent/scripts/ai-launcher.sh
```

Or quick-launch directly:

```bash
bash ~/dev/lucent/scripts/ai-launcher.sh claude sonnet
bash ~/dev/lucent/scripts/ai-launcher.sh claude opus
bash ~/dev/lucent/scripts/ai-launcher.sh claude haiku
```

### 9.6 Verify Claude Code Is Working

1. Launch Claude Code from `~/dev/lucent`
2. Type any message
3. Confirm the hook output appears (you'll see `[Lucent] You are Lucent. Today is YYYY-MM-DD.` prefixing the context)
4. Confirm a voice message plays through the browser UI at `http://localhost:8001`

---

## 10. Ollama — Local AI Backend

Ollama provides local LLM inference used by the sub-agent system and the Discord bot's local model feature.

### 10.1 Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

This installs the `ollama` binary to `/usr/local/bin/ollama` and creates the `ollama.service` systemd unit automatically.

### 10.2 Enable Ollama on Boot

```bash
sudo systemctl enable --now ollama.service
sudo systemctl status ollama.service
```

### 10.3 Pull Required Models

The agent invocation system defaults to `mistral:latest`. Pull at minimum:

```bash
ollama pull mistral
```

Additional models used by the Discord bot (pulled on demand, but pre-pulling speeds things up):

```bash
ollama pull mistral        # default agent model
```

To see what models are currently available:

```bash
ollama list
```

### 10.4 Verify Ollama Is Running

```bash
curl http://localhost:11434/api/tags
```

Should return a JSON list of available models. The Voice Box `/services/health` endpoint also checks Ollama status.

### 10.5 Using Ollama with the Agent System

The sub-agent system (`scripts/invoke_agent.py`) calls Ollama directly:

```bash
python3 ~/dev/lucent/scripts/invoke_agent.py git "Stage and commit recent changes"
python3 ~/dev/lucent/scripts/invoke_agent.py curator "Compress 2026-05-10.md to 1-2 paragraphs"
python3 ~/dev/lucent/scripts/invoke_agent.py --model qwen3.6:35b planner "Break down the voice input feature"
```

Available agents (defined in `agents/`):

| Agent | File | Domain |
|-------|------|--------|
| `curator` | `curator-agent.md` | Memory compression, note curation, LTMemory reviews |
| `git` | `git-agent.md` | Commits, pushes, version control |
| `writer` | `writer-agent.md` | Documentation, technical writing |
| `reviewer` | `reviewer-agent.md` | Code review, quality assessment |
| `planner` | `planner-agent.md` | Task breakdown, architecture design |

### 10.6 Auto-Start on WSL Login

Ollama is also started from `.bashrc` (see Section 8.2) as a fallback in case the systemd service is not running.

---

## 11. OpenCode — Alternative Platform

OpenCode is a secondary AI coding platform. Lucent has a TypeScript plugin that enforces the startup ritual when OpenCode is used instead of Claude Code.

### 11.1 Install OpenCode

```bash
curl -fsSL https://opencode.ai/install | bash
```

This installs OpenCode to `~/.opencode/bin/opencode`. The PATH addition in `.bashrc` (Section 8.1) makes it available as `opencode`.

Verify:

```bash
opencode --version
which opencode  # should be ~/.opencode/bin/opencode
```

### 11.2 Install the OpenCode Plugin Dependencies

The Lucent plugin is a TypeScript file compiled at runtime. It requires its npm dependencies:

```bash
cd ~/dev/lucent/.opencode
npm install
```

This installs `@opencode-ai/plugin@1.14.48` into `.opencode/node_modules/`.

### 11.3 OpenCode Configuration Files

**`opencode.json`** (repo root) — Points OpenCode to Lucent's memory files and plugin:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": [
    "memory/core.md",
    "memory/lucentIdent.md",
    "memory/userIdent.md",
    "memory/LTMemory.md",
    "memory/REMINDERS.md"
  ],
  "plugin": [
    ".opencode/lucent-plugin.ts"
  ]
}
```

**`.opencode/settings.json`** — Environment and memory configuration:

```json
{
  "env": {
    "LUCENT_DIR": "."
  },
  "memory": {
    "files": [
      "memory/core.md",
      "memory/lucentIdent.md",
      "memory/userIdent.md",
      "memory/LTMemory.md"
    ],
    "updatePrompt": "At the end of each session, summarize the session into a daily note in memory/."
  }
}
```

### 11.4 How the OpenCode Plugin Works

The plugin (`.opencode/lucent-plugin.ts`) registers a tool called `lucent_startup` that the model is instructed to call before its first response. When called, it:

1. Runs `.opencode/startup-helper.py` — checks voice box health, initializes session logger
2. Reads today's daily note + yesterday + two days ago — injects live session context
3. Returns the three-layer protocol reminder (voice → log → text)

This mirrors what `lucent-init.sh` does for Claude Code, adapted for OpenCode's plugin architecture.

### 11.5 Launch OpenCode as Lucent

Always launch from the Lucent project root:

```bash
cd ~/dev/lucent
opencode .
```

Or via the AI launcher:

```bash
bash ~/dev/lucent/scripts/ai-launcher.sh opencode big-pickle
bash ~/dev/lucent/scripts/ai-launcher.sh opencode deepseek-v4-flash-free
```

### 11.6 Available Free OpenCode Models

The launcher includes these pre-configured free models:
- `big-pickle`
- `deepseek-v4-flash-free`
- `minimax-m2.5-free`
- `nemotron-3-super-free`
- `ring-2.6-1t-free`

Any locally-running Ollama model can also be selected from the launcher menu.

---

## 12. Docker & Open WebUI

Open WebUI is a browser-based interface for interacting with Ollama models. It runs in Docker on port 8088.

### 12.1 Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add your user to the docker group (optional — current setup uses sudo)
sudo usermod -aG docker $USER

# Start and enable Docker
sudo systemctl enable --now docker
```

### 12.2 Start Open WebUI

The `.bashrc` auto-start block (Section 8.2) handles this on each login. To start it manually:

```bash
sudo docker run -d \
    -p 8088:8080 \
    --add-host=host.docker.internal:host-gateway \
    -v open-webui-data:/app/backend/data \
    --name open-webui \
    --restart always \
    ghcr.io/open-webui/open-webui:latest
```

Access at: `http://localhost:8088`

### 12.3 Manage Open WebUI

```bash
# Check status
sudo docker ps | grep open-webui

# Stop
sudo docker stop open-webui

# Remove (data volume is preserved)
sudo docker rm open-webui

# View logs
sudo docker logs open-webui
```

---

## 13. Discord Integration

The Discord integration allows sending messages to Lucent through a Discord server, which are then routed through the voice box and processed.

### 13.1 Create a Discord Bot

1. Go to https://discord.com/developers/applications
2. Create a new Application
3. Navigate to **Bot** → **Add Bot**
4. Copy the **Bot Token** → set as `DISCORD_BOT_TOKEN` in `ui/.env`
5. Under **Privileged Gateway Intents**, enable **Message Content Intent**
6. Navigate to **OAuth2 → URL Generator**
   - Scopes: `bot`
   - Permissions: `Send Messages`, `Read Messages/View Channels`, `Add Reactions`
7. Use the generated URL to invite the bot to your server

### 13.2 Configure Discord IDs

In `ui/.env`:

```bash
DISCORD_SERVER_ID=<right-click your server → Copy ID>
DISCORD_CHANNEL_ID=<right-click the commands channel → Copy ID>
DISCORD_LOG_CHANNEL_ID=<right-click the logs channel → Copy ID>
```

To enable Copy ID: Discord Settings → Advanced → Developer Mode → ON.

### 13.3 Create a Webhook for Logging

1. In the Discord log channel → Edit Channel → Integrations → Webhooks
2. Create webhook → Copy URL
3. Set as `DISCORD_LOG_WEBHOOK_URL` in `ui/.env`

### 13.4 Restart Discord Services

After configuring `.env`:

```bash
sudo systemctl restart discord-bot.service lucent-server.service lucent-poller.service lucent-monitor.service
```

### 13.5 Discord Architecture

```
Discord User
    │  (sends message to commands channel)
    ▼
discord_bot.py (port 8003)
    │  (POSTs to /discord/pending)
    ▼
ui/server.py (port 8001) ─── stores in discord_pending queue
    │  (polled by)
    ▼
discord_poller.py ─────────── delivers to terminal / Claude Code
    │  (response routed via)
    ▼
ui/server.py /response ─────── routes back to discord_bot.py
    │  (bot sends reply in thread)
    ▼
Discord Channel
```

---

## 14. Port Reference

| Port | Service | Component |
|------|---------|-----------|
| 8001 | Voice Box API | `ui/server.py` (FastAPI/uvicorn) |
| 8003 | Discord Bot Webhook | `ui/discord_bot.py` (Flask) |
| 8088 | Open WebUI | Docker container (maps to internal 8080) |
| 11434 | Ollama | Local LLM inference engine |

---

## 15. Verification Checklist

Run through this checklist after deployment to confirm everything is working.

### 15.1 Services

```bash
# All five Lucent services should show "active (running)"
sudo systemctl status lucent-voice-box lucent-server lucent-monitor lucent-poller discord-bot --no-pager | grep -E "●|Active:"

# Ollama and Docker should also be active
sudo systemctl status ollama docker --no-pager | grep -E "●|Active:"
```

### 15.2 Voice Box API

```bash
# Health check
curl -s http://localhost:8001/services/health | python3 -m json.tool

# Send a test voice message
curl -X POST http://localhost:8001/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Deployment verification complete."}'

# Check backup status
curl -s http://localhost:8001/backup/status | python3 -m json.tool
```

### 15.3 Ollama

```bash
curl -s http://localhost:11434/api/tags | python3 -m json.tool
ollama list
```

### 15.4 Cron Jobs

```bash
crontab -l | grep lucent
# Should show two entries (backup_memory + rotate_voice_logs)
```

### 15.5 Git Remotes

```bash
git -C ~/dev/lucent remote -v
git -C ~/dev/lucent/memory remote -v
```

### 15.6 Claude Code

```bash
cd ~/dev/lucent
claude --version
# Launch Claude Code and confirm hook runs (you should see [Lucent] prefix in context)
```

### 15.7 Memory Backup Test

```bash
python3 ~/dev/lucent/scripts/backup_memory.py
# Should print: ✓ No changes to commit  OR  ✓ Committed and pushed
```

### 15.8 Session Logger Test

```bash
python3 ~/dev/lucent/scripts/session_logger.py init
python3 ~/dev/lucent/scripts/session_logger.py check
# Should print: ✓ Checkpoint valid
```

### 15.9 Web UI

Open a browser and navigate to:
- `http://localhost:8001` — Lucent Voice Box UI
- `http://localhost:8088` — Open WebUI (Ollama browser interface)

---

## 16. Troubleshooting

### Voice Box Not Responding

```bash
# Check service status
sudo systemctl status lucent-voice-box.service

# View recent logs
sudo journalctl -u lucent-voice-box.service -n 50

# Restart
sudo systemctl restart lucent-voice-box.service

# Manual start for debugging
cd ~/dev/lucent/ui
python3 -m uvicorn server:app --host 127.0.0.1 --port 8001
```

### Claude Code Hook Not Running

```bash
# Verify hook file is executable
ls -la ~/dev/lucent/scripts/lucent-init.sh
chmod +x ~/dev/lucent/scripts/lucent-init.sh

# Test the hook manually
bash ~/dev/lucent/scripts/lucent-init.sh | head -20

# Verify settings.json is correct
cat ~/dev/lucent/.claude/settings.json
```

### Memory Backup Failing

```bash
# Run manually and check output
python3 ~/dev/lucent/scripts/backup_memory.py

# Check if memory is a git repo
git -C ~/dev/lucent/memory status

# Check SSH/HTTPS auth to GitHub
git -C ~/dev/lucent/memory push --dry-run
```

### Ollama Not Starting

```bash
sudo systemctl status ollama.service
sudo journalctl -u ollama.service -n 30

# Start manually
ollama serve &
curl http://localhost:11434/api/tags
```

### Discord Bot Not Connecting

```bash
# Check .env is populated
cat ~/dev/lucent/ui/.env | grep DISCORD

# View bot logs
sudo journalctl -u discord-bot.service -n 50

# Restart bot
sudo systemctl restart discord-bot.service
```

### Open WebUI Container Not Starting

```bash
# Check if container exists (even stopped)
sudo docker ps -a | grep open-webui

# Remove old container and re-create
sudo docker rm open-webui
sudo docker run -d \
    -p 8088:8080 \
    --add-host=host.docker.internal:host-gateway \
    -v open-webui-data:/app/backend/data \
    --name open-webui \
    --restart always \
    ghcr.io/open-webui/open-webui:latest
```

### OpenCode Plugin Not Loading

```bash
# Re-install plugin dependencies
cd ~/dev/lucent/.opencode
npm install

# Verify plugin file exists
ls -la ~/dev/lucent/.opencode/lucent-plugin.ts

# Launch OpenCode with verbose output
cd ~/dev/lucent
opencode . --debug
```

### `python3` Not Found in systemd Services

The service files use `/usr/bin/python3`. Verify:

```bash
which python3
ls -la /usr/bin/python3
```

If python3 is at a different path, update the `ExecStart` lines in the service files and re-copy them to `/etc/systemd/system/`.

---

*Generated: 2026-05-13 | Lucent Core: github.com/antonizick/lucent | Memory: github.com/antonizick/LucentMemory*
