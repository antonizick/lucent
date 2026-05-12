#!/usr/bin/env python3
"""
AI Platform Launcher — Multi-platform AI model selector
Supports: Claude, OpenCode
Models: Anthropic, Local Ollama, OpenCode Free
"""

import sys
import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple

try:
    import questionary
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
except ImportError:
    print("Installing required dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "questionary", "rich"],
        check=False,
    )
    import questionary
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

console = Console()

# ─── Configuration ───
LUCENT_DIR = "/home/nick/dev/lucent"
ANTHROPIC_MODELS = ["opus", "sonnet", "haiku"]
OPENCODE_FREE_MODELS = [
    "big-pickle",
    "deepseek-v4-flash-free",
    "minimax-m2.5-free",
    "nemotron-3-super-free",
    "ring-2.6-1t-free",
]


def get_ollama_models() -> list[str]:
    """Query Ollama for available local models."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().split("\n")[1:]  # Skip header
        models = [line.split()[0] for line in lines if line.strip()]
        return sorted(models)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def show_header(title: str) -> None:
    """Display a styled header."""
    header_text = Text(title, style="bold cyan")
    panel = Panel(header_text, expand=False, style="blue")
    console.print(panel)
    console.print()


def select_claude_model() -> Optional[Tuple[str, str]]:
    """Select Claude platform and model. Returns (model, model_type) or None."""
    console.clear()
    show_header("🤖 Claude — Select Model")
    console.print()
    console.print()

    ollama_models = get_ollama_models()

    # Build choices with categories
    choices = []
    choices.append(questionary.Separator())

    # Anthropic models
    for model in ANTHROPIC_MODELS:
        choices.append(
            questionary.Choice(
                f"  {model.capitalize()} (Anthropic)", value=(model, "anthropic")
            )
        )

    # Separator
    choices.append(questionary.Separator())

    # Ollama models
    if ollama_models:
        for model in ollama_models:
            choices.append(
                questionary.Choice(f"  {model} (Ollama)", value=(model, "ollama"))
            )
    else:
        choices.append(questionary.Separator("No local Ollama models found"))

    choices.append(questionary.Separator())
    choices.append(questionary.Choice("← Back", value=None))
    choices.append(questionary.Separator())
    choices.append(questionary.Choice("❌ Exit", value="EXIT"))

    result = questionary.select(
        "Select model:",
        choices=choices,
        pointer="▶ ",
        use_shortcuts=False,
        use_arrow_keys=True,
    ).ask()

    return result


def select_opencode_model() -> Optional[Tuple[str, str]]:
    """Select OpenCode model. Returns (model, model_type) or None."""
    console.clear()
    show_header("🔧 OpenCode — Select Model")
    console.print()
    console.print()

    ollama_models = get_ollama_models()

    # Build choices with categories
    choices = []
    choices.append(questionary.Separator())

    # OpenCode free models
    for model in OPENCODE_FREE_MODELS:
        display_name = model.replace("-", " ").title()
        choices.append(
            questionary.Choice(
                f"  {display_name} (Free)", value=(model, "free")
            )
        )

    # Separator
    choices.append(questionary.Separator())

    # Ollama models
    if ollama_models:
        for model in ollama_models:
            choices.append(
                questionary.Choice(f"  {model} (Ollama)", value=(model, "ollama"))
            )
    else:
        choices.append(questionary.Separator("No local Ollama models found"))

    choices.append(questionary.Separator())
    choices.append(questionary.Choice("← Back", value=None))
    choices.append(questionary.Separator())
    choices.append(questionary.Choice("❌ Exit", value="EXIT"))

    result = questionary.select(
        "Select model:",
        choices=choices,
        pointer="▶ ",
        use_shortcuts=False,
        use_arrow_keys=True,
    ).ask()

    return result


def launch_claude(model: str, model_type: str) -> None:
    """Launch Claude with selected model."""
    os.chdir(LUCENT_DIR)

    console.print()
    console.print(
        Panel(
            f"[bold green]Launching Claude[/bold green] with [cyan]{model}[/cyan]...",
            style="green",
        )
    )
    console.print("[dim]Press Ctrl+C to cancel[/dim]")
    console.print()

    if model_type == "anthropic":
        os.execvp("claude", ["claude", "--model", model])
    elif model_type == "ollama":
        os.execvp("ollama", ["ollama", "launch", "claude", "--model", model])


def launch_opencode(model: str, model_type: str) -> None:
    """Launch OpenCode with selected model."""
    os.chdir(LUCENT_DIR)

    console.print()
    console.print(
        Panel(
            f"[bold green]Launching OpenCode[/bold green] with [cyan]{model}[/cyan]...",
            style="green",
        )
    )
    console.print("[dim]Press Ctrl+C to cancel[/dim]")
    console.print()

    if model_type == "free":
        os.execvp(
            "opencode",
            ["opencode", LUCENT_DIR, "--model", f"opencode/{model}"],
        )
    elif model_type == "ollama":
        os.execvp("ollama", ["ollama", "launch", "opencode", "--model", model])


def select_platform() -> Optional[str]:
    """Select platform (Claude or OpenCode)."""
    console.clear()
    show_header("Lucent Launcher")
    console.print()
    console.print()

    choice = questionary.select(
        "Select platform:",
        choices=[
            questionary.Separator(),
            questionary.Choice("  Claude (Anthropic + Local Models)", value="claude"),
            questionary.Choice("  OpenCode (Free Models + Local Models)", value="opencode"),
            questionary.Separator(),
            questionary.Choice("❌ Exit", value="EXIT"),
        ],
        pointer="▶ ",
        use_shortcuts=False,
        use_arrow_keys=True,
    ).ask()

    return choice


def interactive_mode() -> None:
    """Run interactive menu mode."""
    console.clear()
    while True:
        platform = select_platform()

        if platform == "EXIT":
            console.print("\n[yellow]Goodbye![/yellow]")
            return

        if platform == "claude":
            while True:
                result = select_claude_model()
                if result == "EXIT":
                    console.print("\n[yellow]Goodbye![/yellow]")
                    return
                if result is None or not isinstance(result, tuple):
                    break  # Go back to platform selection
                model, model_type = result
                launch_claude(model, model_type)

        elif platform == "opencode":
            while True:
                result = select_opencode_model()
                if result == "EXIT":
                    console.print("\n[yellow]Goodbye![/yellow]")
                    return
                if result is None or not isinstance(result, tuple):
                    break  # Go back to platform selection
                model, model_type = result
                launch_opencode(model, model_type)

        else:
            break


def quick_launch(platform: str, model: str) -> None:
    """Quick-launch mode with CLI arguments."""
    if platform == "claude":
        if model in ANTHROPIC_MODELS:
            launch_claude(model, "anthropic")
        else:
            launch_claude(model, "ollama")
    elif platform == "opencode":
        if model in OPENCODE_FREE_MODELS:
            launch_opencode(model, "free")
        else:
            launch_opencode(model, "ollama")
    else:
        console.print(f"[red]Unknown platform: {platform}[/red]")
        console.print("[yellow]Supported: claude, opencode[/yellow]")
        sys.exit(1)


def main() -> None:
    """Entry point."""
    if len(sys.argv) == 3:
        # Quick-launch mode: python launcher.py claude opus
        quick_launch(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 1:
        # Interactive mode
        try:
            interactive_mode()
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled.[/yellow]")
            sys.exit(0)
    else:
        console.print("Usage: ai-launcher.py [platform] [model]")
        console.print("  Interactive:  ai-launcher.py")
        console.print("  Quick-launch: ai-launcher.py claude opus")
        console.print("  Quick-launch: ai-launcher.py opencode big-pickle")
        sys.exit(1)


if __name__ == "__main__":
    main()
