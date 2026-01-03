"""LLM integration for generating Anki cards."""

import asyncio
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openai import APIError, AsyncOpenAI, OpenAI, RateLimitError
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tqdm.asyncio import tqdm

from anki_cards_from_kindle_highlights.db import ClippingRecord


class AnkiCardLLMResponse(BaseModel):
    pattern: Literal[
        "DISTINCTION",
        "MENTAL_MODEL",
        "METAPHOR",
        "FRAMEWORK",
        "TACTIC",
        "CASE_STUDY",
        "DEFINITION",
        "SKIP",
    ]
    front: str | None
    back: str | None


@dataclass
class GenerationResult:
    """Result of processing a single highlight."""

    record_id: int
    card: AnkiCardLLMResponse | None
    error: str | None = None


@dataclass
class BatchStatus:
    """Status of an OpenAI batch job."""

    batch_id: str
    status: str
    total: int
    completed: int
    failed: int
    is_complete: bool
    output_file_id: str | None = None
    error_file_id: str | None = None


@retry(  # type: ignore[misc]
    retry=retry_if_exception_type((RateLimitError, APIError)),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def llm_highlight_to_card(
    client: AsyncOpenAI,
    prompt: str,
    book_title: str,
    highlight: str,
    model: str,
    semaphore: asyncio.Semaphore,
) -> AnkiCardLLMResponse | None:
    """Convert a highlight to an Anki card using an LLM (async with rate limiting)."""
    async with semaphore:
        completion = await client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": f"Book: {book_title}\nHighlight: {highlight}",
                },
            ],
            response_format=AnkiCardLLMResponse,
        )

        card: AnkiCardLLMResponse | None = completion.choices[0].message.parsed

        if card is None:
            return None

        return card


async def _process_single_record(
    client: AsyncOpenAI,
    prompt: str,
    record: ClippingRecord,
    model: str,
    semaphore: asyncio.Semaphore,
) -> GenerationResult:
    """Process a single clipping record and return the result."""
    try:
        card = await llm_highlight_to_card(
            client=client,
            prompt=prompt,
            book_title=record.book_title,
            highlight=record.content or "",
            model=model,
            semaphore=semaphore,
        )
        return GenerationResult(record_id=record.id or 0, card=card)
    except Exception as e:
        return GenerationResult(record_id=record.id or 0, card=None, error=str(e))


async def _run_parallel_async(
    api_key: str,
    prompt: str,
    records: list[ClippingRecord],
    model: str,
    max_parallel: int,
) -> list[GenerationResult]:
    """Run parallel LLM requests with semaphore-based concurrency control."""
    client = AsyncOpenAI(api_key=api_key)
    semaphore = asyncio.Semaphore(max_parallel)

    tasks = [
        _process_single_record(client, prompt, record, model, semaphore)
        for record in records
    ]

    results: list[GenerationResult] = []
    for coro in tqdm.as_completed(tasks, total=len(tasks), desc="Processing clippings"):
        result = await coro
        results.append(result)

    return results


def llm_highlight_to_card_parallel_async(
    api_key: str,
    prompt: str,
    records: list[ClippingRecord],
    model: str,
    max_parallel: int = 10,
) -> list[GenerationResult]:
    """Process multiple clipping records in parallel using async LLM calls.

    Args:
        api_key: OpenAI API key.
        prompt: System prompt for the LLM.
        records: List of ClippingRecord objects to process.
        model: OpenAI model to use.
        max_parallel: Maximum number of concurrent requests (default 10).

    Returns:
        List of GenerationResult objects with the processed cards.
    """
    return asyncio.run(
        _run_parallel_async(
            api_key=api_key,
            prompt=prompt,
            records=records,
            model=model,
            max_parallel=max_parallel,
        )
    )


# =============================================================================
# OpenAI Batch API Functions
# =============================================================================


def _get_response_schema() -> dict[str, Any]:
    """Get the JSON schema for AnkiCardLLMResponse with additionalProperties: false."""
    schema = AnkiCardLLMResponse.model_json_schema()
    # OpenAI Batch API requires additionalProperties: false for strict mode
    schema["additionalProperties"] = False
    return schema


def _create_batch_request(
    record: ClippingRecord, prompt: str, model: str
) -> dict[str, Any] | None:
    """Create a single batch request entry for a clipping record."""
    if record.content is None:
        return None

    return {
        "custom_id": str(record.id),
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": f"Book: {record.book_title}\nHighlight: {record.content}",
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "AnkiCardLLMResponse",
                    "strict": True,
                    "schema": _get_response_schema(),
                },
            },
        },
    }


