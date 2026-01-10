"""Tests for LLM integration with mocked OpenAI."""

import json
from datetime import datetime

import pytest

from anki_cards_from_kindle_highlights.clippings import ClippingType
from anki_cards_from_kindle_highlights.db import ClippingRecord
from anki_cards_from_kindle_highlights.llm import (
    AnkiCardLLMResponse,
    BatchStatus,
    GenerationResult,
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


class TestAnkiCardLLMResponse:
    """Tests for the AnkiCardLLMResponse model."""

    def test_valid_response(self) -> None:
        """Test creating a valid response."""
        response = AnkiCardLLMResponse(
            pattern="MENTAL_MODEL",
            front="What is the key insight?",
            back="The answer.",
        )

        assert response.pattern == "MENTAL_MODEL"
        assert response.front == "What is the key insight?"
        assert response.back == "The answer."

    def test_skip_pattern(self) -> None:
        """Test SKIP pattern with None front/back."""
        response = AnkiCardLLMResponse(
            pattern="SKIP",
            front=None,
            back=None,
        )

        assert response.pattern == "SKIP"
        assert response.front is None
        assert response.back is None

    def test_all_valid_patterns(self) -> None:
        """Test all valid pattern values."""
        assert (
            AnkiCardLLMResponse(pattern="DISTINCTION", front="F", back="B").pattern
            == "DISTINCTION"
        )
        assert (
            AnkiCardLLMResponse(pattern="MENTAL_MODEL", front="F", back="B").pattern
            == "MENTAL_MODEL"
        )
        assert (
            AnkiCardLLMResponse(pattern="METAPHOR", front="F", back="B").pattern
            == "METAPHOR"
        )
        assert (
            AnkiCardLLMResponse(pattern="FRAMEWORK", front="F", back="B").pattern
            == "FRAMEWORK"
        )
        assert (
            AnkiCardLLMResponse(pattern="TACTIC", front="F", back="B").pattern
            == "TACTIC"
        )
        assert (
            AnkiCardLLMResponse(pattern="CASE_STUDY", front="F", back="B").pattern
            == "CASE_STUDY"
        )
        assert (
            AnkiCardLLMResponse(pattern="DEFINITION", front="F", back="B").pattern
            == "DEFINITION"
        )
        assert (
            AnkiCardLLMResponse(pattern="SKIP", front="F", back="B").pattern == "SKIP"
        )


class TestGenerationResult:
    """Tests for the GenerationResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful result."""
        card = AnkiCardLLMResponse(pattern="MENTAL_MODEL", front="F", back="B")
        result = GenerationResult(record_id=1, card=card)

        assert result.record_id == 1
        assert result.card is not None
        assert result.error is None

    def test_error_result(self) -> None:
        """Test creating an error result."""
        result = GenerationResult(record_id=1, card=None, error="API Error")

        assert result.record_id == 1
        assert result.card is None
        assert result.error == "API Error"


class TestBatchStatus:
    """Tests for the BatchStatus dataclass."""

    def test_in_progress_status(self) -> None:
        """Test in-progress batch status."""
        status = BatchStatus(
            batch_id="batch_123",
            status="in_progress",
            total=10,
            completed=5,
            failed=0,
            is_complete=False,
        )

        assert status.is_complete is False
        assert status.completed == 5

    def test_completed_status(self) -> None:
        """Test completed batch status."""
        status = BatchStatus(
            batch_id="batch_123",
            status="completed",
            total=10,
            completed=10,
            failed=0,
            is_complete=True,
            output_file_id="file_123",
        )

        assert status.is_complete is True
        assert status.output_file_id == "file_123"


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
