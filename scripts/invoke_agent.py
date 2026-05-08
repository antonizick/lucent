#!/usr/bin/env python3
"""
Invoke a named sub-agent with a task via Claude Haiku API.

Usage:
  python3 scripts/invoke_agent.py git "Stage and commit recent changes"
  python3 scripts/invoke_agent.py planner "Break down the voice input feature"
"""

import anthropic
import sys
import os
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv

# Find Lucent root
SCRIPT_DIR = Path(__file__).parent
LUCENT_ROOT = SCRIPT_DIR.parent

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

def invoke_agent(agent_name, task):
    """
    Invoke a named agent with a task via Claude Haiku API.

    Args:
        agent_name: Name of the agent (e.g., "git", "planner")
        task: Task description or question for the agent

    Returns:
        Response string prefixed with [AgentName]
    """
    # Load environment and API key
    env_path = LUCENT_ROOT / "ui" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found in environment or ui/.env. "
            "Please set the API key to use agent invocation."
        )

    # Load agent context
    system_prompt = load_agent_context(agent_name)

    # Call Claude Haiku API
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": task}]
    )

    response = message.content[0].text

    # Format with agent prefix
    agent_display_name = agent_name.capitalize()
    return f"[{agent_display_name}] {response}"

def main():
    """CLI entry point."""
    if len(sys.argv) < 3:
        print("Usage: invoke_agent.py <agent_name> <task>")
        print("Example: invoke_agent.py git 'Stage and commit recent changes'")
        print("\nAvailable agents: git, planner, curator, writer, reviewer")
        sys.exit(1)

    agent_name = sys.argv[1]
    task = " ".join(sys.argv[2:])

    try:
        result = invoke_agent(agent_name, task)
        print(result)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"API Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
