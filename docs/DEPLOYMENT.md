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
5. [NX Vox — Piper TTS Voice Engine](#5-nx-vox--piper-tts-voice-engine)
6. [Environment Variables](#6-environment-variables)
7. [Systemd Services](#7-systemd-services)
8. [Cron Jobs](#8-cron-jobs)
9. [Shell Configuration — .bashrc](#9-shell-configuration--bashrc)
10. [Claude Code — Primary Platform](#10-claude-code--primary-platform)
11. [Ollama — Local AI Backend](#11-ollama--local-ai-backend)
12. [OpenCode — Alternative Platform](#12-opencode--alternative-platform)
13. [Docker & Open WebUI](#13-docker--open-webui)
14. [Discord Integration](#14-discord-integration)
15. [Gibson Security Auditing](#15-gibson-security-auditing)
16. [Port Reference](#16-port-reference)
17. [Verification Checklist](#17-verification-checklist)
18. [Troubleshooting](#18-troubleshooting)

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
│   ├── piper_manager.py      # Thread-safe Piper TTS wrapper
│   ├── voice_config.json     # Avatar→voice assignments
│   ├── discord_bot.py
│   ├── discord_monitor.py
│   ├── discord_poller.py
│   ├── discord_logger.py
│   ├── requirements.txt
│   ├── start.sh
│   ├── .env
│   ├── voices/               # Piper TTS model files (git-ignored, ~300 MB)
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

### 4.3 Install Piper TTS (Neural Voice Engine)

Piper TTS is installed separately from `requirements.txt`. **The recommended method is `setup.sh`** (see Section 5), which handles Piper installation, voice model downloads, and synthesis verification in one step.

If you need to install Piper manually:

```bash
# Option A — from the local wheel bundled in the repo root (fastest, no internet for pip)
pip3 install /home/nick/dev/lucent/piper_tts-*.whl

# Option B — from PyPI
pip3 install piper-tts
```

Piper has a native ONNX Runtime dependency. If install fails with a missing `onnxruntime` error:

```bash
pip3 install onnxruntime
pip3 install piper-tts
```

> **Voice models are not installed by pip.** They are large `.onnx` files (~60-200 MB each) that live in `ui/voices/` and are downloaded by `setup.sh`. See Section 5 for the complete voice engine setup.

### 4.4 Full Pip Install Command (All at Once)

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
    "flask>=3.0.0" \
    "piper-tts"
```

### 4.5 Verify Python Path

The Claude Code hook and scripts rely on `python3` being available. Confirm:

```bash
which python3         # /usr/bin/python3
python3 --version     # Python 3.10.x or higher
```

---

## 5. NX Vox — Piper TTS Voice Engine

Lucent uses **Piper TTS** for all speech synthesis. Piper is a local, neural text-to-speech engine — it runs entirely on your machine with no cloud API, no internet connection required after setup, and no API key. Voice models are ONNX files stored in `ui/voices/`.

**Why this matters for deployment:** Voice model files are git-ignored (too large to commit). On a fresh machine they must be downloaded and placed in `ui/voices/` before the Voice Box will produce audio. The server starts without them but will log a warning and fall back to silence until at least one voice model is present.

### 5.1 Quickstart — Run `setup.sh`

The repo includes an idempotent setup script that handles everything in one command:

```bash
cd ~/dev/lucent
bash setup.sh
```

This script:
1. Detects and installs Piper TTS (from the local `.whl` wheel in the repo root, or from PyPI as fallback)
2. Creates `ui/voices/` if it doesn't exist
3. Downloads all four voice models from HuggingFace (skips any already present)
4. Runs a quick synthesis test to confirm Piper is working

**Expected output (first run, ~5-10 minutes on a fast connection):**

```
[1/4] Installing Piper TTS...
✓ piper-tts installed

[2/4] Creating voices directory...
✓ ui/voices/ ready

[3/4] Downloading voice models...
  en_GB-cori-high        [✓] 109 MB
  en_GB-jenny_dioco-medium [✓] 61 MB
  en_GB-alan-medium      [✓] 61 MB
  en_GB-northern_english_male-medium [✓] 61 MB

[4/4] Verifying synthesis...
✓ Piper synthesis OK — 12,340 bytes generated

Setup complete.
```

If a voice is already present, the download is skipped. Safe to run again after partial failures.

### 5.2 What Gets Installed

| File / Directory | Size | Purpose |
|---|---|---|
| `piper-tts` Python package | ~5 MB | TTS library + ONNX Runtime |
| `ui/voices/en_GB-cori-high.onnx` | ~109 MB | Female, high quality — default voice |
| `ui/voices/en_GB-jenny_dioco-medium.onnx` | ~61 MB | Female, medium quality |
| `ui/voices/en_GB-alan-medium.onnx` | ~61 MB | Male, medium quality |
| `ui/voices/en_GB-northern_english_male-medium.onnx` | ~61 MB | Male, medium quality |
| `ui/voices/*.onnx.json` (4 files) | ~2 KB each | Config sidecar for each model |

Total voice storage: ~295 MB

All voice files are British English (`en_GB`). The server discovers them automatically by scanning `ui/voices/` — no code changes needed to add or remove voices.

### 5.3 Per-Avatar Voice Assignment

Each avatar has a default voice configured in `ui/voice_config.json`:

```json
{
  "avatar_voices": {
    "Lucent": "en_GB-cori-high",
    "Emma":   "en_GB-jenny_dioco-medium",
    "Alex":   "en_GB-alan-medium",
    "Karen":  "en_GB-cori-high"
  },
  "default_voice": "en_GB-cori-high"
}
```

This file is committed to git and requires no changes on a new deployment — the mapping is already correct as long as the voice model files are present in `ui/voices/`.

### 5.4 Manual Voice Download (if setup.sh fails)

If the setup script fails at the download step, you can download voices manually using `curl`. Run from the project root:

```bash
VOICES_DIR="ui/voices"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en"

# en_GB-cori-high (~109 MB)
curl -L --progress-bar \
  -o "${VOICES_DIR}/en_GB-cori-high.onnx" \
  "${BASE}/en_GB/cori/high/en_GB-cori-high.onnx?download=true"
curl -L --progress-bar \
  -o "${VOICES_DIR}/en_GB-cori-high.onnx.json" \
  "${BASE}/en_GB/cori/high/en_GB-cori-high.onnx.json?download=true"

# en_GB-jenny_dioco-medium (~61 MB)
curl -L --progress-bar \
  -o "${VOICES_DIR}/en_GB-jenny_dioco-medium.onnx" \
  "${BASE}/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx?download=true"
curl -L --progress-bar \
  -o "${VOICES_DIR}/en_GB-jenny_dioco-medium.onnx.json" \
  "${BASE}/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx.json?download=true"

# en_GB-alan-medium (~61 MB)
curl -L --progress-bar \
  -o "${VOICES_DIR}/en_GB-alan-medium.onnx" \
  "${BASE}/en_GB/alan/medium/en_GB-alan-medium.onnx?download=true"
curl -L --progress-bar \
  -o "${VOICES_DIR}/en_GB-alan-medium.onnx.json" \
  "${BASE}/en_GB/alan/medium/en_GB-alan-medium.onnx.json?download=true"

# en_GB-northern_english_male-medium (~61 MB)
curl -L --progress-bar \
  -o "${VOICES_DIR}/en_GB-northern_english_male-medium.onnx" \
  "${BASE}/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx?download=true"
curl -L --progress-bar \
  -o "${VOICES_DIR}/en_GB-northern_english_male-medium.onnx.json" \
  "${BASE}/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json?download=true"
```

> **Warning:** If a downloaded `.onnx` file is only a few bytes (< 1 KB), the URL was wrong. The file will contain an error message, not a model. Check the file size with `ls -lh ui/voices/` and re-download with the correct path.

### 5.5 Verify Piper Is Working

After downloading voices, verify the setup before starting the full service:

```bash
# Quick synthesis test from the command line
cd ~/dev/lucent/ui
python3 -c "
from piper import PiperVoice
import wave, io

voice = PiperVoice.load('voices/en_GB-cori-high.onnx')
out = io.BytesIO()
with wave.open(out, 'wb') as f:
    voice.synthesize_wav('Voice system ready.', f)
print(f'OK — {len(out.getvalue()):,} bytes synthesized')
"
```

Expected output: `OK — 12340 bytes synthesized` (size varies by text length).

### 5.6 Server Startup Behaviour

When `lucent-voice-box.service` starts, the `piper_manager` loads the default voice (`en_GB-cori-high`) during the FastAPI lifespan startup. This takes 2–4 seconds. During loading:

- `GET /services/health` returns `"piper": "loading"`
- `POST /speak` requests will queue and wait
- Once loaded, `GET /services/health` returns `"piper": "ready"`

High-quality models (`-high`) load slightly slower than medium. This is normal — the service is still healthy.

### 5.7 Adding New Voices

See **`docs/VOICES.md`** for the complete guide to browsing, downloading, testing, installing, and assigning additional Piper voices. The short version:

1. Find a voice at `https://rhasspy.github.io/piper-samples/` (click to hear samples)
2. Download the `.onnx` and `.onnx.json` pair into `ui/voices/`
3. Reload the browser — the voice appears in the dropdown automatically
4. Optionally assign it to an avatar via `POST /vox/config` or edit `ui/voice_config.json`

---

## 6. Environment Variables

### 6.1 Create the .env File

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

### 6.2 Secure the .env File

```bash
chmod 600 ~/dev/lucent/ui/.env
```

---

## 7. Systemd Services

### 7.1 Service Architecture

Five Lucent-specific services must be installed and enabled. The service unit files live in the repo root and must be **copied** (not symlinked) to `/etc/systemd/system/`.

| Service File | Description | Port |
|-------------|-------------|------|
| `lucent-voice-box.service` | FastAPI Voice Box — core TTS/API hub | 8001 |
| `lucent-server.service` | Discord Integration Server | — |
| `lucent-monitor.service` | Discord Instruction Monitor | — |
| `lucent-poller.service` | Discord Message Poller | — |
| `discord-bot.service` | Discord Bot (webhook receiver) | 8003 |

Service dependency order: `lucent-voice-box` → `lucent-server` → `lucent-monitor` and `lucent-poller`

### 7.2 Install All Service Files

```bash
cd ~/dev/lucent

sudo cp lucent-voice-box.service /etc/systemd/system/
sudo cp lucent-server.service    /etc/systemd/system/
sudo cp lucent-monitor.service   /etc/systemd/system/
sudo cp lucent-poller.service    /etc/systemd/system/
sudo cp discord-bot.service      /etc/systemd/system/

sudo systemctl daemon-reload
```

### 7.3 Enable and Start Services

Enable all services to start on boot, then start them now:

```bash
sudo systemctl enable --now lucent-voice-box.service
sudo systemctl enable --now lucent-server.service
sudo systemctl enable --now lucent-monitor.service
sudo systemctl enable --now lucent-poller.service
sudo systemctl enable --now discord-bot.service
```

### 7.4 Verify Services Are Running

```bash
sudo systemctl status lucent-voice-box lucent-server lucent-monitor lucent-poller discord-bot --no-pager
```

Or use the included restart script which also shows status:

```bash
bash ~/dev/lucent/restart-services.sh
```

### 7.5 Service File Reference

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

### 7.6 Service Management Reference

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

## 8. Cron Jobs

Two cron jobs keep memory backed up and logs rotated.

### 8.1 Install Cron Jobs

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

### 8.2 What Each Job Does

**Memory Backup (hourly)**
- Runs `git add -A && git commit && git push` inside `memory/`
- Skips commit if there are no changes (safe to run repeatedly)
- Logs results to `/tmp/memory-backup-cron.log`
- Also appends backup events to today's daily note

**Voice Log Rotation (weekly)**
- Compresses previous month's activity logs into `ui/logs/archives/activity_YYYY-MM.tar.gz`
- Mirrors the same behavior triggered at Voice Box startup for monthly compression
- Logs results to `/tmp/voice-log-rotation.log`

### 8.3 Verify Cron Jobs Are Installed

```bash
crontab -l
```

---

## 9. Shell Configuration — .bashrc

These blocks must be present in `~/.bashrc` for Lucent to function correctly on every shell session.

### 9.1 PATH Additions

Add these exports near the bottom of `~/.bashrc`:

```bash
# pip user-installed binaries (includes claude CLI)
export PATH=$PATH:~/.local/bin

# OpenCode binary
export PATH=/home/nick/.opencode/bin:$PATH
```

### 9.2 Auto-Start Services on WSL Launch

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

### 9.3 Apply .bashrc Changes

```bash
source ~/.bashrc
```

---

## 10. Claude Code — Primary Platform

### 10.1 Install Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
```

Verify:

```bash
claude --version
which claude   # should be ~/.local/bin/claude or /usr/local/bin/claude
```

> If `claude` is not found after install, ensure `~/.local/bin` is in your PATH (see Section 9.1).

### 10.2 Authenticate with Anthropic

```bash
claude login
```

This opens a browser for OAuth authentication with your Anthropic account. Follow the prompts. Your API key is stored in `~/.claude/` after login.

Alternatively, set the API key directly in `ui/.env` (used by the Voice Box server for agent invocation):

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." >> ~/dev/lucent/ui/.env
```

### 10.3 Project-Level Claude Code Hooks

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

### 10.4 Launch Claude Code as Lucent

Always launch from the lucent project root:

```bash
cd ~/dev/lucent
claude
```

Or use the AI launcher (see Section 10.5).

### 10.5 AI Launcher

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

### 10.6 Verify Claude Code Is Working

1. Launch Claude Code from `~/dev/lucent`
2. Type any message
3. Confirm the hook output appears (you'll see `[Lucent] You are Lucent. Today is YYYY-MM-DD.` prefixing the context)
4. Confirm a voice message plays through the browser UI at `http://localhost:8001`

---

## 11. Ollama — Local AI Backend

Ollama provides local LLM inference used by the sub-agent system and the Discord bot's local model feature.

### 11.1 Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

This installs the `ollama` binary to `/usr/local/bin/ollama` and creates the `ollama.service` systemd unit automatically.

### 11.2 Enable Ollama on Boot

```bash
sudo systemctl enable --now ollama.service
sudo systemctl status ollama.service
```

### 11.3 Pull Required Models

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

### 11.4 Verify Ollama Is Running

```bash
curl http://localhost:11434/api/tags
```

Should return a JSON list of available models. The Voice Box `/services/health` endpoint also checks Ollama status.

### 11.5 Using Ollama with the Agent System

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

### 11.6 Auto-Start on WSL Login

Ollama is also started from `.bashrc` (see Section 8.2) as a fallback in case the systemd service is not running.

---

## 12. OpenCode — Alternative Platform

OpenCode is a secondary AI coding platform. Lucent has a TypeScript plugin that enforces the startup ritual when OpenCode is used instead of Claude Code.

### 12.1 Install OpenCode

```bash
curl -fsSL https://opencode.ai/install | bash
```

This installs OpenCode to `~/.opencode/bin/opencode`. The PATH addition in `.bashrc` (Section 8.1) makes it available as `opencode`.

Verify:

```bash
opencode --version
which opencode  # should be ~/.opencode/bin/opencode
```

### 12.2 Install the OpenCode Plugin Dependencies

The Lucent plugin is a TypeScript file compiled at runtime. It requires its npm dependencies:

```bash
cd ~/dev/lucent/.opencode
npm install
```

This installs `@opencode-ai/plugin@1.14.48` into `.opencode/node_modules/`.

### 12.3 OpenCode Configuration Files

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

### 12.4 How the OpenCode Plugin Works

The plugin (`.opencode/lucent-plugin.ts`) registers a tool called `lucent_startup` that the model is instructed to call before its first response. When called, it:

1. Runs `.opencode/startup-helper.py` — checks voice box health, initializes session logger
2. Reads today's daily note + yesterday + two days ago — injects live session context
3. Returns the three-layer protocol reminder (voice → log → text)

This mirrors what `lucent-init.sh` does for Claude Code, adapted for OpenCode's plugin architecture.

### 12.5 Launch OpenCode as Lucent

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

### 12.6 Available Free OpenCode Models

The launcher includes these pre-configured free models:
- `big-pickle`
- `deepseek-v4-flash-free`
- `minimax-m2.5-free`
- `nemotron-3-super-free`
- `ring-2.6-1t-free`

Any locally-running Ollama model can also be selected from the launcher menu.

---

## 13. Docker & Open WebUI

Open WebUI is a browser-based interface for interacting with Ollama models. It runs in Docker on port 8088.

### 13.1 Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add your user to the docker group (optional — current setup uses sudo)
sudo usermod -aG docker $USER

# Start and enable Docker
sudo systemctl enable --now docker
```

### 13.2 Start Open WebUI

The `.bashrc` auto-start block (Section 9.2) handles this on each login. To start it manually:

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

### 13.3 Manage Open WebUI

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

## 14. Discord Integration

The Discord integration allows sending messages to Lucent through a Discord server, which are then routed through the voice box and processed.

### 14.1 Create a Discord Bot

1. Go to https://discord.com/developers/applications
2. Create a new Application
3. Navigate to **Bot** → **Add Bot**
4. Copy the **Bot Token** → set as `DISCORD_BOT_TOKEN` in `ui/.env`
5. Under **Privileged Gateway Intents**, enable **Message Content Intent**
6. Navigate to **OAuth2 → URL Generator**
   - Scopes: `bot`
   - Permissions: `Send Messages`, `Read Messages/View Channels`, `Add Reactions`
7. Use the generated URL to invite the bot to your server

### 14.2 Configure Discord IDs

In `ui/.env`:

```bash
DISCORD_SERVER_ID=<right-click your server → Copy ID>
DISCORD_CHANNEL_ID=<right-click the commands channel → Copy ID>
DISCORD_LOG_CHANNEL_ID=<right-click the logs channel → Copy ID>
```

To enable Copy ID: Discord Settings → Advanced → Developer Mode → ON.

### 14.3 Create a Webhook for Logging

1. In the Discord log channel → Edit Channel → Integrations → Webhooks
2. Create webhook → Copy URL
3. Set as `DISCORD_LOG_WEBHOOK_URL` in `ui/.env`

### 14.4 Restart Discord Services

After configuring `.env`:

```bash
sudo systemctl restart discord-bot.service lucent-server.service lucent-poller.service lucent-monitor.service
```

### 14.5 Discord Architecture

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

## 15. Gibson Security Auditing

Gibson is a specialized security auditor agent for scanning code vulnerabilities. It categorizes findings by type (custom code, external libraries, dependencies) and provides actionable remediation guidance with exact upgrade commands.

### 15.1 Security Scanning

**Manual Audit:**
```bash
python3 scripts/run-security-audit.py /home/nick/dev/lucent
```

**Output:**
- Markdown report: `memory/security-audits/YYYY-MM-DD/{project}-HH-MM-SS.md`
- Voice summary with findings categorized by severity and type
- JSON output for programmatic integration

### 15.2 Vulnerability Categories

Gibson detects and categorizes:

1. **Custom Code** — Your responsibility to fix
   - XSS vulnerabilities (innerHTML with untrusted data)
   - Command injection (eval, exec)
   - SQL injection patterns
   - Missing CORS headers
   - Hardcoded secrets

2. **External Code** — Cannot be modified directly
   - Vulnerabilities in minified/vendored libraries
   - Recommends library upgrades as remediation

3. **Dependencies** — Fixed by version upgrades
   - CVE numbers and official titles
   - Current version → upgrade version
   - Exact npm/pip upgrade commands
   - Major version upgrade warnings

4. **Secrets** — Code reference visibility
   - Flags environment variable references
   - Validates .gitignore protection
   - Clarifies: references ≠ exposed secrets

### 15.3 Report Format

Reports include three major sections with detailed findings:

```
# Security Audit: {project}

--------------------------------------------------
## Custom Code — Issues you authored and can fix directly

### 🟠 HIGH / 🟡 MEDIUM
- Finding name
- Affected file(s)
- Issue description
- How to Fix: Specific remediation steps

--------------------------------------------------
## External Code — Patterns in third-party code

### 🟠 HIGH
- Finding name
- Affected file(s)
- Why No Fix: Explanation + upgrade guidance

--------------------------------------------------
## Dependencies — npm/pip vulnerabilities

### 🔴 CRITICAL / 🟠 HIGH / 🟡 MEDIUM
- Package name + CVE ID + official title
- Location: package.json file
- Current version → Upgrade to version (⚠️ Major warning if applicable)
- How to Fix: `npm upgrade package@version` (exact command)

--------------------------------------------------
## 🔑 Secrets Analysis
- Code references found (not actual secrets)
- Protected secrets (.gitignore status)
```

### 15.4 Git Pre-Commit Integration

Gibson integrates with git to block vulnerable commits:

```bash
# Automatically runs on commit attempt
git commit -m "Code changes"

# Behavior:
- Critical vulns: BLOCK (override with --no-verify, not recommended)
- High vulns: BLOCK (override with --no-verify)
- Medium/Low: WARN + auto-proceed after 60 seconds
```

### 15.5 Voice Summary Format

Gibson provides voice feedback with all findings:

```
"Gibson audit of lucent: 1 critical (1 fixable deps), 6 high (1 in code, 5 fixable deps), 
4 medium (1 in code, 3 fixable deps) findings. Code issues: [list]. 
3 secret reference patterns found (not actual secrets). Full report saved to security-audits folder."
```

### 15.6 Scheduling Regular Audits

**Manual scheduling:**
```bash
# Weekly audit (add to crontab)
0 2 * * 0 python3 /home/nick/dev/lucent/scripts/run-security-audit.py /home/nick/dev/lucent
```

**Output location:**
All reports archived in: `memory/security-audits/YYYY-MM-DD/{project}-HH-MM-SS.md`

### 15.7 Invoking Gibson Programmatically

```bash
# Via agent framework
python3 scripts/lucent.py agent gibson "Audit /home/nick/dev/lucent"

# Direct Python
python3 scripts/run-security-audit.py /path/to/project
```

---

## 16. Port Reference

| Port | Service | Component |
|------|---------|-----------|
| 8001 | Voice Box API | `ui/server.py` (FastAPI/uvicorn) |
| 8003 | Discord Bot Webhook | `ui/discord_bot.py` (Flask) |
| 8088 | Open WebUI | Docker container (maps to internal 8080) |
| 11434 | Ollama | Local LLM inference engine |

---

## 17. Verification Checklist

Run through this checklist after deployment to confirm everything is working.

### 17.1 Services

```bash
# All five Lucent services should show "active (running)"
sudo systemctl status lucent-voice-box lucent-server lucent-monitor lucent-poller discord-bot --no-pager | grep -E "●|Active:"

# Ollama and Docker should also be active
sudo systemctl status ollama docker --no-pager | grep -E "●|Active:"
```

### 17.2 Voice Box API

```bash
# Health check — "piper" field should show "ready" once model is loaded
curl -s http://localhost:8001/services/health | python3 -m json.tool

# Send a test voice message
curl -X POST http://localhost:8001/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Deployment verification complete."}'

# Check backup status
curl -s http://localhost:8001/backup/status | python3 -m json.tool
```

### 17.3 Piper TTS Voice Engine

```bash
# List all installed voices (should show 4 voices)
curl -s http://localhost:8001/vox/voices | python3 -m json.tool

# Check current active voice and synthesis stats
curl -s http://localhost:8001/vox/status | python3 -m json.tool

# Verify voice model files are present and correctly sized
ls -lh ~/dev/lucent/ui/voices/*.onnx
# Each file should be > 10 MB. Files < 1 KB are corrupt downloads.

# Confirm avatar-to-voice mapping is loaded
curl -s http://localhost:8001/vox/config | python3 -m json.tool
# Should show Lucent=cori-high, Emma=jenny_dioco-medium, Alex=alan-medium, Karen=cori-high
```

### 17.4 Ollama

```bash
curl -s http://localhost:11434/api/tags | python3 -m json.tool
ollama list
```

### 17.5 Cron Jobs

```bash
crontab -l | grep lucent
# Should show two entries (backup_memory + rotate_voice_logs)
```

### 17.6 Git Remotes

```bash
git -C ~/dev/lucent remote -v
git -C ~/dev/lucent/memory remote -v
```

### 17.7 Claude Code

```bash
cd ~/dev/lucent
claude --version
# Launch Claude Code and confirm hook runs (you should see [Lucent] prefix in context)
```

### 17.8 Memory Backup Test

```bash
python3 ~/dev/lucent/scripts/backup_memory.py
# Should print: ✓ No changes to commit  OR  ✓ Committed and pushed
```

### 17.9 Session Logger Test

```bash
python3 ~/dev/lucent/scripts/session_logger.py init
python3 ~/dev/lucent/scripts/session_logger.py check
# Should print: ✓ Checkpoint valid
```

### 17.10 Web UI

Open a browser and navigate to:
- `http://localhost:8001` — Lucent Voice Box UI
- `http://localhost:8088` — Open WebUI (Ollama browser interface)

---

## 18. Troubleshooting

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

### Piper TTS — No Audio (Voice Box Starts but Silent)

The Voice Box starts without voice models and silently skips synthesis. Check:

```bash
# Are model files present and correctly sized?
ls -lh ~/dev/lucent/ui/voices/*.onnx
```

If files are missing or tiny (< 1 KB), they weren't downloaded. Re-run setup:

```bash
bash ~/dev/lucent/setup.sh
```

Or download the default voice manually:

```bash
curl -L --progress-bar \
  -o ~/dev/lucent/ui/voices/en_GB-cori-high.onnx \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx?download=true"
curl -L --progress-bar \
  -o ~/dev/lucent/ui/voices/en_GB-cori-high.onnx.json \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx.json?download=true"
```

Then restart the voice box service:

```bash
sudo systemctl restart lucent-voice-box.service
```

### Piper TTS — `ModuleNotFoundError: No module named 'piper'`

Piper TTS was not installed. Install it:

```bash
# From local wheel (preferred — no internet for pip)
pip3 install ~/dev/lucent/piper_tts-*.whl

# From PyPI
pip3 install piper-tts
```

If the wheel file isn't present in the repo, install from PyPI or download from the [Piper releases page](https://github.com/OHF-Voice/piper1-gpl/releases).

### Piper TTS — Voice Box Slow to Start (30+ seconds)

High-quality models take 4–8 seconds to load into RAM. This is expected. The service logs:

```
INFO:     Loading Piper voice: en_GB-cori-high
INFO:     Piper voice loaded in 4.2s
```

If the server takes over 60 seconds, check available RAM — a high-quality model needs ~300–500 MB free.

### Piper TTS — Downloaded Voice File Is 15 Bytes

The HuggingFace URL path was wrong. The file contains `Entry not found` rather than model weights. Check:

- The voice name spelling (`jenny_dioco` not `jenny-dioco`)
- The quality tier exists for that voice (some voices only have `low`)
- The language code is correct (`en_GB` vs `en_US`)

Query HuggingFace to find the actual paths:

```bash
curl -s "https://huggingface.co/api/models/rhasspy/piper-voices?full=false" | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
# Replace 'cori' with the voice name you want to verify
matches = [s['rfilename'] for s in data.get('siblings', [])
           if 'cori' in s['rfilename'] and '.onnx' in s['rfilename']]
print('\n'.join(matches))
"
```

### Piper TTS — Browser Plays No Audio After Server Restart

The browser's `AudioContext` requires a user gesture (click) before playback is allowed. The Voice Box UI shows `"Click anywhere to enable speech"` at the bottom until the first click. Click anywhere on the page, then trigger speech again.

If audio still doesn't play after clicking, open the browser console and look for `AudioContext` errors. A page reload usually resolves stale audio state.

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

*Updated: 2026-05-14 (added NX Vox / Piper TTS section) | Lucent Core: github.com/antonizick/lucent | Memory: github.com/antonizick/LucentMemory*
