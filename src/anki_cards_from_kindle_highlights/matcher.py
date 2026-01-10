"""Match Kindle clippings to their location in book text."""

from dataclasses import dataclass
from typing import Protocol

from anki_cards_from_kindle_highlights.books import Book


class HasContent(Protocol):
    """Protocol for objects that have a content attribute."""

    content: str


class NoMatchException(Exception):
    """Raised when a clipping cannot be found in the book text."""


class AmbiguousMatchException(Exception):
    """Raised when a clipping matches multiple locations in the book text."""

    def __init__(self, message: str, match_count: int) -> None:
        super().__init__(message)
        self.match_count = match_count


def _skeletonize(text: str) -> tuple[str, list[int]]:
    """Convert text to a skeleton of lowercase alphanumeric characters.

    Returns:
        A tuple of (skeleton_string, index_map) where index_map[i] is the
        index in the original text corresponding to skeleton_string[i].
    """
    skeleton_chars: list[str] = []
    index_map: list[int] = []

    for i, char in enumerate(text):
        if char.isalnum():
            skeleton_chars.append(char.lower())
            index_map.append(i)

    return "".join(skeleton_chars), index_map


@dataclass
class MatchResult:
    """Result of a successful match."""

    start: int  # Start offset in original text
    length: int  # Length in original text


class BookMatcher(Book):
    """A Book with skeleton-based matching capabilities."""

    def __init__(self, author: str, title: str, epub_path: str | None) -> None:
        super().__init__(author, title, epub_path)
        self._skeleton: str | None = None
        self._index_map: list[int] | None = None

    @classmethod
    def from_book(cls, book: Book) -> "BookMatcher":
        """Create a BookMatcher from an existing Book object."""
        return cls(author=book.author, title=book.title, epub_path=book.epub_path)

    @property
    def skeleton(self) -> tuple[str, list[int]] | None:
        """Get the skeleton representation of the book text.

        Returns:
            A tuple of (skeleton_string, index_map), or None if book has no text.
            The index_map maps each skeleton character position to its original text position.
        """
        if self._skeleton is not None and self._index_map is not None:
            return self._skeleton, self._index_map

        text = self.text
        if text is None:
            return None

        self._skeleton, self._index_map = _skeletonize(text)
        return self._skeleton, self._index_map

    def match(self, clipping: HasContent) -> MatchResult:
        """Match a clipping to its location in the book text.

        Args:
            clipping: Any object with a 'content' attribute (Clipping or ClippingRecord).

        Returns:
            MatchResult with start offset and length in the original text.

        Raises:
            NoMatchException: If the clipping text is not found in the book.
            AmbiguousMatchException: If the clipping matches multiple locations.
            ValueError: If the clipping has no content or book has no text.
        """
        if not clipping.content.strip():
            raise ValueError("Clipping has no content")

        skeleton_data = self.skeleton
        if skeleton_data is None:
            raise ValueError("Book has no text")

        book_skeleton, index_map = skeleton_data
        clipping_skeleton, _ = _skeletonize(clipping.content)

        if not clipping_skeleton:
            raise ValueError("Clipping content has no alphanumeric characters")

        # Find all occurrences of the clipping skeleton in the book skeleton
        matches: list[int] = []
        start = 0
        while True:
            pos = book_skeleton.find(clipping_skeleton, start)
            if pos == -1:
                break
            matches.append(pos)
            start = pos + 1

        if len(matches) == 0:
            raise NoMatchException(
                f"Clipping not found in book: '{clipping.content[:50]}...'"
            )

        if len(matches) > 1:
            raise AmbiguousMatchException(
                f"Clipping matches {len(matches)} locations: '{clipping.content[:50]}...'",
                match_count=len(matches),
            )

        # Single unique match - calculate original text position
        skeleton_start = matches[0]
        skeleton_end = skeleton_start + len(clipping_skeleton) - 1

        # Map skeleton positions back to original text positions
        original_start = index_map[skeleton_start]
        original_end = index_map[skeleton_end]

        # Length includes the end character
        original_length = original_end - original_start + 1

        return MatchResult(start=original_start, length=original_length)
