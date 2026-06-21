"""locate_spans node (flash model, Section 5 of the blueprint)."""

from __future__ import annotations

import ast
import json
import logging

from .config import CATEGORIES
from .models import get_flash_model
from .prompts import LOCATE_PROMPT
from .state import ExtractionState

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> str:
    """Pull the outer JSON object out of a model response.

    Tolerates ```json fences and leading/trailing prose by slicing from the
    first ``{`` to the last ``}``.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("` \n")
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _loads_lenient(candidate: str):
    """Parse a JSON object, tolerating Python-style single-quoted output.

    Gemini frequently emits ``{'general': [...]}`` (single quotes), which is not
    valid JSON. Fall back to ``ast.literal_eval``, which accepts single-quoted
    string/list/dict literals while staying safe (no code execution).
    """
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return ast.literal_eval(candidate)


def _parse_located(content: str) -> dict[str, list[str]]:
    """Best-effort parse of the flash model's category->snippets map."""
    candidate = _extract_json_object(content)
    try:
        data = _loads_lenient(candidate)
        if not isinstance(data, dict):
            raise ValueError(f"expected a JSON object, got {type(data).__name__}")
    except (json.JSONDecodeError, ValueError, SyntaxError) as exc:
        logger.warning(
            "locate: failed to parse flash output (%s); raw length=%d chars",
            exc, len(content),
        )
        return {cat: [] for cat in CATEGORIES}

    out: dict[str, list[str]] = {}
    for cat in CATEGORIES:
        vals = data.get(cat, [])
        if isinstance(vals, str):
            vals = [vals]
        out[cat] = [str(v) for v in vals if str(v).strip()]
    return out


def _content_to_text(content) -> str:
    """Flatten a chat message's content to plain text.

    LangChain returns ``str`` for some providers but a list of content-block
    dicts (``[{"type": "text", "text": "..."}]``) for others. Stringifying the
    list with ``str()`` buries the JSON inside a Python repr, so pull the text
    out of each block explicitly.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ]
        return "".join(parts)
    return str(content)


def locate_spans(state: ExtractionState) -> dict:
    model = get_flash_model()
    msg = model.invoke(
        [
            {"role": "system", "content": LOCATE_PROMPT},
            {"role": "user", "content": state["raw_text"]},
        ]
    )
    content = _content_to_text(msg.content)
    located = _parse_located(content)
    logger.info(
        "locate: snippets per category %s",
        {cat: len(v) for cat, v in located.items()},
    )
    return {"located_spans": located}
