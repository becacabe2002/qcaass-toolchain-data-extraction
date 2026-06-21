"""LangGraph state (Section 4 of the blueprint)."""

from __future__ import annotations

from typing import Annotated, TypedDict

from .schema import (
    AlgorithmsSection,
    Architecture,
    ChallengesSection,
    GeneralInfo,
    OverviewCharacteristics,
    ToolRecord,
)


def merge_dicts(left: dict, right: dict) -> dict:
    """Reducer for keys written concurrently by distinct fan-out branches.

    Each extractor writes only its own category key, so a shallow merge never
    loses data and overwrites the same key cleanly on a retry pass.
    """
    return {**left, **right}


class ExtractionState(TypedDict, total=False):
    tool_id: str
    source_doc_path: str
    raw_text: str  # canonical normalized source (validation reference)
    raw_paragraphs: list[str]  # canonical paragraphs, for re-anchoring
    token_count: int

    # locate output, then re-anchored to canonical text in-place:
    # category name -> list of canonical paragraph strings
    located_spans: dict[str, list[str]]
    reanchor_dropped: list[str]  # paragraphs that failed to re-anchor

    # Per-category extraction outputs (distinct keys -> no reducer needed)
    general: GeneralInfo | None
    overview: OverviewCharacteristics | None
    architecture: Architecture | None
    algorithms: AlgorithmsSection | None
    challenges: ChallengesSection | None

    # category -> parse-failure reason (empty string == cleared). Concurrent
    # branches each touch only their own key, merged by merge_dicts.
    parse_failures: Annotated[dict[str, str], merge_dicts]

    # Validator results - OVERWRITTEN every validate pass, never accumulated
    validation_errors: list[dict]  # [{field_path, value, quote, reason}]
    validation_offsets: list[dict]  # passing-quote audit log [{field_path, offset, length}]
    categories_to_retry: list[str]  # set by validate, read by the retry router
    retry_counts: dict[str, int]  # category -> attempts; enforces <=1 budget

    # Final assembled record (consumed by the batch driver)
    record: ToolRecord | None
