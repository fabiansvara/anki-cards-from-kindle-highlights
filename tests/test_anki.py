"""Tests for Anki integration with mocked AnkiConnect.

Focus on:
- Error handling (connection failures, API errors)
- Logic/branching (model selection based on pattern)
- Data transformation (request structure, field formatting, tag generation)
- Response parsing (extracting data from Anki's response format)
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from anki_cards_from_kindle_highlights.anki import (
    ANKI_FIELDS,
    AnkiCard,
    AnkiConnectError,
    card_to_anki,
    get_cards,
    invoke,
)


class TestInvokeErrorHandling:
    """Tests for error handling in the invoke function."""

    def test_connection_error_raises_helpful_message(self) -> None:
        """Test that connection errors produce a helpful error message."""
        import requests

        with patch("anki_cards_from_kindle_highlights.anki.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError()

            with pytest.raises(AnkiConnectError) as exc_info:
                invoke("testAction")

            # Verify the error message is helpful for users
            error_msg = str(exc_info.value)
            assert "Cannot connect" in error_msg
            assert "AnkiConnect" in error_msg
            assert "ankiweb.net" in error_msg  # Should include install link

    def test_api_error_propagates_message(self, mock_anki_connect: MagicMock) -> None:
        """Test that API errors from Anki are properly propagated."""
        mock_anki_connect.return_value.json.return_value = {
            "result": None,
            "error": "deck was not found",
        }

        with pytest.raises(AnkiConnectError, match="deck was not found"):
            invoke("addNote", note={})

    def test_request_format_is_correct(self, mock_anki_connect: MagicMock) -> None:
        """Test that we send the correct request format to AnkiConnect."""
        mock_anki_connect.return_value.json.return_value = {
            "result": None,
            "error": None,
        }

        invoke("testAction", someParam="someValue", anotherParam=123)

        # Verify the request structure matches AnkiConnect's expected format
        call_kwargs = mock_anki_connect.call_args[1]
        request_body = call_kwargs["json"]

        assert request_body["action"] == "testAction"
        assert request_body["version"] == 6  # AnkiConnect API version
        assert request_body["params"]["someParam"] == "someValue"
        assert request_body["params"]["anotherParam"] == 123


class TestCardToAnkiLogic:
    """Tests for card_to_anki's logic and data transformation."""

    def _get_sent_note(self, mock_anki_connect: MagicMock) -> dict[str, Any]:
        """Helper to extract the note dict sent to Anki."""
        call_kwargs = mock_anki_connect.call_args[1]
        note: dict[str, Any] = call_kwargs["json"]["params"]["note"]
        return note

    def test_definition_pattern_uses_cloze_model(
        self, mock_anki_connect: MagicMock
    ) -> None:
        """Test that DEFINITION pattern selects the cloze model."""
        mock_anki_connect.return_value.json.return_value = {
            "result": 1,
            "error": None,
        }

        card = AnkiCard(
            book_title="Book",
            author="Author",
            original_clipping="Text",
            front="{{c1::Term}} is defined as X",
            back="",
            pattern="DEFINITION",
            db_id=1,
        )
        card_to_anki(card)

        note = self._get_sent_note(mock_anki_connect)
        assert "Cloze" in note["modelName"]

    def test_non_definition_patterns_use_basic_model(
        self, mock_anki_connect: MagicMock
    ) -> None:
        """Test that non-DEFINITION patterns select the basic model."""
        mock_anki_connect.return_value.json.return_value = {
            "result": 1,
            "error": None,
        }

        for pattern in ["MENTAL_MODEL", "DISTINCTION", "FRAMEWORK", "TACTIC"]:
            card = AnkiCard(
                book_title="Book",
                author="Author",
                original_clipping="Text",
                front="Question",
                back="Answer",
                pattern=pattern,
                db_id=1,
            )
            card_to_anki(card)

            note = self._get_sent_note(mock_anki_connect)
            assert "Basic" in note["modelName"], f"Pattern {pattern} should use Basic"

    def test_all_fields_are_sent(self, mock_anki_connect: MagicMock) -> None:
        """Test that all required fields are included in the note."""
        mock_anki_connect.return_value.json.return_value = {
            "result": 1,
            "error": None,
        }

        card = AnkiCard(
            book_title="My Book Title",
            author="John Author",
            original_clipping="The original text",
            front="The question",
            back="The answer",
            pattern="MENTAL_MODEL",
            db_id=42,
        )
        card_to_anki(card)

        note = self._get_sent_note(mock_anki_connect)
        fields = note["fields"]

        # Verify all fields are present and correctly populated
        assert fields["book_title"] == "My Book Title"
        assert fields["author"] == "John Author"
        assert fields["original_clipping"] == "The original text"
        assert fields["front"] == "The question"
        assert fields["back"] == "The answer"
        assert fields["pattern"] == "MENTAL_MODEL"
        assert fields["db_id"] == "42"  # Should be string for Anki

    def test_tags_are_generated_correctly(self, mock_anki_connect: MagicMock) -> None:
        """Test that tags are generated from book title and pattern."""
        mock_anki_connect.return_value.json.return_value = {
            "result": 1,
            "error": None,
        }

        card = AnkiCard(
            book_title="The Great Book",
            author="Author",
            original_clipping="Text",
            front="Q",
            back="A",
            pattern="FRAMEWORK",
            db_id=1,
        )
        card_to_anki(card)

        note = self._get_sent_note(mock_anki_connect)
        tags = note["tags"]

        # Verify tag format (spaces replaced with underscores)
        assert "book::The_Great_Book" in tags
        assert "pattern::FRAMEWORK" in tags

    def test_duplicate_handling_options(self, mock_anki_connect: MagicMock) -> None:
        """Test that duplicate handling is configured correctly."""
        mock_anki_connect.return_value.json.return_value = {
            "result": 1,
            "error": None,
        }

        card = AnkiCard(
            book_title="Book",
            author="Author",
            original_clipping="Text",
            front="Q",
            back="A",
            pattern="TACTIC",
            db_id=1,
        )
        card_to_anki(card)

        note = self._get_sent_note(mock_anki_connect)
        options = note["options"]

        assert options["allowDuplicate"] is False
        assert options["duplicateScope"] == "deck"


