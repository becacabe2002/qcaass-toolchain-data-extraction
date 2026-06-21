"""Deterministic re-anchor node (Section 5 of the blueprint).

Fuzzy-match each paragraph the flash model returned back into the canonical
source and substitute the exact source slice, so downstream extractors only
ever see verbatim canonical text.
"""

from __future__ import annotations

import logging

from rapidfuzz import fuzz, process

from .config import REANCHOR_THRESHOLD
from .state import ExtractionState

logger = logging.getLogger(__name__)


def reanchor(state: ExtractionState) -> dict:
    raw_paras = state["raw_paragraphs"]
    fixed: dict[str, list[str]] = {}
    dropped: list[str] = []
    for cat, paras in state["located_spans"].items():
        keep: list[str] = []
        for p in paras:
            # partial_ratio aligns a short located span against the best-matching
            # window of a longer source unit, so length mismatch no longer sinks
            # an otherwise-good match (fuzz.ratio is length-sensitive).
            match = process.extractOne(p, raw_paras, scorer=fuzz.partial_ratio)
            if match and match[1] >= REANCHOR_THRESHOLD:
                canonical = raw_paras[match[2]]  # canonical slice, not model text
                if canonical not in keep:  # de-dup repeated anchors
                    keep.append(canonical)
            else:
                dropped.append(p)
        fixed[cat] = keep
        logger.info(
            "reanchor[%s]: kept %d, dropped %d", cat, len(keep), len(paras) - len(keep)
        )
    return {"located_spans": fixed, "reanchor_dropped": dropped}
