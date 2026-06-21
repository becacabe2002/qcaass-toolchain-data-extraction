"""Build order step 4: reanchor recovers canonical text, drops fabrications."""

from __future__ import annotations

from qcaass_extraction.reanchor import reanchor

CANON_A = "It provides an orchestrator that schedules circuits across backends."
CANON_B = "Qubitron offers a built-in implementation of the Grover search algorithm."


def _state(located):
    return {"raw_paragraphs": [CANON_A, CANON_B], "located_spans": located}


def test_mangled_paragraph_recovers_canonical():
    # Model returned a lightly-mangled paraphrase of CANON_A.
    mangled = "it provides an orchestrator that schedules circuits across backend"
    out = reanchor(_state({"architecture": [mangled]}))
    assert out["located_spans"]["architecture"] == [CANON_A]
    assert out["reanchor_dropped"] == []


def test_fabricated_paragraph_dropped():
    bogus = "This sentence is wholly invented and matches nothing in the source corpus."
    out = reanchor(_state({"general": [bogus]}))
    assert out["located_spans"]["general"] == []
    assert bogus in out["reanchor_dropped"]


def test_exact_paragraph_passes_through():
    out = reanchor(_state({"algorithms": [CANON_B]}))
    assert out["located_spans"]["algorithms"] == [CANON_B]


def test_duplicate_anchors_deduped():
    out = reanchor(_state({"architecture": [CANON_A, CANON_A]}))
    assert out["located_spans"]["architecture"] == [CANON_A]


def test_short_span_anchors_into_large_block():
    # A short located span embedded in a much larger source unit must survive:
    # length-sensitive fuzz.ratio used to drop this; partial_ratio keeps it.
    big = (
        "Background and motivation are discussed across several sentences here. "
        + CANON_A
        + " Further unrelated trailing discussion continues at considerable length."
    )
    out = reanchor({"raw_paragraphs": [big], "located_spans": {"architecture": [CANON_A]}})
    assert out["located_spans"]["architecture"] == [big]
    assert out["reanchor_dropped"] == []
