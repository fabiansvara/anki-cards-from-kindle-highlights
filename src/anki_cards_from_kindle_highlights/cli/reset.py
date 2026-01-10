"""Reset commands - reset generations and sync status."""

import questionary

from anki_cards_from_kindle_highlights.db import ClippingsDatabase, get_db_path


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
