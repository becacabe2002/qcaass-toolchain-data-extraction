"""Batch driver (Section 7 of the blueprint)."""

from __future__ import annotations

import logging

from .graph import build_graph
from .schema import ToolRecord
from .state import ExtractionState
from .workbook import write_workbook

logger = logging.getLogger(__name__)


def build_initial_state(tool_id: str, source_doc_path: str) -> ExtractionState:
    return {
        "tool_id": tool_id,
        "source_doc_path": source_doc_path,
        "located_spans": {},
        "reanchor_dropped": [],
        "general": None,
        "overview": None,
        "architecture": None,
        "algorithms": None,
        "challenges": None,
        "parse_failures": {},
        "validation_errors": [],
        "validation_offsets": [],
        "categories_to_retry": [],
        "retry_counts": {},
        "record": None,
    }


def run_corpus(doc_paths: list[str], out_path: str) -> list[ToolRecord]:
    graph = build_graph()
    records: list[ToolRecord] = []
    for i, p in enumerate(doc_paths):
        init = build_initial_state(tool_id=f"T{i:03d}", source_doc_path=p)
        logger.info("Extracting %s (%s)", init["tool_id"], p)
        try:
            final = graph.invoke(init)
        except Exception:  # noqa: BLE001 - keep the batch going
            logger.exception("Graph failed for %s", p)
            continue
        if final.get("record") is not None:
            if final["record"].needs_review:
                logger.warning("%s flagged needs_review", init["tool_id"])
            if final.get("reanchor_dropped"):
                logger.warning(
                    "%s dropped %d span(s) at reanchor",
                    init["tool_id"], len(final["reanchor_dropped"]),
                )
            records.append(final["record"])
    write_workbook(records, out_path)
    logger.info("Wrote %d record(s) to %s", len(records), out_path)
    return records
