"""Tests for the CLI module."""

from typer.testing import CliRunner

from anki_cards_from_kindle_highlights.cli import app

runner = CliRunner()


def test_version_flag() -> None:
    """Test that --version shows the version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    # Check for version format (e.g., "0.2.0")
    assert "." in result.stdout  # Version has dots


def test_help_flag() -> None:
    """Test that --help shows help text."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Generate Anki cards from Kindle highlights" in result.stdout


def test_no_args_shows_help() -> None:
    """Test that running without arguments shows help."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    # Should show available commands
    assert "generate" in result.stdout or "import" in result.stdout


def test_import_command_help() -> None:
    """Test import command help."""
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "clippings" in result.stdout.lower()


def test_generate_command_help() -> None:
    """Test generate command help."""
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    assert "openai" in result.stdout.lower()


def test_dump_command_help() -> None:
    """Test dump command help."""
    result = runner.invoke(app, ["dump", "--help"])
    assert result.exit_code == 0
    assert "csv" in result.stdout.lower() or "export" in result.stdout.lower()


def test_sync_command_help() -> None:
    """Test sync-to-anki command help."""
    result = runner.invoke(app, ["sync-to-anki", "--help"])
    assert result.exit_code == 0
    assert "anki" in result.stdout.lower()
