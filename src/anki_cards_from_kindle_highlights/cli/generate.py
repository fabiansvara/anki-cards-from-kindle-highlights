"""Generate command - create Anki cards using LLM."""

import random
from typing import Annotated

import questionary
import typer

from anki_cards_from_kindle_highlights.cli.helpers import get_prompt
from anki_cards_from_kindle_highlights.db import ClippingsDatabase, get_db_path
from anki_cards_from_kindle_highlights.llm import llm_highlight_to_card_parallel_async


def generate(
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
    max_generations: Annotated[
        int | None,
        typer.Option(
            "--max-generations",
            help="Limit generation to at most this many clippings (for testing)",
        ),
    ] = None,
    parallel_requests: Annotated[
        int,
        typer.Option(
            "--parallel-requests",
            "-p",
            help="Maximum number of parallel LLM requests",
        ),
    ] = 10,
) -> None:
    """Generate Anki cards for unprocessed clippings in the database."""
    if openai_api_key is None:
        print(
            "Error: OpenAI API key is required. Set OPENAI_API_KEY or use --openai-api-key"
        )
        raise typer.Exit(1)

    db_path = get_db_path()
    print(f"Database location: {db_path}")

    db = ClippingsDatabase(db_path)

    # Get books with unprocessed clippings
    books = db.get_books_with_unprocessed()

    if not books:
        print("No unprocessed clippings found.")
        db.close()
        return

    print(f"Found {len(books)} books with unprocessed clippings\n")

    # Build choices for questionary
    choices = [
        questionary.Choice(
            title=f"{title} ({author}) - {count} clippings",
            value=(title, author),
        )
        for title, author, count in books
    ]

    # Let user select books
    selected = questionary.checkbox(
        "Select books to process:",
        choices=choices,
    ).ask()

    if not selected:
        print("No books selected. Exiting.")
        db.close()
        return

    print(f"\nSelected {len(selected)} books")

    # Get unprocessed clippings for selected books
    unprocessed = db.get_unprocessed_clippings(books=selected)

    if not unprocessed:
        print("No unprocessed clippings found for selected books.")
        db.close()
        return

    # Sample if max_generations is set
    if max_generations is not None and max_generations < len(unprocessed):
        random.seed(42)  # Deterministic sampling
        unprocessed = random.sample(unprocessed, max_generations)
        print(
            f"Sampled {len(unprocessed)} clippings (--max-generations {max_generations})\n"
        )
    else:
        print(f"Processing {len(unprocessed)} clippings\n")

    prompt = get_prompt()

    # Filter out records with no content
    records_to_process = [r for r in unprocessed if r.content]
    no_content_count = len(unprocessed) - len(records_to_process)

    print(f"Using {parallel_requests} parallel requests\n")

    # Process in parallel
    results = llm_highlight_to_card_parallel_async(
        api_key=openai_api_key,
        prompt=prompt,
        records=records_to_process,
        model=model,
        max_parallel=parallel_requests,
    )

    # Update database with results
    generated = 0
    skipped = no_content_count
    errors = 0

    for result in results:
        if result.error is not None:
            errors += 1
            continue

        if result.card is None:
            skipped += 1
            continue

        # Update the database with the LLM response (including SKIP)
        db.update_card_data(
            record_id=result.record_id,
            pattern=result.card.pattern,
            front=result.card.front,
            back=result.card.back,
        )

        if result.card.pattern == "SKIP":
            skipped += 1
        else:
            generated += 1

    db.close()

    print()
    print(f"Generated {generated} cards")
    print(f"Skipped {skipped} clippings (SKIP or no content)")
    if errors > 0:
        print(f"Errors: {errors}")
