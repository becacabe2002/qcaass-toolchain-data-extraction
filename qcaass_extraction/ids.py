"""Stable, content-derived document identifiers.

The blueprint's index-based ``T{i:03d}`` shifts every id when the corpus is
reordered or grown, which breaks resume and cross-run comparison at scale. A
content hash is stable across reorderings and renames-with-same-content, so a
finished document keeps its id (and its checkpoint) no matter how the batch is
re-invoked.
"""

from __future__ import annotations

import hashlib

_HASH_LEN = 10  # 40 bits of sha1 hex; ample for a few-hundred-doc corpus.


def tool_id(path: str) -> str:
    """Return a stable ``T_<sha1[:10]>`` id derived from the file's bytes."""
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"T_{h.hexdigest()[:_HASH_LEN]}"
