"""Parser for Kindle My Clippings.txt files."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class ClippingType(Enum):
    """Type of Kindle clipping."""

    HIGHLIGHT = "Highlight"
    NOTE = "Note"
    BOOKMARK = "Bookmark"


@dataclass
class Clipping:
    """Represents a single Kindle clipping."""

    book_title: str
    author: str | None
    clipping_type: ClippingType
    page: int | None
    location_start: int
    location_end: int | None
    date_added: datetime
    content: str | None


# Pattern to extract author from title like "Book Title (Author Name)"
AUTHOR_PATTERN = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")

# Pattern to parse the metadata line
# Examples:
# - Your Highlight at location 95-96 | Added on Tuesday, 21 March 2023 22:08:17
# - Your Highlight on page 5 | location 35-36 | Added on Wednesday, 9 August 2023 23:26:06
# - Your Bookmark on page 72 | location 932 | Added on Sunday, 13 July 2025 23:35:53
METADATA_PATTERN = re.compile(
    r"- Your (Highlight|Note|Bookmark)"
    r"(?: on page (\d+))?"
    r"(?: (?:at )?location (\d+)(?:-(\d+))?)?"
    r" \| Added on (.+)$"
)


def parse_clippings_file(file_path: Path) -> list[Clipping]:
    """Parse a Kindle My Clippings.txt file and return a list of Clipping objects."""
    content = file_path.read_text(encoding="utf-8-sig")  # Handle BOM

    # Split by the separator
    entries = content.split("==========")

    clippings: list[Clipping] = []

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        lines = entry.split("\n")
        if len(lines) < 2:
            continue

        # Parse title and author
        title_line = lines[0].strip()
        # Remove BOM if present
        title_line = title_line.lstrip("\ufeff")

        author: str | None = None
        book_title = title_line

        author_match = AUTHOR_PATTERN.match(title_line)
        if author_match:
            book_title = author_match.group(1).strip()
            author = author_match.group(2).strip()

        # Parse metadata line
        metadata_line = lines[1].strip()
        metadata_match = METADATA_PATTERN.match(metadata_line)

        if not metadata_match:
            continue

        clipping_type_str = metadata_match.group(1)
        clipping_type = ClippingType(clipping_type_str)

        page_str = metadata_match.group(2)
        page = int(page_str) if page_str else None

        location_start_str = metadata_match.group(3)
        location_start = int(location_start_str) if location_start_str else 0

        location_end_str = metadata_match.group(4)
        location_end = int(location_end_str) if location_end_str else None

        date_str = metadata_match.group(5)
        date_added = _parse_date(date_str)

        # Content is everything after the empty line (line index 2+)
        content_lines = lines[3:] if len(lines) > 3 else []
        clipping_content = "\n".join(content_lines).strip() or None

        clippings.append(
            Clipping(
                book_title=book_title,
                author=author,
                clipping_type=clipping_type,
                page=page,
                location_start=location_start,
                location_end=location_end,
                date_added=date_added,
                content=clipping_content,
            )
        )

    return clippings


def _parse_date(date_str: str) -> datetime:
    """Parse a Kindle date string into a datetime object."""
    # Format: "Tuesday, 21 March 2023 22:08:17"
    try:
        return datetime.strptime(date_str, "%A, %d %B %Y %H:%M:%S")
    except ValueError:
        # Fallback for different formats
        return datetime.now()
