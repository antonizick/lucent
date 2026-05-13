#!/usr/bin/env python3
"""
Discord Message Logger - Logs all Discord messages sent/received in the lucent-commands channel.
Provides full visibility into message exchanges for debugging and testing.
"""

import os
import discord
from discord.ext import commands
import json
from datetime import datetime
from pathlib import Path

# Config
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_SERVER_ID = int(os.getenv("DISCORD_SERVER_ID", 0))
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", 0))

# Logs directory
LOG_DIR = Path("/tmp/discord_messages")
LOG_DIR.mkdir(exist_ok=True)
MESSAGE_LOG = LOG_DIR / "message_exchange.log"
MESSAGE_JSON = LOG_DIR / "messages.jsonl"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)


def log_message_exchange(direction: str, message: dict):
    """Log a message exchange (sent or received)."""
    timestamp = datetime.now().isoformat()

    # Human-readable log
    with open(MESSAGE_LOG, "a") as f:
        f.write(f"\n{'='*70}\n")
        f.write(f"[{timestamp}] {direction.upper()}\n")
        f.write(f"Message ID: {message.get('message_id')}\n")
        f.write(f"Author: {message.get('author')}\n")
        f.write(f"Channel: {message.get('channel')}\n")
        f.write(f"Content: {message.get('content')}\n")
        if message.get('response'):
            f.write(f"Response: {message.get('response')}\n")
        if message.get('reactions'):
            f.write(f"Reactions: {message.get('reactions')}\n")
        if message.get('search_used'):
            f.write(f"Search Used: {message.get('search_used')}\n")

    # JSON log (machine-readable)
    entry = {
        "timestamp": timestamp,
        "direction": direction,
        **message
    }
    with open(MESSAGE_JSON, "a") as f:
        f.write(json.dumps(entry) + "\n")


@bot.event
async def on_ready():
    """Log when bot is ready."""
    log_message_exchange("SYSTEM", {
        "message_id": "N/A",
        "author": "discord_message_logger",
        "channel": "system",
        "content": f"Logger started, monitoring channel {DISCORD_CHANNEL_ID}"
    })
    print(f"[LOGGER] Ready, monitoring channel {DISCORD_CHANNEL_ID}")


@bot.event
async def on_message(message):
    """Log all messages in the monitored channel."""
    # Only log messages in the lucent-commands channel
    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    # Log incoming user messages
    if not message.author.bot:
        log_message_exchange("RECEIVED", {
            "message_id": str(message.id),
            "author": str(message.author),
            "channel": message.channel.name,
            "content": message.content,
            "timestamp_discord": message.created_at.isoformat()
        })

    # Log bot responses
    if message.author.bot and message.author == bot.user:
        reactions = [str(r.emoji) for r in message.reactions]
        log_message_exchange("SENT", {
            "message_id": str(message.id),
            "author": str(message.author),
            "channel": message.channel.name,
            "content": message.content,
            "reactions": reactions,
            "timestamp_discord": message.created_at.isoformat()
        })


async def main():
    """Start the message logger."""
    if not DISCORD_BOT_TOKEN:
        print("[ERROR] DISCORD_BOT_TOKEN not set")
        return

    if not DISCORD_CHANNEL_ID or DISCORD_CHANNEL_ID == 0:
        print("[ERROR] DISCORD_CHANNEL_ID not set")
        return

    print(f"[LOGGER] Starting message logger for channel {DISCORD_CHANNEL_ID}")
    print(f"[LOGGER] Logging to {MESSAGE_LOG} and {MESSAGE_JSON}")

    await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
