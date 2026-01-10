"""Command-line interface for anki-cards-from-kindle-highlights."""

import csv
import random
from pathlib import Path
from typing import Annotated

import questionary
import typer
from tqdm import tqdm

from anki_cards_from_kindle_highlights import __version__
from anki_cards_from_kindle_highlights.anki import (
    AnkiCard,
    AnkiConnectError,
    card_to_anki,
    get_cards,
    setup_anki,
)
from anki_cards_from_kindle_highlights.books import Book, books_from_calibre
from anki_cards_from_kindle_highlights.clippings import (
    ClippingType,
    parse_clippings_file,
)
from anki_cards_from_kindle_highlights.db import ClippingsDatabase, get_db_path
from anki_cards_from_kindle_highlights.llm import (
    get_batch_status,
    llm_highlight_to_card_parallel_async,
    retrieve_batch_results,
    upload_and_create_batch,
)

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
            title=f"{title} ({author or 'Unknown'}) - {count} clippings",
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
    records_to_process = [r for r in unprocessed if r.content is not None]
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


@app.command("import")
def import_clippings(
    clippings_file: Annotated[
        Path,
        typer.Option(
            "--clippings-file",
            "-c",
            help="Path to Kindle My Clippings.txt file",
            exists=True,
            readable=True,
        ),
    ],
) -> None:
    """Import clippings from a Kindle My Clippings.txt file into the database."""
    db_path = get_db_path()
    print(f"Database location: {db_path}")
    print(f"Reading clippings from: {clippings_file}")

    clippings = parse_clippings_file(clippings_file)
    print(f"Found {len(clippings)} total clippings")

    # Filter to only highlights (skip bookmarks and notes for now)
    highlights = [c for c in clippings if c.clipping_type == ClippingType.HIGHLIGHT]
    print(f"Found {len(highlights)} highlights (filtered out bookmarks/notes)")

    # Get unique books
    books = sorted({c.book_title for c in highlights})
    print(f"Books found: {len(books)}")
    for book in books:
        count = sum(1 for c in highlights if c.book_title == book)
        print(f"  - {book}: {count} highlights")

    db = ClippingsDatabase(db_path)
    inserted = 0
    duplicates = 0

    for clipping in highlights:
        result = db.insert_clipping(clipping)
        if result is not None:
            inserted += 1
        else:
            duplicates += 1

    db.close()

    print()
    print(f"Inserted {inserted} new clippings into database")
    if duplicates > 0:
        print(f"Skipped {duplicates} duplicates (already in database)")


@app.command()
def dump(
    output_file: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Path to output CSV file",
        ),
    ],
    only_generated: Annotated[
        bool,
        typer.Option(
            "--only-generated",
            help="Only export rows with LLM results (including SKIP)",
        ),
    ] = False,
) -> None:
    """Export the database to a CSV file."""
    db_path = get_db_path()
    print(f"Database location: {db_path}")

    db = ClippingsDatabase(db_path)

    if only_generated:
        records = db.get_generated_records()
        print(f"Exporting {len(records)} generated records")
    else:
        records = db.get_all_records()
        print(f"Exporting {len(records)} total records")

    db.close()

    if not records:
        print("No records to export.")
        return

    # Write to CSV
    fieldnames = [
        "id",
        "book_title",
        "author",
        "clipping_type",
        "page",
        "location_start",
        "location_end",
        "date_added",
        "content",
        "pattern",
        "front",
        "back",
        "imported_at",
        "generated_at",
        "synced_to_anki",
    ]

    with output_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            writer.writerow(
                {
                    "id": record.id,
                    "book_title": record.book_title,
                    "author": record.author,
                    "clipping_type": record.clipping_type.value,
                    "page": record.page,
                    "location_start": record.location_start,
                    "location_end": record.location_end,
                    "date_added": record.date_added.isoformat(),
                    "content": record.content,
                    "pattern": record.pattern,
                    "front": record.front,
                    "back": record.back,
                    "imported_at": record.imported_at.isoformat(),
                    "generated_at": record.generated_at.isoformat()
                    if record.generated_at
                    else None,
                    "synced_to_anki": record.synced_to_anki,
                }
            )

    print(f"Exported to: {output_file}")


@app.command("reset-generations")
def reset_generations() -> None:
    """Reset all LLM-generated fields to NULL and synced_to_anki to False."""
    db_path = get_db_path()
    print(f"Database location: {db_path}")

    db = ClippingsDatabase(db_path)

    # Confirm with user
    confirm = questionary.confirm(
        "This will reset all generated cards (pattern, front, back, generated_at) "
        "and set synced_to_anki to False. Continue?"
    ).ask()

    if not confirm:
        print("Aborted.")
        db.close()
        return

    affected = db.reset_all_generations()
    db.close()

    print(f"Reset {affected} records")


def _abbreviate(text: str | None, max_len: int = 50) -> str:
    """Abbreviate text to a maximum length with ellipsis."""
    if text is None:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


