"""CLI entry point.

    python -m qcaass_extraction <out.xlsx> <doc1> [doc2 ...]
    python -m qcaass_extraction <out.xlsx> --dir <folder>
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys

from dotenv import load_dotenv

from .driver import run_corpus


def _collect_docs(args) -> list[str]:
    paths: list[str] = list(args.docs)
    if args.dir:
        for ext in ("*.pdf", "*.html", "*.htm", "*.txt", "*.md"):
            paths.extend(glob.glob(os.path.join(args.dir, ext)))
    return sorted(set(paths))


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(prog="qcaass_extraction")
    parser.add_argument("out_path", help="Output .xlsx workbook path")
    parser.add_argument("docs", nargs="*", help="Document paths")
    parser.add_argument("--dir", help="Folder to scan for documents")
    args = parser.parse_args(argv)

    docs = _collect_docs(args)
    if not docs:
        parser.error("no documents given (pass paths or --dir)")

    run_corpus(docs, args.out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
