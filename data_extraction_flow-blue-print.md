# QCaaS Toolchain Data Extraction Pipeline — Design Blueprint (v2)

## Changes in this revision

- **Output is a local `.xlsx` workbook**, written once after the batch completes via pandas + an atomic temp-file swap. The `langchain_google_community` Sheets dependency and all per-document upsert/idempotency machinery are gone.
- **Locate step keeps returning verbatim paragraph text**, but a new deterministic **`reanchor`** node re-aligns that text to the canonical source before extraction, closing the quote-fidelity hole without asking the flash model for offsets/IDs.
- **Parallel extractors fan out via plain edges**, not the `Send` API (`Send` is for runtime-unknown fan-out; here the four branches are fixed).
- **`validation_errors` is overwritten each pass** (no accumulating reducer), and a new **`retry_counts`** field enforces the one-retry-per-category budget that v1 specified but had no way to honor.
- Architecture stays a single structured-output call, now with explicit parse-failure handling.
- No / Not-stated three-value enums retained; precise definitions to be refined later (schema values reserved so no data migration is needed).

## 1. Purpose

A LangGraph-based pipeline that ingests a corpus of documents about QCaaS toolchains and produces a structured, evidence-grounded extraction conforming to a predefined Data Extraction Form (DEF). The extraction is written to a local `.xlsx` workbook for downstream empirical analysis and paper writing.

Two non-negotiable properties:

- **Every coded label carries a verbatim evidence quote** from the source document. Free-text fields are inherently self-evidencing.
- **Quote fidelity is validated** before any value reaches the workbook. Hallucinated quotes are caught deterministically.

## 2. High-Level Architecture

```
┌──────────┐   ┌────────────┐   ┌──────────┐   ┌──────────────────────┐   ┌──────────┐   ┌──────────┐
│ load_doc │ → │locate_spans│ → │ reanchor │ → │ parallel extractors  │ → │ validate │ → │ assemble │
│          │   │  (flash)   │   │ (det.)   │   │ (strong, fan-out ×4) │   │  (det.)  │   │ (record) │
└──────────┘   └────────────┘   └──────────┘   └──────────────────────┘   └────┬─────┘   └────┬─────┘
                                                   ├─ general + overview        │ retry        │
                                                   ├─ architecture        ◄─────┘ (≤1/cat)     ▼
                                                   ├─ algorithms                          ToolRecord
                                                   └─ challenges                          → batch buffer

                          [batch driver collects every ToolRecord, then] → write_workbook (.xlsx, once)
```

**Two-stage extraction rationale.** A flash model with a large context window triages the document once, returning paragraphs grouped by extraction category. The expensive strong model then reads only the relevant spans per category. This reduces strong-model input tokens substantially without sacrificing recall — provided the locate step is instructed to over-retrieve rather than under-retrieve.

**Re-anchoring rationale.** The flash model returns paragraph *text*, but LLMs do not reliably reproduce long passages character-for-character regardless of prompt wording. The `reanchor` node fuzzy-matches each returned paragraph back into the canonical source text and substitutes the exact source slice. Downstream extractors therefore only ever see canonical text, so any quote they copy verbatim is guaranteed to be a substring of the source — and a failed re-anchor is a useful signal that the flash model fabricated or mangled a span.

**Short-document bypass.** Documents under ~10k tokens skip both `locate_spans` and `reanchor` (their spans are already canonical — they *are* the raw text) and fan out directly to the extractors. A conditional edge after `load_doc` routes on token count.

**Persistence is batch-level, not per-document.** Each graph run produces a validated `ToolRecord`. A driver loop collects every record and writes the whole workbook once, which makes "rebuild from scratch each run" the default and eliminates per-document idempotency, last-row-finding, and partial-write-across-sheets concerns.

## 3. Extraction Schema (Pydantic)

All categorical fields are wrapped so that `value` and `evidence` travel together. Free-text fields stay as plain strings. The three-value enums (`Yes` / `No` / `Not stated`) are retained; the operational definitions for `No` vs `Not stated` will be sharpened later, but the enum values are fixed now so refinement needs no schema/data migration.

