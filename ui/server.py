import os
import json
import logging
import requests
import subprocess
from datetime import datetime, date
from pathlib import Path
from collections import deque
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Setup Discord logging (optional, depends on webhook URL)
from discord_logger import setup_discord_logging
setup_discord_logging()
logger = logging.getLogger(__name__)

app = FastAPI()

# In-memory queues
speech_queue = deque(maxlen=100)  # Voice UI speech (backward compat)
message_queue = deque(maxlen=100)  # Generic message queue (Discord, terminal, voice input)
discord_pending = deque(maxlen=100)  # Pending Discord messages for terminal delivery

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
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat())

@app.get("/")
async def root():
    """Serve index.html"""
    html_path = static_dir / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return {"message": "Lucent Voice Box"}

@app.post("/speak")
async def speak(request: SpeakRequest):
    """Queue text to be spoken via TTS on the frontend."""
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    item = {
        "text": request.text,
        "timestamp": datetime.now().isoformat()
    }
    speech_queue.append(item)

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

@app.post("/response")
async def handle_response(request: ResponseRequest):
    """Handle responses from the poller (route to appropriate handler)."""
    if request.source == "discord_command":
        # Send to Discord via bot's webhook
        try:
            payload = {
                "message_id": request.message_id,
                "thread_id": request.thread_id,
                "response": request.response
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

    # Discord Poller (check if process running)
    result = subprocess.run(["pgrep", "-f", "discord_poller.py"], capture_output=True)
    poller_status = "online" if result.returncode == 0 else "offline"
    services.append({"name": "Discord poller", "status": poller_status})

    # Discord Monitor (check if process running)
    result = subprocess.run(["pgrep", "-f", "discord_monitor.py"], capture_output=True)
    monitor_status = "online" if result.returncode == 0 else "offline"
    services.append({"name": "Discord monitor", "status": monitor_status})

    # Lucent server (self)
    services.append({"name": "Lucent server", "status": "online"})

    return {"services": services}

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
