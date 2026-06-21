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

# LangChain `init_chat_model` identifiers. Override via env to switch providers.
FLASH_MODEL = os.getenv("FLASH_MODEL", "google_genai:gemini-3.5-flash")
STRONG_MODEL = os.getenv("STRONG_MODEL", "openai:gpt-5.4-2026-03-05")