```python
from typing import Literal
from pydantic import BaseModel, Field

# ---------- Reusable coded-field wrappers ----------

class YesNoField(BaseModel):
    value: Literal["Yes", "No", "Not stated"]
    evidence: str = ""  # verbatim quote; empty only when Not stated

class SourceTypeField(BaseModel):
    value: Literal["OS", "CS", "Not stated"]
    evidence: str = ""

class ContributionTypeField(BaseModel):
    value: Literal[
        "Methodology-vision",
        "Proof of concept",
        "Practical for customers",
        "Not stated",
    ]
    evidence: str = ""

class InputInstructionField(BaseModel):
    value: Literal["HL", "QI", "MV", "Multiple", "Not stated"]
    evidence: str = ""

class OutputTypeField(BaseModel):
    value: Literal["QSC", "SF", "Metrics", "Logs", "Multiple", "Not stated"]
    evidence: str = ""

class AutomationLevelField(BaseModel):
    value: Literal["FA", "SA", "NA", "Not stated"]
    evidence: str = ""

class EvaluationTypeField(BaseModel):
    value: Literal["EX", "IM", "None", "Not stated"]
    evidence: str = ""

# ---------- Category 1: General Information ----------

class GeneralInfo(BaseModel):
    tool_name: str
    purpose: str = Field(description="1–2 sentence summary, free text")
    source_type: SourceTypeField
    contribution_type: ContributionTypeField

# ---------- Category 2: Overview Characteristics ----------

class OverviewCharacteristics(BaseModel):
    input_instruction: InputInstructionField
    output_type: OutputTypeField
    automation_level: AutomationLevelField
    evaluation_type: EvaluationTypeField

# ---------- Category 3: Architectural and Technical Features ----------
# 12 fields total: 2 free-text + 10 YesNoField components.

class Architecture(BaseModel):
    design_principles: str          # free text
    technological_foundation: str   # free text
    orchestrator: YesNoField
    manager_controller: YesNoField
    vendor_agnostic_layer: YesNoField
    backend_integration: YesNoField
    debugging_testing: YesNoField
    simulation_support: YesNoField
    security_mechanisms: YesNoField
    scalability_mechanisms: YesNoField
    telemetry_monitoring: YesNoField
    user_interface: YesNoField

# ---------- Category 4: Quantum Algorithms ----------

class QuantumAlgorithm(BaseModel):
    name: str
    algorithm_type: str
    evidence: str  # quote showing this algorithm is offered as built-in/selectable

class AlgorithmsSection(BaseModel):
    offers_algorithms: Literal["Yes", "No", "Not stated"]
    overall_evidence: str = ""
    algorithms: list[QuantumAlgorithm] = Field(default_factory=list)

# ---------- Category 5: Challenges ----------

ChallengeCategory = Literal[
    "Usability", "Performance", "Reliability", "Scalability",
    "Interoperability", "Access", "Security", "Maintainability",
]

class Challenge(BaseModel):
    statement: str                  # free text describing the limitation
    category: ChallengeCategory
    category_evidence: str          # quote justifying the categorization
    evidence_strength: Literal["Explicit empirical", "Implicit anecdotal"]
    strength_evidence: str          # quote justifying the strength rating

class ChallengesSection(BaseModel):
    challenges: list[Challenge] = Field(default_factory=list)

# ---------- Top-level record per document ----------

class ToolRecord(BaseModel):
    tool_id: str
    source_doc_path: str
    general: GeneralInfo
    overview: OverviewCharacteristics
    architecture: Architecture
    algorithms: AlgorithmsSection
    challenges: ChallengesSection
    needs_review: bool = False      # set if the validator escalated any field
```

Bind these to the strong model via `llm.with_structured_output(ModelClass)`.

## 4. LangGraph State

```python
from typing import TypedDict

class ExtractionState(TypedDict):
    tool_id: str
    source_doc_path: str
    raw_text: str                       # canonical normalized source (validation reference)
    raw_paragraphs: list[str]           # canonical paragraphs, for re-anchoring
    token_count: int

    # locate output, then re-anchored to canonical text in-place:
    # category name → list of canonical paragraph strings
    located_spans: dict[str, list[str]]
    reanchor_dropped: list[str]         # paragraphs the flash model returned that failed to re-anchor

    # Per-category extraction outputs
    general: GeneralInfo | None
    overview: OverviewCharacteristics | None
    architecture: Architecture | None
    algorithms: AlgorithmsSection | None
    challenges: ChallengesSection | None

    # Validator results — recomputed (OVERWRITTEN) on every validate pass, never accumulated
    validation_errors: list[dict]       # [{field_path, value, quote, reason}]
    categories_to_retry: list[str]      # set by validate, read by the retry router
    retry_counts: dict[str, int]        # category → attempts; enforces the ≤1 retry budget

    # Final assembled record (consumed by the batch driver)
    record: ToolRecord | None
```

