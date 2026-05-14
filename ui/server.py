import os
import re
import json
import logging
import requests
import subprocess
import tarfile
import shutil
from datetime import datetime, date
from pathlib import Path
from collections import deque
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Set
from dotenv import load_dotenv
import asyncio

load_dotenv()

# Setup Discord logging (optional, depends on webhook URL)
from discord_logger import setup_discord_logging
setup_discord_logging()
logger = logging.getLogger(__name__)

# Activity logging for Voice Box
LOGS_DIR = Path(__file__).parent / "logs"
LOG_ARCHIVES_DIR = LOGS_DIR / "archives"

def init_logs_dirs():
    """Initialize log directories."""
    LOGS_DIR.mkdir(exist_ok=True)
    LOG_ARCHIVES_DIR.mkdir(exist_ok=True)

def log_activity(message: str, source: str = "voice_box"):
    """Write activity to today's activity log with timestamp."""
    init_logs_dirs()
    today = date.today().isoformat()
    activity_log = LOGS_DIR / f"activity_{today}.log"

    timestamp = datetime.now().isoformat()
    log_entry = f"[{timestamp}] [{source}] {message}\n"

    try:
        with open(activity_log, "a") as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"Failed to write activity log: {e}")

def compress_monthly_logs():
    """Compress all log files from the previous month into a tar.gz archive."""
    init_logs_dirs()
    today = date.today()

    # Get previous month
    if today.month == 1:
        prev_month = today.replace(year=today.year - 1, month=12)
    else:
        prev_month = today.replace(month=today.month - 1)

    month_str = prev_month.strftime("%Y-%m")

    # Find logs matching the previous month
    logs_to_compress = list(LOGS_DIR.glob(f"activity_{month_str}-*.log"))

    if not logs_to_compress:
        return {"status": "no_logs", "month": month_str}

    archive_name = f"activity_{month_str}.tar.gz"
    archive_path = LOG_ARCHIVES_DIR / archive_name

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            for log_file in logs_to_compress:
                tar.add(log_file, arcname=log_file.name)

        # Remove original log files after archiving
        for log_file in logs_to_compress:
            log_file.unlink()

        logger.info(f"Compressed logs for {month_str} into {archive_name}")
        return {
            "status": "success",
            "month": month_str,
            "archive": archive_name,
            "logs_compressed": len(logs_to_compress)
        }
    except Exception as e:
        logger.error(f"Failed to compress logs: {e}")
        return {"status": "error", "message": str(e)}

app = FastAPI()

# In-memory queues
speech_queue = deque(maxlen=100)  # Voice UI speech (backward compat)
message_queue = deque(maxlen=100)  # Generic message queue (Discord, terminal, voice input)
discord_pending = deque(maxlen=100)  # Pending Discord messages for terminal delivery

# SSE client tracking for multi-client broadcasting
speech_event = asyncio.Event()
last_speech = None

# Agent state
current_agent = "Lucent"

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

class SpeakRequest(BaseModel):
    text: str

class MessageRequest(BaseModel):
    """Generic message from any source (Discord, terminal, voice UI)."""
    source: str  # "discord_command", "voice_ui_input", "terminal_input"
    text: str
    user_id: Optional[str] = None
    channel_id: Optional[str] = None  # Discord channel ID
    message_id: Optional[str] = None  # Discord message ID
    thread_id: Optional[str] = None  # Discord thread ID
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat())

class ResponseRequest(BaseModel):
    """Response to send back to the message source."""
    source: str  # "discord_command", "voice_ui_input", etc.
    message_id: Optional[str] = None
    channel_id: Optional[str] = None
    thread_id: Optional[str] = None
    user_id: Optional[str] = None
    response: str
    search_used: bool = False  # Flag for emoji reaction (newspaper emoji if True)
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat())

class AgentSwitchRequest(BaseModel):
    """Request to switch the current active agent."""
    agent: str

@app.get("/")
async def root():
    """Serve index.html"""
    html_path = static_dir / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return {"message": "Lucent Voice Box"}

