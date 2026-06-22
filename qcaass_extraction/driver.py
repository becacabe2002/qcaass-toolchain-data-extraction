"""Batch driver (Section 7 of the blueprint), hardened for a 174-file corpus.

Cross-document concurrency, per-document checkpoint + resume, failure
isolation, and an explicit rerun policy. The per-document graph is unchanged;
only orchestration of many runs differs from the blueprint's serial loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable

from .checkpoint import CheckpointStore
from .config import DEFAULT_CONCURRENCY, DEFAULT_OUT_DIR
from .graph import build_graph
from .ids import tool_id as compute_tool_id
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


def select_targets(
    doc_paths: Iterable[str], rerun, store: CheckpointStore
) -> list[tuple[str, str]]:
    """Apply the rerun policy, returning the ``(tool_id, path)`` pairs to process.

    ``rerun`` is one of:
      - ``"resume"`` (default): skip docs that already have a checkpoint.
      - ``"all"``: reprocess everything; checkpoints are overwritten.
      - ``"status:failed"`` / ``"status:needs_review"``: reprocess only docs
        whose most recent manifest status matches.
      - an iterable of tool_ids: reprocess only those.
    """
    pairs = [(compute_tool_id(p), p) for p in doc_paths]

    if rerun == "all":
        return pairs
    if rerun == "resume" or rerun is None:
        return [(tid, p) for tid, p in pairs if not store.is_done(tid)]
    if isinstance(rerun, str) and rerun.startswith("status:"):
        want = rerun.split(":", 1)[1]
        last = store.last_status_by_id()
        return [(tid, p) for tid, p in pairs if last.get(tid) == want]
    # Explicit iterable of tool_ids.
    wanted = set(rerun)
    return [(tid, p) for tid, p in pairs if tid in wanted]


async def _process_one(graph, tid: str, path: str, store: CheckpointStore) -> None:
    start = time.perf_counter()
    try:
        final = await graph.ainvoke(build_initial_state(tid, path))
    except Exception as exc:  # noqa: BLE001 - isolate one bad doc from the batch
        logger.exception("Graph failed for %s (%s)", tid, path)
        store.log(tid, path, "failed", error=repr(exc),
                  duration_s=time.perf_counter() - start)
        return

    record = final.get("record")
    if record is None:
        store.log(tid, path, "failed", error="no record produced",
                  duration_s=time.perf_counter() - start)
        return

    dropped = len(final.get("reanchor_dropped") or [])
    status = "needs_review" if record.needs_review else "done"
    store.save_record(record)  # checkpoint immediately; overwrites prior id
    store.log(tid, path, status, duration_s=time.perf_counter() - start,
              reanchor_dropped=dropped)
    if record.needs_review:
        logger.warning("%s needs_review (%d error(s))", tid,
                       len(record.validation_errors))
    if dropped:
        logger.warning("%s dropped %d span(s) at reanchor", tid, dropped)


async def run_corpus_async(
    doc_paths: list[str],
    out_path: str,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    out_dir: str = DEFAULT_OUT_DIR,
    rerun="resume",
) -> list[ToolRecord]:
    graph = build_graph()
    store = CheckpointStore(out_dir)
    targets = select_targets(doc_paths, rerun, store)
    logger.info("Processing %d of %d doc(s) (rerun=%s, concurrency=%d)",
                len(targets), len(doc_paths), rerun, concurrency)

    sem = asyncio.Semaphore(concurrency)

    async def worker(tid: str, path: str) -> None:
        async with sem:
            logger.info("Extracting %s (%s)", tid, path)
            await _process_one(graph, tid, path, store)

    await asyncio.gather(*(worker(tid, p) for tid, p in targets))

    records = store.load_all_records()  # rebuild from every checkpoint on disk
    write_workbook(records, out_path)
    logger.info("Wrote %d record(s) to %s", len(records), out_path)
    return records


def run_corpus(
    doc_paths: list[str],
    out_path: str,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    out_dir: str = DEFAULT_OUT_DIR,
    rerun="resume",
) -> list[ToolRecord]:
    """Synchronous entry point wrapping the async driver."""
    return asyncio.run(
        run_corpus_async(
            doc_paths, out_path,
            concurrency=concurrency, out_dir=out_dir, rerun=rerun,
        )
    )