Note the deliberate absence of `Annotated[..., add]` on `validation_errors`: the four extractors write to *distinct* keys (`general`, `overview`, `architecture`, `challenges`), so no concurrent-write reducer is needed, and the validator must see only the current pass's errors.

## 5. Node Specifications

### `load_doc`
- Read document from path; extract text (PDF → text, HTML → text, etc.).
- Normalize whitespace; de-hyphenate line-break artifacts. **This normalized text is the canonical reference for both re-anchoring and quote validation.** Its fidelity directly determines validation reliability, so invest here.
- Split into `raw_paragraphs` (on blank lines / block boundaries) for the re-anchor matcher.
- Compute `token_count`.
- Conditional edge: `token_count > 10000` → `locate_spans`; else set `located_spans = {cat: [raw_text] for cat in CATEGORIES}` and fan out directly to the four extractors (bypassing both locate and reanchor, since the spans are already canonical).

### `locate_spans` (flash model)
- Single call. Returns `dict[category_name, list[paragraph_text]]`.
- Categories: `general`, `overview`, `architecture`, `algorithms`, `challenges`.
- Prompt instructs the model to **be generous**: include any paragraph plausibly related. Over-retrieval is cheap; under-retrieval silently produces false "Not stated" later.
- The prompt asks for verbatim text, but exact fidelity is *not* relied upon here — `reanchor` is the safety net.

### `reanchor` (deterministic)
- For each `(category, paragraph)` returned by locate, fuzzy-match the paragraph against `raw_paragraphs` and replace it with the exact canonical slice.
- Matches below threshold are dropped and recorded in `reanchor_dropped` (a fabrication/mangling signal worth logging and spot-checking).
- After this node, every string in `located_spans` is a verbatim substring of `raw_text`.

```python
from rapidfuzz import process, fuzz

REANCHOR_THRESHOLD = 85

def reanchor(state: ExtractionState) -> dict:
    raw_paras = state["raw_paragraphs"]
    fixed: dict[str, list[str]] = {}
    dropped: list[str] = []
    for cat, paras in state["located_spans"].items():
        keep = []
        for p in paras:
            match = process.extractOne(p, raw_paras, scorer=fuzz.ratio)
            if match and match[1] >= REANCHOR_THRESHOLD:
                keep.append(raw_paras[match[2]])   # canonical slice, not the model's text
            else:
                dropped.append(p)
        fixed[cat] = keep
    return {"located_spans": fixed, "reanchor_dropped": dropped}
```

### Parallel extractor nodes (strong model)
Four nodes, reached by **plain fan-out edges** from `reanchor` (and from the bypass branch). Each writes a distinct state key, so they run concurrently in one superstep with no reducer:

- `extract_general_and_overview` — bundled (both short, share a call efficiently). Returns `GeneralInfo` and `OverviewCharacteristics`.
- `extract_architecture` — returns `Architecture` (12 fields; the heaviest call). Wrap `with_structured_output` in parse-failure handling (see below).
- `extract_algorithms` — returns `AlgorithmsSection`.
- `extract_challenges` — returns `ChallengesSection`.

Each receives only its category's canonical spans from `located_spans`. Each uses `with_structured_output()` against its target Pydantic class. Because structured output can return `None` or raise on a malformed completion, each extractor catches that case, records a synthetic validation error for the category, and leaves its state key populated with a safe empty/"Not stated" default so the graph can proceed to (and retry from) `validate`.

### `validate` (deterministic)
Recomputes `validation_errors` from scratch each pass (overwrite). For every populated `evidence` field across the current outputs:
1. Skip if value is `"Not stated"` and evidence is empty (legitimate).
2. Enforce a **minimum quote length** (e.g. ≥ 4 words) to avoid accidental-substring false positives.
3. Normalize quote and source identically (collapse whitespace, lowercase, strip punctuation/smart-quote variants).
4. Check substring containment in `raw_text`; **log the matched character offset** for auditing.
5. On mismatch, append `{field_path, value, quote, reason}` to `validation_errors` and add the field's category to `categories_to_retry`.