@app.post("/speak")
async def speak(request: SpeakRequest):
    """Queue text to be spoken via TTS on the frontend (broadcast to all SSE clients)."""
    global last_speech

    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    item = {
        "text": request.text,
        "timestamp": datetime.now().isoformat()
    }

    # Keep for backward compat polling
    speech_queue.append(item)

    # Broadcast to SSE clients
    last_speech = item
    speech_event.set()

    # Log activity
    log_activity(request.text)

    return {
        "status": "queued",
        "text": request.text,
        "timestamp": item["timestamp"]
    }

@app.post("/message/pending")
async def queue_message(request: MessageRequest):
    """Queue a message from any source (Discord, terminal, voice UI)."""
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    item = {
        "source": request.source,
        "text": request.text,
        "user_id": request.user_id,
        "channel_id": request.channel_id,
        "message_id": request.message_id,
        "thread_id": request.thread_id,
        "timestamp": request.timestamp
    }
    message_queue.append(item)
    logger.info(f"[{request.source}] Queued message: {request.text[:100]}")

    return {
        "status": "queued",
        "source": request.source,
        "text": request.text,
        "timestamp": request.timestamp
    }

@app.get("/message/pending")
async def get_pending_message():
    """Get next pending message from the generic queue."""
    if message_queue:
        return {"message": message_queue.popleft()}
    else:
        return {"message": None}

@app.get("/speak/pending")
async def get_pending_speech():
    """Get next pending speech request from the queue (backward compat for Voice UI)."""
    if speech_queue:
        return {"speech": speech_queue.popleft()}
    else:
        return {"speech": None}

@app.get("/speak/stream")
async def speak_stream():
    """SSE endpoint for multi-client speech broadcasting."""
    async def event_generator():
        # Send last speech item if exists (for reconnecting clients)
        if last_speech:
            yield f"data: {json.dumps(last_speech)}\n\n"

        # Keep connection open and wait for new speech events
        while True:
            await speech_event.wait()
            if last_speech:
                yield f"data: {json.dumps(last_speech)}\n\n"
            speech_event.clear()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/response")
