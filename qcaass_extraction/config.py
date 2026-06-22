"""Central configuration: categories, thresholds, model names."""

from __future__ import annotations

import os

# The five extraction categories used by locate / fan-out / retry routing.
CATEGORIES = ["general", "overview", "architecture", "algorithms", "challenges"]

# Documents below this token count skip locate_spans + reanchor (their spans
# are already canonical) and fan out directly to the extractors.
SHORT_DOC_TOKEN_THRESHOLD = int(os.getenv("SHORT_DOC_TOKEN_THRESHOLD", "10000"))

# rapidfuzz ratio threshold (0..100) for accepting a re-anchor match.
REANCHOR_THRESHOLD = float(os.getenv("REANCHOR_THRESHOLD", "85"))

# Minimum quote length (in words) for a verbatim evidence quote to be trusted.
MIN_QUOTE_WORDS = int(os.getenv("MIN_QUOTE_WORDS", "4"))

# One retry per category per document.
MAX_RETRIES_PER_CATEGORY = int(os.getenv("MAX_RETRIES_PER_CATEGORY", "1"))

# Number of documents processed concurrently by the batch driver. Tune to the
# API tier's TPM/RPM ceiling; start conservative.
DEFAULT_CONCURRENCY = int(os.getenv("CONCURRENCY", "5"))

# Where per-document checkpoints and the run manifest live (enables resume).
DEFAULT_OUT_DIR = os.getenv("OUT_DIR", "runs/latest")

# Per-call transport retries (429 / throttle) with provider-side backoff. This
# is independent of the per-category validation retry budget above.
MAX_API_RETRIES = int(os.getenv("MAX_API_RETRIES", "6"))

# LangChain `init_chat_model` identifiers. Override via env to switch providers.
FLASH_MODEL = os.getenv("FLASH_MODEL", "google_genai:gemini-3.5-flash")
STRONG_MODEL = os.getenv("STRONG_MODEL", "openai:gpt-5.4-2026-03-05")

_flash_model = None
_strong_model = None


def get_flash_model():
    global _flash_model
    if _flash_model is None:
        from langchain.chat_models import init_chat_model
        _flash_model = init_chat_model(
            FLASH_MODEL, temperature=0, max_tokens=8192, max_retries=MAX_API_RETRIES
        )
    return _flash_model


def get_strong_model():
    global _strong_model
    if _strong_model is None:
        from langchain.chat_models import init_chat_model
        _strong_model = init_chat_model(
            STRONG_MODEL, reasoning_effort="none", max_retries=MAX_API_RETRIES
        )
    return _strong_model