**Retry policy (now enforceable).** A conditional edge after `validate` inspects `categories_to_retry` and `retry_counts`:
- For each category with errors and `retry_counts[cat] < 1`: increment `retry_counts[cat]` and route back to that category's extractor with a stricter prompt that explicitly forbids paraphrase.
- Re-run extractors flow back into `validate` (a controlled `validate ↔ extractor` loop).
- Categories whose errors survive the single retry are accepted with `needs_review = True` on the record. When `categories_to_retry` is empty (or all are exhausted), route to `assemble`.

### `assemble`
- Build `ToolRecord` from the category outputs; set `needs_review` if any error survived.
- Write it to `state["record"]`. The per-document graph ends here; persistence happens in the batch driver.

## 6. Two-Stage Extraction Details

### Locate-step prompt skeleton

```
You will be given a document about a quantum-computing toolchain.
For each of these five categories, return any paragraphs from the document
that could plausibly contain information for that category. Be generous —
include paragraphs that are even tangentially relevant. Return the paragraph
text as faithfully as you can.

Categories:
- general:        tool name, purpose, source type (open/closed), contribution type
- overview:       input instruction type, output type, automation level, evaluation
- architecture:   design principles, languages/tech, components (orchestrator,
                  manager, abstraction layer, backends, debugging, simulation,
                  security, scalability, telemetry, UI)
- algorithms:     built-in or selectable quantum algorithms offered by the tool
- challenges:     limitations, barriers, problems with adopting/using the tool

Return JSON: {category: [paragraph_text, ...]}.
```

(Exact reproduction is *not* required from this step — `reanchor` realigns the text to the canonical source.)

### Strong-model extraction guardrails (in system prompt)

- Quotes in `evidence` must be **verbatim** from the provided spans, character-for-character. No paraphrasing, no ellipsis-stitching of non-adjacent text.
- Quotes should be short — one sentence or one clause, not paragraphs.
- If no verbatim quote supports a coded value, set the value to `"Not stated"` and leave evidence empty. **Do not fabricate quotes.**
- Distinguish carefully between **No** and **Not stated** (definitions to be refined):
  - *Yes* — verbatim quote affirming the feature exists.
  - *No* — quote that explicitly negates the feature, or quote showing the topic area *is* discussed but this specific capability is absent.
  - *Not stated* — the document does not engage with the topic area at all; evidence empty.

## 7. Local XLSX Output Layout

One workbook, three worksheets. Long-format for the one-to-many sections keeps the data analysis-ready (group-by-category counts, cross-tabs) without comma-separated cell hell.

### Sheet 1: `tools` — one row per document

| Column | Source |
|---|---|
| `tool_id` | state |
| `source_doc_path` | state |
| `tool_name` | `general.tool_name` |
| `purpose` | `general.purpose` |
| `source_type_value` / `source_type_evidence` | `general.source_type` |
| `contribution_type_value` / `contribution_type_evidence` | `general.contribution_type` |
| `input_instruction_value` / `_evidence` | `overview.input_instruction` |
| `output_type_value` / `_evidence` | `overview.output_type` |
| `automation_level_value` / `_evidence` | `overview.automation_level` |
| `evaluation_type_value` / `_evidence` | `overview.evaluation_type` |
| `design_principles` | `architecture.design_principles` |
| `technological_foundation` | `architecture.technological_foundation` |
| `{component}_value` / `{component}_evidence` × 10 | architecture YesNoFields |
| `offers_algorithms_value` / `_evidence` | `algorithms.offers_algorithms` |
| `needs_review` | bool, set if validator escalated |

### Sheet 2: `algorithms` — one row per offered algorithm

| Column | Source |
|---|---|
| `tool_id` | foreign key |
| `algorithm_name` | `QuantumAlgorithm.name` |
| `algorithm_type` | `QuantumAlgorithm.algorithm_type` |
| `evidence` | `QuantumAlgorithm.evidence` |

### Sheet 3: `challenges` — one row per challenge

| Column | Source |
|---|---|
| `tool_id` | foreign key |
| `statement` | `Challenge.statement` |
| `category` | `Challenge.category` |
| `category_evidence` | `Challenge.category_evidence` |
| `evidence_strength` | `Challenge.evidence_strength` |
| `strength_evidence` | `Challenge.strength_evidence` |

### Writing the workbook (once, after the batch)

