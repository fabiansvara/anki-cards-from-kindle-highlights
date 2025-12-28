"""LLM integration for generating Anki cards."""

from typing import Literal

from openai import OpenAI
from pydantic import BaseModel


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


def llm_highlight_to_card(
    client: OpenAI,
    prompt: str,
    book_title: str,
    highlight: str,
    model: str,
) -> AnkiCardLLMResponse | None:
    """Convert a highlight to an Anki card using an LLM."""
    if len(highlight.strip()) < 20:
        print(f"Skipping (Too short): {highlight[:15]}...")
        return None

    try:
        completion = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": f"Book: {book_title}\nHighlight: {highlight}",
                },
            ],
            response_format=AnkiCardLLMResponse,
            # temperature=0.1,
        )

        card: AnkiCardLLMResponse | None = completion.choices[0].message.parsed

        if card is None:
            print("Error: Failed to parse LLM response")
            return None

        return card

    except Exception as e:
        print(f"Error processing highlight: {e}")
        return None
