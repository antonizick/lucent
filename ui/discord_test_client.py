#!/usr/bin/env python3
"""
Discord Test Client - Posts test messages via the message queue and verifies responses.
Allows self-testing of the Discord integration without manual user input.
"""

import os
import discord
from discord.ext import commands
import asyncio
import aiohttp
import time
from datetime import datetime
import uuid

# Config
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", 0))
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Test results log
TEST_LOG = "/tmp/discord_test_results.log"

# Track test messages by ID
test_messages = {}

def log_test(message: str):
    """Log test result to file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(TEST_LOG, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[TEST] {message}")


async def post_to_queue(text: str) -> dict:
    """Post a message to the /message/pending queue."""
    payload = {
        "source": "discord_test_client",
        "user_id": str(bot.user.id),
        "channel_id": str(DISCORD_CHANNEL_ID),
        "message_id": str(uuid.uuid4()),
        "thread_id": None,
        "text": text,
        "timestamp": datetime.now().isoformat()
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_URL}/message/pending",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    log_test(f"Queued: {text[:50]}... (ID: {payload['message_id']})")
                    return payload
                else:
                    log_test(f"ERROR: Failed to queue message, status {resp.status}")
                    return None
    except Exception as e:
        log_test(f"ERROR: Exception posting to queue: {e}")
        return None


@bot.event
async def on_ready():
    """Called when bot connects."""
    log_test(f"Bot connected as {bot.user}")

    # Post test messages via the queue
    log_test("=" * 60)
    log_test("POSTING TEST MESSAGES")
    log_test("=" * 60)

    # Test 1: Weather query (should trigger web search)
    msg1 = await post_to_queue("What is the weather tomorrow in Chicago?")
    if msg1:
        test_messages[msg1["message_id"]] = {"query": msg1["text"], "expect_search": True}

    # Test 2: Event query (should trigger web search)
    msg2 = await post_to_queue("What events are happening this weekend in Woodstock?")
    if msg2:
        test_messages[msg2["message_id"]] = {"query": msg2["text"], "expect_search": True}

    # Test 3: Non-search query
    msg3 = await post_to_queue("How does photosynthesis work?")
    if msg3:
        test_messages[msg3["message_id"]] = {"query": msg3["text"], "expect_search": False}

    # Wait for responses to be generated and posted to Discord
    log_test("Waiting 30 seconds for responses...")
    await asyncio.sleep(30)

    # Disconnect after testing
    await bot.close()


@bot.event
async def on_message(message):
    """Monitor for responses and check reactions."""
    # Only monitor responses in the test channel
    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    # Skip messages from the test client itself
    if message.author.id == bot.user.id:
        return

    # Wait a moment for reactions to be added
    await asyncio.sleep(2)
    await message.refresh()

    reactions = [str(r.emoji) for r in message.reactions]
    has_emoji = "📰" in reactions

    log_test(f"Response received: {message.content[:60]}...")
    log_test(f"  Reactions: {reactions}")
    log_test(f"  Has newspaper emoji: {has_emoji}")


async def main():
    """Start the test client."""
    if not DISCORD_BOT_TOKEN:
        print("[ERROR] DISCORD_BOT_TOKEN not set")
        return

    if not DISCORD_CHANNEL_ID or DISCORD_CHANNEL_ID == 0:
        print("[ERROR] DISCORD_CHANNEL_ID not set")
        return

    # Clear previous test log
    with open(TEST_LOG, "w") as f:
        f.write(f"=== Discord Test Session {datetime.now().isoformat()} ===\n")

    log_test("Starting Discord test client")
    log_test(f"Backend: {BACKEND_URL}")
    log_test(f"Channel: {DISCORD_CHANNEL_ID}")

    await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
