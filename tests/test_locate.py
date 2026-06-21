"""locate parsing: tolerate fences/prose, surface failures instead of swallowing."""

from __future__ import annotations

from qcaass_extraction.config import CATEGORIES
from qcaass_extraction.locate import _parse_located


def test_plain_json_object_parsed():
    out = _parse_located('{"general": ["a snippet"], "challenges": ["x"]}')
    assert out["general"] == ["a snippet"]
    assert out["overview"] == []  # missing keys default empty


def test_markdown_fenced_json_parsed():
    out = _parse_located('```json\n{"general": ["snippet"]}\n```')
    assert out["general"] == ["snippet"]


def test_prose_wrapped_json_parsed():
    raw = 'Here are the passages I found:\n{"architecture": ["orchestrator span"]}\nDone.'
    out = _parse_located(raw)
    assert out["architecture"] == ["orchestrator span"]


def test_single_quoted_python_dict_parsed():
    # Gemini often emits single-quoted, Python-style output.
    out = _parse_located("{'general': ['a snippet'], 'overview': ['b snippet']}")
    assert out["general"] == ["a snippet"]
    assert out["overview"] == ["b snippet"]


def test_string_value_coerced_to_list():
    out = _parse_located('{"algorithms": "single snippet"}')
    assert out["algorithms"] == ["single snippet"]


def test_unparseable_returns_all_empty():
    out = _parse_located("this is not json at all")
    assert out == {cat: [] for cat in CATEGORIES}