@app.command("sync-to-anki")
def sync_to_anki() -> None:
    """Sync all unsynced cards (with pattern set) to Anki."""
    db_path = get_db_path()
    print(f"Database location: {db_path}")

    db = ClippingsDatabase(db_path)

    try:
        # Setup Anki once (creates deck/models if needed)
        print("Setting up Anki...")
        setup_anki()
        print()
    except AnkiConnectError as e:
        print(f"Error: {e}")
        db.close()
        raise typer.Exit(1) from e

    # Reconcile DB and Anki state
    print("Reconciling database with Anki...")
    _reconcile_db_with_anki(db)
    print()

    # Now get unsynced cards (after reconciliation)
    unsynced = db.get_unsynced_cards()

    if not unsynced:
        print("No unsynced cards found.")
        db.close()
        return

    print(f"Found {len(unsynced)} cards to sync\n")

    synced = 0
    errors = 0

    for record in tqdm(unsynced, desc="Syncing to Anki"):
        # Show current card info below progress bar
        book_abbrev = _abbreviate(record.book_title, 30)
        clipping_abbrev = _abbreviate(record.content, 40)
        tqdm.write(f"  📖 {book_abbrev} | {clipping_abbrev}")

        if record.front is None or record.back is None:
            tqdm.write("    ⚠️  Skipping: missing front or back content")
            errors += 1
            continue

        # Create AnkiCard from record
        anki_card = AnkiCard(
            book_title=record.book_title,
            author=record.author or "",
            original_clipping=record.content or "",
            front=record.front,
            back=record.back,
            pattern=record.pattern or "",
            db_id=record.id,
        )

        try:
            card_to_anki(anki_card)
            db.mark_synced(record.id)
            synced += 1
        except AnkiConnectError as e:
            tqdm.write(f"    ❌ Error: {e}")
            errors += 1

    db.close()

    print()
    print(f"✅ Synced {synced} cards to Anki")
    if errors > 0:
        print(f"⚠️  Errors: {errors}")


def _reconcile_db_with_anki(db: ClippingsDatabase) -> None:
    """Reconcile database sync status with actual Anki cards.

    - Cards marked synced in DB but missing in Anki: reset their generation
    - Cards in Anki but not marked synced in DB: warn about inconsistency
    """
    # Get cards currently in Anki
    anki_cards = get_cards()

    anki_db_ids = {card.db_id for card in anki_cards}

    # Get records marked as synced in DB
    synced_records = db.get_synced_records()
    db_synced_ids = {record.id for record in synced_records}

    # Find IDs marked synced in DB but NOT in Anki (user deleted from Anki for re-generation)
    missing_from_anki = db_synced_ids - anki_db_ids
    if missing_from_anki:
        print(
            f"  🔄 {len(missing_from_anki)} cards deleted from Anki, resetting for re-generation."
        )
        print(f"     DB IDs: {sorted(missing_from_anki)}")
        db.reset_generations_for_ids(list(missing_from_anki))

    # Find IDs in Anki but NOT marked synced in DB (inconsistency)
    not_synced_in_db = anki_db_ids - db_synced_ids
    if not_synced_in_db:
        print(
            f"  ⚠️  Warning: {len(not_synced_in_db)} cards exist in Anki but not marked synced in DB."
        )
        print(f"     DB IDs: {sorted(not_synced_in_db)}")

    if not missing_from_anki and not not_synced_in_db:
        print("  ✅ Database and Anki are in sync.")


@app.command("generate-batch")
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
            title=f"{title} ({author or 'Unknown'}) - {count} clippings",
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
    records_to_process = [r for r in unprocessed if r.content is not None]

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


@app.command("set-unsynced")
def set_unsynced() -> None:
    """Reset synced_to_anki to False for all records."""
    db_path = get_db_path()
    print(f"Database location: {db_path}")

    db = ClippingsDatabase(db_path)

    # Confirm with user
    confirm = questionary.confirm(
        "This will mark all cards as unsynced (synced_to_anki = False). Continue?"
    ).ask()

    if not confirm:
        print("Aborted.")
        db.close()
        return

    affected = db.reset_all_synced()
    db.close()

    print(f"✅ Reset {affected} records to unsynced")


@app.command("get-books")
def get_books(
    calibre_dir: Annotated[
        Path,
        typer.Option(
            "--calibre-dir",
            help="Path to Calibre library directory",
            exists=True,
            readable=True,
        ),
    ],
) -> None:
    """Browse books from a Calibre library and view their text content."""
    try:
        all_books = books_from_calibre(calibre_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise typer.Exit(1) from e

    # Filter to only books with epub files
    books_with_epub = {k: v for k, v in all_books.items() if v.epub_path is not None}

    if not books_with_epub:
        print("No books with EPUB files found.")
        return

    print(f"Found {len(books_with_epub)} books with EPUB files\n")

    # Build choices for questionary with abbreviated display
    def format_book_choice(book: "Book") -> str:
        author = _abbreviate(book.author, 25)
        title = _abbreviate(book.title, 50)
        return f"{author} — {title}"

    choices = [
        questionary.Choice(
            title=format_book_choice(book),
            value=book,
        )
        for book in books_with_epub.values()
    ]

    # Sort choices by title
    choices.sort(key=lambda c: c.title)

    selected: Book | None = questionary.select(
        "Select a book to view:",
        choices=choices,
    ).ask()

    if selected is None:
        print("No book selected.")
        return

    print(f"\nLoading text from: {selected.title}...")
    text = selected.text

    if text is None:
        print("Error: Could not extract text from EPUB.")
        raise typer.Exit(1)

    # Write to temp file with UTF-8 BOM and open with default text editor
    # This avoids encoding issues with PowerShell/cmd pagers on Windows
    import os
    import tempfile

    # Create a safe filename from the book title
    safe_title = "".join(
        c if c.isalnum() or c in " -_" else "_" for c in selected.title
    )
    safe_title = safe_title[:50]  # Limit length

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=f"_{safe_title}.txt",
        delete=False,
    ) as f:
        f.write(text)
        temp_path = f.name

    print(f"Opening: {temp_path}")
    os.startfile(temp_path)


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


if __name__ == "__main__":
    app()