async def handle_response(request: ResponseRequest):
    """Handle responses from the poller (route to appropriate handler)."""
    if request.source == "discord_command":
        # Send to Discord via bot's webhook
        try:
            payload = {
                "message_id": request.message_id,
                "thread_id": request.thread_id,
                "response": request.response,
                "search_used": request.search_used
            }
            resp = requests.post(
                "http://127.0.0.1:8003/webhook/response",
                json=payload,
                timeout=10
            )

            if resp.status_code == 200:
                logger.info(f"Response routed to Discord: {request.response[:80]}")
                return {
                    "status": "routed",
                    "destination": "discord",
                    "message_id": request.message_id
                }
            else:
                logger.error(f"Bot webhook error: {resp.status_code}")
                return {
                    "status": "error",
                    "message": f"Bot webhook error: {resp.status_code}"
                }
        except Exception as e:
            logger.error(f"Failed to route to Discord: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    else:
        logger.warning(f"Unknown source: {request.source}")
        return {
            "status": "error",
            "message": f"Unknown source: {request.source}"
        }

@app.post("/discord/pending")
async def store_discord_message(request: MessageRequest):
    """Store Discord message for terminal delivery (instead of autonomous processing)."""
    if request.source != "discord_command":
        raise HTTPException(status_code=400, detail="Only discord_command messages accepted")

    item = {
        "user_id": request.user_id,
        "channel_id": request.channel_id,
        "message_id": request.message_id,
        "text": request.text,
        "timestamp": request.timestamp
    }
    discord_pending.append(item)
    logger.info(f"[DISCORD_PENDING] Stored message from {request.user_id}: {request.text[:80]}")

    return {
        "status": "stored",
        "count": len(discord_pending)
    }

@app.get("/discord/pending")
async def peek_pending_discord_messages():
    """Peek at pending Discord messages without clearing (for monitor processing)."""
    messages = list(discord_pending)
    return {
        "messages": messages,
        "count": len(messages)
    }

@app.delete("/discord/pending")
async def clear_pending_discord_messages():
    """Clear all pending Discord messages (used after processing)."""
    count = len(discord_pending)
    discord_pending.clear()
    return {
        "status": "cleared",
        "count": count
    }

@app.get("/discord/messages")
async def get_pending_discord_messages():
    """Get all pending Discord messages for terminal display (destructive)."""
    messages = list(discord_pending)
    discord_pending.clear()  # Clear after retrieval

    return {
        "messages": messages,
        "count": len(messages)
    }

@app.get("/log")
async def get_log():
    """Get today's daily note (live log)."""
    today = date.today().isoformat()
    log_path = Path(__file__).parent.parent / "memory" / f"{today}.md"

    if log_path.exists():
        try:
            content = log_path.read_text()
            return {"content": content}
        except Exception as e:
            return {"content": f"Error reading log: {str(e)}"}
    else:
        return {"content": "No log for today yet."}

@app.get("/log/weekly")
async def get_weekly_log():
    """Get insights from the last 4 days of daily notes."""
    from datetime import timedelta

    memory_dir = Path(__file__).parent.parent / "memory"
    today = date.today()
    insights = []

    # Collect the last 4 days (not including today)
    for i in range(1, 5):
        day = today - timedelta(days=i)
        log_path = memory_dir / f"{day.isoformat()}.md"

        if log_path.exists():
            try:
                content = log_path.read_text()
                # Extract first paragraph or key insights
                lines = content.split('\n')
                summary = []
                for line in lines:
                    if line.strip() and not line.startswith('#'):
                        summary.append(line)
                        if len(summary) >= 3:  # First 3 lines of content
                            break

                if summary:
                    day_str = day.strftime("%a, %b %d")
                    insights.append(f"**{day_str}**\n" + '\n'.join(summary[:3]))
            except Exception as e:
                logger.error(f"Error reading {log_path}: {e}")

    if insights:
        content = "\n\n".join(insights)
    else:
        content = "No logs from the past 4 days."

    return {"content": content}

@app.get("/log/memory")
async def get_memory_log():
    """Get long-term memory insights."""
    memory_file = Path(__file__).parent.parent / "memory" / "LTMemory.md"

    if memory_file.exists():
        try:
            content = memory_file.read_text()
            return {"content": content}
        except Exception as e:
            return {"content": f"Error reading memory: {str(e)}"}
    else:
        return {"content": "No long-term memory file found."}

@app.get("/activity-log")
async def get_activity_log():
    """Get today's activity log (Voice Box speech history)."""
    init_logs_dirs()
    today = date.today().isoformat()
    activity_log = LOGS_DIR / f"activity_{today}.log"

    if activity_log.exists():
        try:
            content = activity_log.read_text()
            return {
                "date": today,
                "content": content,
                "entries": len(content.strip().split("\n")) if content.strip() else 0
            }
        except Exception as e:
            return {"error": f"Error reading activity log: {str(e)}"}
    else:
        return {
            "date": today,
            "content": "",
            "entries": 0,
            "message": "No activity logged for today yet"
        }

@app.post("/logs/compress-monthly")
async def compress_logs_endpoint():
    """Trigger monthly log compression."""
    result = compress_monthly_logs()
    return result

@app.get("/logs/archives")
async def list_archives():
    """List all archived log files."""
    init_logs_dirs()
    archives = sorted(LOG_ARCHIVES_DIR.glob("activity_*.tar.gz"))

    archive_list = []
    for archive in archives:
        stat = archive.stat()
        archive_list.append({
            "name": archive.name,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })

    return {
        "archives": sorted(archive_list, key=lambda x: x["name"], reverse=True),
        "total": len(archive_list)
    }

@app.get("/logs/archives/{archive_name}")
async def download_archive(archive_name: str):
    """Download a specific archive file."""
    # Validate archive name to prevent path traversal
    if ".." in archive_name or "/" in archive_name:
        raise HTTPException(status_code=400, detail="Invalid archive name")

    archive_path = LOG_ARCHIVES_DIR / archive_name

    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="Archive not found")

    return FileResponse(
        archive_path,
        media_type="application/gzip",
        filename=archive_name
    )

@app.get("/services/health")
async def services_health():
    """Check health status of all services."""
    services = []

    # Ollama Local inference engine
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        ollama_status = "online" if resp.status_code == 200 else "offline"
    except:
        ollama_status = "offline"
    services.append({"name": "Ollama Local inference engine", "status": ollama_status})

    # Voice Box (self)
    services.append({"name": "Voice box", "status": "online"})

    # Discord Bot Flask server
    try:
        resp = requests.get("http://localhost:8003/", timeout=3)
        discord_bot_status = "online" if resp.status_code < 500 else "offline"
    except:
        discord_bot_status = "offline"
    services.append({"name": "Discord bot", "status": discord_bot_status})

    # Discord Monitor (check if process running)
    result = subprocess.run(["pgrep", "-f", "discord_monitor.py"], capture_output=True)
    monitor_status = "online" if result.returncode == 0 else "offline"
    services.append({"name": "Discord monitor", "status": monitor_status})

    # Lucent server (self)
    services.append({"name": "Lucent server", "status": "online"})

    return {"services": services}