class TestGetCardsResponseParsing:
    """Tests for get_cards' parsing of Anki's response format."""

    def test_parses_anki_field_structure(self, mock_anki_connect: MagicMock) -> None:
        """Test parsing of Anki's nested field structure."""
        # Anki returns fields in a specific nested format
        mock_anki_connect.return_value.json.side_effect = [
            {"result": [100], "error": None},  # findNotes
            {
                "result": [
                    {
                        "fields": {
                            "book_title": {"value": "Parsed Book"},
                            "author": {"value": "Parsed Author"},
                            "original_clipping": {"value": "Clipping"},
                            "front": {"value": "Front"},
                            "back": {"value": "Back"},
                            "pattern": {"value": "METAPHOR"},
                            "db_id": {"value": "999"},
                        }
                    }
                ],
                "error": None,
            },
        ]

        cards = get_cards()

        assert len(cards) == 1
        card = cards[0]
        assert card.book_title == "Parsed Book"
        assert card.author == "Parsed Author"
        assert card.pattern == "METAPHOR"
        assert card.db_id == 999  # Should be converted to int

    def test_handles_missing_fields_gracefully(
        self, mock_anki_connect: MagicMock
    ) -> None:
        """Test that missing fields don't crash parsing."""
        mock_anki_connect.return_value.json.side_effect = [
            {"result": [1], "error": None},
            {
                "result": [
                    {
                        "fields": {
                            # Only some fields present
                            "book_title": {"value": "Book"},
                            "db_id": {"value": "1"},
                        }
                    }
                ],
                "error": None,
            },
        ]

        # Should not raise, should use defaults
        cards = get_cards()
        assert len(cards) == 1
        assert cards[0].book_title == "Book"
        assert cards[0].author == ""  # Default for missing field

    def test_empty_deck_returns_empty_list(self, mock_anki_connect: MagicMock) -> None:
        """Test that an empty deck returns an empty list without errors."""
        mock_anki_connect.return_value.json.return_value = {
            "result": [],
            "error": None,
        }

        cards = get_cards()
        assert cards == []
        # Should only call findNotes, not notesInfo
        assert mock_anki_connect.call_count == 1


class TestAnkiFieldsConfiguration:
    """Tests for the ANKI_FIELDS configuration."""

    def test_db_id_is_first_field(self) -> None:
        """Test that db_id is the first field (Anki uses first field for dedup)."""
        assert ANKI_FIELDS[0] == "db_id"

    def test_all_required_fields_present(self) -> None:
        """Test that all required fields are in ANKI_FIELDS."""
        required = ["db_id", "book_title", "author", "front", "back", "pattern"]
        for field in required:
            assert field in ANKI_FIELDS, f"Missing required field: {field}"
