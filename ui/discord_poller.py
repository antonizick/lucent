"""Discord message poller — polls /message/pending, processes messages, posts responses."""

import os
import sys
import time
import requests
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8002")
LUCENT_ROOT = os.getenv("LUCENT_ROOT", "/home/nick/dev/lucent")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
POLLING_INTERVAL = 5  # Seconds between polls

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("discord_poller")

class LucentPoller:
    def __init__(self):
        self.lucent_root = Path(LUCENT_ROOT)
        self.memory_dir = self.lucent_root / "memory"
        self.backend_url = BACKEND_URL
        self.ollama_url = OLLAMA_URL
        self.model = "qwen2:7b"  # Or "mistral" if available

    def load_context(self) -> str:
        """Load Lucent's full context (identity, memory, daily note)."""
        context_parts = []

        # Load core identity files
        for filename in ["core.md", "lucentIdent.md", "userIdent.md"]:
            fpath = self.lucent_root / filename
            if fpath.exists():
                try:
                    content = fpath.read_text()
                    context_parts.append(f"=== {filename} ===\n{content}")
                except Exception as e:
                    logger.warning(f"Failed to read {filename}: {e}")

        # Load LTMemory
        ltmem_path = self.lucent_root / "LTMemory.md"
        if ltmem_path.exists():
            try:
                content = ltmem_path.read_text()
                context_parts.append(f"=== LTMemory ===\n{content}")
            except Exception as e:
                logger.warning(f"Failed to read LTMemory: {e}")

        # Load today's daily note
        today = datetime.now().strftime("%Y-%m-%d")
        daily_note = self.memory_dir / f"{today}.md"
        if daily_note.exists():
            try:
                content = daily_note.read_text()
                context_parts.append(f"=== Today's Note ===\n{content}")
            except Exception as e:
                logger.warning(f"Failed to read daily note: {e}")

        return "\n\n".join(context_parts)

    def deliver_message(self, message: dict) -> bool:
        """Deliver Discord message to backend for terminal display."""
        try:
            payload = {
                "source": message.get("source"),
                "user_id": message.get("user_id"),
                "channel_id": message.get("channel_id"),
                "message_id": message.get("message_id"),
                "text": message.get("text"),
                "timestamp": message.get("timestamp")
            }

            logger.info(f"Posting to /discord/pending: source={payload.get('source')}, text={payload.get('text')[:60]}")

            resp = requests.post(
                f"{self.backend_url}/discord/pending",
                json=payload,
                timeout=10
            )

            logger.info(f"Response status: {resp.status_code}, body: {resp.text[:200]}")

            if resp.status_code == 200:
                logger.info(f"Delivered message to terminal: {message.get('text', '')[:80]}")
                return True
            else:
                logger.error(f"Failed to deliver message: {resp.status_code} - {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Exception delivering message: {e}")
            return False

    def post_response(self, message: dict, response_text: str) -> bool:
        """Post response to /response endpoint."""
        try:
            payload = {
                "source": message.get("source"),
                "message_id": message.get("message_id"),
                "channel_id": message.get("channel_id"),
                "thread_id": message.get("thread_id"),
                "user_id": message.get("user_id"),
                "response": response_text,
                "timestamp": datetime.now().isoformat()
            }

            resp = requests.post(
                f"{self.backend_url}/response",
                json=payload,
                timeout=10
            )

            if resp.status_code == 200:
                logger.info(f"Response posted: {response_text[:100]}")
                return True
            else:
                logger.error(f"Failed to post response: {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"Exception posting response: {e}")
            return False

    def poll(self):
        """Main polling loop."""
        logger.info(f"Starting Discord poller (polling every {POLLING_INTERVAL}s)")
        logger.info(f"Backend: {self.backend_url}")
        logger.info(f"Ollama: {self.ollama_url}")

        while True:
            try:
                # Poll for pending messages
                resp = requests.get(
                    f"{self.backend_url}/message/pending",
                    timeout=10
                )

                if resp.status_code == 200:
                    data = resp.json()
                    message = data.get("message")

                    if message:
                        logger.info(f"Got message from {message.get('source')}")
                        self.deliver_message(message)
                else:
                    logger.warning(f"Poll error: {resp.status_code}")

                time.sleep(POLLING_INTERVAL)

            except requests.exceptions.ConnectionError:
                logger.error(f"Connection error to {self.backend_url}")
                logger.info(f"Retrying in {POLLING_INTERVAL}s...")
                time.sleep(POLLING_INTERVAL)
            except KeyboardInterrupt:
                logger.info("Poller stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                time.sleep(POLLING_INTERVAL)

def main():
    poller = LucentPoller()
    poller.poll()

if __name__ == "__main__":
    main()
