"""CLI entry point.

    python -m qcaass_extraction <out.xlsx> <doc1> [doc2 ...]
    python -m qcaass_extraction <out.xlsx> --dir <folder>
    python -m qcaass_extraction <out.xlsx> --dir <folder> --rerun all
    python -m qcaass_extraction <out.xlsx> --dir <folder> --rerun status:failed
    python -m qcaass_extraction <out.xlsx> --dir <folder> --estimate
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys

from dotenv import load_dotenv

from .config import DEFAULT_CONCURRENCY, DEFAULT_OUT_DIR
from .driver import estimate_corpus, format_estimate
from .driver import run_corpus


def _collect_docs(args) -> list[str]:
    paths: list[str] = list(args.docs)
    if args.dir:
        for ext in ("*.pdf", "*.html", "*.htm", "*.txt", "*.md"):
            paths.extend(glob.glob(os.path.join(args.dir, ext)))
    return sorted(set(paths))


def _parse_rerun(value: str):
    """resume | all | status:<x> stay as strings; comma-lists become id sets."""
    if value in ("resume", "all") or value.startswith("status:"):
        return value
    return {v.strip() for v in value.split(",") if v.strip()}


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(prog="qcaass_extraction")
    parser.add_argument("out_path", help="Output .xlsx workbook path")
    parser.add_argument("docs", nargs="*", help="Document paths")
    parser.add_argument("--dir", help="Folder to scan for documents")
    parser.add_argument(
        "--rerun", type=_parse_rerun, default="resume",
        help="resume (default) | all | status:failed | status:needs_review | "
             "comma-separated tool_ids",
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help="Documents processed in parallel (default %(default)s)",
    )
    parser.add_argument(
        "--out-dir", default=DEFAULT_OUT_DIR,
        help="Checkpoint/manifest directory enabling resume (default %(default)s)",
    )
    parser.add_argument(
        "--estimate", action="store_true",
        help="Print a cost/call-count estimate and exit without calling models",
    )
    args = parser.parse_args(argv)

    docs = _collect_docs(args)
    if not docs:
        parser.error("no documents given (pass paths or --dir)")

    if args.estimate:
        print(format_estimate(estimate_corpus(docs)))
        return 0

    run_corpus(
        docs, args.out_path,
        concurrency=args.concurrency, out_dir=args.out_dir, rerun=args.rerun,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
