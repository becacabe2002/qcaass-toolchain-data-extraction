"""Build order step 5: single-document end-to-end with the short-doc bypass.

The strong model is faked so no API key or network is needed; the rest of the
graph (bypass routing, fan-out, validate, assemble) runs for real.
"""

from __future__ import annotations

import pytest

from qcaass_extraction import build_graph, build_initial_state
from qcaass_extraction.schema import (
    AlgorithmsSection,
    Architecture,
    GeneralAndOverview,
    ChallengesSection,
)
from tests.conftest import SAMPLE_SOURCE


class _FakeStructured:
    def __init__(self, cls, record):
        self.cls = cls
        self.record = record

    def invoke(self, _messages):
        if self.cls is GeneralAndOverview:
            return GeneralAndOverview(
                general=self.record.general, overview=self.record.overview
            )
        if self.cls is Architecture:
            return self.record.architecture
        if self.cls is AlgorithmsSection:
            return self.record.algorithms
        if self.cls is ChallengesSection:
            return self.record.challenges
        raise AssertionError(f"unexpected cls {self.cls}")


class _FakeModel:
    def __init__(self, record):
        self.record = record

    def with_structured_output(self, cls):
        return _FakeStructured(cls, self.record)


@pytest.fixture
def doc_file(tmp_path):
    p = tmp_path / "qubitron.txt"
    p.write_text(SAMPLE_SOURCE, encoding="utf-8")
    return str(p)


def test_end_to_end_bypass(monkeypatch, doc_file, sample_record):
    monkeypatch.setattr(
        "qcaass_extraction.extractors.get_strong_model",
        lambda: _FakeModel(sample_record),
    )
    graph = build_graph()
    init = build_initial_state(tool_id="T000", source_doc_path=doc_file)
    final = graph.invoke(init)

    rec = final["record"]
    assert rec is not None
    assert rec.general.tool_name == "Qubitron"
    assert rec.algorithms.offers_algorithms == "Yes"
    assert rec.needs_review is False  # clean quotes -> no escalation
    assert final["validation_errors"] == []
    # Bypass: short doc never populated reanchor drops.
    assert final["reanchor_dropped"] == []
