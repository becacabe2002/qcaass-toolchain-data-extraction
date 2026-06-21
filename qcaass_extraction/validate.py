"""Deterministic quote-fidelity validator (Sections 5 & 8 of the blueprint).

Pure Python, no model calls. Recomputes ``validation_errors`` from scratch
each pass (overwrite, never accumulate).
"""

from __future__ import annotations

from typing import Iterable

from .config import MAX_RETRIES_PER_CATEGORY, MIN_QUOTE_WORDS
from .normalize import match_key, word_count
from .schema import (
    AlgorithmsSection,
    Architecture,
    ChallengesSection,
    GeneralInfo,
    OverviewCharacteristics,
)
from .state import ExtractionState

# A coded value that legitimately carries no evidence.
NOT_STATED = "Not stated"


class EvidenceField:
    """One (field_path, value, quote, category) tuple awaiting validation."""

    __slots__ = ("field_path", "value", "quote", "category", "coded")

    def __init__(self, field_path, value, quote, category, coded=True):
        self.field_path = field_path
        self.value = value
        self.quote = quote
        self.category = category
        self.coded = coded  # coded enums may legitimately be "Not stated"


def collect_evidence_fields(
    general: GeneralInfo | None,
    overview: OverviewCharacteristics | None,
    architecture: Architecture | None,
    algorithms: AlgorithmsSection | None,
    challenges: ChallengesSection | None,
) -> list[EvidenceField]:
    """Flatten every coded/evidence-bearing field across category outputs."""
    fields: list[EvidenceField] = []

    if general is not None:
        fields.append(
            EvidenceField("general.source_type", general.source_type.value,
                          general.source_type.evidence, "general")
        )
        fields.append(
            EvidenceField("general.contribution_type", general.contribution_type.value,
                          general.contribution_type.evidence, "general")
        )

    if overview is not None:
        for name in ("input_instruction", "output_type", "automation_level",
                     "evaluation_type"):
            f = getattr(overview, name)
            fields.append(
                EvidenceField(f"overview.{name}", f.value, f.evidence, "overview")
            )

    if architecture is not None:
        from .schema import ARCHITECTURE_COMPONENTS
        for name in ARCHITECTURE_COMPONENTS:
            f = getattr(architecture, name)
            fields.append(
                EvidenceField(f"architecture.{name}", f.value, f.evidence,
                              "architecture")
            )

    if algorithms is not None:
        fields.append(
            EvidenceField("algorithms.overall_evidence", algorithms.offers_algorithms,
                          algorithms.overall_evidence, "algorithms")
        )
        for i, alg in enumerate(algorithms.algorithms):
            # Algorithm evidence is not a coded enum: the quote is mandatory.
            fields.append(
                EvidenceField(f"algorithms.algorithms[{i}].evidence", alg.name,
                              alg.evidence, "algorithms", coded=False)
            )

    if challenges is not None:
        for i, ch in enumerate(challenges.challenges):
            fields.append(
                EvidenceField(f"challenges.challenges[{i}].category_evidence",
                              ch.category, ch.category_evidence, "challenges",
                              coded=False)
            )
            fields.append(
                EvidenceField(f"challenges.challenges[{i}].strength_evidence",
                              ch.evidence_strength, ch.strength_evidence, "challenges",
                              coded=False)
            )

    return fields


def check_quote(quote: str, source_key: str) -> tuple[bool, str, int]:
    """Return (ok, reason, offset). offset is -1 when not matched."""
    if word_count(quote) < MIN_QUOTE_WORDS:
        return False, f"quote shorter than {MIN_QUOTE_WORDS} words", -1
    key = match_key(quote)
    offset = source_key.find(key)
    if offset == -1:
        return False, "quote not found verbatim in source", -1
    return True, "", offset


def validate(state: ExtractionState) -> dict:
    """Validate node: recompute errors, decide retries, increment budget."""
    raw_text = state.get("raw_text", "")
    source_key = match_key(raw_text)

    fields = collect_evidence_fields(
        state.get("general"),
        state.get("overview"),
        state.get("architecture"),
        state.get("algorithms"),
        state.get("challenges"),
    )

    errors: list[dict] = []
    offsets: list[dict] = []  # passing-quote audit log
    errored_categories: set[str] = set()

    for f in fields:
        # Legitimate empty: a coded enum set to "Not stated" with no quote.
        if not f.quote:
            if f.coded and f.value == NOT_STATED:
                continue
            errors.append({
                "field_path": f.field_path,
                "value": f.value,
                "quote": "",
                "reason": "coded value carries no evidence quote",
            })
            errored_categories.add(f.category)
            continue

        ok, reason, offset = check_quote(f.quote, source_key)
        if ok:
            offsets.append({"field_path": f.field_path, "offset": offset,
                            "length": len(match_key(f.quote))})
        else:
            errors.append({
                "field_path": f.field_path,
                "value": f.value,
                "quote": f.quote,
                "reason": reason,
            })
            errored_categories.add(f.category)

    # Fail loud on a totally starved extraction: if the locate/reanchor stage
    # left *every* category with no spans, the strong model ran on zero input
    # and "Not stated" everywhere is an artifact, not a finding. Flag it for
    # review without routing a (useless) retry.
    located = state.get("located_spans")
    if located and all(not spans for spans in located.values()):
        errors.append({
            "field_path": "located_spans",
            "value": None,
            "quote": "",
            "reason": "all located spans empty after reanchor; extraction ran on zero input",
        })

    # Parse failures (non-empty reason) count as errored categories too.
    for cat, reason in (state.get("parse_failures") or {}).items():
        if reason:
            errors.append({
                "field_path": cat,
                "value": None,
                "quote": "",
                "reason": f"parse failure: {reason}",
            })
            errored_categories.add(cat)

    # Decide which categories to retry and burn one unit of budget for each.
    retry_counts = dict(state.get("retry_counts") or {})
    to_retry: list[str] = []
    for cat in sorted(errored_categories):
        if retry_counts.get(cat, 0) < MAX_RETRIES_PER_CATEGORY:
            retry_counts[cat] = retry_counts.get(cat, 0) + 1
            to_retry.append(cat)

    return {
        "validation_errors": errors,
        "validation_offsets": offsets,
        "categories_to_retry": to_retry,
        "retry_counts": retry_counts,
    }
