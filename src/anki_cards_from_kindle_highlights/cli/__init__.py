"""CLI module - assembles the typer app with all commands."""

from typing import Annotated

import typer

from anki_cards_from_kindle_highlights.cli.dump import dump
from anki_cards_from_kindle_highlights.cli.generate import generate
from anki_cards_from_kindle_highlights.cli.generate_batch import generate_batch
from anki_cards_from_kindle_highlights.cli.helpers import version_callback
from anki_cards_from_kindle_highlights.cli.import_cmd import import_clippings
from anki_cards_from_kindle_highlights.cli.reset import reset_generations, set_unsynced
from anki_cards_from_kindle_highlights.cli.sync import sync_to_anki
from anki_cards_from_kindle_highlights.cli.view_book import view_book

app = typer.Typer(
    name="anki-cards-from-kindle-highlights",
    help="Generate Anki cards from Kindle highlights using LLMs.",
    no_args_is_help=True,
)

# Register commands
app.command()(generate)
app.command("import")(import_clippings)
app.command()(dump)
app.command("reset-generations")(reset_generations)
app.command("sync-to-anki")(sync_to_anki)
app.command("generate-batch")(generate_batch)
app.command("set-unsynced")(set_unsynced)
app.command("view-book")(view_book)


@app.callback()
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
    """Generate Anki cards from Kindle highlights using LLMs."""
    _ = version  # Unused, handled by callback
