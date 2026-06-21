"""Paragraph segmentation: PDF page blocks must split into anchorable spans."""

from __future__ import annotations

from qcaass_extraction.loader import split_paragraphs


def test_page_block_splits_into_multiple_small_spans():
    # A pypdf-style page block: many sentences, lines wrapped on single newlines,
    # no blank-line paragraph breaks. The old splitter returned this as ONE block.
    block = "\n".join(
        f"Sentence number {i} contributes additional context to the page block."
        for i in range(12)
    )
    spans = split_paragraphs(block)
    assert len(spans) > 1
    # Internal line wraps are collapsed so anchored slices are clean text.
    assert all("\n" not in s for s in spans)
    # No span balloons back to the whole page.
    assert all(len(s) < len(block) for s in spans)


def test_blank_separated_paragraphs_preserved():
    text = "First paragraph stays intact.\n\nSecond paragraph also stays intact."
    spans = split_paragraphs(text)
    assert "First paragraph stays intact." in spans
    assert "Second paragraph also stays intact." in spans


def test_empty_input_yields_no_spans():
    assert split_paragraphs("\n\n   \n\n") == []
