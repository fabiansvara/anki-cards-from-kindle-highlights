"""Command-line interface for anki-cards-from-kindle-highlights."""

from pathlib import Path
from typing import Annotated

import typer
from openai import OpenAI

from anki_cards_from_kindle_highlights import __version__
from anki_cards_from_kindle_highlights.llm import llm_highlight_to_card

app = typer.Typer(
    name="anki-cards-from-kindle-highlights",
    help="Generate Anki cards from Kindle highlights using LLMs.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        print(f"anki-cards-from-kindle-highlights {__version__}")
        raise typer.Exit()


def get_prompt() -> str:
    """Load the system prompt from prompt.txt."""
    prompt_file = Path(__file__).parent / "prompt.txt"
    return prompt_file.read_text(encoding="utf-8")


@app.command()
def main(
    book_title: Annotated[
        str,
        typer.Option("--book-title", "-b", help="Title of the book"),
    ],
    highlight: Annotated[
        str,
        typer.Option("--highlight", "-h", help="The highlight text to convert"),
    ],
    openai_api_key: Annotated[
        str | None,
        typer.Option(
            "--openai-api-key",
            envvar="OPENAI_API_KEY",
            help="OpenAI API key (defaults to OPENAI_API_KEY env var)",
        ),
    ] = None,
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="OpenAI model to use"),
    ] = "gpt-4o-2024-08-06",
    version: Annotated[  # noqa: ARG001
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """Generate an Anki card from a Kindle highlight."""
    if openai_api_key is None:
        print(
            "Error: OpenAI API key is required. Set OPENAI_API_KEY or use --openai-api-key"
        )
        raise typer.Exit(1)

    client = OpenAI(api_key=openai_api_key)
    prompt = get_prompt()

    card = llm_highlight_to_card(
        client=client,
        prompt=prompt,
        book_title=book_title,
        highlight=highlight,
        model=model,
    )

    if card is None:
        raise typer.Exit(1)

    print(f"Pattern: {card.pattern}")
    print(f"Front: {card.front}")
    print(f"Back: {card.back}")


if __name__ == "__main__":
    app()