```python
import os
import pandas as pd

def write_workbook(records: list[ToolRecord], path: str) -> None:
    tools_rows, algo_rows, chal_rows = [], [], []
    for r in records:
        tools_rows.append(flatten_tool_row(r))       # one dict per doc
        algo_rows.extend(flatten_algo_rows(r))       # 0..n per doc
        chal_rows.extend(flatten_challenge_rows(r))  # 0..n per doc

    tmp = path + ".tmp"
    with pd.ExcelWriter(tmp, engine="openpyxl") as xw:
        pd.DataFrame(tools_rows).to_excel(xw, sheet_name="tools", index=False)
        pd.DataFrame(algo_rows).to_excel(xw, sheet_name="algorithms", index=False)
        pd.DataFrame(chal_rows).to_excel(xw, sheet_name="challenges", index=False)
    os.replace(tmp, path)   # atomic on Linux, near-atomic on Windows → no half-written workbook
```

The three `flatten_*` functions are pure (`ToolRecord` → list of dicts) and unit-testable in isolation.

### Batch driver

```python
def run_corpus(doc_paths: list[str], out_path: str) -> None:
    records: list[ToolRecord] = []
    for i, p in enumerate(doc_paths):
        init = build_initial_state(tool_id=f"T{i:03d}", source_doc_path=p)
        final = graph.invoke(init)
        if final["record"] is not None:
            records.append(final["record"])
    write_workbook(records, out_path)
```

If incremental updates are ever needed instead of full rebuild: read the three sheets into DataFrames, drop rows whose `tool_id` is in the current batch, `concat` the new rows, and write the whole workbook back via the same atomic swap. Still no row-level surgery.

## 8. Validation Details

- **Re-anchoring is what makes substring matching trustworthy**: extractors only see canonical text, so a verbatim quote is a verbatim substring of `raw_text` by construction.
- **Normalization for substring matching**: collapse runs of whitespace to single spaces; remove soft-hyphen/line-break artifacts; case-insensitive; normalize smart vs straight quotes. Match on the normalized form of both quote and source.
- **Minimum quote length** (≥ ~4 words) guards against short clauses matching by coincidence.
- **Offset logging**: record the matched character span for every passing quote, for human audit.
- **Retry budget**: 1 retry per category per document, enforced via `retry_counts`. Beyond that, accept with `needs_review = True`.
- **Validator is deterministic and fast** — pure Python, no model calls.

## 9. Cost & Latency Notes

- Locate step: 1 flash call per document, large input, modest output.
- Re-anchor: free (deterministic fuzzy matching).
- Extraction: 4 strong-model calls per document, run concurrently. Limited by the slowest branch (architecture, typically).
- Evidence roughly doubles output tokens per coded field but barely affects input cost.
- Validator and workbook write: free / local.
- For ~50 documents, cost is dominated by the 50 × 4 strong-model calls (plus any retries).

## 10. Open Items / To Confirm Before Building

- Document format and quantity — PDF vs HTML vs raw text affects the loader (and therefore canonical-text fidelity).
- Strong-model robustness on the 12-field `Architecture` schema — keep as one call unless flakiness appears; natural split is component clusters (infra / quality / surface), not an arbitrary halving.
- Whether to interrupt before `assemble` for human review of `needs_review` records, or review post-hoc in the workbook.
- One `.xlsx` with three sheets (human-friendly browsing) vs. three CSVs (lighter analysis-env dependency).
- Choice of flash and strong models.
- Sharpen the `No` vs `Not stated` definitions before the main extraction run.

## 11. Suggested Build Order

1. Pydantic schema + a unit test that instantiates every model with example values.
2. The validator (pure function: document + outputs → list of errors). Test against synthetic hallucinated quotes, short-clause false positives, and smart-quote variants.
3. `flatten_*` functions + `write_workbook` with mocked records — confirm the three-sheet workbook renders as expected and the atomic swap works on both OSes.
4. `reanchor` in isolation — feed it deliberately mangled paragraphs and confirm canonical recovery + correct drops.
5. Single-document end-to-end with the short-doc bypass (skip locate + reanchor). Verify against a known-good extraction.
6. Add `locate_spans`, `reanchor`, and conditional routing.
7. Add the four fan-out extractors (plain edges) and the `validate ↔ extractor` retry loop with `retry_counts`.
8. Batch over the full corpus via the driver.