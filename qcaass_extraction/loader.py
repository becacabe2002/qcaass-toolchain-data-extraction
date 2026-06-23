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

# Header/footer margin bands as a fraction of page height. A text block whose
# box sits within the top/bottom band is a running-header/footer candidate.
_HEADER_BAND = float(os.getenv("PDF_HEADER_BAND", "0.10"))
_FOOTER_BAND = float(os.getenv("PDF_FOOTER_BAND", "0.10"))
# A margin-band line is treated as boilerplate once it recurs on at least this
# many distinct pages (running headers repeat; one-off titles do not).
_BOILERPLATE_MIN_PAGES = int(os.getenv("PDF_BOILERPLATE_MIN_PAGES", "2"))

# Line writing direction for normal (horizontal, left-to-right) body text.
# Rotated side-margin watermarks (arXiv/Wiley download notices) carry a
# different unit vector, e.g. (0, -1) for bottom-to-top text.
_HORIZONTAL_DIR = (1.0, 0.0)

# A block spanning at least this fraction of the page width is treated as
# full-width (title, abstract, page-spanning figure/table) rather than column
# body. Full-width blocks break the column flow and read in plain top-to-bottom
# order; a single-column page is all "full-width" blocks and falls through to a
# straight vertical sort.
_FULLWIDTH_FRAC = float(os.getenv("PDF_FULLWIDTH_FRAC", "0.7"))

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"\d+")


def _norm_running(text: str) -> str:
    """Normalize a margin line for cross-page recurrence matching.

    Lowercase, drop digits, and strip non-alphanumerics so a running header
    (``HEVIA et al.``) matches itself across pages while per-page numbers
    (``1521``/``1522``) collapse to the empty string.
    """
    text = _DIGITS.sub("", text.lower())
    return _NON_ALNUM.sub("", text)


def _block_text(block: dict) -> str:
    """Concatenate all span text in a PyMuPDF dict block."""
    return "".join(
        span["text"] for line in block.get("lines", []) for span in line["spans"]
    )


def _block_dirs(block: dict) -> set:
    """Set of line writing-direction vectors in a block."""
    return {tuple(line.get("dir", _HORIZONTAL_DIR)) for line in block.get("lines", [])}


def _in_margin_band(bbox, page_h: float) -> bool:
    """True if a block's box lies in the top or bottom margin band."""
    y0, y1 = bbox[1], bbox[3]
    return y0 < _HEADER_BAND * page_h or y1 > (1.0 - _FOOTER_BAND) * page_h


def _collect_boilerplate(pages_blocks: list[list[dict]], page_h: float) -> set[str]:
    """Learn the set of recurring margin-band lines across pages.

    ``pages_blocks`` is one list of PyMuPDF dict text blocks per page. A
    normalized margin line is boilerplate when it is non-empty and appears on at
    least ``_BOILERPLATE_MIN_PAGES`` distinct pages.
    """
    pages_seen: dict[str, set[int]] = {}
    for pno, blocks in enumerate(pages_blocks):
        for block in blocks:
            if block.get("type", 0) != 0:
                continue
            if not _in_margin_band(block["bbox"], page_h):
                continue
            key = _norm_running(_block_text(block))
            if key:
                pages_seen.setdefault(key, set()).add(pno)
    return {k for k, pages in pages_seen.items() if len(pages) >= _BOILERPLATE_MIN_PAGES}


def _block_width(block: dict) -> float:
    """Horizontal extent of a block's bounding box."""
    x0, _, x1, _ = block["bbox"]
    return x1 - x0


def _columnize(blocks: list[dict]) -> list[dict]:
    """Order a horizontal band of column blocks left-to-right, top-to-bottom.

    Blocks whose x-ranges overlap belong to the same column; greedy grouping by
    horizontal overlap recovers a 1-, 2-, or N-column layout without knowing the
    column count ahead of time. Columns emit left to right, blocks within a
    column top to bottom.
    """
    columns: list[dict] = []  # each: {"x0", "x1", "blocks": [...]}
    for block in sorted(blocks, key=lambda b: b["bbox"][0]):
        x0, x1 = block["bbox"][0], block["bbox"][2]
        for col in columns:
            if x0 < col["x1"] and x1 > col["x0"]:  # x-ranges intersect
                col["blocks"].append(block)
                col["x0"], col["x1"] = min(col["x0"], x0), max(col["x1"], x1)
                break
        else:
            columns.append({"x0": x0, "x1": x1, "blocks": [block]})
    columns.sort(key=lambda c: c["x0"])
    ordered: list[dict] = []
    for col in columns:
        ordered.extend(sorted(col["blocks"], key=lambda b: b["bbox"][1]))
    return ordered


def _reading_order(blocks: list[dict], page_w: float) -> list[dict]:
    """Sort kept body blocks into human reading order.

    Multi-column papers store blocks in content-stream order, which interleaves
    left- and right-column text and scrambles the extracted prose. Walk blocks
    top-to-bottom: full-width blocks (titles, page-spanning figures) split the
    page into horizontal bands, and each band of narrower blocks is ordered
    column by column. A single-column page is one band read straight down.
    """
    if len(blocks) <= 1 or page_w <= 0:
        return blocks
    full_width = _FULLWIDTH_FRAC * page_w
    ordered: list[dict] = []
    band: list[dict] = []
    for block in sorted(blocks, key=lambda b: b["bbox"][1]):
        if _block_width(block) >= full_width:
            if band:
                ordered.extend(_columnize(band))
                band = []
            ordered.append(block)
        else:
            band.append(block)
    if band:
        ordered.extend(_columnize(band))
    return ordered


def _keep_block(block: dict, page_h: float, boilerplate: set[str]) -> bool:
    """Decide whether a body block survives header/footer/watermark stripping."""
    if block.get("type", 0) != 0:
        return False
    # Rotated side-margin watermark (non-horizontal text direction).
    if _block_dirs(block) - {_HORIZONTAL_DIR}:
        return False
    if _in_margin_band(block["bbox"], page_h):
        key = _norm_running(_block_text(block))
        # Recurring running header/footer, or a per-page page number (digits
        # only, so the normalized key is empty).
        if key in boilerplate or not key:
            return False
    return True


def _extract_pdf(doc) -> str:
    """Extract body text from a PDF, dropping running headers/footers/watermarks.

    Two passes: first learn which margin-band lines recur across pages, then
    emit each page keeping only body blocks. Falls back to the raw page text if
    a page yields no kept blocks (never return empty from a page that had text).
    """
    pages_blocks = [page.get_text("dict")["blocks"] for page in doc]
    page_h = doc[0].rect.height if doc.page_count else 0.0
    boilerplate = _collect_boilerplate(pages_blocks, page_h)

    page_texts: list[str] = []
    for page, blocks in zip(doc, pages_blocks):
        h = page.rect.height
        kept = [b for b in blocks if _keep_block(b, h, boilerplate)]
        if kept:
            kept = _reading_order(kept, page.rect.width)
            page_texts.append("\n".join(_block_text(b) for b in kept))
        else:
            page_texts.append(page.get_text())
    return "\n\n".join(page_texts)


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
        import fitz  # PyMuPDF

        with fitz.open(path) as doc:
            return _extract_pdf(doc)
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
