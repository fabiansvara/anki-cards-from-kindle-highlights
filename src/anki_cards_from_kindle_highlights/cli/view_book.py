"""View book command - browse Calibre library with matched clippings."""

from pathlib import Path
from typing import Annotated, ClassVar

import questionary
import typer
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, RichLog
from thefuzz import fuzz
from tqdm import tqdm

from anki_cards_from_kindle_highlights.books import Book, books_from_calibre
from anki_cards_from_kindle_highlights.cli.helpers import abbreviate
from anki_cards_from_kindle_highlights.db import ClippingsDatabase, get_db_path
from anki_cards_from_kindle_highlights.matcher import (
    AmbiguousMatchException,
    BookMatcher,
    MatchResult,
    NoMatchException,
)


class BookViewer(App[None]):
    """A simple book viewer with keyboard navigation."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
        Binding("home", "scroll_home", "Top"),
        Binding("end", "scroll_end", "Bottom"),
        Binding("g", "scroll_home", "Top"),
        Binding("G", "scroll_end", "Bottom", key_display="Shift+G"),
    ]

    DEFAULT_CSS = """
    RichLog {
        scrollbar-gutter: stable;
    }
    """

    def __init__(self, title: str, content: Text) -> None:
        super().__init__()
        self._book_title = title
        self._content = content

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(highlight=True, markup=True, wrap=True, id="log")
        yield Footer()

    def on_mount(self) -> None:
        self.title = self._book_title
        log = self.query_one("#log", RichLog)
        log.write(self._content)
        log.focus()

    def action_scroll_home(self) -> None:
        log = self.query_one("#log", RichLog)
        log.scroll_home()

    def action_scroll_end(self) -> None:
        log = self.query_one("#log", RichLog)
        log.scroll_end()


def _find_matching_clippings_book(
    book: Book,
    db_books: list[tuple[str, str]],
) -> tuple[str, str] | None:
    """Find a matching book from the clippings DB for a given book.

    First tries exact matching, then falls back to fuzzy matching.

    Args:
        book: The Book object to match.
        db_books: List of (title, author) tuples from the clippings database.

    Returns:
        The matching (title, author) tuple from db_books, or None if no match.
    """
    book_author = book.author.lower().strip()
    book_title = book.title.lower().strip()

    # Try exact match first
    for db_title, db_author in db_books:
        db_author_lower = db_author.lower().strip()
        db_title_lower = db_title.lower().strip()

        if book_title == db_title_lower and book_author == db_author_lower:
            return (db_title, db_author)

    # Fuzzy matching - combine author and title for better matching
    best_match: tuple[str, str] | None = None
    best_score = 0

    for db_title, db_author in db_books:
        # Score based on both title and author similarity
        title_score = fuzz.ratio(book_title, db_title.lower())
        author_score = fuzz.ratio(book_author, db_author.lower())

        # Weight title more heavily (title is more distinctive)
        combined_score = (title_score * 0.7) + (author_score * 0.3)

        if combined_score > best_score:
            best_score = combined_score
            best_match = (db_title, db_author)

    # Require a minimum score of 70 to consider it a match
    if best_score >= 70:
        return best_match

    return None


def _build_rich_text_with_highlights(
    original_text: str,
    matches: list[tuple[MatchResult, str]],
) -> Text:
    """Build a rich Text object with highlighted clippings.

    Args:
        original_text: The full text of the book.
        matches: List of (MatchResult, clipping_content) tuples.

    Returns:
        A rich Text object with highlighted sections styled with red background.
    """
    text = Text(original_text)

    # Apply red background style to each matched section
    for match_result, _ in matches:
        start = match_result.start
        end = start + match_result.length
        text.stylize("bold white on red", start, end)

    return text


def _show_book_text(
    book: Book,
    matches: list[tuple[MatchResult, str]],
) -> None:
    """Show the book text in an interactive pager with highlighted clippings."""
    text = book.text
    if text is None:
        print("Error: Could not extract text from EPUB.")
        raise typer.Exit(1)

    # Build rich Text with highlighted matches
    if matches:
        print(f"\nHighlighting {len(matches)} matched clippings...")
        rich_text = _build_rich_text_with_highlights(text, matches)
    else:
        rich_text = Text(text)

    title = f"{book.title} — {book.author}"

    print("\n📖 Opening book viewer...")
    print("   Navigation: ↑/↓/PgUp/PgDown, Home/End, q to quit\n")

    viewer = BookViewer(title=title, content=rich_text)
    viewer.run()


def view_book(
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
    """Browse books from a Calibre library and view their text with matched clippings."""
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
    def format_book_choice(book: Book) -> str:
        author = abbreviate(book.author, 25)
        title = abbreviate(book.title, 50)
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

    print(f"\nSelected: {selected.title} by {selected.author}")

    # Get clippings for this book from the local database
    db_path = get_db_path()
    db = ClippingsDatabase(db_path)

    # Get all unique books from clippings DB
    db_books = db.get_unique_books()

    if not db_books:
        print("\nNo clippings found in database. Run 'import' first.")
        db.close()
        # Still show the book text without clipping matches
        _show_book_text(selected, [])
        return

    # Find matching book in clippings DB (exact or fuzzy match)
    matched_book = _find_matching_clippings_book(selected, db_books)

    if matched_book is None:
        print("\n⚠️  No matching clippings found for this book in the database.")
        print(f"   Calibre: {selected.author} — {selected.title}")
        print("   Try importing clippings with the 'import' command first.")
        db.close()
        # Still show the book text without clipping matches
        _show_book_text(selected, [])
        return

    db_title, db_author = matched_book
    print(f"📚 Matched to clippings: {db_author} — {db_title}")

    # Get all clippings for this book
    clippings = db.get_clippings_for_book(db_title, db_author)
    db.close()

    print(f"   Found {len(clippings)} clippings\n")

    if not clippings:
        _show_book_text(selected, [])
        return

    # Load book text and create matcher
    print("Loading book text...")
    text = selected.text

    if text is None:
        print("Error: Could not extract text from EPUB.")
        raise typer.Exit(1)

    print("Creating book matcher...")
    matcher = BookMatcher.from_book(selected)

    # Match each clipping
    print("Matching clippings to book text...")
    successful_matches: list[tuple[MatchResult, str]] = []
    no_match_count = 0
    ambiguous_count = 0
    error_count = 0

    for clipping in tqdm(clippings, desc="Matching clippings"):
        if not clipping.content.strip():
            continue

        try:
            result = matcher.match(clipping)
            successful_matches.append((result, clipping.content))
        except NoMatchException:
            no_match_count += 1
        except AmbiguousMatchException:
            ambiguous_count += 1
        except ValueError:
            error_count += 1

    print()
    print(f"✅ Matched: {len(successful_matches)}")
    if no_match_count > 0:
        print(f"❌ No match found: {no_match_count}")
    if ambiguous_count > 0:
        print(f"⚠️  Ambiguous (multiple matches): {ambiguous_count}")
    if error_count > 0:
        print(f"⛔ Errors: {error_count}")

    # Label the text with matches and show it
    _show_book_text(selected, successful_matches)
