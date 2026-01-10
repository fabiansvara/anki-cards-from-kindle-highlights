"""Integration tests for CLI commands with ephemeral database and mocked APIs."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from anki_cards_from_kindle_highlights.cli import app
from anki_cards_from_kindle_highlights.clippings import Clipping, ClippingType
from anki_cards_from_kindle_highlights.db import DB_PATH_ENV_VAR, ClippingsDatabase

runner = CliRunner()


@pytest.fixture
def test_db_path(temp_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up a test database path via environment variable.

    This is much cleaner than patching get_db_path in every module.
    """
    monkeypatch.setenv(DB_PATH_ENV_VAR, str(temp_db_path))
    return temp_db_path


class TestImportCommand:
    """Integration tests for the import command."""

    def test_import_clippings_file(
        self, test_db_path: Path, sample_clippings_file: Path
    ) -> None:
        """Test importing clippings from a file."""
        result = runner.invoke(
            app, ["import", "--clippings-file", str(sample_clippings_file)]
        )

        assert result.exit_code == 0
        assert "Inserted" in result.stdout

        # Verify database has records
        db = ClippingsDatabase(test_db_path)
        records = db.get_all_records()
        db.close()

        assert len(records) >= 1

    def test_import_nonexistent_file(self, test_db_path: Path) -> None:
        """Test importing from a nonexistent file."""
        _ = test_db_path  # Fixture needed for env var side effect
        result = runner.invoke(
            app, ["import", "--clippings-file", "/nonexistent/path.txt"]
        )

        # Should fail with error (typer validates file exists)
        assert result.exit_code != 0


