# QCaaS Toolchain Data Extraction Pipeline

A LangGraph-based pipeline that extracts structured evidence-grounded data from QCaaS toolchain documents into a local `.xlsx` workbook. Scales to 174+ files with cross-document concurrency, per-document checkpoint/resume, and automatic fallback to focused extraction on validation failures.

## Architecture

- **Two-stage extraction**: flash model over-retrieves candidate spans; strong model extracts from re-anchored canonical text.
- **Merged-then-fallback**: one call extracts the whole record; if validation fails, falls back to per-category focused calls.
- **Per-document persistence**: each finished document is checkpointed immediately, enabling resume after crash.
- **Stable IDs**: tool_id derived from file content hash, so documents keep their checkpoint across reorderings.
- **Rate-limit backoff**: exponential backoff on 429/throttle keeps concurrent runs under API tier ceilings.

See [data_extraction_flow-blue-print.md](data_extraction_flow-blue-print.md) for full architecture & motivation.

## Setup

### Environment

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

### API Keys

Create a `.env` file with your LLM provider credentials:

```env
# Provider and model choices (defaults shown)
FLASH_MODEL=google_genai:gemini-3.5-flash
STRONG_MODEL=openai:gpt-5.4-2026-03-05

# Optional tuning
SHORT_DOC_TOKEN_THRESHOLD=10000
REANCHOR_THRESHOLD=85
MIN_QUOTE_WORDS=4
MAX_RETRIES_PER_CATEGORY=1

# Batch driver tuning
CONCURRENCY=5
OUT_DIR=runs/latest
MAX_API_RETRIES=6
```

## Running Extraction

### Basic run (default: resume, concurrency=5)

```bash
python -m qcaass_extraction output.xlsx --dir data/
```

Processes only unfinished documents (respects prior checkpoints in `runs/latest/records/`).

### Estimate cost before running

```bash
python -m qcaass_extraction output.xlsx --dir data/ --estimate
```

Prints token counts, document count, min model calls. Helpful before a large run.

### Rerun policies

**Resume (default)**: Skip docs with existing checkpoints; crash-safe.
```bash
python -m qcaass_extraction output.xlsx --dir data/
```

**All**: Reprocess every document; overwrites prior checkpoints.
```bash
python -m qcaass_extraction output.xlsx --dir data/ --rerun all
```

**Failed docs only**: Re-extract only documents with "failed" status in manifest.
```bash
python -m qcaass_extraction output.xlsx --dir data/ --rerun status:failed
```

**Specific docs**: Provide comma-separated tool_ids (shown in manifest).
```bash
python -m qcaass_extraction output.xlsx --dir data/ --rerun T_abc1234,T_def5678
```

### Concurrency and rate limits

Tune concurrency to your API tier. Start conservative (5); higher values faster but risk 429s.

```bash
python -m qcaass_extraction output.xlsx --dir data/ --concurrency 10
```

Rate-limit backoff (`MAX_API_RETRIES=6` by default) handles 429s automatically via exponential backoff.

### Custom checkpoint directory

By default checkpoints live in `runs/latest/`. To snapshot a prior run:

```bash
python -m qcaass_extraction output.xlsx --dir data/ --out-dir runs/2026-03-22-attempt-1
```

## Output

### `output.xlsx` — Three sheets

- **tools**: one row per document (tool_id, name, purpose, evidence, architecture, challenges summary)
- **algorithms**: one row per offered algorithm (tool_id, name, type, evidence)
- **challenges**: one row per limitation (tool_id, statement, category, evidence)
- **validation_errors**: every quote-fidelity error (field_path, value, quote, reason)

All evidence quotes are verbatim substrings of the source (validated at extraction time).

### `runs/<out-dir>/records/` — Checkpoints

One JSON file per finished document: `T_<content-hash>.json`. Enables resume and partial-run queries.

### `runs/<out-dir>/manifest.jsonl` — Run log

One line per attempt (JSON):
```json
{"tool_id": "T_abc...", "path": "data/x.pdf", "status": "done|needs_review|failed", "duration_s": 2.15, "reanchor_dropped": 0, "ts": 1711000000.123}
```

## Examples

### Quick validate: run on 4 PDFs

