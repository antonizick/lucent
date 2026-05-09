#!/usr/bin/env python3
"""
Invoke a named sub-agent with a task via local Ollama.

Usage:
  python3 scripts/invoke_agent.py git "Stage and commit recent changes"
  python3 scripts/invoke_agent.py planner "Break down the voice input feature"
  python3 scripts/invoke_agent.py --model qwen3.6:35b git "Task"
"""

import requests
import sys
import argparse
from pathlib import Path
from datetime import date, timedelta
from verify_startup import ensure_startup_ritual, augment_system_prompt

# Find Lucent root
SCRIPT_DIR = Path(__file__).parent
LUCENT_ROOT = SCRIPT_DIR.parent
OLLAMA_URL = "http://localhost:11434"

def load_agent_context(agent_name):
    """Load all context files for an agent invocation."""
    context_parts = []

    # Core files
    for filename in ["core.md", "LTMemory.md", "userIdent.md"]:
        path = LUCENT_ROOT / filename
        if path.exists():
            context_parts.append(f"=== {filename} ===\n{path.read_text()}")

    # Agent personality
    agent_file = LUCENT_ROOT / "agents" / f"{agent_name}-agent.md"
    if not agent_file.exists():
        raise FileNotFoundError(f"Agent '{agent_name}' not found at {agent_file}")
    context_parts.append(f"=== YOUR IDENTITY ===\n{agent_file.read_text()}")

    # Last 7 days of daily notes
    today = date.today()
    memory_dir = LUCENT_ROOT / "memory"
    for i in range(7):
        day = today - timedelta(days=i)
        note_path = memory_dir / f"{day.strftime('%Y-%m-%d')}.md"
        if note_path.exists():
            label = "Today's note" if i == 0 else f"Daily note ({day})"
            context_parts.append(f"=== {label} ===\n{note_path.read_text()}")

    return "\n\n".join(context_parts)

def invoke_agent(agent_name, task, model="mistral:latest"):
    """
    Invoke a named agent with a task via local Ollama.

    Args:
        agent_name: Name of the agent (e.g., "git", "planner")
        task: Task description or question for the agent
        model: Ollama model to use (default: mistral:latest)

    Returns:
        Response string prefixed with [AgentName]
    """
    # Verify startup ritual has fired; if not, enforce it
    ritual_context, executed = ensure_startup_ritual(LUCENT_ROOT, model)

    # Load agent context
    system_prompt = load_agent_context(agent_name)

    # Prepend startup ritual context if it just executed
    if executed:
        system_prompt = augment_system_prompt(system_prompt, ritual_context)

    # Call Ollama
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": task,
                "system": system_prompt,
                "stream": False,
                "temperature": 0.7
            },
            timeout=900
        )

        if resp.status_code == 200:
            data = resp.json()
            response_text = data.get("response", "").strip()
            if response_text:
                # Format with agent prefix
                agent_display_name = agent_name.capitalize()
                return f"[{agent_display_name}] {response_text}"
            else:
                raise ValueError("Empty response from Ollama")
        else:
            raise ValueError(f"Ollama error: {resp.status_code}")

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Could not connect to Ollama at {OLLAMA_URL}. "
            "Is Ollama running? Start with: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama request timed out (900s)")

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Invoke a named sub-agent with a task via Ollama"
    )
    parser.add_argument(
        "--model",
        default="mistral:latest",
        help="Ollama model to use (default: mistral:latest)"
    )
    parser.add_argument(
        "agent",
        help="Agent name (git, planner, curator, writer, reviewer)"
    )
    parser.add_argument(
        "task",
        nargs="+",
        help="Task description or question for the agent"
    )

    args = parser.parse_args()
    agent_name = args.agent
    task = " ".join(args.task)
    model = args.model

    try:
        result = invoke_agent(agent_name, task, model)
        print(result)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
