"""Document loading, canonicalization, and stable document IDs."""

from __future__ import annotations

import hashlib
import os
import re

from .config import CATEGORIES, SHORT_DOC_TOKEN_THRESHOLD
from .normalize import canonicalize
from .state import ExtractionState

_HASH_LEN = 10


def tool_id(path: str) -> str:
    """Return a stable ``T_<sha1[:10]>`` id derived from the file's bytes."""
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"T_{h.hexdigest()[:_HASH_LEN]}"

# Approx. paragraph window size (chars) when regrouping sentences. A few
# sentences per span keeps anchored slices small enough to save strong-model
# tokens while preserving local context.
_PARA_WINDOW_CHARS = 400
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Below this many words of extracted text a document is treated as a failed
# load (likely a scanned/image-only PDF or a corrupt file) rather than fed to
# the model — extracting from near-nothing silently produces false "Not stated".
_MIN_DOC_WORDS = 50


class EmptyExtractionError(ValueError):
    """Raised when a document yields too little text to extract from."""


def estimate_tokens(text: str) -> int:
    """Cheap token estimate. Uses tiktoken when available, else ~4 chars/token."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(len(text) // 4, len(text.split()))


def extract_text(path: str) -> str:
    """Extract raw text from a PDF, HTML, or plain-text file."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if ext in (".html", ".htm"):
        from bs4 import BeautifulSoup

        with open(path, encoding="utf-8", errors="replace") as fh:
            soup = BeautifulSoup(fh.read(), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text("\n")
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def split_paragraphs(text: str) -> list[str]:
    """Split canonical text into paragraph-sized spans for re-anchoring.

    PDF extraction wraps lines within a page on single ``\\n`` and separates
    pages on ``\\n\\n``, so a naive blank-line split yields page-sized blocks.
    Those defeat the re-anchor step (a short located paragraph never scores
    close to a whole page). Instead we collapse each block's internal line
    wraps, split it into sentences, and regroup sentences into ~paragraph
    windows so located spans can anchor to a tight canonical slice.
    """
    spans: list[str] = []
    for block in text.split("\n\n"):
        block = re.sub(r"\s+", " ", block).strip()
        if not block:
            continue
        sentences = [s for s in _SENTENCE_SPLIT.split(block) if s]
        window = ""
        for sentence in sentences:
            window = f"{window} {sentence}".strip() if window else sentence
            if len(window) >= _PARA_WINDOW_CHARS:
                spans.append(window)
                window = ""
        if window:
            spans.append(window)
    return spans


def load_doc(state: ExtractionState) -> dict:
    path = state["source_doc_path"]
    try:
        raw = extract_text(path)
    except Exception as exc:  # noqa: BLE001 - surface parse errors as a failed load
        raise EmptyExtractionError(f"could not read {path}: {exc}") from exc
    canonical = canonicalize(raw)
    if len(canonical.split()) < _MIN_DOC_WORDS:
        raise EmptyExtractionError(
            f"only {len(canonical.split())} words extracted from {path} "
            "(scanned/image PDF or corrupt file?)"
        )
    paragraphs = split_paragraphs(canonical)
    token_count = estimate_tokens(canonical)

    out: dict = {
        "raw_text": canonical,
        "raw_paragraphs": paragraphs,
        "token_count": token_count,
    }
    # Short-document bypass: spans are already canonical (they are the source).
    if token_count <= SHORT_DOC_TOKEN_THRESHOLD:
        out["located_spans"] = {cat: [canonical] for cat in CATEGORIES}
        out["reanchor_dropped"] = []
    return out
