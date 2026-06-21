"""Lazy LLM factory. Importing this module must not require API keys."""

from __future__ import annotations

from functools import lru_cache

from .config import FLASH_MODEL, STRONG_MODEL


@lru_cache(maxsize=None)
def get_flash_model():
    from langchain.chat_models import init_chat_model

    # Locate over-retrieves short snippets for five categories; give it ample
    # output budget so the JSON object is never truncated mid-array.
    return init_chat_model(FLASH_MODEL, temperature=0, max_tokens=8192)


@lru_cache(maxsize=None)
def get_strong_model():
    from langchain.chat_models import init_chat_model

    # Extraction is mechanical (copy verbatim quotes) — disable reasoning.
    # gpt-5.4 valid values: none/low/medium/high/xhigh (no "minimal").
    return init_chat_model(STRONG_MODEL, reasoning_effort="none")
