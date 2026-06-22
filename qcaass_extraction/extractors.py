"""Parallel strong-model extractor nodes (Section 5 of the blueprint).

Four nodes reached by plain fan-out edges. Each writes a distinct state key,
so they run concurrently with no reducer. Parse failures are caught, a safe
empty default is written, and the failure is recorded in `parse_failures`
(merged by a dict reducer) so the validator can route a retry.
"""

from __future__ import annotations

from .config import CATEGORIES
from .config import get_strong_model
from .prompts import (
    CATEGORY_INSTRUCTIONS,
    MERGED_INSTRUCTION,
    STRICT_RETRY_SUFFIX,
    STRONG_SYSTEM_GUARDRAILS,
)
from .schema import (
    AlgorithmsSection,
    Architecture,
    ChallengesSection,
    FullExtraction,
    GeneralAndOverview,
    empty_algorithms,
    empty_architecture,
    empty_challenges,
    empty_general,
    empty_overview,
)
from .state import ExtractionState


def _spans_text(state: ExtractionState, category: str) -> str:
    spans = state.get("located_spans", {}).get(category, [])
    return "\n\n".join(spans)


def _merged_spans_text(state: ExtractionState) -> str:
    """Union of every category's spans, de-duplicated, in first-seen order.

    The merged call needs all spans at once. Short-doc bypass populates each
    category with the same canonical text, so de-duplication collapses that to
    a single copy instead of repeating the whole document five times.
    """
    located = state.get("located_spans", {}) or {}
    seen: set[str] = set()
    ordered: list[str] = []
    for cat in CATEGORIES:
        for span in located.get(cat, []):
            if span not in seen:
                seen.add(span)
                ordered.append(span)
    return "\n\n".join(ordered)


def extract_merged(state: ExtractionState) -> dict:
    """Default path: one structured-output call returns the whole record.

    On parse failure every category gets a safe empty default plus a recorded
    ``parse_failures`` reason, so the validator routes each into its focused
    fallback extractor.
    """
    spans = _merged_spans_text(state)
    try:
        res: FullExtraction = _run_structured(
            FullExtraction, MERGED_INSTRUCTION, spans, retry=False
        )
        return {
            "general": res.general,
            "overview": res.overview,
            "architecture": res.architecture,
            "algorithms": res.algorithms,
            "challenges": res.challenges,
            "parse_failures": {cat: "" for cat in CATEGORIES},
        }
    except Exception as exc:  # noqa: BLE001 - parse-failure containment
        return {
            "general": empty_general(),
            "overview": empty_overview(),
            "architecture": empty_architecture(),
            "algorithms": empty_algorithms(),
            "challenges": empty_challenges(),
            "parse_failures": {cat: str(exc) for cat in CATEGORIES},
        }


def _is_retry(state: ExtractionState, category: str) -> bool:
    return (state.get("retry_counts") or {}).get(category, 0) > 0


def _run_structured(model_cls, instruction: str, spans: str, retry: bool):
    """Invoke the strong model with structured output. Raises on failure."""
    system = STRONG_SYSTEM_GUARDRAILS + "\n\n" + instruction
    if retry:
        system += STRICT_RETRY_SUFFIX
    llm = get_strong_model().with_structured_output(model_cls)
    user = f"Spans:\n\n{spans}" if spans else "Spans:\n\n(none provided)"
    result = llm.invoke(
        [{"role": "system", "content": system}, {"role": "user", "content": user}]
    )
    if result is None:
        raise ValueError("structured output returned None")
    return result


def extract_general_and_overview(state: ExtractionState) -> dict:
    cat = "general"  # bundled call keyed under both general+overview
    spans = _spans_text(state, "general") + "\n\n" + _spans_text(state, "overview")
    try:
        res: GeneralAndOverview = _run_structured(
            GeneralAndOverview,
            CATEGORY_INSTRUCTIONS["general_overview"],
            spans,
            _is_retry(state, "general") or _is_retry(state, "overview"),
        )
        return {
            "general": res.general,
            "overview": res.overview,
            "parse_failures": {"general": "", "overview": ""},
        }
    except Exception as exc:  # noqa: BLE001 - parse-failure containment
        return {
            "general": empty_general(),
            "overview": empty_overview(),
            "parse_failures": {"general": str(exc), "overview": str(exc)},
        }


def extract_architecture(state: ExtractionState) -> dict:
    try:
        res = _run_structured(
            Architecture,
            CATEGORY_INSTRUCTIONS["architecture"],
            _spans_text(state, "architecture"),
            _is_retry(state, "architecture"),
        )
        return {"architecture": res, "parse_failures": {"architecture": ""}}
    except Exception as exc:  # noqa: BLE001
        return {
            "architecture": empty_architecture(),
            "parse_failures": {"architecture": str(exc)},
        }


def extract_algorithms(state: ExtractionState) -> dict:
    try:
        res = _run_structured(
            AlgorithmsSection,
            CATEGORY_INSTRUCTIONS["algorithms"],
            _spans_text(state, "algorithms"),
            _is_retry(state, "algorithms"),
        )
        return {"algorithms": res, "parse_failures": {"algorithms": ""}}
    except Exception as exc:  # noqa: BLE001
        return {
            "algorithms": empty_algorithms(),
            "parse_failures": {"algorithms": str(exc)},
        }


def extract_challenges(state: ExtractionState) -> dict:
    try:
        res = _run_structured(
            ChallengesSection,
            CATEGORY_INSTRUCTIONS["challenges"],
            _spans_text(state, "challenges"),
            _is_retry(state, "challenges"),
        )
        return {"challenges": res, "parse_failures": {"challenges": ""}}
    except Exception as exc:  # noqa: BLE001
        return {
            "challenges": empty_challenges(),
            "parse_failures": {"challenges": str(exc)},
        }


# category name -> extractor node name (for the retry router).
CATEGORY_TO_NODE = {
    "general": "extract_general_and_overview",
    "overview": "extract_general_and_overview",
    "architecture": "extract_architecture",
    "algorithms": "extract_algorithms",
    "challenges": "extract_challenges",
}
