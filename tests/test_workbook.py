"""Build order step 3: flatten_* + write_workbook with mocked records."""

from __future__ import annotations

import os

import pandas as pd

from qcaass_extraction.workbook import (
    flatten_algo_rows,
    flatten_challenge_rows,
    flatten_tool_row,
    write_workbook,
)


def test_flatten_tool_row(sample_record):
    row = flatten_tool_row(sample_record)
    assert row["tool_id"] == "T000"
    assert row["tool_name"] == "Qubitron"
    assert row["orchestrator_value"] == "Yes"
    assert row["offers_algorithms_value"] == "Yes"
    assert "user_interface_evidence" in row


def test_flatten_child_rows(sample_record):
    assert len(flatten_algo_rows(sample_record)) == 1
    assert flatten_algo_rows(sample_record)[0]["algorithm_name"] == "Grover search"
    assert len(flatten_challenge_rows(sample_record)) == 1
    assert flatten_challenge_rows(sample_record)[0]["category"] == "Usability"


def test_write_workbook_three_sheets(sample_record, tmp_path):
    out = str(tmp_path / "out.xlsx")
    write_workbook([sample_record], out)
    assert os.path.exists(out)
    assert not os.path.exists(out + ".tmp.xlsx")  # atomic swap cleaned up

    xls = pd.ExcelFile(out)
    assert xls.sheet_names == ["tools", "algorithms", "challenges"]
    tools = pd.read_excel(out, sheet_name="tools")
    assert tools.loc[0, "tool_name"] == "Qubitron"


def test_write_empty_workbook_has_headers(tmp_path):
    out = str(tmp_path / "empty.xlsx")
    write_workbook([], out)
    tools = pd.read_excel(out, sheet_name="tools")
    assert "tool_id" in tools.columns  # headers present even with no rows
    assert len(tools) == 0
