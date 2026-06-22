"""LangGraph wiring (Section 2 architecture)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .config import SHORT_DOC_TOKEN_THRESHOLD
from .extractors import (
    CATEGORY_TO_NODE,
    extract_algorithms,
    extract_architecture,
    extract_challenges,
    extract_general_and_overview,
    extract_merged,
)
from .loader import load_doc
from .locate import locate_spans, reanchor
from .schema import (
    ToolRecord,
    empty_algorithms,
    empty_architecture,
    empty_challenges,
    empty_general,
    empty_overview,
)
from .state import ExtractionState
from .validate import validate

# Focused per-category extractors. Reached only as the fallback path when the
# merged call's output fails validation (see route_after_validate).
def assemble(state: ExtractionState) -> dict:
    errors = state.get("validation_errors") or []
    record = ToolRecord(
        tool_id=state["tool_id"],
        source_doc_path=state["source_doc_path"],
        general=state.get("general") or empty_general(),
        overview=state.get("overview") or empty_overview(),
        architecture=state.get("architecture") or empty_architecture(),
        algorithms=state.get("algorithms") or empty_algorithms(),
        challenges=state.get("challenges") or empty_challenges(),
        needs_review=bool(errors),
        validation_errors=errors,
    )
    return {"record": record}


EXTRACTOR_NODES = [
    "extract_general_and_overview",
    "extract_architecture",
    "extract_algorithms",
    "extract_challenges",
]


def route_after_load(state: ExtractionState):
    """Long doc -> locate then merged; short doc -> straight to merged extract."""
    if state["token_count"] > SHORT_DOC_TOKEN_THRESHOLD:
        return "locate_spans"
    return "extract_merged"


def route_after_validate(state: ExtractionState):
    """Fall back to the failed categories' focused extractors, else assemble."""
    to_retry = state.get("categories_to_retry") or []
    nodes = sorted({CATEGORY_TO_NODE[c] for c in to_retry})
    return nodes or ["assemble"]


def build_graph():
    g = StateGraph(ExtractionState)

    g.add_node("load_doc", load_doc)
    g.add_node("locate_spans", locate_spans)
    g.add_node("reanchor", reanchor)
    g.add_node("extract_merged", extract_merged)
    g.add_node("extract_general_and_overview", extract_general_and_overview)
    g.add_node("extract_architecture", extract_architecture)
    g.add_node("extract_algorithms", extract_algorithms)
    g.add_node("extract_challenges", extract_challenges)
    g.add_node("validate", validate)
    g.add_node("assemble", assemble)

    g.add_edge(START, "load_doc")
    g.add_conditional_edges(
        "load_doc", route_after_load, ["locate_spans", "extract_merged"]
    )
    g.add_edge("locate_spans", "reanchor")
    # Default path: merged single call -> validate.
    g.add_edge("reanchor", "extract_merged")
    g.add_edge("extract_merged", "validate")
    # Fallback path: each focused extractor re-runs one category, then re-validates.
    for node in EXTRACTOR_NODES:
        g.add_edge(node, "validate")
    g.add_conditional_edges(
        "validate", route_after_validate, [*EXTRACTOR_NODES, "assemble"]
    )
    g.add_edge("assemble", END)

    return g.compile()