def create_batch_jsonl(
    records: list[ClippingRecord], prompt: str, model: str
) -> tuple[str, list[int]]:
    """Create JSONL content for OpenAI batch API.

    Args:
        records: List of ClippingRecord objects to process.
        prompt: System prompt for the LLM.
        model: OpenAI model to use.

    Returns:
        Tuple of (jsonl_content, list of record IDs included in batch).
    """
    lines = []
    included_ids = []

    for record in records:
        request = _create_batch_request(record, prompt, model)
        if request is not None:
            lines.append(json.dumps(request))
            included_ids.append(record.id or 0)

    return "\n".join(lines), included_ids


def upload_and_create_batch(
    api_key: str,
    records: list[ClippingRecord],
    prompt: str,
    model: str,
) -> tuple[str, list[int]]:
    """Upload JSONL file and create a batch job.

    Args:
        api_key: OpenAI API key.
        records: List of ClippingRecord objects to process.
        prompt: System prompt for the LLM.
        model: OpenAI model to use.

    Returns:
        Tuple of (batch_id, list of record IDs included in batch).
    """
    client = OpenAI(api_key=api_key)

    # Create JSONL content
    jsonl_content, included_ids = create_batch_jsonl(records, prompt, model)

    # Write to temp file and upload
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        f.write(jsonl_content)
        temp_path = Path(f.name)

    try:
        # Upload the file
        with temp_path.open("rb") as f:
            file_response = client.files.create(file=f, purpose="batch")

        # Create the batch
        batch = client.batches.create(
            input_file_id=file_response.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata={"description": "anki-cards-from-kindle-highlights batch"},
        )

        return batch.id, included_ids
    finally:
        temp_path.unlink()


def get_batch_status(api_key: str, batch_id: str) -> BatchStatus:
    """Check the status of a batch job.

    Args:
        api_key: OpenAI API key.
        batch_id: The batch ID to check.

    Returns:
        BatchStatus object with current status.
    """
    client = OpenAI(api_key=api_key)
    batch = client.batches.retrieve(batch_id)

    request_counts = batch.request_counts
    total = request_counts.total if request_counts else 0
    completed = request_counts.completed if request_counts else 0
    failed = request_counts.failed if request_counts else 0

    is_complete = batch.status in ("completed", "failed", "expired", "cancelled")

    return BatchStatus(
        batch_id=batch.id,
        status=batch.status,
        total=total,
        completed=completed,
        failed=failed,
        is_complete=is_complete,
        output_file_id=batch.output_file_id,
        error_file_id=batch.error_file_id,
    )


def retrieve_batch_results(api_key: str, batch_id: str) -> list[GenerationResult]:
    """Retrieve and parse results from a completed batch.

    Args:
        api_key: OpenAI API key.
        batch_id: The batch ID to retrieve results for.

    Returns:
        List of GenerationResult objects.

    Raises:
        ValueError: If batch is not complete or has no output file.
    """
    client = OpenAI(api_key=api_key)
    batch = client.batches.retrieve(batch_id)

    if batch.status != "completed":
        raise ValueError(f"Batch is not complete. Status: {batch.status}")

    if batch.output_file_id is None:
        raise ValueError("Batch has no output file")

    # Download the output file
    file_content = client.files.content(batch.output_file_id)
    lines = file_content.text.strip().split("\n")

    results: list[GenerationResult] = []

    for line in lines:
        if not line.strip():
            continue

        response = json.loads(line)
        custom_id = response.get("custom_id", "0")
        record_id = int(custom_id)

        # Check for errors
        error = response.get("error")
        if error:
            results.append(
                GenerationResult(
                    record_id=record_id,
                    card=None,
                    error=str(error),
                )
            )
            continue

        # Parse the response
        try:
            body = response.get("response", {}).get("body", {})
            choices = body.get("choices", [])
            if not choices:
                results.append(
                    GenerationResult(
                        record_id=record_id,
                        card=None,
                        error="No choices in response",
                    )
                )
                continue

            message = choices[0].get("message", {})
            content = message.get("content", "")

            # Parse the JSON content
            card_data = json.loads(content)
            card = AnkiCardLLMResponse(**card_data)

            results.append(GenerationResult(record_id=record_id, card=card))

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            results.append(
                GenerationResult(
                    record_id=record_id,
                    card=None,
                    error=f"Failed to parse response: {e}",
                )
            )

    return results
