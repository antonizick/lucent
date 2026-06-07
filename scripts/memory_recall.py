#!/usr/bin/env python3
"""
NERO Phase 1 — Hook entry point for semantic recall.

Called by lucent-init.sh before each turn — on either host (Claude Code's
UserPromptSubmit hook or OpenCode's chat.message via lucent-plugin.ts; both
feed lucent-init.sh the same {"prompt": "..."} stdin shape). Reads the user's
message from stdin, queries the memory index, and prints a <memory-context>
block if relevant memories are found.

RELIABILITY CONTRACT (100% guarantee):
  - Never exits non-zero (a non-zero exit would block the message on Claude Code's
    UserPromptSubmit; OpenCode's hook ignores exit codes but the contract still holds).
  - Never hangs — all Ollama calls have a 10s timeout; the whole script has
    a 15s wall-clock limit enforced by the caller via `timeout` in the hook.
  - Never prints garbage — only outputs a well-formed <memory-context> block or nothing.
  - Any exception at any level is caught and silently discarded.
  - If Ollama is unavailable, the hook output is identical to before this script existed.

stdin : JSON payload from the per-turn hook (either host)
stdout: <memory-context>…</memory-context> block, or empty
"""

import json
import sys
from pathlib import Path

# Add scripts/ to path so we can import memory_index
sys.path.insert(0, str(Path(__file__).parent))


def _extract_message(data: dict) -> str:
    """
    Pull user message text from the hook JSON payload.
    Claude Code may send several shapes; handle all gracefully.
    """
    msg = data.get("message", "")

    # Shape 1: {"message": "plain text"}
    if isinstance(msg, str):
        return msg

    # Shape 2: {"message": {"role": "user", "content": "text"}}
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        # Shape 3: content is a list of blocks [{"type": "text", "text": "..."}]
        if isinstance(content, list):
            return " ".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )

    # Shape 4: top-level "content" or "prompt" key (some hook versions)
    for key in ("content", "prompt", "text", "input"):
        val = data.get(key, "")
        if val and isinstance(val, str):
            return val

    return ""


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return  # Can't parse hook payload — skip silently

    try:
        message = _extract_message(data).strip()
    except Exception:
        return

    # Skip recall for very short messages (single words, punctuation, etc.)
    if not message or len(message) < 8:
        return

    try:
        from memory_index import recall_block
        block = recall_block(message)
        if block:
            print(block)
    except Exception:
        return  # Index error, import error, anything — skip silently


if __name__ == "__main__":
    main()
