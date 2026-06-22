# QCaaS Toolchain Data Extraction Pipeline — Design Blueprint (v3)

## Changes in this revision (v3 — 174-file scaling)

- **Merged-then-fallback extraction**: single strong-model call extracts all five categories (general, overview, architecture, algorithms, challenges) into a `FullExtraction` structured output. Only on validation failure do categories fall back to focused re-extraction. Cuts per-doc strong-model calls from 4 to 1 (or 2-4 on retry).
- **Async concurrent batch driver**: documents process in parallel with semaphore-bounded concurrency (tune per API tier; default 5). Replaces serial loop.
- **Per-document checkpointing**: each finished doc saved to `out_dir/records/<tool_id>.json` immediately after completion. Enables crash recovery: rerun the same command and only unfinished docs process.
- **Stable content-hash IDs**: `tool_id(path)` derives from file content, not enumeration. Reordering docs or running multiple batches produces identical IDs, enabling resume and cross-run comparison.
- **Rerun policies**: "resume" (default, skip done), "all" (reprocess everything), "status:failed" (retry only failed docs), explicit tool_ids (process specific docs).
- **Manifest log** (`out_dir/manifest.jsonl`): audits every document attempt with status, duration, error (if any).
- **Rate-limit resilience**: model clients with exponential backoff on 429; cross-doc concurrency bounded.
- **`validation_errors` sheet**: every quote-fidelity failure captured in the workbook for spot-checking and refinement.
- **Loader robustness**: detects empty/near-empty extractions (scanned PDFs) early; short docs bypass locate/reanchor.

## 1. Purpose

A LangGraph-based pipeline that ingests a corpus of documents about QCaaS toolchains and produces a structured, evidence-grounded extraction conforming to a predefined Data Extraction Form (DEF). The extraction is written to a local `.xlsx` workbook for downstream empirical analysis and paper writing.

Two non-negotiable properties:

- **Every coded label carries a verbatim evidence quote** from the source document. Free-text fields are inherently self-evidencing.
- **Quote fidelity is validated** before any value reaches the workbook. Hallucinated quotes are caught deterministically.

## 2. High-Level Architecture

```
┌──────────┐   ┌────────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────────────┐   ┌──────────┐
│ load_doc │ → │locate_spans│ → │ reanchor │ → │extract_merged│ → │ validate │ → │ fallback (if err) │ → │ assemble │
│          │   │  (flash)   │   │ (det.)   │   │   (strong)   │   │  (det.)  │   │ (strong, ≤1/cat) │   │ (record) │
└──────────┘   └────────────┘   └──────────┘   └──────────────┘   └────┬─────┘   └──────────────────┘   └──────────┘
                                                                         │
                                                                    retry on
                                                               validation errors
                                                                    (loop back
                                                                   to validate)

                     [batch driver: async concurrency + checkpoint/resume] → write_workbook (.xlsx, once)
```

**Two-stage extraction rationale.** A flash model with a large context window triages the document once, returning paragraphs grouped by extraction category. The expensive strong model then reads only the relevant spans per category. This reduces strong-model input tokens substantially without sacrificing recall — provided the locate step is instructed to over-retrieve rather than under-retrieve.

**Merged-then-fallback extraction.** At scale (174+ documents), concurrency is the primary source of parallelism, not intra-document fan-out. A single merged call extracts the whole `ToolRecord` in one strong-model invocation, cutting 4× the model calls without loss of fidelity. If validation fails, only the errored categories fall back to focused re-extraction. This combines the throughput of merged extraction with the precision of category-specific retries.

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
    tool_id: str                        # stable content-hash ID
    source_doc_path: str
    raw_text: str                       # canonical normalized source (validation reference)
    raw_paragraphs: list[str]           # canonical paragraphs, for re-anchoring
    token_count: int

    # locate output, then re-anchored to canonical text in-place:
    # category name → list of canonical paragraph strings
    located_spans: dict[str, list[str]]
    reanchor_dropped: list[str]         # paragraphs the flash model returned that failed to re-anchor

    # Merged extraction output (extract_merged node) — all categories at once
    general: GeneralInfo | None
    overview: OverviewCharacteristics | None
    architecture: Architecture | None
    algorithms: AlgorithmsSection | None
    challenges: ChallengesSection | None
    parse_failures: dict[str, str]      # category → error; tracks extract_merged parse failures

    # Validator results — recomputed (OVERWRITTEN) on every validate pass, never accumulated
    validation_errors: list[dict]       # [{field_path, value, quote, reason}]
    categories_to_retry: list[str]      # set by validate, read by fallback routers
    retry_counts: dict[str, int]        # category → attempts; enforces the ≤1 retry budget

    # Final assembled record (consumed by the batch driver)
    record: ToolRecord | None
