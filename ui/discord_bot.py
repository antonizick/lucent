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
DISCORD_CLAUDE_CHANNEL_ID = int(os.getenv("DISCORD_CLAUDE_CHANNEL_ID", 0))
LUCENT_ROOT = os.getenv("LUCENT_ROOT", "/home/nick/dev/lucent")
CLAUDE_BIN = "/home/nick/.local/bin/claude"
RESET_FLAG_PATH = "/tmp/lucent_discord_reset.flag"
CLAUDE_MODEL_PATH = "/tmp/lucent_discord_claude_model"
CLAUDE_MODEL_ALIASES = {"opus": "opus", "sonnet": "sonnet", "haiku": "haiku"}
CLAUDE_MODEL_DEFAULT = "sonnet"

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
    if message.author == bot.user:
        return

    # Dedicated Claude CLI channel
    if DISCORD_CLAUDE_CHANNEL_ID and message.channel.id == DISCORD_CLAUDE_CHANNEL_ID:
        await handle_claude_message(message)
        return

    # Original Lucent command channel
    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

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

def get_claude_model():
    try:
        return open(CLAUDE_MODEL_PATH).read().strip() or CLAUDE_MODEL_DEFAULT
    except FileNotFoundError:
        return CLAUDE_MODEL_DEFAULT


async def handle_claude_message(message: discord.Message):
    """Handle messages in the dedicated Claude CLI channel."""
    text = message.content.strip()

    if text.lower() in ("/clear", "/new"):
        with open(RESET_FLAG_PATH, "w") as f:
            f.write("reset")
        await message.add_reaction("🔄")
        await message.reply("Session cleared. Next message starts fresh.", tts=True)
        return

    if text.lower().startswith("/model"):
        parts = text.split(maxsplit=1)
        if len(parts) == 1:
            current = get_claude_model()
            await message.reply(f"Current model: {current}. Options: opus, sonnet, haiku.", tts=True)
            return
        alias = parts[1].strip().lower()
        if alias not in CLAUDE_MODEL_ALIASES:
            await message.reply(f"Unknown model {alias}. Options: opus, sonnet, haiku.", tts=True)
            return
        with open(CLAUDE_MODEL_PATH, "w") as f:
            f.write(CLAUDE_MODEL_ALIASES[alias])
        await message.add_reaction("✅")
        await message.reply(f"Model set to {alias}. Takes effect on next message.", tts=True)
        return

    use_continue = not os.path.exists(RESET_FLAG_PATH)
    if os.path.exists(RESET_FLAG_PATH):
        os.remove(RESET_FLAG_PATH)

    model = get_claude_model()
    await message.add_reaction("⏳")

    base_cmd = [CLAUDE_BIN, "--model", model, "-p", text]
    cmd = [CLAUDE_BIN, "--continue", "--model", model, "-p", text] if use_continue else base_cmd

    # Strip ANTHROPIC_API_KEY so claude uses its own stored credentials
    subprocess_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=LUCENT_ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=subprocess_env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        except asyncio.TimeoutError:
            proc.kill()
            await message.remove_reaction("⏳", bot.user)
            await message.reply("⚠️ Timed out after 180 seconds.", tts=True)
            return

        output = stdout.decode().strip()
        if not output:
            output = stderr.decode().strip()[:500] or "*(no response)*"

        await message.remove_reaction("⏳", bot.user)

        # Clean output: remove "session complete" and similar messages for voice box
        voice_output = output
        if "session complete" in voice_output.lower():
            # Remove the "session complete" line
            lines = voice_output.split('\n')
            lines = [line for line in lines if "session complete" not in line.lower()]
            voice_output = '\n'.join(lines).strip()

        chunks = [output[i:i+1900] for i in range(0, len(output), 1900)]

        # Send cleaned response to voice box ONLY if there's actual content after filtering
        if voice_output:
            try:
                speak_payload = {
                    "text": voice_output,
                    "source": "discord"
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "http://localhost:8001/speak",
                        json=speak_payload,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            print(f"[DISCORD] Sent response to voice box via /speak")
                        else:
                            print(f"[DISCORD] Voice box /speak failed: {resp.status}")
            except Exception as e:
                print(f"[ERROR] Exception sending to voice box: {e}")
        else:
            print(f"[DISCORD] Filtered output is empty, skipping voice box send")

        for i, chunk in enumerate(chunks):
            label = "**Lucent:**" if i == 0 else "**Lucent (cont.):**"
            if i == 0:
                await message.reply(f"{label}\n{chunk}", tts=True)
            else:
                channel = bot.get_channel(DISCORD_CLAUDE_CHANNEL_ID)
                await channel.send(f"{label}\n{chunk}")

    except Exception as e:
        await message.remove_reaction("⏳", bot.user)
        await message.reply(f"⚠️ Error: {e}", tts=True)


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
