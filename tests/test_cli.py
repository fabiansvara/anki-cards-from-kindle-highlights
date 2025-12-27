"""Tests for the CLI module."""

from typer.testing import CliRunner

from anki_cards_from_kindle_highlights.cli import app

runner = CliRunner()


def test_version_flag():
    """Test that --version shows the version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
