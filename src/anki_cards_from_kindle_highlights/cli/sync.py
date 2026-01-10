"""Sync command - sync cards to Anki."""

import typer
from tqdm import tqdm

from anki_cards_from_kindle_highlights.anki import (
    AnkiCard,
    AnkiConnectError,
    card_to_anki,
    get_cards,
    setup_anki,
)
from anki_cards_from_kindle_highlights.cli.helpers import abbreviate
from anki_cards_from_kindle_highlights.db import ClippingsDatabase, get_db_path


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
        book_abbrev = abbreviate(record.book_title, 30)
        clipping_abbrev = abbreviate(record.content, 40)
        tqdm.write(f"  📖 {book_abbrev} | {clipping_abbrev}")

        if record.front is None or record.back is None:
            tqdm.write("    ⚠️  Skipping: missing front or back content")
            errors += 1
            continue

        # Create AnkiCard from record
        anki_card = AnkiCard(
            book_title=record.book_title,
            author=record.author,
            original_clipping=record.content,
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