@app.get("/security/status")
async def security_status():
    """Get latest security audit status with color coding."""
    lucent_root = Path(__file__).parent.parent
    audits_dir = lucent_root / "memory" / "security-audits"

    # Find the most recent audit report
    if not audits_dir.exists():
        return {
            "status": "unknown",
            "color": "gray",
            "summary": "No audits found",
            "critical": 0,
            "high": 0,
            "medium": 0
        }

    latest_report = None
    latest_time = None

    for date_dir in audits_dir.iterdir():
        if date_dir.is_dir():
            for report_file in date_dir.glob("*.md"):
                mtime = report_file.stat().st_mtime
                if latest_time is None or mtime > latest_time:
                    latest_time = mtime
                    latest_report = report_file

    if not latest_report:
        return {
            "status": "unknown",
            "color": "gray",
            "summary": "No audits found",
            "critical": 0,
            "high": 0,
            "medium": 0
        }

    try:
        content = latest_report.read_text()
        logger.info(f"Reading security report: {latest_report.name}")

        # Extract counts from summary section - look for the pattern in the report
        critical = 0
        high = 0
        medium = 0

        summary_match = re.search(r'- 🔴 \*\*Critical:\*\* (\d+)\s*\n- 🟠 \*\*High:\*\* (\d+)\s*\n- 🟡 \*\*Medium:\*\* (\d+)', content)
        if summary_match:
            critical = int(summary_match.group(1))
            high = int(summary_match.group(2))
            medium = int(summary_match.group(3))
            logger.info(f"Security status: C={critical} H={high} M={medium}")
        else:
            logger.warning("Regex pattern not matched in security report")

        # Determine status and color
        if critical > 0:
            status = "Critical"
            color = "red"
            summary_text = f"🔴 {critical} critical issue{'s' if critical != 1 else ''}"
        elif high > 0:
            status = "High Risk"
            color = "red"
            summary_text = f"🔴 {high} high severity issue{'s' if high != 1 else ''}"
        elif medium > 0:
            status = "Medium Risk"
            color = "yellow"
            summary_text = f"🟡 {medium} medium severity issue{'s' if medium != 1 else ''}"
        else:
            status = "Secure"
            color = "green"
            summary_text = "🟢 All clear"

        return {
            "status": status,
            "color": color,
            "summary": summary_text,
            "critical": critical,
            "high": high,
            "medium": medium,
            "report_path": str(latest_report.relative_to(lucent_root))
        }
    except Exception as e:
        import traceback
        logger.error(f"Error parsing security report: {e}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "color": "gray",
            "summary": f"Error: {str(e)[:50]}",
            "critical": 0,
            "high": 0,
            "medium": 0
        }