```bash
python -m qcaass_extraction test-output.xlsx data/*.pdf
```

### Large corpus: estimate, then run with retries on failures

```bash
# Estimate cost
python -m qcaass_extraction output.xlsx --dir /large/corpus/ --estimate

# Run with higher concurrency
python -m qcaass_extraction output.xlsx --dir /large/corpus/ --concurrency 8

# Check manifest for failures
cat runs/latest/manifest.jsonl | grep '"status": "failed"' | jq .

# Re-extract failed docs
python -m qcaass_extraction output.xlsx --dir /large/corpus/ --rerun status:failed

# Re-extract all docs after fixing prompts/schema
python -m qcaass_extraction output.xlsx --dir /large/corpus/ --rerun all --out-dir runs/fixed
```

### Inspect a single doc's record

```bash
# Find its tool_id in the manifest
cat runs/latest/manifest.jsonl | jq '.tool_id' | head -1

# Read the checkpoint JSON
cat "runs/latest/records/T_<id>.json" | python -m json.tool
```

## Architecture Deep Dive

### Per-document graph flow

1. **load_doc**: Extract text, normalize, estimate tokens.
   - Short doc (< 10k tokens) → skip locate/reanchor, go straight to extract.
   - Long doc → locate spans.
2. **locate_spans** (flash model): Over-retrieve candidate passages for five categories.
3. **reanchor** (deterministic): Fuzzy-match returned passages back to canonical text; drop mismatches.
4. **extract_merged** (strong model): Single call, whole `ToolRecord` structured output.
   - On success → validate.
   - On parse failure → fallback to per-category extractors.
5. **validate** (deterministic): Check quotes are verbatim substrings; decide retries.
6. **fallback extractors** (strong model, per-category): Re-extract only errored categories.
7. **assemble**: Build `ToolRecord`, set `needs_review` if errors survived.

### Batch driver flow

1. **Checkpoint check**: Skip docs already finished.
2. **Concurrency-bounded worker pool**: Up to `--concurrency` docs in parallel.
3. **Per-doc isolation**: One doc's graph failure doesn't abort the batch.
4. **Immediate persistence**: Each finished record saved to `records/<tool_id>.json`.
5. **Manifest log**: Every attempt appended to `manifest.jsonl` (for auditing).
6. **Workbook rebuild**: After batch, read all checkpoints and write one `.xlsx`.

So a 174-file run is parallelizable (e.g., 174 docs / 5 concurrency ≈ 35 graph invokes in parallel). With checkpoint/resume, a crash at doc 170 doesn't lose work—rerun the same command and only unfinished docs are processed.

## Tuning for your API tier

| Tier | Concurrency | Notes |
|------|-------------|-------|
| Free / low-rate | 1–2 | No parallelism, but no 429s. Slow but safe. |
| Standard | 5–8 | Default concurrency=5; good for <1K TPM limits. |
| High-rate | 10–20 | High throughput; monitor 429s; backoff handles them. |

Monitor the manifest for `"error": "429"` or `"error": "rate_limit_exceeded"`. If frequent, lower `--concurrency`.

## Troubleshooting

### High "reanchor_dropped" count

The flash model returned passages that don't match the source. Likely causes:
- OCR artifacts or smart-quote mismatches (normally handled by normalization).
- Span detection is off (over-retrieving tangentially-related text).

Check the manifest's `reanchor_dropped` field and spot-check the source PDF.

### Many documents with "needs_review"

Validation failures (quotes not found verbatim in source, missing evidence, etc.). Check `validation_errors` sheet in the workbook or the individual checkpoint JSON:

```bash
cat runs/latest/records/T_<id>.json | jq '.validation_errors'
```

Fix the prompt / re-anchor threshold if systematic, then `--rerun status:needs_review`.

### Out of memory on very large corpus

Concurrent docs are bounded by `--concurrency`, not unbounded. Each graph is stateless and released when done. If you hit memory limits, lower `--concurrency` or run multiple times on different subsets of documents.

### Model won't structure-output

Ensure `STRONG_MODEL` supports the provider's structured-output syntax. Some older models may not support it; fall back to a newer variant. The fallback extractors will handle single-field calls as a workaround, but performance degrades.