class TestDumpCommand:
    """Integration tests for the dump command."""

    def test_dump_empty_database(self, test_db_path: Path, tmp_path: Path) -> None:
        """Test dumping an empty database."""
        # Create empty database
        db = ClippingsDatabase(test_db_path)
        db.close()

        output_file = tmp_path / "output.csv"
        result = runner.invoke(app, ["dump", "--output", str(output_file)])

        assert result.exit_code == 0
        assert "No records" in result.stdout or "0" in result.stdout

    def test_dump_with_records(self, test_db_path: Path, tmp_path: Path) -> None:
        """Test dumping database with records."""
        # Create database with a record
        db = ClippingsDatabase(test_db_path)
        clipping = Clipping(
            book_title="Test Book",
            author="Test Author",
            clipping_type=ClippingType.HIGHLIGHT,
            page=1,
            location_start=10,
            location_end=20,
            date_added=datetime.now(),
            content="Test content",
        )
        db.insert_clipping(clipping)
        db.close()

        output_file = tmp_path / "output.csv"
        result = runner.invoke(app, ["dump", "--output", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()


class TestGenerateCommand:
    """Integration tests for the generate command with mocked OpenAI."""

    def test_generate_requires_api_key(self, test_db_path: Path) -> None:
        """Test that generate requires an API key."""
        _ = test_db_path  # Fixture needed for env var side effect
        # Ensure no API key is set
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(app, ["generate"])

        assert result.exit_code != 0

    def test_generate_no_unprocessed(self, test_db_path: Path) -> None:
        """Test generate with no unprocessed clippings."""
        # Create empty database
        db = ClippingsDatabase(test_db_path)
        db.close()

        result = runner.invoke(app, ["generate", "--openai-api-key", "test-key"])

        assert result.exit_code == 0
        assert "No unprocessed" in result.stdout


class TestSyncCommand:
    """Integration tests for sync-to-anki command with mocked Anki."""

    def test_sync_no_unsynced(
        self, test_db_path: Path, mock_anki_connect: MagicMock
    ) -> None:
        """Test sync with no unsynced cards."""
        # Setup mock responses - model names must match so setup doesn't create them
        mock_anki_connect.return_value.json.side_effect = [
            {"result": None, "error": None},  # createDeck
            {
                "result": ["Kindle_Smart_Basic", "Kindle_Smart_Cloze"],
                "error": None,
            },  # modelNames
            {"result": [], "error": None},  # findNotes (for reconciliation)
        ]

        # Create empty database
        db = ClippingsDatabase(test_db_path)
        db.close()

        result = runner.invoke(app, ["sync-to-anki"])

        assert result.exit_code == 0
        assert "No unsynced" in result.stdout

    def test_sync_with_cards(
        self, test_db_path: Path, mock_anki_connect: MagicMock
    ) -> None:
        """Test sync with cards to sync."""
        # Setup mock responses for successful sync
        mock_anki_connect.return_value.json.side_effect = [
            {"result": None, "error": None},  # createDeck
            {"result": ["Kindle_Smart_Basic", "Kindle_Smart_Cloze"], "error": None},
            {"result": [], "error": None},  # findNotes
            {"result": 12345, "error": None},  # addNote
        ]

        # Create database with a card to sync
        db = ClippingsDatabase(test_db_path)
        clipping = Clipping(
            book_title="Test Book",
            author="Test Author",
            clipping_type=ClippingType.HIGHLIGHT,
            page=1,
            location_start=10,
            location_end=20,
            date_added=datetime.now(),
            content="Test content",
        )
        row_id = db.insert_clipping(clipping)
        if row_id:
            db.update_card_data(row_id, "MENTAL_MODEL", "Front", "Back")
        db.close()

        result = runner.invoke(app, ["sync-to-anki"])

        assert result.exit_code == 0


class TestGenerateBatchCommand:
    """Integration tests for generate-batch command with mocked OpenAI."""

    def test_generate_batch_requires_api_key(self, test_db_path: Path) -> None:
        """Test that generate-batch requires an API key."""
        _ = test_db_path  # Fixture needed for env var side effect
        result = runner.invoke(app, ["generate-batch"])

        assert result.exit_code != 0

    def test_generate_batch_no_unprocessed(self, test_db_path: Path) -> None:
        """Test generate-batch with no unprocessed clippings."""
        # Create empty database
        db = ClippingsDatabase(test_db_path)
        db.close()

        result = runner.invoke(app, ["generate-batch", "--openai-api-key", "test-key"])

        assert result.exit_code == 0
        assert "No unprocessed" in result.stdout

    def test_load_batch_not_complete(self, test_db_path: Path) -> None:
        """Test loading batch results when batch is not complete."""
        _ = test_db_path  # Fixture needed for env var side effect
        from anki_cards_from_kindle_highlights.llm import BatchStatus

        with patch(
            "anki_cards_from_kindle_highlights.cli.generate_batch.get_batch_status"
        ) as mock_status:
            mock_status.return_value = BatchStatus(
                batch_id="batch_123",
                status="in_progress",
                total=10,
                completed=5,
                failed=0,
                is_complete=False,
            )

            result = runner.invoke(
                app,
                [
                    "generate-batch",
                    "--openai-api-key",
                    "test-key",
                    "--load-batch-id",
                    "batch_123",
                ],
            )

            assert result.exit_code == 0
            assert (
                "still processing" in result.stdout.lower()
                or "progress" in result.stdout.lower()
            )


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    def test_import_then_dump(
        self,
        test_db_path: Path,
        sample_clippings_file: Path,
        tmp_path: Path,
    ) -> None:
        """Test importing clippings then dumping them."""
        _ = test_db_path  # Fixture needed for env var side effect
        # Step 1: Import clippings
        result = runner.invoke(
            app, ["import", "--clippings-file", str(sample_clippings_file)]
        )
        assert result.exit_code == 0
        assert "Inserted" in result.stdout

        # Step 2: Dump to CSV
        output_file = tmp_path / "export.csv"
        result = runner.invoke(app, ["dump", "--output", str(output_file)])
        assert result.exit_code == 0

        # Step 3: Verify CSV has content
        if output_file.exists():
            content = output_file.read_text()
            assert len(content) > 0

    def test_import_generate_card_manually_sync(
        self,
        test_db_path: Path,
        sample_clippings_file: Path,
        mock_anki_connect: MagicMock,
    ) -> None:
        """Test the complete workflow with manual card generation."""
        # Step 1: Import clippings
        result = runner.invoke(
            app, ["import", "--clippings-file", str(sample_clippings_file)]
        )
        assert result.exit_code == 0

        # Step 2: Check database has records
        db = ClippingsDatabase(test_db_path)
        records = db.get_all_records()
        assert len(records) >= 1

        # Step 3: Manually update a card (simulating LLM generation)
        first_record = records[0]
        db.update_card_data(first_record.id, "MENTAL_MODEL", "Question?", "Answer!")
        db.close()

        # Step 4: Sync to Anki (mocked)
        mock_anki_connect.return_value.json.side_effect = [
            {"result": None, "error": None},  # createDeck
            {"result": ["Kindle_Smart_Basic", "Kindle_Smart_Cloze"], "error": None},
            {"result": [], "error": None},  # findNotes
            {"result": 12345, "error": None},  # addNote
        ]

        result = runner.invoke(app, ["sync-to-anki"])
        assert result.exit_code == 0

        # Verify card is now synced
        db = ClippingsDatabase(test_db_path)
        record = db.get_record_by_id(first_record.id)
        db.close()

        assert record is not None
        assert record.synced_to_anki is True
