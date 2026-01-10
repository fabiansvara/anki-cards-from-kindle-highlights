"""Book metadata and Calibre library integration."""

import sqlite3
import warnings
from pathlib import Path

import ebooklib
import html2text
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

# Suppress warning about parsing XHTML (common in EPUBs) as HTML
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Configure html2text for readable output
_h2t = html2text.HTML2Text()
_h2t.ignore_links = True
_h2t.ignore_images = True
_h2t.body_width = 0  # Don't wrap lines


def _html_to_text(html: bytes | str) -> str:
    """Convert HTML to Markdown-style text for readability.

    Uses BeautifulSoup/lxml for encoding detection, then html2text for conversion.
    """
    # Use lxml for encoding detection when given bytes
    if isinstance(html, bytes):
        soup = BeautifulSoup(html, "lxml")
        html = str(soup)

    result: str = _h2t.handle(html)
    return result


class Book:
    """Represents a book with its metadata and content."""

    def __init__(self, author: str, title: str, epub_path: str | None) -> None:
        self.author = author
        self.title = title
        self.epub_path = epub_path
        self._text: str | None = None

    @property
    def text(self) -> str | None:
        """Extract and cache the plain text content of the book.

        Returns:
            The book's text content as a plain string, or None if no epub exists.
        """
        if self._text is not None:
            return self._text

        if self.epub_path is None:
            return None

        epub_file = Path(self.epub_path)
        if not epub_file.exists():
            return None

        try:
            book = epub.read_epub(self.epub_path)
        except Exception:
            return None

        text_parts: list[str] = []

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                # Pass raw bytes to BeautifulSoup - it handles encoding detection
                content = item.get_content()
                plain_text = _html_to_text(content)
                text_parts.append(plain_text)

        self._text = "\n\n".join(text_parts)
        return self._text

    def __repr__(self) -> str:
        return f"Book(author={self.author!r}, title={self.title!r}, epub_path={self.epub_path!r})"


def books_from_calibre(calibre_dir: str | Path) -> dict[tuple[str, str], Book]:
    """Read book metadata from a Calibre library.

    Args:
        calibre_dir: Path to the Calibre library directory (contains metadata.db).

    Returns:
        Dictionary mapping (author, title) tuples to Book objects.

    Raises:
        FileNotFoundError: If the Calibre metadata.db file doesn't exist.
    """
    calibre_path = Path(calibre_dir)
    db_path = calibre_path / "metadata.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Query to get book info with author and epub path
    # Calibre stores books in: calibre_dir/author/title (id)/filename.epub
    query = """
        SELECT
            b.id,
            b.title,
            b.path as book_path,
            a.name as author,
            d.name as filename,
            d.format
        FROM books b
        LEFT JOIN books_authors_link bal ON b.id = bal.book
        LEFT JOIN authors a ON bal.author = a.id
        LEFT JOIN data d ON b.id = d.book
        ORDER BY b.id, a.name
    """

    cursor = conn.execute(query)
    rows = cursor.fetchall()
    conn.close()

    # Process rows: group by book, prefer epub format
    books_data: dict[int, dict[str, str | None]] = {}

    for row in rows:
        book_id = row["id"]
        title = row["title"]
        author = row["author"] or "Unknown"
        book_path = row["book_path"]
        filename = row["filename"]
        fmt = row["format"]

        if author is None:
            continue
        if title is None:
            continue

        if book_id not in books_data:
            books_data[book_id] = {
                "title": title,
                "author": author,
                "book_path": book_path,
                "epub_filename": None,
            }

        # If this row has epub format, store the filename
        if fmt and fmt.upper() == "EPUB" and filename:
            books_data[book_id]["epub_filename"] = f"{filename}.epub"

    # Build the result dictionary
    result: dict[tuple[str, str], Book] = {}

    for book_info in books_data.values():
        author = book_info["author"]
        title = book_info["title"]
        book_path = book_info["book_path"]
        epub_filename = book_info["epub_filename"]

        # assert to pass type checker -- this is guaranteed by the None checks above
        assert author is not None
        assert title is not None

        if epub_filename and book_path:
            epub_path = str(calibre_path / book_path / epub_filename)
        else:
            epub_path = None

        result[(author, title)] = Book(author=author, title=title, epub_path=epub_path)

    return result