```

**State flow:**
- `load_doc` → `raw_text`, `raw_paragraphs`, `token_count`, conditional edge (locate for long docs vs. skip for short).
- `locate_spans` → `located_spans` (category-keyed spans).
- `reanchor` → `located_spans` (in-place canonical realignment), `reanchor_dropped`.
- `extract_merged` → `general`, `overview`, `architecture`, `algorithms`, `challenges` (all from one call); or `parse_failures` on failure.
- `validate` → `validation_errors`, `categories_to_retry`, `retry_counts` (overwritten each pass).
- `[fallback extractors]` (conditional) → category state keys (only errored categories).
- `assemble` → `record`.

Note the deliberate absence of `Annotated[..., add]` on `validation_errors`: each pass overwrites it completely, never accumulating. The validator must see only the current pass's errors to decide retries correctly.

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

### Merged extractor node (strong model)

`extract_merged` — single call, returns `FullExtraction` (all five categories: general, overview, architecture, algorithms, challenges). Receives all canonical spans grouped by category from `located_spans`. 

Uses `with_structured_output(FullExtraction)` on the strong model. Because structured output can return `None` or raise on malformed completion, wraps in parse-failure handling: on failure, populates `parse_failures` dict (keyed by category), leaves all state keys with safe empty/"Not stated" defaults, and proceeds to `validate`. The validator will route errored categories to fallback extraction.

### Fallback extractor nodes (strong model, reached only on validation errors)

Four nodes, reached by **conditional edges** from `validate` when `categories_to_retry` is non-empty. Each writes its category's state key:

- `extract_general_and_overview` — bundled (both short, share a call efficiently). Returns `GeneralInfo` and `OverviewCharacteristics`.
- `extract_architecture` — returns `Architecture` (12 fields; the heaviest call).
- `extract_algorithms` — returns `AlgorithmsSection`.
- `extract_challenges` — returns `ChallengesSection`.

Each receives only its category's canonical spans from `located_spans` and runs a stricter prompt forbidding paraphrase. Like `extract_merged`, catches parse failures and leaves defaults so the graph re-enters `validate` for another retry pass.

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

### Sheet 4: `validation_errors` — every quote-fidelity failure

| Column | Source |
|---|---|
| `tool_id` | foreign key |
| `field_path` | dot-notation path (e.g. `general.source_type`) |
| `value` | the coded/extracted value |
| `quote` | the evidence string that failed validation |
| `reason` | why it failed (e.g. "not found in source", "below min length") |

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

### Batch driver (async, concurrent, checkpointing)

```python
async def run_corpus_async(doc_paths: list[str], out_path: str, *, concurrency=5, 
                           out_dir="runs/latest", rerun="resume") -> None:
    sem = asyncio.Semaphore(concurrency)
    targets = select_targets(doc_paths, rerun, out_dir)  # resume/all/status:X/explicit-ids
    
    async def worker(path):
        tid = tool_id(path)  # stable content-hash ID
        async with sem:
            try:
                init = build_initial_state(tool_id=tid, source_doc_path=path)
                final = await graph.ainvoke(init)
                if final["record"] is not None:
                    save_record(final["record"], out_dir)  # per-doc checkpoint
                    log_manifest(tid, path, "done" if not final["record"].needs_review else "needs_review")
            except Exception as e:
                log_manifest(tid, path, "failed", error=repr(e))
    
    await asyncio.gather(*(worker(p) for p in targets))
    records = load_all_records(out_dir)  # rebuild from checkpoints
    write_workbook(records, out_path)
```

**Key features:**
- **Bounded concurrency**: `Semaphore(concurrency)` limits parallelism (tune per API tier, default 5).
- **Stable IDs**: `tool_id(path)` derives from file content hash, enabling resume across reorderings.
- **Checkpoint per doc**: `save_record()` writes `out_dir/records/<tool_id>.json` immediately after completion.
- **Manifest log**: `out_dir/manifest.jsonl` appends `{tool_id, path, status, error, duration_s, ts}` per attempt.
- **Rerun policies**: `select_targets()` filters by: "resume" (skip done), "all" (reprocess all), "status:X" (by last status), or explicit tool_ids.
- **Failure isolation**: one doc's exception doesn't abort the batch; error is logged and next doc processes.
- **Workbook rebuild**: read all checkpoints, not an in-memory list, so partial runs still yield a complete workbook of what's done.

Synchronous wrapper:
```python
def run_corpus(doc_paths, out_path, **kwargs):
    return asyncio.run(run_corpus_async(doc_paths, out_path, **kwargs))
