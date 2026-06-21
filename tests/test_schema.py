"""Build order step 1: instantiate every model with example values."""

from __future__ import annotations

from qcaass_extraction.schema import (
    empty_algorithms,
    empty_architecture,
    empty_challenges,
    empty_general,
    empty_overview,
)


def test_sample_record_roundtrips(sample_record):
    dumped = sample_record.model_dump()
    assert dumped["tool_id"] == "T000"
    assert dumped["algorithms"]["algorithms"][0]["name"] == "Grover search"


def test_empty_defaults_are_not_stated():
    assert empty_general().source_type.value == "Not stated"
    assert empty_overview().automation_level.value == "Not stated"
    assert empty_architecture().orchestrator.value == "Not stated"
    assert empty_algorithms().offers_algorithms == "Not stated"
    assert empty_challenges().challenges == []
