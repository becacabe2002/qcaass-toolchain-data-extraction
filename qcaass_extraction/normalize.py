"""Text normalization shared by the loader, re-anchor, and validator."""

from __future__ import annotations

import re
import unicodedata

# Smart quotes / dashes -> ASCII equivalents.
_TRANSLATIONS = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "–": "-",
    "—": "-",
    "‐": "-",
    "‑": "-",
    "­": "",  # soft hyphen
    " ": " ",  # non-breaking space
}
_TRANS_TABLE = {ord(k): v for k, v in _TRANSLATIONS.items()}

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def canonicalize(text: str) -> str:
    """Loader-level normalization, preserving readable canonical text.

    Collapses whitespace, repairs hyphenated line breaks, normalizes smart
    quotes/dashes. The result is what every quote is later checked against.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_TRANS_TABLE)
    # Join words split across line breaks: "quan-\ntum" -> "quantum".
    text = re.sub(r"-\n\s*", "", text)
    # Normalize line endings; keep blank lines as paragraph separators.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of spaces/tabs but keep newlines for paragraph splitting.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def match_key(text: str) -> str:
    """Aggressive normalization for substring matching (validation only).

    Lowercase, strip punctuation/smart-quote variants, collapse all
    whitespace. Used identically on both the quote and the source.
    """
    text = unicodedata.normalize("NFC", text).translate(_TRANS_TABLE)
    text = text.lower()
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text)
    return text.strip()


def word_count(text: str) -> int:
    return len(text.split())
