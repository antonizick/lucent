"""Discord logging handler — sends console output to Discord webhook."""

import logging
import os
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from collections import deque
from typing import Optional

load_dotenv()

DISCORD_LOG_WEBHOOK_URL = os.getenv("DISCORD_LOG_WEBHOOK_URL", "")

class DiscordLogHandler(logging.Handler):
    """Logging handler that broadcasts logs to Discord webhook."""

    def __init__(self, webhook_url: str, batch_size: int = 500, batch_delay: float = 5.0):
        super().__init__()
        self.webhook_url = webhook_url
        self.batch_size = batch_size  # Characters per batch
        self.batch_delay = batch_delay  # Seconds between batches
        self.buffer = deque()
        self.buffer_text = ""
        self.last_send_time = datetime.now()

    async def send_to_discord(self, text: str, level: str = "info"):
        """Send log text to Discord webhook."""
        if not self.webhook_url:
            return

        try:
            # Split long messages into chunks
            max_length = 1900  # Leave room for formatting
            chunks = [text[i:i+max_length] for i in range(0, len(text), max_length)]

            async with aiohttp.ClientSession() as session:
                for chunk in chunks:
                    payload = {
                        "content": f"```\n[{level.upper()}] {chunk}\n```"
                    }
                    async with session.post(
                        self.webhook_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status not in [200, 204]:
                            print(f"[DISCORD_LOG_ERROR] Failed to post log: {resp.status}")
        except Exception as e:
            print(f"[DISCORD_LOG_ERROR] Exception posting log: {e}")

    def emit(self, record: logging.LogRecord):
        """Called when a log record is emitted."""
        try:
            # Format the log record
            msg = self.format(record)
            level = record.levelname.lower()

            # Add to buffer
            self.buffer_text += msg + "\n"

            # Check if we should send
            now = datetime.now()
            time_elapsed = (now - self.last_send_time).total_seconds()

            if len(self.buffer_text) >= self.batch_size or time_elapsed >= self.batch_delay:
                # Send buffer to Discord asynchronously
                asyncio.create_task(self.send_to_discord(self.buffer_text, level))
                self.buffer_text = ""
                self.last_send_time = now
        except Exception:
            self.handleError(record)

def setup_discord_logging(webhook_url: Optional[str] = None, level: int = logging.INFO):
    """Setup Discord logging for the Lucent application."""
    if not webhook_url:
        webhook_url = DISCORD_LOG_WEBHOOK_URL

    if not webhook_url:
        print("[WARN] DISCORD_LOG_WEBHOOK_URL not set. Discord logging disabled.")
        return None

    # Create Discord handler
    handler = DiscordLogHandler(webhook_url)
    handler.setLevel(level)

    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    return handler

if __name__ == "__main__":
    # Test the Discord logger
    setup_discord_logging()
    logger = logging.getLogger(__name__)

    logger.info("Testing Discord logger")
    logger.warning("This is a warning")
    logger.error("This is an error")
    print("Logs queued for Discord. Waiting 6 seconds for batch send...")

    asyncio.run(asyncio.sleep(6))
    print("Test complete")
