"""Paragraph segmentation: PDF page blocks must split into anchorable spans."""

from __future__ import annotations

from qcaass_extraction.loader import (
    _block_text,
    _collect_boilerplate,
    _keep_block,
    _reading_order,
    split_paragraphs,
)

_PAGE_W = 595.0

_PAGE_H = 842.0


def _block(text, y0, y1, x0=78, x1=523, dir=(1.0, 0.0)):
    """Build a minimal PyMuPDF-style dict text block for filtering tests."""
    return {
        "type": 0,
        "bbox": (x0, y0, x1, y1),
        "lines": [{"dir": dir, "spans": [{"text": text}]}],
    }


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


def test_recurring_top_band_header_dropped_oneoff_title_kept():
    # Running header "HEVIA et al." in the top band on two pages -> boilerplate.
    header = lambda: _block("HEVIA et al.", 20, 35)
    title = _block("References", 74, 92)  # top band but appears once
    pages = [[header()], [header()], [title]]
    boilerplate = _collect_boilerplate(pages, _PAGE_H)
    assert not _keep_block(header(), _PAGE_H, boilerplate)
    assert _keep_block(title, _PAGE_H, boilerplate)


def test_rotated_watermark_dropped():
    watermark = _block(
        "arXiv:2309.11926v1 [cs.SE] 21 Sep 2023", 265, 610, x0=11, x1=38, dir=(0.0, -1.0)
    )
    assert not _keep_block(watermark, _PAGE_H, _collect_boilerplate([[watermark]], _PAGE_H))


def test_bare_page_number_dropped_even_when_unique():
    page_num = _block("1521", 805, 820, x0=295, x1=300)  # footer band, digits only
    boilerplate = _collect_boilerplate([[page_num]], _PAGE_H)
    assert "1521" not in {*boilerplate}  # normalizes to empty, not a recurring key
    assert not _keep_block(page_num, _PAGE_H, boilerplate)


def test_body_block_always_kept():
    body = _block("Quantum microservices decompose the system into ...", 300, 360)
    assert _keep_block(body, _PAGE_H, set())


def _ordered_text(blocks):
    return [_block_text(b) for b in _reading_order(blocks, _PAGE_W)]


def test_two_column_reads_each_column_top_to_bottom():
    # Content-stream order interleaves columns (L-top, R-top, L-bot, R-bot).
    # Reading order must finish the left column before the right.
    blocks = [
        _block("left top", 100, 130, x0=50, x1=280),
        _block("right top", 100, 130, x0=310, x1=540),
        _block("left bottom", 140, 170, x0=50, x1=280),
        _block("right bottom", 140, 170, x0=310, x1=540),
    ]
    assert _ordered_text(blocks) == [
        "left top",
        "left bottom",
        "right top",
        "right bottom",
    ]


def test_full_width_block_bands_the_columns():
    # A page-spanning title above two columns reads first; a full-width figure
    # between bands separates the upper columns from the lower ones.
    blocks = [
        _block("right top", 120, 150, x0=310, x1=540),
        _block("TITLE", 40, 70, x0=50, x1=540),
        _block("left top", 120, 150, x0=50, x1=280),
        _block("spanning figure", 200, 240, x0=50, x1=540),
        _block("left bottom", 300, 330, x0=50, x1=280),
        _block("right bottom", 300, 330, x0=310, x1=540),
    ]
    assert _ordered_text(blocks) == [
        "TITLE",
        "left top",
        "right top",
        "spanning figure",
        "left bottom",
        "right bottom",
    ]


def test_single_column_preserves_vertical_order():
    blocks = [
        _block("para one", 100, 140),
        _block("para two", 150, 190),
        _block("para three", 200, 240),
    ]
    assert _ordered_text(blocks) == ["para one", "para two", "para three"]
