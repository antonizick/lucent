"""Discord instruction monitor — fetches pending messages, processes them, posts responses."""

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
POLLING_INTERVAL = 3  # Seconds between polls for pending messages

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("discord_monitor")

class DiscordInstructionMonitor:
    def __init__(self):
        self.lucent_root = Path(LUCENT_ROOT)
        self.memory_dir = self.lucent_root / "memory"
        self.backend_url = BACKEND_URL
        self.ollama_url = OLLAMA_URL
        self.model = "mistral"  # Fast model for Discord responses

    def load_context(self) -> str:
        """Load Lucent's full context (identity, memory, daily note)."""
        context_parts = []

        # Load core identity files
        for filename in ["lucentIdent.md", "userIdent.md"]:
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

    def process_instruction(self, message: dict) -> str:
        """Process Discord instruction through Ollama and return response."""
        try:
            context = self.load_context()
            instruction_text = message.get("text", "")

            system_prompt = f"""You are Lucent, Nick's personal AI assistant. This is an instruction from Nick via Discord.

{context}

Respond naturally and concisely to this instruction. Keep responses under 2-3 sentences unless more detail is needed."""

            # Call Ollama
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": instruction_text,
                    "system": system_prompt,
                    "stream": False,
                    "temperature": 0.7
                },
                timeout=30
            )

            if resp.status_code == 200:
                data = resp.json()
                response_text = data.get("response", "").strip()
                if response_text:
                    logger.info(f"Generated response: {response_text[:100]}")
                    return response_text
                else:
                    logger.error("Empty response from Ollama")
                    return "[Error: empty response from model]"
            else:
                logger.error(f"Ollama error: {resp.status_code}")
                return f"[Error processing instruction: {resp.status_code}]"

        except requests.exceptions.Timeout:
            logger.error("Ollama timeout")
            return "[Error: response generation timed out]"
        except Exception as e:
            logger.error(f"Exception processing instruction: {e}")
            return f"[Error processing instruction: {str(e)}]"

    def post_response(self, message: dict, response_text: str) -> bool:
        """Post response back to Discord."""
        try:
            payload = {
                "source": "discord_command",  # All Discord messages have this source
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
                logger.info(f"Response posted to Discord: {response_text[:80]}")
                return True
            else:
                logger.error(f"Failed to post response: {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"Exception posting response: {e}")
            return False

    def fetch_pending_messages(self) -> list:
        """Peek at pending Discord messages without clearing."""
        try:
            resp = requests.get(
                f"{self.backend_url}/discord/pending",
                timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                messages = data.get("messages", [])
                if messages:
                    logger.info(f"Fetched {len(messages)} pending Discord messages")
                return messages
            else:
                logger.warning(f"Failed to fetch pending messages: {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"Exception fetching pending messages: {e}")
            return []

    def clear_processed_messages(self) -> bool:
        """Clear the pending messages queue after processing."""
        try:
            resp = requests.delete(
                f"{self.backend_url}/discord/pending",
                timeout=10
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Exception clearing messages: {e}")
            return False

    def monitor(self):
        """Main monitoring loop."""
        logger.info(f"Starting Discord instruction monitor (polling every {POLLING_INTERVAL}s)")
        logger.info(f"Backend: {self.backend_url}")
        logger.info(f"Ollama: {self.ollama_url}")

        while True:
            try:
                # Fetch pending Discord instructions
                messages = self.fetch_pending_messages()

                if messages:
                    for message in messages:
                        logger.info(f"Processing Discord instruction from {message.get('user_id')}")

                        # Process the instruction
                        response = self.process_instruction(message)

                        # Post response back to Discord
                        self.post_response(message, response)

                    # Clear processed messages
                    self.clear_processed_messages()

                time.sleep(POLLING_INTERVAL)

            except requests.exceptions.ConnectionError:
                logger.error(f"Connection error to {self.backend_url}")
                logger.info(f"Retrying in {POLLING_INTERVAL}s...")
                time.sleep(POLLING_INTERVAL)
            except KeyboardInterrupt:
                logger.info("Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                time.sleep(POLLING_INTERVAL)

def main():
    monitor = DiscordInstructionMonitor()
    monitor.monitor()

if __name__ == "__main__":
    main()
