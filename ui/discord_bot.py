import discord
from discord.ext import commands
import os
import json
import aiohttp
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import threading

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_SERVER_ID = int(os.getenv("DISCORD_SERVER_ID", 0))
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", 0))
DISCORD_LOG_CHANNEL_ID = int(os.getenv("DISCORD_LOG_CHANNEL_ID", 0))
DISCORD_LOG_WEBHOOK_URL = os.getenv("DISCORD_LOG_WEBHOOK_URL", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8002")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Flask webhook for receiving responses from server
flask_app = Flask(__name__)

@flask_app.route("/webhook/response", methods=["POST"])
def webhook_response():
    """Receive response from server and post to Discord."""
    try:
        data = request.json
        message_id = data.get("message_id")
        thread_id = data.get("thread_id")
        response_text = data.get("response")
        search_used = data.get("search_used", False)

        print(f"[WEBHOOK] Received response: message_id={message_id}, search_used={search_used}")

        if not response_text:
            return jsonify({"error": "Missing response text"}), 400

        # Schedule the async post_response to run in the bot's event loop
        asyncio.run_coroutine_threadsafe(
            post_response(message_id, thread_id, response_text, search_used),
            bot.loop
        )

        print(f"[WEBHOOK] Scheduled post_response with search_used={search_used}")
        return jsonify({"status": "scheduled"}), 200
    except Exception as e:
        print(f"[ERROR] Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

@bot.event
async def on_ready():
    """Called when bot connects and is ready."""
    print(f"Logged in as {bot.user}")
    print(f"Server ID: {DISCORD_SERVER_ID}")
    print(f"Command Channel ID: {DISCORD_CHANNEL_ID}")
    print(f"Log Channel ID: {DISCORD_LOG_CHANNEL_ID}")
    print(f"Bot ready and listening")

@bot.event
async def on_message(message):
    """Listen for messages in the Lucent command channel."""
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Only respond in the configured Lucent channel
    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    # Skip commands
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    # Post message to backend queue
    await queue_message(message)

async def queue_message(message: discord.Message):
    """Post Discord message to backend /message/pending queue."""
    payload = {
        "source": "discord_command",
        "user_id": str(message.author.id),
        "channel_id": str(message.channel.id),
        "message_id": str(message.id),
        "thread_id": str(message.channel.id) if hasattr(message.channel, 'parent') else None,
        "text": message.content,
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
                    # Add reaction to confirm receipt
                    await message.add_reaction("✅")
                    print(f"[DISCORD] Queued message from {message.author}: {message.content[:50]}")
                else:
                    print(f"[ERROR] Failed to queue message: {resp.status}")
                    await message.add_reaction("❌")
    except Exception as e:
        print(f"[ERROR] Exception posting to queue: {e}")
        await message.add_reaction("❌")

async def post_response(message_id: str, thread_id: str, response_text: str, search_used: bool = False):
    """Post Lucent's response back to Discord thread."""
    try:
        channel = bot.get_channel(DISCORD_CHANNEL_ID)
        if not channel:
            print(f"[ERROR] Could not find channel {DISCORD_CHANNEL_ID}")
            return

        # If there's a thread_id, post in thread; otherwise post as reply
        if thread_id and thread_id != "None":
            thread = await channel.fetch_thread(int(thread_id))
            msg = await thread.send(f"**Lucent:** {response_text}")
        else:
            try:
                original_msg = await channel.fetch_message(int(message_id))
                msg = await original_msg.reply(f"**Lucent:** {response_text}")
            except discord.NotFound:
                msg = await channel.send(f"**Lucent:** {response_text}")

        if search_used:
            try:
                await msg.add_reaction("📰")
                print(f"[DISCORD] Added newspaper emoji to response")
            except Exception as emoji_error:
                print(f"[ERROR] Failed to add newspaper emoji: {emoji_error}")

        print(f"[DISCORD] Posted response to message {message_id} (search_used={search_used})")
    except Exception as e:
        print(f"[ERROR] Failed to post response: {e}")

async def broadcast_log(text: str, level: str = "info"):
    """Broadcast console log to Discord log channel via webhook."""
    if not DISCORD_LOG_WEBHOOK_URL:
        return

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "content": f"```\n[{level.upper()}] {text}\n```"
            }
            async with session.post(
                DISCORD_LOG_WEBHOOK_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 204:
                    print(f"[ERROR] Failed to post log: {resp.status}")
    except Exception as e:
        print(f"[ERROR] Exception posting log: {e}")

def run_flask():
    """Run Flask webhook server in background thread."""
    flask_app.run(host="127.0.0.1", port=8003, debug=False, use_reloader=False)

def run_bot():
    """Start the Discord bot."""
    if not DISCORD_BOT_TOKEN:
        print("[ERROR] DISCORD_BOT_TOKEN not set in .env")
        return

    # Start Flask webhook in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("[INFO] Flask webhook started on http://127.0.0.1:8003")

    try:
        bot.run(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"[ERROR] Failed to start bot: {e}")

if __name__ == "__main__":
    run_bot()
