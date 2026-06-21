"""assemble node (Section 5 of the blueprint)."""

from __future__ import annotations

from .schema import (
    ToolRecord,
    empty_algorithms,
    empty_architecture,
    empty_challenges,
    empty_general,
    empty_overview,
)
from .state import ExtractionState


def assemble(state: ExtractionState) -> dict:
    needs_review = bool(state.get("validation_errors"))
    record = ToolRecord(
        tool_id=state["tool_id"],
        source_doc_path=state["source_doc_path"],
        general=state.get("general") or empty_general(),
        overview=state.get("overview") or empty_overview(),
        architecture=state.get("architecture") or empty_architecture(),
        algorithms=state.get("algorithms") or empty_algorithms(),
        challenges=state.get("challenges") or empty_challenges(),
        needs_review=needs_review,
    )
    return {"record": record}
