"""Document loading + canonicalization (Section 5 `load_doc`)."""

from __future__ import annotations

import os
import re

from .config import CATEGORIES, SHORT_DOC_TOKEN_THRESHOLD
from .normalize import canonicalize
from .state import ExtractionState

# Approx. paragraph window size (chars) when regrouping sentences. A few
# sentences per span keeps anchored slices small enough to save strong-model
# tokens while preserving local context.
_PARA_WINDOW_CHARS = 400
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


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
    raw = extract_text(state["source_doc_path"])
    canonical = canonicalize(raw)
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
