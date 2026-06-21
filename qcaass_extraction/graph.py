"""LangGraph wiring (Section 2 architecture)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .assemble import assemble
from .config import SHORT_DOC_TOKEN_THRESHOLD
from .extractors import (
    CATEGORY_TO_NODE,
    extract_algorithms,
    extract_architecture,
    extract_challenges,
    extract_general_and_overview,
)
from .loader import load_doc
from .locate import locate_spans
from .reanchor import reanchor
from .state import ExtractionState
from .validate import validate

EXTRACTOR_NODES = [
    "extract_general_and_overview",
    "extract_architecture",
    "extract_algorithms",
    "extract_challenges",
]


def route_after_load(state: ExtractionState):
    """Long doc -> locate; short doc -> fan out straight to extractors."""
    if state["token_count"] > SHORT_DOC_TOKEN_THRESHOLD:
        return ["locate_spans"]
    return list(EXTRACTOR_NODES)


def route_after_validate(state: ExtractionState):
    """Retry the failed categories' extractors, else assemble."""
    to_retry = state.get("categories_to_retry") or []
    nodes = sorted({CATEGORY_TO_NODE[c] for c in to_retry})
    return nodes or ["assemble"]


def build_graph():
    g = StateGraph(ExtractionState)

    g.add_node("load_doc", load_doc)
    g.add_node("locate_spans", locate_spans)
    g.add_node("reanchor", reanchor)
    g.add_node("extract_general_and_overview", extract_general_and_overview)
    g.add_node("extract_architecture", extract_architecture)
    g.add_node("extract_algorithms", extract_algorithms)
    g.add_node("extract_challenges", extract_challenges)
    g.add_node("validate", validate)
    g.add_node("assemble", assemble)

    g.add_edge(START, "load_doc")
    g.add_conditional_edges(
        "load_doc", route_after_load, ["locate_spans", *EXTRACTOR_NODES]
    )
    g.add_edge("locate_spans", "reanchor")
    for node in EXTRACTOR_NODES:
        g.add_edge("reanchor", node)
        g.add_edge(node, "validate")
    g.add_conditional_edges(
        "validate", route_after_validate, [*EXTRACTOR_NODES, "assemble"]
    )
    g.add_edge("assemble", END)

    return g.compile()
