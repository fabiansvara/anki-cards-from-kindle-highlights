"""LLM integration for generating Anki cards."""

import asyncio
from dataclasses import dataclass
from typing import Literal

from openai import APIError, AsyncOpenAI, RateLimitError
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
    if len(highlight.strip()) < 20:
        return None

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


async def _run_parallel_batch(
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


def llm_highlight_to_card_parallel_batch(
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
        _run_parallel_batch(
            api_key=api_key,
            prompt=prompt,
            records=records,
            model=model,
            max_parallel=max_parallel,
        )
    )
