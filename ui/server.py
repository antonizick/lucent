import os
import json
from datetime import datetime, date
from pathlib import Path
from collections import deque
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Simple in-memory queue for speech requests
speech_queue = deque(maxlen=100)  # Keep last 100 requests

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

@app.get("/speak/pending")
async def get_pending_speech():
    """Get next pending speech request from the queue."""
    if speech_queue:
        return {"speech": speech_queue.popleft()}
    else:
        return {"speech": None}

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
