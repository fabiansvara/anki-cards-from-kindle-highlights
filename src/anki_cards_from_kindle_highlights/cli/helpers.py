"""Shared helper functions for CLI commands."""

from pathlib import Path

import typer

from anki_cards_from_kindle_highlights import __version__


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        print(f"anki-cards-from-kindle-highlights {__version__}")
        raise typer.Exit()


def get_prompt() -> str:
    """Load the system prompt from prompt.txt."""
    prompt_file = Path(__file__).parent.parent / "prompt.txt"
    return prompt_file.read_text(encoding="utf-8")


def abbreviate(text: str | None, max_len: int = 50) -> str:
    """Abbreviate text to a maximum length with ellipsis."""
    if text is None:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