```

## 8. Validation Details

- **Re-anchoring is what makes substring matching trustworthy**: extractors only see canonical text, so a verbatim quote is a verbatim substring of `raw_text` by construction.
- **Normalization for substring matching**: collapse runs of whitespace to single spaces; remove soft-hyphen/line-break artifacts; case-insensitive; normalize smart vs straight quotes. Match on the normalized form of both quote and source.
- **Minimum quote length** (≥ ~4 words) guards against short clauses matching by coincidence.
- **Offset logging**: record the matched character span for every passing quote, for human audit.
- **Retry budget**: 1 retry per category per document, enforced via `retry_counts`. Beyond that, accept with `needs_review = True`.
- **Validator is deterministic and fast** — pure Python, no model calls.

## 9. Cost & Latency Notes

- Locate step: 1 flash call per document (long docs only; short docs skip directly to extraction).
- Re-anchor: free (deterministic fuzzy matching).
- Extraction (happy path): 1 strong-model call per document (merged extraction).
- Extraction (fallback): up to 4 focused strong-model calls per document, only if merged validation fails. Each errored category retries ≤1 time.
- Evidence roughly doubles output tokens per coded field but barely affects input cost.
- Validator and workbook write: free / local.
- For 174 documents with merged extraction: ~348 min calls (174 flash + 174 strong), vs. ~870 for 4-way fan-out. Fallback adds only on validation failures.

## 10. Scaling & Reliability

### Crash recovery via checkpointing

- Per-document checkpoints in `out_dir/records/<tool_id>.json` enable resume from any point. Default rerun mode is "resume": skip finished docs.
- Manifest log (`out_dir/manifest.jsonl`) audits every attempt: `{tool_id, path, status: done|needs_review|failed, duration_s, ts}`.
- No in-memory state means a crash at doc 170/174 costs only the 4 unfinished docs on rerun, not 174 full calls.

### Stable tool IDs

- `tool_id(path)` derives from file content hash, not enumeration. Reordering docs, renaming files, or running multiple batches produces identical IDs for identical content.
- Enables cross-run comparison and prevents duplicate-ID collisions on resume.

### Rate-limit resilience

- LLM model clients configured with `max_retries=6` (default) for exponential backoff on 429/throttle.
- Cross-doc semaphore (`concurrency=5` default) keeps under TPM/RPM ceilings; tune per API tier.

## 11. Open Items / To Confirm Before Building

- Document format and quantity — PDF vs HTML vs raw text affects the loader (and therefore canonical-text fidelity).
- Strong-model robustness on the merged `FullExtraction` schema — fallback extractors handle category-level failures gracefully.
- Whether to interrupt before `assemble` for human review of `needs_review` records, or review post-hoc in the workbook.
- One `.xlsx` with three sheets (human-friendly browsing) vs. three CSVs (lighter analysis-env dependency).
- Choice of flash and strong models.
- Sharpen the `No` vs `Not stated` definitions before the main extraction run.
- Pre-run cost estimation: helpful for 174-file corpus to confirm projected call count before committing API spend.

## 12. Suggested Build Order

1. Pydantic schema + a unit test that instantiates every model with example values.
   - Add `FullExtraction` model (all five categories in one call).
2. The validator (pure function: document + outputs → list of errors). Test against synthetic hallucinated quotes, short-clause false positives, and smart-quote variants.
3. `flatten_*` functions + `write_workbook` with mocked records — confirm the four-sheet workbook renders as expected (tools, algorithms, challenges, validation_errors) and the atomic swap works on both OSes.
4. `reanchor` in isolation — feed it deliberately mangled paragraphs and confirm canonical recovery + correct drops.
5. Single-document end-to-end with the short-doc bypass (skip locate + reanchor). Verify against a known-good extraction.
6. Add `locate_spans`, `reanchor`, and conditional routing.
7. **Add the merged extractor** (`extract_merged` returning `FullExtraction`) with parse-failure handling (populates `parse_failures` on failure).
8. Add fallback extractors (four focused calls, reached only on validation errors) and the `validate ↔ fallback` retry loop with `retry_counts`.
9. **Stable IDs** (`ids.py`: `tool_id(path)` from content hash).
10. **Checkpoint store** (`checkpoint.py`: per-doc records + manifest logging).
11. **Async concurrent driver** (`driver.py`): bounded concurrency, rerun policies, per-doc failure isolation.
12. CLI + argument parsing: `--rerun`, `--concurrency`, `--out-dir`, `--estimate`.
13. Batch over 174+ documents with concurrent processing. Monitor manifest for failures; retry with `--rerun status:failed`.