def get_last_commit_time(repo_path: Path) -> Optional[dict]:
    """Get last commit time and info for a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return None

        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        commit_timestamp_str = result.stdout.strip()

        from datetime import datetime as dt
        commit_dt = dt.fromisoformat(commit_timestamp_str)
        now = dt.now(commit_dt.tzinfo)
        hours_ago = (now - commit_dt).total_seconds() / 3600

        if hours_ago < 2:
            status = "green"
        elif hours_ago < 4:
            status = "yellow"
        else:
            status = "red"

        today = date.today()
        commit_date = commit_dt.date()

        if commit_date == today:
            date_display = "today"
        elif commit_date == date.fromordinal(today.toordinal() - 1):
            date_display = "yesterday"
        else:
            date_display = commit_date.strftime("%Y-%m-%d")

        time_display = commit_dt.strftime("%H:%M")

        return {
            "time": time_display,
            "date_display": date_display,
            "hours_ago": round(hours_ago, 1),
            "status": status,
            "timestamp": commit_timestamp_str
        }
    except Exception as e:
        logger.warning(f"Failed to get last commit time for {repo_path}: {e}")
        return None

@app.get("/backup/status")
async def backup_status():
    """Get backup status for both Lucent root and memory repositories."""
    lucent_root = Path(__file__).parent.parent
    memory_dir = lucent_root / "memory"

    lucent_status = get_last_commit_time(lucent_root)
    memory_status = get_last_commit_time(memory_dir)

    return {
        "lucent": lucent_status,
        "memory": memory_status
    }

@app.post("/run-backup")
async def run_backup():
    """Trigger an immediate backup of the memory folder."""
    try:
        lucent_root = Path(__file__).parent.parent
        backup_script = lucent_root / "scripts" / "backup_memory.py"

        if not backup_script.exists():
            logger.warning(f"Backup script not found: {backup_script}")
            return {"status": "error", "message": "Backup script not found"}

        subprocess.Popen(
            ["python3", str(backup_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(lucent_root)
        )

        log_activity("Backup triggered via UI (automated warning response)")
        return {"status": "success", "message": "Backup initiated"}
    except Exception as e:
        logger.error(f"Failed to trigger backup: {e}")
        return {"status": "error", "message": str(e)}

# Model management for Discord
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DISCORD_MODEL_FILE = Path(__file__).parent / ".discord_model"

@app.get("/ollama/models")
async def get_available_models():
    """Get list of available Ollama models."""
    try:
        resp = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            # Get current model
            current = "mistral:latest"
            if DISCORD_MODEL_FILE.exists():
                current = DISCORD_MODEL_FILE.read_text().strip()
            return {
                "available": models,
                "current": current
            }
        else:
            return {"error": "Could not reach Ollama"}
    except Exception as e:
        logger.error(f"Error fetching Ollama models: {e}")
        return {"error": str(e)}

@app.post("/ollama/model")
async def set_model(model_name: str):
    """Set the current Discord model."""
    if not model_name or not model_name.strip():
        return {"error": "Model name required"}, 400

    model_name = model_name.strip().lower()

    # Validate model exists in Ollama
    try:
        resp = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            available = [m["name"].lower() for m in data.get("models", [])]

            # Try exact match first
            exact_match = None
            for model in available:
                if model == model_name:
                    exact_match = model
                    break

            # Try partial match (for "qwen" matching "qwen3.6:35b")
            partial_matches = []
            if not exact_match:
                for model in available:
                    if model_name in model:
                        partial_matches.append(model)

            final_model = exact_match or (partial_matches[0] if len(partial_matches) == 1 else None)

            if not final_model:
                return {
                    "error": f"Model '{model_name}' not found",
                    "available": available
                }, 404
        else:
            return {"error": "Could not reach Ollama"}, 503
    except Exception as e:
        logger.error(f"Error validating model: {e}")
        return {"error": f"Error validating model: {str(e)}"}, 500

    DISCORD_MODEL_FILE.write_text(final_model)
    logger.info(f"Discord model switched to: {final_model}")
    return {"status": "switched", "model": final_model}

class AgentRequest(BaseModel):
    """Request to invoke a named agent."""
    agent: str
    task: str

@app.post("/agent/invoke")
async def invoke_agent_endpoint(request: AgentRequest):
    """Invoke a named sub-agent with a task via Claude Haiku API."""
    import asyncio
    import sys

    # Add scripts directory to path for import
    scripts_dir = Path(__file__).parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    try:
        from invoke_agent import invoke_agent as invoke_agent_fn
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, invoke_agent_fn, request.agent, request.task
        )
        return {
            "agent": request.agent,
            "response": result,
            "status": "success"
        }
    except FileNotFoundError as e:
        logger.error(f"Agent invocation error: {e}")
        return {
            "agent": request.agent,
            "error": str(e),
            "status": "error"
        }, 404
    except ValueError as e:
        logger.error(f"Agent invocation error: {e}")
        return {
            "agent": request.agent,
            "error": str(e),
            "status": "error"
        }, 400
    except Exception as e:
        logger.error(f"Agent invocation error: {e}")
        return {
            "agent": request.agent,
            "error": f"Failed to invoke agent: {str(e)}",
            "status": "error"
        }, 500

@app.post("/agent/switch")
async def switch_agent(request: AgentSwitchRequest):
    """Switch the current active agent for avatar auto-selection."""
    global current_agent
    current_agent = request.agent
    return {"agent": current_agent}

@app.get("/agent/current")
async def get_current_agent():
    """Get the currently active agent."""
    return {"agent": current_agent}

@app.get("/api/avatars")
async def list_avatars():
    """Discover available avatars from the static/avatars directory."""
    avatars_dir = Path(__file__).parent / "static" / "avatars"
    avatars = []

    if avatars_dir.exists():
        for item in sorted(avatars_dir.iterdir()):
            if item.is_dir():
                avatars.append(item.name)

    return {"avatars": avatars}

@app.get("/api/avatars/{avatar}/images")
async def get_avatar_images(avatar: str, state: str):
    """Get all images for a specific avatar and state."""
    # Sanitize avatar name to prevent path traversal
    if ".." in avatar or "/" in avatar or "\\" in avatar:
        raise HTTPException(status_code=400, detail="Invalid avatar name")

    state_dir = Path(__file__).parent / "static" / "avatars" / avatar / state
    images = []

    if state_dir.exists():
        for item in sorted(state_dir.iterdir()):
            if item.is_file() and item.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                # Return relative path for frontend
                images.append(f"/static/avatars/{avatar}/{state}/{item.name}")

    return {"images": images}

@app.get("/agents")
async def list_agents():
    """Discover available agents and their descriptions."""
    agents_dir = Path(__file__).parent.parent / "agents"
    agents = []

    if agents_dir.exists():
        for item in sorted(agents_dir.iterdir()):
            if item.is_file() and item.suffix == ".md" and item.name != ".gitkeep":
                try:
                    content = item.read_text()
                    lines = content.split("\n")
                    name = None
                    description = None

                    # Find the description in the Identity section
                    for i, line in enumerate(lines):
                        if "## Identity" in line or "## Personality" in line:
                            # Get the first non-empty paragraph after Identity/Personality
                            for j in range(i + 1, min(i + 10, len(lines))):
                                if lines[j].strip() and not lines[j].startswith("#"):
                                    text = lines[j].strip()
                                    description = text

                                    # Extract agent name from bold text "You are **Name**"
                                    import re
                                    match = re.search(r'\*\*(\w+)\*\*', text)
                                    if match:
                                        name = match.group(1)
                                    break
                            break

                    # If name not found in description, extract from heading
                    if not name:
                        for line in lines:
                            if line.startswith("# ") and "Agent" in line:
                                # Extract name: "# Memory Curator Agent" -> "Curator"
                                extracted = line.replace("# ", "").replace(" Agent", "").strip()
                                # Take the last word as the agent name
                                name = extracted.split()[-1]
                                break

                    if name:
                        agents.append({
                            "name": name,
                            "description": description or "Agent specializing in this domain"
                        })
                except Exception as e:
                    logger.error(f"Error parsing agent file {item.name}: {e}")

    return {"agents": agents}

@app.get("/activity-log-viewer")
async def activity_log_viewer():
    """Serve the activity log viewer page."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lucent — Activity Log</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            :root {
                --bg-primary: #080810;
                --bg-secondary: #0d0d1a;
                --text-primary: #ffffff;
                --text-secondary: #b0b0b0;
                --neon-cyan: #00e5ff;
                --border: #00e5ff;
            }

            body.light-mode {
                --bg-primary: #f5f5f5;
                --bg-secondary: #ffffff;
                --text-primary: #1a1a1a;
                --text-secondary: #666666;
                --neon-cyan: #0066cc;
                --border: #0066cc;
            }

            body {
                font-family: 'Courier New', monospace;
                background-color: var(--bg-primary);
                color: var(--text-primary);
                padding: 20px;
                line-height: 1.6;
            }

            .container {
                max-width: 900px;
                margin: 0 auto;
            }

            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid var(--neon-cyan);
            }

            h1 {
                font-size: 24px;
                color: var(--neon-cyan);
                text-shadow: 0 0 10px rgba(0, 229, 255, 0.5);
                letter-spacing: 2px;
            }

            .controls {
                display: flex;
                gap: 10px;
            }

            button {
                padding: 8px 16px;
                background-color: var(--bg-secondary);
                color: var(--text-primary);
                border: 1px solid var(--neon-cyan);
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                transition: all 0.2s ease;
            }

            button:hover {
                background-color: rgba(0, 229, 255, 0.1);
                box-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
            }

            .theme-toggle {
                background-color: transparent;
            }

            .info {
                margin-bottom: 15px;
                padding: 12px;
                background-color: var(--bg-secondary);
                border-left: 3px solid var(--neon-cyan);
                color: var(--text-secondary);
                font-size: 13px;
            }

            .log-content {
                background-color: var(--bg-secondary);
                border: 1px solid var(--neon-cyan);
                border-radius: 4px;
                padding: 15px;
                white-space: pre-wrap;
                word-break: break-word;
                font-size: 12px;
                max-height: 70vh;
                overflow-y: auto;
                color: var(--text-primary);
            }

            .log-content::-webkit-scrollbar {
                width: 8px;
            }

            .log-content::-webkit-scrollbar-track {
                background: var(--bg-primary);
            }

            .log-content::-webkit-scrollbar-thumb {
                background: rgba(0, 229, 255, 0.3);
                border-radius: 4px;
            }

            .log-content::-webkit-scrollbar-thumb:hover {
                background: rgba(0, 229, 255, 0.5);
            }

            .loading {
                text-align: center;
                color: var(--text-secondary);
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Activity Log</h1>
                <div class="controls">
                    <button id="refreshBtn">🔄 Refresh</button>
                    <button id="themeToggle">🌙</button>
                </div>
            </div>

            <div class="info">
                <strong>Last Updated:</strong> <span id="timestamp">Loading...</span> |
                <strong>Entries:</strong> <span id="entryCount">-</span>
            </div>

            <div class="log-content" id="logContent">
                <div class="loading">Loading activity log...</div>
            </div>
        </div>

        <script>
            const logContent = document.getElementById('logContent');
            const timestamp = document.getElementById('timestamp');
            const entryCount = document.getElementById('entryCount');
            const refreshBtn = document.getElementById('refreshBtn');
            const themeToggle = document.getElementById('themeToggle');

            let autoRefreshInterval = null;
            let isRefreshPaused = false;

            async function loadActivityLog() {
                try {
                    const response = await fetch('/activity-log');
                    const data = await response.json();

                    logContent.textContent = data.content || 'No activity logged for today yet';
                    entryCount.textContent = data.entries || 0;

                    const now = new Date();
                    timestamp.textContent = now.toLocaleTimeString();

                    // Auto-scroll to bottom
                    logContent.scrollTop = logContent.scrollHeight;
                } catch (error) {
                    logContent.textContent = `Error loading activity log: ${error.message}`;
                    console.error('Error:', error);
                }
            }

            function startAutoRefresh() {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                }
                autoRefreshInterval = setInterval(loadActivityLog, 5000);
                isRefreshPaused = false;
                refreshBtn.style.opacity = '1.0';
            }

            function pauseAutoRefresh() {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                }
                isRefreshPaused = true;
                refreshBtn.style.opacity = '0.6';
            }

            refreshBtn.addEventListener('click', loadActivityLog);

            // Pause refresh on hover, resume on mouse leave
            logContent.addEventListener('mouseenter', pauseAutoRefresh);
            logContent.addEventListener('mouseleave', startAutoRefresh);

            // Theme toggle
            function initTheme() {
                const savedTheme = localStorage.getItem('theme') || 'dark';
                if (savedTheme === 'light') {
                    document.body.classList.add('light-mode');
                    themeToggle.textContent = '☀️';
                } else {
                    themeToggle.textContent = '🌙';
                }
            }

            themeToggle.addEventListener('click', () => {
                const isLight = document.body.classList.toggle('light-mode');
                const theme = isLight ? 'light' : 'dark';
                localStorage.setItem('theme', theme);
                themeToggle.textContent = isLight ? '☀️' : '🌙';
            });

            initTheme();
            loadActivityLog();
            startAutoRefresh();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.on_event("startup")
async def startup_event():
    """Initialize logs directory on startup."""
    init_logs_dirs()
    logger.info("Voice Box activity logging initialized")
    # Check if we need to compress logs (monthly task)
    # This is a simple check at startup; for production use APScheduler
    result = compress_monthly_logs()
    if result.get("status") == "success":
        logger.info(f"Monthly compression completed: {result}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
