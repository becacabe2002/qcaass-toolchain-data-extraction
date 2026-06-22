"""Per-document checkpoint store + run manifest.

At 174 files a single end-of-run workbook write means a crash at doc 170 loses
every record and all the API spend behind it. Instead each finished document is
persisted immediately as its own JSON file, and every attempt is appended to a
manifest. A rerun reads the store to skip finished docs (resume) and rebuilds
the workbook from whatever is on disk, so a partial run still yields output.

Writes are atomic (temp file + ``os.replace``), matching the workbook's swap.
"""

from __future__ import annotations

import json
import os
import time
from typing import Literal

from .schema import ToolRecord

Status = Literal["done", "needs_review", "failed"]


class CheckpointStore:
    """File-backed checkpoint store rooted at ``out_dir``."""

    def __init__(self, out_dir: str) -> None:
        self.out_dir = out_dir
        self.records_dir = os.path.join(out_dir, "records")
        self.manifest_path = os.path.join(out_dir, "manifest.jsonl")
        os.makedirs(self.records_dir, exist_ok=True)

    # ----- records -----

    def _record_path(self, tool_id: str) -> str:
        return os.path.join(self.records_dir, f"{tool_id}.json")

    def is_done(self, tool_id: str) -> bool:
        return os.path.exists(self._record_path(tool_id))

    def save_record(self, record: ToolRecord) -> None:
        """Persist one record, overwriting any prior checkpoint for its id."""
        path = self._record_path(record.tool_id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(record.model_dump_json(indent=2))
        os.replace(tmp, path)

    def load_all_records(self) -> list[ToolRecord]:
        """Load every checkpointed record, sorted by id for stable output."""
        records: list[ToolRecord] = []
        for name in sorted(os.listdir(self.records_dir)):
            if not name.endswith(".json") or name.endswith(".tmp"):
                continue
            with open(os.path.join(self.records_dir, name), encoding="utf-8") as fh:
                records.append(ToolRecord.model_validate_json(fh.read()))
        return records

    # ----- manifest -----

    def log(
        self,
        tool_id: str,
        path: str,
        status: Status,
        *,
        error: str = "",
        duration_s: float = 0.0,
        reanchor_dropped: int = 0,
    ) -> None:
        entry = {
            "tool_id": tool_id,
            "path": path,
            "status": status,
            "error": error,
            "duration_s": round(duration_s, 3),
            "reanchor_dropped": reanchor_dropped,
            "ts": time.time(),
        }
        with open(self.manifest_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def last_status_by_id(self) -> dict[str, Status]:
        """Map each tool_id to the status of its most recent manifest entry."""
        latest: dict[str, Status] = {}
        if not os.path.exists(self.manifest_path):
            return latest
        with open(self.manifest_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                latest[entry["tool_id"]] = entry["status"]
        return latest
