"""Local XLSX output (Section 7 of the blueprint).

Three sheets, long-format for one-to-many sections. Flatten functions are
pure (ToolRecord -> list[dict]) and unit-testable in isolation.
"""

from __future__ import annotations

import os

import pandas as pd
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from .schema import ARCHITECTURE_COMPONENTS, ToolRecord


def _clean(value):
    """Strip control characters openpyxl refuses to write to a worksheet."""
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


def _render_type_evidence(field) -> str:
    """Flatten per-type evidence into one cell: 'HL: quote | QI: quote'."""
    return " | ".join(f"{te.type}: {te.evidence}" for te in field.type_evidence)


def flatten_tool_row(r: ToolRecord) -> dict:
    """Sheet 1 `tools`: one row per document."""
    g, o, a = r.general, r.overview, r.architecture
    row: dict = {
        "tool_id": r.tool_id,
        "source_doc_path": r.source_doc_path,
        "tool_name": g.tool_name,
        "purpose": g.purpose,
        "source_type_value": g.source_type.value,
        "source_type_evidence": g.source_type.evidence,
        "contribution_type_value": g.contribution_type.value,
        "contribution_type_evidence": g.contribution_type.evidence,
        "input_instruction_value": o.input_instruction.value,
        "input_instruction_evidence": _render_type_evidence(o.input_instruction),
        "output_type_value": o.output_type.value,
        "output_type_evidence": _render_type_evidence(o.output_type),
        "automation_level_value": o.automation_level.value,
        "automation_level_evidence": o.automation_level.evidence,
        "evaluation_type_value": o.evaluation_type.value,
        "evaluation_type_evidence": o.evaluation_type.evidence,
        "design_principles": a.design_principles,
        "technological_foundation": a.technological_foundation,
    }
    for comp in ARCHITECTURE_COMPONENTS:
        field = getattr(a, comp)
        row[f"{comp}_value"] = field.value
        row[f"{comp}_evidence"] = field.evidence
    row["offers_algorithms_value"] = r.algorithms.offers_algorithms
    row["offers_algorithms_evidence"] = r.algorithms.overall_evidence
    row["needs_review"] = r.needs_review
    return row


def flatten_algo_rows(r: ToolRecord) -> list[dict]:
    """Sheet 2 `algorithms`: one row per offered algorithm."""
    return [
        {
            "tool_id": r.tool_id,
            "algorithm_name": alg.name,
            "algorithm_type": alg.algorithm_type,
            "evidence": alg.evidence,
        }
        for alg in r.algorithms.algorithms
    ]


def flatten_challenge_rows(r: ToolRecord) -> list[dict]:
    """Sheet 3 `challenges`: one row per challenge."""
    return [
        {
            "tool_id": r.tool_id,
            "statement": ch.statement,
            "category": ch.category,
            "category_evidence": ch.category_evidence,
            "evidence_strength": ch.evidence_strength,
            "strength_evidence": ch.strength_evidence,
        }
        for ch in r.challenges.challenges
    ]


def flatten_error_rows(r: ToolRecord) -> list[dict]:
    """Sheet 4 `validation_errors`: one row per failure."""
    return [
        {
            "tool_id": r.tool_id,
            "field_path": e.get("field_path"),
            "value": str(e.get("value")),
            "quote": e.get("quote"),
            "reason": e.get("reason"),
        }
        for e in r.validation_errors
    ]


# Stable column order so empty DataFrames still render the expected headers.
_TOOLS_COLUMNS = (
    ["tool_id", "source_doc_path", "tool_name", "purpose",
     "source_type_value", "source_type_evidence",
     "contribution_type_value", "contribution_type_evidence",
     "input_instruction_value", "input_instruction_evidence",
     "output_type_value", "output_type_evidence",
     "automation_level_value", "automation_level_evidence",
     "evaluation_type_value", "evaluation_type_evidence",
     "design_principles", "technological_foundation"]
    + [f"{c}_{suffix}" for c in ARCHITECTURE_COMPONENTS for suffix in ("value", "evidence")]
    + ["offers_algorithms_value", "offers_algorithms_evidence", "needs_review"]
)
_ALGO_COLUMNS = ["tool_id", "algorithm_name", "algorithm_type", "evidence"]
_CHAL_COLUMNS = ["tool_id", "statement", "category", "category_evidence",
                 "evidence_strength", "strength_evidence"]
_ERROR_COLUMNS = ["tool_id", "field_path", "value", "quote", "reason"]


def _frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    cleaned = [{k: _clean(v) for k, v in row.items()} for row in rows]
    return pd.DataFrame(cleaned, columns=columns)


def write_workbook(records: list[ToolRecord], path: str) -> None:
    """Write the whole workbook once via an atomic temp-file swap."""
    tools_rows, algo_rows, chal_rows, error_rows = [], [], [], []
    for r in records:
        tools_rows.append(flatten_tool_row(r))
        algo_rows.extend(flatten_algo_rows(r))
        chal_rows.extend(flatten_challenge_rows(r))
        error_rows.extend(flatten_error_rows(r))

    # Keep an .xlsx suffix so pandas/openpyxl accepts the temp file's extension.
    tmp = path + ".tmp.xlsx"
    with pd.ExcelWriter(tmp, engine="openpyxl") as xw:
        _frame(tools_rows, _TOOLS_COLUMNS).to_excel(xw, sheet_name="tools", index=False)
        _frame(algo_rows, _ALGO_COLUMNS).to_excel(xw, sheet_name="algorithms", index=False)
        _frame(chal_rows, _CHAL_COLUMNS).to_excel(xw, sheet_name="challenges", index=False)
        _frame(error_rows, _ERROR_COLUMNS).to_excel(xw, sheet_name="validation_errors", index=False)
    os.replace(tmp, path)  # atomic on POSIX, near-atomic on Windows
