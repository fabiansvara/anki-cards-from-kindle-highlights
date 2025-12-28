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
    r"(?: \|? ?(?:at )?location (\d+)(?:-(\d+))?)?"
    r" \| Added on (.+)$"
)


def parse_clippings_file(file_path: Path) -> list[Clipping]:
    """
    Parses a Kindle 'My Clippings.txt' file into structured Clipping objects.
    """
    clippings = []

    # Updated Regex:
    # 1. re.IGNORECASE handles "Location" vs "location" and "Page" vs "page"
    # 2. Page capture is [\w]+ to handle "xi", "iv", etc. without breaking the match
    metadata_pattern = re.compile(
        r"- Your (?P<type>Highlight|Note|Bookmark)"
        r"(?: on page (?P<page_str>[\w]+))?"  # Capture page as string first (e.g. '5' or 'xi')
        r"\s*\|?"  # Separator
        r"\s*(?: at)? location (?P<loc_start>\d+)"  # Capture Start Location
        r"(?:-(?P<loc_end>\d+))?"  # Capture End Location
        r"\s*\|\s*Added on (?P<date_str>.+)",  # Capture Date
        re.IGNORECASE,  # Case insensitive flag
    )

    try:
        # utf-8-sig handles the BOM (\ufeff) often found in Kindle files
        with Path(file_path).open(encoding="utf-8-sig") as f:
            raw_text = f.read()
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return []

    # The delimiter is strictly 10 equals signs
    raw_entries = raw_text.split("==========")

    for entry in raw_entries:
        entry = entry.strip()
        if not entry:
            continue

        lines = entry.splitlines()
        if len(lines) < 2:
            continue

        # --- 1. Parse Title and Author ---
        header_line = lines[0].strip()
        book_title = header_line
        author = None

        # Split on the *last* parenthesis to handle titles that contain parentheses
        # e.g. "Book Title (Series Information) (Author Name)"
        if "(" in header_line and header_line.endswith(")"):
            split_index = header_line.rfind("(")
            book_title = header_line[:split_index].strip()
            author = header_line[split_index + 1 : -1].strip()

        # --- 2. Parse Metadata ---
        metadata_line = lines[1].strip()
        match = metadata_pattern.search(metadata_line)

        if not match:
            # Helpful for debugging: print which lines are being skipped
            # print(f"Skipping malformed metadata: {metadata_line}")
            continue

        data = match.groupdict()

        # Parse Type (capitalize to match Enum values e.g. "Highlight")
        c_type_str = data["type"].capitalize()
        try:
            c_type = ClippingType(c_type_str)
        except ValueError:
            # Fallback if unknown type appears
            continue

        # Parse Page: Handle "xi" or other non-integers gracefully
        page = None
        if data["page_str"]:
            try:
                page = int(data["page_str"])
            except ValueError:
                # If page is roman numeral (e.g. 'xi'), keep it as None
                # since the dataclass expects int | None
                page = None

        # Parse Locations
        loc_start = int(data["loc_start"])
        loc_end = int(data["loc_end"]) if data["loc_end"] else None

        # Parse Date
        date_str = data["date_str"].strip()
        try:
            # Standard Kindle format: "Tuesday, 21 March 2023 22:08:17"
            date_added = datetime.strptime(date_str, "%A, %d %B %Y %H:%M:%S")
        except ValueError:
            # Fallback for slight variations or localized dates
            date_added = datetime.min

        # --- 3. Parse Content ---
        content = ""
        if len(lines) > 2:
            content_lines = lines[2:]
            content = "\n".join(content_lines).strip()

        clipping = Clipping(
            book_title=book_title,
            author=author,
            clipping_type=c_type,
            page=page,
            location_start=loc_start,
            location_end=loc_end,
            date_added=date_added,
            content=content,
        )

        clippings.append(clipping)

    return clippings


def _parse_date(date_str: str) -> datetime:
    """Parse a Kindle date string into a datetime object."""
    # Format: "Tuesday, 21 March 2023 22:08:17"
    try:
        return datetime.strptime(date_str, "%A, %d %B %Y %H:%M:%S")
    except ValueError:
        # Fallback for different formats
        return datetime.now()
