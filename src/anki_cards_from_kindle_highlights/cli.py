"""Command-line interface for anki-cards-from-kindle-highlights."""

from typing import Annotated

import typer

from anki_cards_from_kindle_highlights import __version__

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


@app.command()
def main(
    version: Annotated[
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
    """Run the application."""
    print("Hello from anki-cards-from-kindle-highlights!")


if __name__ == "__main__":
    app()
