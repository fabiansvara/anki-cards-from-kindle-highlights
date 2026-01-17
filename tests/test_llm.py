"""Tests for LLM integration with mocked OpenAI."""

import json
from datetime import datetime

import pytest

from anki_cards_from_kindle_highlights.clippings import ClippingType
from anki_cards_from_kindle_highlights.db import ClippingRecord
from anki_cards_from_kindle_highlights.llm import (
    _create_batch_request,
    _get_response_schema,
    create_batch_jsonl,
)


@pytest.fixture
def sample_record() -> ClippingRecord:
    """Create a sample ClippingRecord for testing."""
    return ClippingRecord(
        id=1,
        book_title="Test Book",
        author="Test Author",
        clipping_type=ClippingType.HIGHLIGHT,
        page=10,
        location_start=100,
        location_end=150,
        date_added=datetime(2024, 1, 1),
        content="This is a test highlight.",
        pattern=None,
        front=None,
        back=None,
        imported_at=datetime(2024, 1, 1),
        generated_at=None,
        synced_to_anki=False,
    )


class TestGetResponseSchema:
    """Tests for _get_response_schema function."""

    def test_schema_has_additional_properties_false(self) -> None:
        """Test that schema includes additionalProperties: false."""
        schema = _get_response_schema()

        assert schema["additionalProperties"] is False

    def test_schema_has_required_fields(self) -> None:
        """Test that schema has required fields."""
        schema = _get_response_schema()

        assert "properties" in schema
        assert "pattern" in schema["properties"]
        assert "front" in schema["properties"]
        assert "back" in schema["properties"]


class TestCreateBatchRequest:
    """Tests for _create_batch_request function."""

    def test_creates_valid_request(self, sample_record: ClippingRecord) -> None:
        """Test creating a valid batch request."""
        request = _create_batch_request(sample_record, "Test prompt", "gpt-4o")

        assert request is not None
        assert request["custom_id"] == "1"
        assert request["method"] == "POST"
        assert request["url"] == "/v1/chat/completions"
        assert "body" in request

    def test_returns_none_for_empty_content(
        self, sample_record: ClippingRecord
    ) -> None:
        """Test that None is returned for empty content."""
        sample_record.content = ""
        request = _create_batch_request(sample_record, "Test prompt", "gpt-4o")

        assert request is None

    def test_request_body_structure(self, sample_record: ClippingRecord) -> None:
        """Test the structure of the request body."""
        request = _create_batch_request(sample_record, "System prompt", "gpt-4o")

        assert request is not None
        body = request["body"]
        assert body["model"] == "gpt-4o"
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "System prompt"
        assert body["messages"][1]["role"] == "user"


class TestCreateBatchJsonl:
    """Tests for create_batch_jsonl function."""

    def test_creates_jsonl_content(self, sample_record: ClippingRecord) -> None:
        """Test creating JSONL content."""
        records = [sample_record]
        jsonl, ids = create_batch_jsonl(records, "Prompt", "gpt-4o")

        assert len(ids) == 1
        assert ids[0] == 1

        # Verify JSONL is valid
        lines = jsonl.strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["custom_id"] == "1"

    def test_skips_empty_content(self, sample_record: ClippingRecord) -> None:
        """Test that records with empty content are skipped."""
        sample_record.content = ""
        records = [sample_record]
        jsonl, ids = create_batch_jsonl(records, "Prompt", "gpt-4o")

        assert len(ids) == 0
        assert jsonl == ""

    def test_multiple_records(self, sample_record: ClippingRecord) -> None:
        """Test creating JSONL with multiple records."""
        record2 = ClippingRecord(
            id=2,
            book_title="Book 2",
            author="Author 2",
            clipping_type=ClippingType.HIGHLIGHT,
            page=20,
            location_start=200,
            location_end=250,
            date_added=datetime(2024, 1, 2),
            content="Second highlight.",
            pattern=None,
            front=None,
            back=None,
            imported_at=datetime(2024, 1, 2),
            generated_at=None,
            synced_to_anki=False,
        )

        records = [sample_record, record2]
        jsonl, ids = create_batch_jsonl(records, "Prompt", "gpt-4o")

        assert len(ids) == 2
        lines = jsonl.strip().split("\n")
        assert len(lines) == 2
