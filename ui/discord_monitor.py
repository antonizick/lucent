"""Discord instruction monitor — fetches pending messages, processes them, posts responses."""

import os
import sys
import time
import requests
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Web search support for internet access
try:
    from ddgs import DDGS
    SEARCH_ENABLED = True
except ImportError:
    SEARCH_ENABLED = False
    logger_placeholder = None

# Import startup ritual verification
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from verify_startup import ensure_startup_ritual, augment_system_prompt

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
        self.model = self.load_selected_model()  # Load persisted model choice

    def load_selected_model(self) -> str:
        """Load the selected model from server or default to mistral."""
        try:
            resp = requests.get(
                f"{self.backend_url}/ollama/models",
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                model = data.get("current", "mistral")
                logger.info(f"Loaded model: {model}")
                return model
        except Exception as e:
            logger.warning(f"Could not load model preference: {e}")
        return "mistral"

    def needs_web_search(self, text: str) -> bool:
        """Two-stage search detection: keywords first (fast), then AI fallback (intelligent)."""
        # STAGE 1: Fast keyword check - catches obvious cases with zero overhead
        search_triggers = [
            # Time-sensitive: current/recent
            r'\b(today|latest|current|recent|now|right now)\b',
            # Time-sensitive: future dates (Nick's weather/store hours)
            r'\b(tomorrow|next week|next month|next day|coming up|upcoming|weekend)\b',
            r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b(?=.*?(weather|open|close|hour|event))',
            # News and events
            r'\b(news|breaking|happened|just|announced|event|happening|what.*s (on|happening))\b',
            # Years
            r'\b(2025|2026)\b',
            # Specific searches needing current data
            r'\b(weather|forecast|temperature|rain|snow)\b',
            r'\b(stock|price|cost|rate|exchange)\b',
            r'\b(open|hours|close|opening time|closing time|restaurant|store|shop|venue|activity|activities)\b',
            r'\b(how to|tutorial|guide)\s+(make|build|create)',
            r'\b(what.*new|new.*what)\b',
            r'\b(trending|viral|popular)\b',
            # Current events
            r'\b(covid|election|war|protest|strike|scandal)\b',
            # Location-based queries for activities
            r'\b(what.*in|where.*in|things to do|do in|visit|attractions)\b',
        ]

        text_lower = text.lower()
        for pattern in search_triggers:
            if re.search(pattern, text_lower):
                logger.info(f"[SEARCH] Stage 1 (keywords): MATCH - will search")
                return True

        # STAGE 2: AI fallback for edge cases not caught by keywords
        # Ask Mistral to interpret context and decide
        logger.info(f"[SEARCH] Stage 1 (keywords): No match - checking with AI")
        try:
            meta_prompt = f"""Does this user question require real-time information from the internet to answer accurately?
Examples that need search: "What's the weather tomorrow?", "What are store hours?", "Latest news about X?"
Examples that don't need search: "How does photosynthesis work?", "Who was George Washington?", "Explain quantum physics"

User question: "{text}"

Answer with ONLY: "yes" or "no" (lowercase, no explanation)"""

            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": meta_prompt,
                    "stream": False,
                    "temperature": 0.1
                },
                timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                response = data.get("response", "").strip().lower()
                needs_search = "yes" in response[:10]  # Check first 10 chars
                logger.info(f"[SEARCH] Stage 2 (AI): {'MATCH' if needs_search else 'NO MATCH'} - AI says '{response[:20]}'")
                return needs_search
            else:
                logger.warning(f"[SEARCH] Stage 2 (AI): Failed with status {resp.status_code}, assuming no search needed")
                return False
        except Exception as e:
            logger.error(f"[SEARCH] Stage 2 (AI): Exception - {e}, assuming no search needed")
            return False

    def search_duckduckgo(self, query: str, max_results: int = 3) -> str:
        """Search DuckDuckGo and return formatted results."""
        if not SEARCH_ENABLED:
            logger.warning("[SEARCH] duckduckgo_search not installed")
            return ""

        try:
            logger.info(f"[SEARCH] Searching DuckDuckGo for: {query}")
            ddgs = DDGS()
            results = ddgs.text(query, max_results=max_results)

            if not results:
                logger.info("[SEARCH] No results found")
                return ""

            formatted = "## Web Search Results:\n"
            for i, result in enumerate(results, 1):
                title = result.get("title", "")
                body = result.get("body", "")
                formatted += f"\n{i}. **{title}**\n   {body}\n"

            logger.info(f"[SEARCH] Found {len(results)} results")
            return formatted
        except Exception as e:
            logger.error(f"[SEARCH] Exception during search: {e}")
            return ""

    def load_context(self) -> str:
        """Load minimal context for Discord (LTMemory + daily note only, no instruction files)."""
        context_parts = []

        # Load LTMemory (state/priorities, not instructions)
        ltmem_path = self.lucent_root / "memory" / "LTMemory.md"
        if ltmem_path.exists():
            try:
                content = ltmem_path.read_text()
                context_parts.append(f"=== Current Priorities & State ===\n{content}")
            except Exception as e:
                logger.warning(f"Failed to read LTMemory: {e}")

        # Load today's daily note (ongoing state)
        today = datetime.now().strftime("%Y-%m-%d")
        daily_note = self.memory_dir / f"{today}.md"
        if daily_note.exists():
            try:
                content = daily_note.read_text()
                context_parts.append(f"=== Today's Work ===\n{content}")
            except Exception as e:
                logger.warning(f"Failed to read daily note: {e}")

        return "\n\n".join(context_parts) if context_parts else "[No context available]"

    def clean_response(self, response_text: str) -> str:
        """Remove tool_use blocks and XML tags from response."""
        # Remove tool_use blocks entirely
        response_text = re.sub(r'<tool_use>.*?</tool_use>', '', response_text, flags=re.DOTALL)
        # Remove stray XML tags
        response_text = re.sub(r'</?tool_use>|</?name>|</?arguments>', '', response_text)
        # Remove empty brackets and clean up whitespace
        response_text = re.sub(r'[\[\]]', '', response_text)
        response_text = response_text.strip()
        return response_text if response_text else "Processing complete."

    def process_instruction(self, message: dict) -> tuple:
        """Process Discord instruction through Ollama and return (response_text, search_used)."""
        try:
            logger.info(f"[PROCESS] Starting instruction processing")
            # Verify/enforce startup ritual
            ritual_context, executed, compression_needed = ensure_startup_ritual(self.lucent_root, self.model)

            instruction_text = message.get("text", "")

            # Hybrid Smart Detection: Check if web search is needed
            search_results = ""
            search_used = False
            if self.needs_web_search(instruction_text):
                logger.info(f"[SEARCH] Web search triggered for query")
                search_results = self.search_duckduckgo(instruction_text)
                if search_results:
                    search_used = True
                    logger.info(f"[SEARCH] Augmenting context with search results ({len(search_results)} chars)")

            context = self.load_context()
            logger.info(f"[PROCESS] Loaded context ({len(context)} chars), instruction: '{instruction_text[:60]}'")

            # Option 1: Reframe prompt - user instruction first (primary), context second (background)
            # Include web search results if available (Hybrid Smart Detection)
            search_section = f"\n--- WEB SEARCH RESULTS ---\n{search_results}\n" if search_results else ""

            system_prompt = f"""You are Lucent, Nick's personal AI assistant.

USER QUESTION/INSTRUCTION:
{instruction_text}

--- BACKGROUND CONTEXT ---
{context}{search_section}
--- TASK ---
Respond naturally and concisely to Nick's question above. Keep responses under 2-3 sentences unless more detail is needed. Do NOT use tool_use syntax, XML tags, or tool calls. Generate only plain text responses."""

            # Prepend startup ritual context if it just executed
            if executed:
                system_prompt = augment_system_prompt(ritual_context, system_prompt)

            # Call Ollama
            logger.info(f"[OLLAMA] Calling Ollama with model={self.model}")
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": instruction_text,
                    "system": system_prompt,
                    "stream": False,
                    "temperature": 0.7
                },
                timeout=900
            )

            logger.info(f"[OLLAMA] Response status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                response_text = data.get("response", "").strip()
                if response_text:
                    response_text = self.clean_response(response_text)
                    logger.info(f"[OLLAMA] Generated response ({len(response_text)} chars): {response_text[:100]}")
                    return response_text, search_used
                else:
                    logger.error("[OLLAMA] Empty response from Ollama")
                    return "[Error: empty response from model]", search_used
            else:
                logger.error(f"[OLLAMA] Ollama error: {resp.status_code} - {resp.text[:200]}")
                return f"[Error processing instruction: {resp.status_code}]", search_used

        except requests.exceptions.Timeout:
            logger.error("Ollama timeout")
            return "[Error: response generation timed out]", False
        except Exception as e:
            logger.error(f"Exception processing instruction: {e}")
            return f"[Error processing instruction: {str(e)}]", False

    def send_voice_feedback(self, response_text: str) -> bool:
        """Send voice feedback to Voice Box."""
        try:
            payload = {"text": response_text}
            resp = requests.post(
                "http://localhost:8001/speak",
                json=payload,
                timeout=10
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Exception sending voice feedback: {e}")
            return False

    def post_response(self, message: dict, response_text: str, search_used: bool = False) -> bool:
        """Post response back to Discord AND voice box UI with audio synthesis."""
        try:
            logger.info(f"[RESPONSE] Posting response back to Discord + voice box (search_used={search_used})")

            # Clean output: remove "session complete" and similar messages for voice box
            voice_output = response_text
            if "session complete" in voice_output.lower():
                # Remove the "session complete" line
                lines = voice_output.split('\n')
                lines = [line for line in lines if "session complete" not in line.lower()]
                voice_output = '\n'.join(lines).strip()

            # Send to voice box UI via /speak endpoint ONLY if there's actual content after filtering
            if voice_output:
                try:
                    speak_payload = {
                        "text": voice_output,
                        "source": "discord"  # Tag responses as Discord-originated
                    }
                    speak_resp = requests.post(
                        f"{self.backend_url}/speak",
                        json=speak_payload,
                        timeout=10
                    )
                    if speak_resp.status_code == 200:
                        logger.info(f"[RESPONSE] Voice box updated: {voice_output[:80]}")
                    else:
                        logger.warning(f"[RESPONSE] Voice box post failed: {speak_resp.status_code}")
                except Exception as e:
                    logger.warning(f"[RESPONSE] Exception sending to voice box: {e}")
            else:
                logger.info(f"[RESPONSE] Filtered output is empty, skipping voice box send")

            # Post response to Discord webhook
            payload = {
                "source": "discord_command",  # All Discord messages have this source
                "message_id": message.get("message_id"),
                "channel_id": message.get("channel_id"),
                "thread_id": message.get("thread_id"),
                "user_id": message.get("user_id"),
                "response": response_text,
                "timestamp": datetime.now().isoformat(),
                "search_used": search_used  # Flag to add newspaper emoji reaction
            }

            logger.info(f"[RESPONSE] Posting to Discord webhook")
            resp = requests.post(
                f"{self.backend_url}/response",
                json=payload,
                timeout=10
            )

            logger.info(f"[RESPONSE] Discord webhook status: {resp.status_code}")
            if resp.status_code == 200:
                logger.info(f"[RESPONSE] Successfully posted to both Discord and voice box: {response_text[:80]}")
                return True
            else:
                logger.error(f"[RESPONSE] Discord webhook error: {resp.status_code} - {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Exception posting response: {e}")
            return False

    def fetch_pending_messages(self) -> list:
        """Peek at pending Discord messages without clearing."""
        try:
            resp = requests.get(
                f"{self.backend_url}/message/pending",
                timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                # /message/pending returns singular "message", not plural "messages"
                message = data.get("message")
                messages = [message] if message else []
                if messages:
                    logger.info(f"[FETCH] Fetched {len(messages)} pending Discord message(s)")
                return messages
            else:
                logger.warning(f"[FETCH] Failed to fetch pending messages: {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"[FETCH] Exception fetching pending messages: {e}")
            return []

    def clear_processed_messages(self) -> bool:
        """Clear the pending messages queue after processing."""
        try:
            resp = requests.delete(
                f"{self.backend_url}/message/pending",
                timeout=10
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Exception clearing messages: {e}")
            return False

    def handle_command(self, message: dict):
        """Handle special Discord commands. Returns (is_command, response)."""
        text = message.get("text", "").strip().lower()

        # Check for list models commands
        if any(phrase in text for phrase in ["list models", "show models", "available models", "what models"]):
            try:
                resp = requests.get(
                    f"{self.backend_url}/ollama/models",
                    timeout=5
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("available", [])
                    current = data.get("current", "unknown")
                    numbered_list = "\n".join([f"{i+1}. {m}" for i, m in enumerate(models)])
                    return True, f"Available models:\n{numbered_list}\n\nCurrent: {current}\n\nReply with a number to switch (e.g., 1 or 2)"
            except Exception as e:
                return True, f"Error listing models: {str(e)}"

        # Check for current model query
        elif any(phrase in text for phrase in ["current model", "which model", "what model"]):
            try:
                resp = requests.get(
                    f"{self.backend_url}/ollama/models",
                    timeout=5
                )
                if resp.status_code == 200:
                    data = resp.json()
                    current = data.get("current", "unknown")
                    return True, f"Current model: {current}"
                else:
                    return True, "Could not fetch model info"
            except Exception as e:
                return True, f"Error checking model: {str(e)}"

        # Check for numbered model selection (just a number)
        elif text.isdigit():
            try:
                resp = requests.get(
                    f"{self.backend_url}/ollama/models",
                    timeout=5
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("available", [])
                    choice = int(text)
                    if 1 <= choice <= len(models):
                        model_name = models[choice - 1]
                        switch_resp = requests.post(
                            f"{self.backend_url}/ollama/model?model_name={model_name}",
                            timeout=5
                        )
                        if switch_resp.status_code == 200:
                            self.model = model_name
                            logger.info(f"Model switched to: {model_name}")
                            return True, f"Switched to model {choice}: {model_name}"
                        else:
                            return True, f"Failed to switch model: {switch_resp.status_code}"
                    else:
                        return True, f"Invalid choice. Please select 1-{len(models)}"
                else:
                    return True, "Could not fetch available models"
            except Exception as e:
                return True, f"Error switching model: {str(e)}"

        # Check for switch model commands (explicit name)
        elif any(phrase in text for phrase in ["use model", "switch to", "change to", "set model"]):
            # Extract model name - look for words after the command phrases
            model_name = None
            for phrase in ["use model", "switch to", "change to", "set model"]:
                if phrase in text:
                    model_name = text.split(phrase)[-1].strip()
                    break

            if model_name:
                try:
                    # First, get available models
                    resp = requests.get(
                        f"{self.backend_url}/ollama/models",
                        timeout=5
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        available = data.get("available", [])

                        # Try exact match first
                        exact_match = None
                        for model in available:
                            if model.lower() == model_name.lower():
                                exact_match = model
                                break

                        # If no exact match, try partial/fuzzy match
                        partial_matches = []
                        if not exact_match:
                            for model in available:
                                if model_name.lower() in model.lower():
                                    partial_matches.append(model)

                        # Determine which model to use
                        final_model = exact_match or (partial_matches[0] if len(partial_matches) == 1 else None)

                        if final_model:
                            # Switch to the matched model
                            switch_resp = requests.post(
                                f"{self.backend_url}/ollama/model?model_name={final_model}",
                                timeout=5
                            )
                            if switch_resp.status_code == 200:
                                self.model = final_model
                                logger.info(f"Model switched to: {final_model}")
                                return True, f"Model switched to: {final_model}"
                            else:
                                return True, f"Failed to switch model: {switch_resp.status_code}"
                        elif len(partial_matches) > 1:
                            return True, f"Multiple matches for '{model_name}': {', '.join(partial_matches)}. Please be more specific."
                        else:
                            return True, f"Model '{model_name}' not found. Available: {', '.join(available)}"
                    else:
                        return True, "Could not fetch available models"
                except Exception as e:
                    return True, f"Error switching model: {str(e)}"
            else:
                return True, "Please specify a model name. Example: 'use model mistral'"

        return False, ""

    def monitor(self):
        """Main monitoring loop."""
        logger.info(f"Starting Discord instruction monitor (polling every {POLLING_INTERVAL}s)")
        logger.info(f"Backend: {self.backend_url}")
        logger.info(f"Ollama: {self.ollama_url}")
        logger.info(f"Current model: {self.model}")

        while True:
            try:
                # Fetch pending Discord instructions
                messages = self.fetch_pending_messages()
                logger.info(f"Poll cycle: fetched {len(messages) if messages else 0} messages")

                if messages:
                    for message in messages:
                        logger.info(f"[PROCESSING] Discord instruction from {message.get('user_id')}: '{message.get('text', '')[:60]}'")

                        # Check if it's a command
                        is_command, response = self.handle_command(message)

                        if is_command:
                            # Send command response
                            self.post_response(message, response, search_used=False)
                        else:
                            # Process as normal instruction (returns tuple: response, search_used)
                            response, search_used = self.process_instruction(message)
                            self.post_response(message, response, search_used=search_used)

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
