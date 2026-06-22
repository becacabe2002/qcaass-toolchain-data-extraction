"""Pre-run cost / call-count estimate (Change 6, optional helper).

Sums token estimates across the corpus and reports the projected number of
model calls before committing to a long run. With the merged single-call
extractor the floor is one flash + one strong call per document; the fan-out
fallback adds calls only for documents that fail validation.
"""

from __future__ import annotations

from .config import SHORT_DOC_TOKEN_THRESHOLD
from .loader import estimate_tokens, extract_text
from .normalize import canonicalize


def estimate_corpus(doc_paths: list[str]) -> dict:
    total_tokens = 0
    long_docs = 0
    failed = 0
    for p in doc_paths:
        try:
            tokens = estimate_tokens(canonicalize(extract_text(p)))
        except Exception:  # noqa: BLE001 - count unreadable docs separately
            failed += 1
            continue
        total_tokens += tokens
        if tokens > SHORT_DOC_TOKEN_THRESHOLD:
            long_docs += 1

    n = len(doc_paths) - failed
    return {
        "documents": len(doc_paths),
        "readable": n,
        "unreadable": failed,
        "long_docs": long_docs,
        "total_input_tokens": total_tokens,
        # Floor: 1 flash (long docs only) + 1 strong per readable doc.
        "min_flash_calls": long_docs,
        "min_strong_calls": n,
        "min_total_calls": long_docs + n,
    }


def format_estimate(est: dict) -> str:
    return (
        f"Documents: {est['documents']} "
        f"({est['readable']} readable, {est['unreadable']} unreadable)\n"
        f"Long docs (use locate): {est['long_docs']}\n"
        f"Total input tokens (approx): {est['total_input_tokens']:,}\n"
        f"Min model calls: {est['min_total_calls']} "
        f"({est['min_flash_calls']} flash + {est['min_strong_calls']} strong), "
        "plus fallback/retry on any failures."
    )
