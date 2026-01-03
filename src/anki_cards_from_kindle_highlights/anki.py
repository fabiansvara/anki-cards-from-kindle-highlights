"""Anki integration via AnkiConnect."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

ANKI_CONNECT_URL = "http://127.0.0.1:8765"
TEMPLATES_DIR = Path(__file__).parent / "anki-templates"

# Field names for Anki note types.
# NOTE: db_id is first because Anki uses the first field for duplicate detection.
ANKI_FIELDS = [
    "db_id",
    "book_title",
    "author",
    "original_clipping",
    "front",
    "back",
    "pattern",
]


@dataclass
class AnkiCard:
    """Represents a card to be sent to Anki."""

    book_title: str
    author: str
    original_clipping: str
    front: str
    back: str
    pattern: str
    db_id: int


class AnkiConnectError(Exception):
    """Error communicating with AnkiConnect."""


def invoke(action: str, **params: Any) -> Any:
    """Invoke an AnkiConnect action."""
    try:
        response = requests.post(
            ANKI_CONNECT_URL,
            json={"action": action, "version": 6, "params": params},
            timeout=30,
        )
    except requests.exceptions.ConnectionError as e:
        raise AnkiConnectError(
            f"Cannot connect to AnkiConnect at {ANKI_CONNECT_URL}. "
            "Make sure Anki is running and AnkiConnect plugin is installed and enabled. "
            "You can install it from: https://ankiweb.net/shared/info/2055492159"
        ) from e

    response.raise_for_status()
    result = response.json()

    if result.get("error"):
        raise AnkiConnectError(result["error"])

    return result.get("result")


def _load_template(filename: str) -> str:
    """Load a template file from the anki-templates directory."""
    template_path = TEMPLATES_DIR / filename
    return template_path.read_text(encoding="utf-8")


def setup_anki(
    deck_name: str = "Kindle Highlights",
    basic_model_name: str = "Kindle_Smart_Basic",
    cloze_model_name: str = "Kindle_Smart_Cloze",
) -> None:
    """Set up Anki deck and note types.

    Creates the deck and note types if they don't exist.

    Args:
        deck_name: Name of the deck to create.
        basic_model_name: Name of the basic (Q&A) model.
        cloze_model_name: Name of the cloze model.
    """
    # 1. Ensure the Deck Exists
    invoke("createDeck", deck=deck_name)
    print(f"Deck '{deck_name}' ready.")

    # 2. Get existing models
    existing_models = invoke("modelNames")

    # 3. Create Basic Model if needed
    if basic_model_name not in existing_models:
        print(f"Creating model: {basic_model_name}...")
        invoke(
            "createModel",
            modelName=basic_model_name,
            inOrderFields=ANKI_FIELDS,
            css=_load_template("basic_css.css"),
            cardTemplates=[
                {
                    "Name": "Card 1",
                    "Front": _load_template("basic_front.html"),
                    "Back": _load_template("basic_back.html"),
                }
            ],
        )
        print(f"Model '{basic_model_name}' created.")
    else:
        print(f"Model '{basic_model_name}' already exists.")

    # 4. Create Cloze Model if needed
    if cloze_model_name not in existing_models:
        print(f"Creating model: {cloze_model_name}...")
        invoke(
            "createModel",
            modelName=cloze_model_name,
            inOrderFields=ANKI_FIELDS,
            css=_load_template("cloze_css.css"),
            isCloze=True,
            cardTemplates=[
                {
                    "Name": "Cloze 1",
                    "Front": _load_template("cloze_front.html"),
                    "Back": _load_template("cloze_back.html"),
                }
            ],
        )
        print(f"Model '{cloze_model_name}' created.")
    else:
        print(f"Model '{cloze_model_name}' already exists.")

    print("Anki setup complete.")


def card_to_anki(
    card: AnkiCard,
    deck_name: str = "Kindle Highlights",
    basic_model_name: str = "Kindle_Smart_Basic",
    cloze_model_name: str = "Kindle_Smart_Cloze",
) -> Any:
    """Send an AnkiCard to Anki via AnkiConnect.

    Uses the cloze model for DEFINITION pattern cards, basic model for all others.

    Args:
        card: The card to add.
        deck_name: Name of the deck to add the card to.
        basic_model_name: Name of the basic note type.
        cloze_model_name: Name of the cloze note type.

    Returns:
        The note ID of the created card.
    """
    # Pick model based on pattern
    model_name = cloze_model_name if card.pattern == "DEFINITION" else basic_model_name

    note = {
        "deckName": deck_name,
        "modelName": model_name,
        "fields": {
            "book_title": card.book_title,
            "author": card.author,
            "original_clipping": card.original_clipping,
            "front": card.front,
            "back": card.back,
            "pattern": card.pattern,
            "db_id": str(card.db_id),
        },
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
        },
        "tags": [
            f"book::{card.book_title.replace(' ', '_')}",
            f"pattern::{card.pattern}",
        ],
    }

    note_id = invoke("addNote", note=note)
    return note_id


def get_cards(deck_name: str = "Kindle Highlights") -> list[AnkiCard]:
    """Get all cards from the Anki deck.

    Args:
        deck_name: Name of the deck to query.

    Returns:
        List of AnkiCard objects from the deck.
    """
    # Find all note IDs in the deck
    note_ids = invoke("findNotes", query=f'deck:"{deck_name}"')

    if not note_ids:
        return []

    # Get note info for all notes
    notes_info = invoke("notesInfo", notes=note_ids)

    cards: list[AnkiCard] = []
    for note in notes_info:
        fields = note.get("fields", {})
        card = AnkiCard(
            book_title=fields.get("book_title", {}).get("value", ""),
            author=fields.get("author", {}).get("value", ""),
            original_clipping=fields.get("original_clipping", {}).get("value", ""),
            front=fields.get("front", {}).get("value", ""),
            back=fields.get("back", {}).get("value", ""),
            pattern=fields.get("pattern", {}).get("value", ""),
            db_id=int(fields.get("db_id", {}).get("value", "0")),
        )
        cards.append(card)

    return cards
