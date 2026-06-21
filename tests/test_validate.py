"""Build order step 2: validator against hallucinations, short clauses, smart quotes."""

from __future__ import annotations

from qcaass_extraction.schema import (
    GeneralInfo,
    SourceTypeField,
    ContributionTypeField,
    AlgorithmsSection,
    QuantumAlgorithm,
)
from qcaass_extraction.validate import validate
from tests.conftest import SAMPLE_SOURCE


def _state(**outputs):
    base = {
        "raw_text": SAMPLE_SOURCE,
        "general": None,
        "overview": None,
        "architecture": None,
        "algorithms": None,
        "challenges": None,
        "parse_failures": {},
        "retry_counts": {},
    }
    base.update(outputs)
    return base


def test_all_empty_located_spans_flagged(sample_record):
    # Total locate/reanchor starvation -> "Not stated" everywhere is an artifact.
    out = validate(_state(
        general=sample_record.general,
        located_spans={c: [] for c in ("general", "overview", "architecture",
                                       "algorithms", "challenges")},
    ))
    assert any(e["field_path"] == "located_spans" for e in out["validation_errors"])
    # Not routed as a retry (a retry cannot conjure spans).
    assert out["categories_to_retry"] == []


def test_partial_located_spans_not_flagged(sample_record):
    # Some categories legitimately have no spans (e.g. no stated challenges).
    out = validate(_state(
        general=sample_record.general,
        located_spans={"general": ["x"], "overview": [], "architecture": [],
                       "algorithms": [], "challenges": []},
    ))
    assert not any(e["field_path"] == "located_spans" for e in out["validation_errors"])


def test_clean_record_has_no_errors(sample_record):
    out = validate(_state(
        general=sample_record.general,
        overview=sample_record.overview,
        architecture=sample_record.architecture,
        algorithms=sample_record.algorithms,
        challenges=sample_record.challenges,
    ))
    assert out["validation_errors"] == []
    assert out["categories_to_retry"] == []
    assert len(out["validation_offsets"]) > 0


def test_hallucinated_quote_flagged():
    g = GeneralInfo(
        tool_name="X", purpose="y",
        source_type=SourceTypeField(value="OS", evidence="this text never appears anywhere"),
        contribution_type=ContributionTypeField(value="Not stated"),
    )
    out = validate(_state(general=g))
    assert any(e["field_path"] == "general.source_type" for e in out["validation_errors"])
    assert "general" in out["categories_to_retry"]


def test_short_clause_rejected():
    g = GeneralInfo(
        tool_name="X", purpose="y",
        source_type=SourceTypeField(value="OS", evidence="open-source"),  # 1 word
        contribution_type=ContributionTypeField(value="Not stated"),
    )
    out = validate(_state(general=g))
    err = next(e for e in out["validation_errors"] if e["field_path"] == "general.source_type")
    assert "shorter than" in err["reason"]


def test_smart_quote_variant_matches():
    # Source uses straight quotes/words; evidence uses smart punctuation + caps.
    g = GeneralInfo(
        tool_name="X", purpose="y",
        source_type=SourceTypeField(
            value="OS",
            evidence="Qubitron is an OPEN-SOURCE toolchain for quantum software",
        ),
        contribution_type=ContributionTypeField(value="Not stated"),
    )
    out = validate(_state(general=g))
    assert all(e["field_path"] != "general.source_type" for e in out["validation_errors"])


def test_not_stated_with_empty_evidence_is_legitimate():
    g = GeneralInfo(
        tool_name="X", purpose="y",
        source_type=SourceTypeField(value="Not stated"),
        contribution_type=ContributionTypeField(value="Not stated"),
    )
    out = validate(_state(general=g))
    assert out["validation_errors"] == []


def test_coded_value_without_evidence_flagged():
    g = GeneralInfo(
        tool_name="X", purpose="y",
        source_type=SourceTypeField(value="OS", evidence=""),  # value but no quote
        contribution_type=ContributionTypeField(value="Not stated"),
    )
    out = validate(_state(general=g))
    assert any("carries no evidence" in e["reason"] for e in out["validation_errors"])


def test_retry_budget_increments_then_exhausts():
    g = GeneralInfo(
        tool_name="X", purpose="y",
        source_type=SourceTypeField(value="OS", evidence="this text never appears anywhere"),
        contribution_type=ContributionTypeField(value="Not stated"),
    )
    first = validate(_state(general=g))
    assert first["categories_to_retry"] == ["general"]
    assert first["retry_counts"]["general"] == 1

    second = validate(_state(general=g, retry_counts=first["retry_counts"]))
    assert second["categories_to_retry"] == []  # budget exhausted
    assert second["validation_errors"]  # still reported -> needs_review later


def test_parse_failure_routes_retry():
    out = validate(_state(parse_failures={"architecture": "boom"}))
    assert "architecture" in out["categories_to_retry"]
    assert any("parse failure" in e["reason"] for e in out["validation_errors"])
