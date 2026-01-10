"""Generate batch command - create Anki cards using OpenAI Batch API."""

import random
from typing import Annotated

import questionary
import typer

from anki_cards_from_kindle_highlights.cli.helpers import get_prompt
from anki_cards_from_kindle_highlights.db import ClippingsDatabase, get_db_path
from anki_cards_from_kindle_highlights.llm import (
    get_batch_status,
    retrieve_batch_results,
    upload_and_create_batch,
)


def _create_new_batch(
    db: ClippingsDatabase,
    api_key: str,
    model: str,
    max_generations: int | None,
) -> None:
    """Create and upload a new batch job."""
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

    # Filter out records with no content
    records_to_process = [r for r in unprocessed if r.content]

    if not records_to_process:
        print("No valid clippings to process.")
        db.close()
        return

    prompt = get_prompt()

    print("Uploading batch to OpenAI...")
    batch_id, included_ids = upload_and_create_batch(
        api_key=api_key,
        records=records_to_process,
        prompt=prompt,
        model=model,
    )

    db.close()

    print()
    print("✅ Batch created successfully!")
    print(f"   Batch ID: {batch_id}")
    print(f"   Records in batch: {len(included_ids)}")
    print()
    print("OpenAI will process this batch asynchronously (up to 24 hours).")
    print("To check status and load results, run:")
    print()
    print(
        f"  anki-cards-from-kindle-highlights generate-batch --load-batch-id {batch_id}"
    )
    print()


def _load_batch_results(
    db: ClippingsDatabase,
    api_key: str,
    batch_id: str,
) -> None:
    """Load results from an existing batch job."""
    print(f"Checking batch status: {batch_id}")

    status = get_batch_status(api_key, batch_id)

    print(f"  Status: {status.status}")
    print(
        f"  Progress: {status.completed}/{status.total} completed, {status.failed} failed"
    )

    if not status.is_complete:
        print()
        print("⏳ Batch is still processing. Please wait and try again later.")
        print()
        print(
            f"  anki-cards-from-kindle-highlights generate-batch --load-batch-id {batch_id}"
        )
        db.close()
        return

    if status.status != "completed":
        print()
        print(f"❌ Batch ended with status: {status.status}")
        db.close()
        raise typer.Exit(1)

    print()
    print("Downloading results...")

    results = retrieve_batch_results(api_key, batch_id)

    # Update database with results
    generated = 0
    skipped = 0
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
    print(f"✅ Generated {generated} cards")
    print(f"⏭️  Skipped {skipped} clippings (SKIP or no content)")
    if errors > 0:
        print(f"❌ Errors: {errors}")


def generate_batch(
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
    load_batch_id: Annotated[
        str | None,
        typer.Option(
            "--load-batch-id",
            help="Load results from a previously created batch",
        ),
    ] = None,
) -> None:
    """Generate Anki cards using OpenAI's Batch API (cheaper, async processing)."""
    if openai_api_key is None:
        print(
            "Error: OpenAI API key is required. Set OPENAI_API_KEY or use --openai-api-key"
        )
        raise typer.Exit(1)

    db_path = get_db_path()
    print(f"Database location: {db_path}")

    db = ClippingsDatabase(db_path)

    # Mode 2: Load results from existing batch
    if load_batch_id is not None:
        _load_batch_results(db, openai_api_key, load_batch_id)
        return

    # Mode 1: Create new batch
    _create_new_batch(db, openai_api_key, model, max_generations)
