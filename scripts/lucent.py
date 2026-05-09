#!/usr/bin/env python3
"""
Universal Lucent wrapper — enforces startup ritual for all entry points.

This is the canonical entry point for invoking Lucent agents from any tool
(OpenCode, Discord, scripts, CLI). It guarantees the startup ritual has fired
before delegating to agent invocation.

Usage:
  python3 scripts/lucent.py agent <agent_name> <task> [--model MODEL]
  python3 scripts/lucent.py agent git "Stage and commit changes"
  python3 scripts/lucent.py agent planner "Break down the voice feature" --model qwen3.6:35b

Aliases (create these in your shell):
  lucent_agent() { python3 /home/nick/dev/lucent/scripts/lucent.py agent "$@"; }
"""

import sys
import argparse
from pathlib import Path

# Import our modules
from verify_startup import ensure_startup_ritual, augment_system_prompt
from invoke_agent import invoke_agent, LUCENT_ROOT

def agent_command(agent_name: str, task: str, model: str = "mistral:latest") -> str:
    """
    Invoke an agent with guaranteed startup ritual.

    Args:
        agent_name: Name of the agent (git, planner, curator, etc.)
        task: Task description
        model: Ollama model to use

    Returns:
        Agent response string
    """
    # Verify/enforce startup ritual
    ritual_context, executed = ensure_startup_ritual(LUCENT_ROOT, model)

    # Invoke agent
    response = invoke_agent(agent_name, task, model)

    # If ritual just executed, prepend context acknowledgment
    if executed:
        acknowledgment = f"[Lucent startup ritual enforced for {model}]\n{response}"
        return acknowledgment

    return response

def main():
    """CLI entry point for universal Lucent wrapper."""
    parser = argparse.ArgumentParser(
        description="Universal Lucent wrapper — enforces startup ritual for all entry points",
        prog="lucent"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Agent invocation subcommand
    agent_parser = subparsers.add_parser(
        "agent",
        help="Invoke a named agent (guaranteed startup ritual)"
    )
    agent_parser.add_argument(
        "agent",
        help="Agent name (git, planner, curator, writer, reviewer)"
    )
    agent_parser.add_argument(
        "task",
        nargs="+",
        help="Task description or question for the agent"
    )
    agent_parser.add_argument(
        "--model",
        default="mistral:latest",
        help="Ollama model to use (default: mistral:latest)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "agent":
        agent_name = args.agent
        task = " ".join(args.task)
        model = args.model

        try:
            result = agent_command(agent_name, task, model)
            print(result)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except (ValueError, RuntimeError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
