"""Structured JSON-lines pipeline logger.

Every log record is a single JSON object on one line (JSON-lines format).
Required fields match the production observability spec:
  timestamp, run_id, phase, source, query_id, doi, title_normalized,
  status, retry_count, error, credit_cost.

Usage:
    logger = PipelineLogger(run_id="RUN-20260604-120000", phase="search")
    logger.log("serpapi_scholar", query_id="SC3-step3", doi=None,
               status="success", credit_cost=1)
    logger.close()

Or as a context manager:
    with PipelineLogger(run_id=..., phase=...) as logger:
        logger.log(...)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

_TASK3 = Path(__file__).resolve().parent
_LOGS_DIR = _TASK3 / "logs"

# Valid status values (open-ended; extend as needed)
STATUS_QUEUED = "queued"
STATUS_ATTEMPTED = "attempted"
STATUS_SUCCESS = "success"
STATUS_RETRY = "retry"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_CIRCUIT_OPEN = "circuit_open"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_DEGRADED = "degraded"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PipelineLogger:
    """Writes JSON-lines structured logs to logs/{run_id}.jsonl.

    The logs/ directory is gitignored — logs are runtime artifacts, not
    committed evidence.
    """

    def __init__(
        self,
        run_id: str,
        phase: str,
        log_dir: Path = _LOGS_DIR,
        also_stderr: bool = False,
    ) -> None:
        self.run_id = run_id
        self.phase = phase
        self.also_stderr = also_stderr
        log_dir.mkdir(parents=True, exist_ok=True)
        self._path = log_dir / f"{run_id}.jsonl"
        self._fh: IO[str] = open(self._path, "a", encoding="utf-8")

    def log(
        self,
        source: str,
        *,
        query_id: str | None = None,
        doi: str | None = None,
        title_normalized: str | None = None,
        status: str,
        retry_count: int = 0,
        error: str | None = None,
        credit_cost: int = 0,
        **extra: Any,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": _utc_now(),
            "run_id": self.run_id,
            "phase": self.phase,
            "source": source,
            "query_id": query_id,
            "doi": doi,
            "title_normalized": title_normalized,
            "status": status,
            "retry_count": retry_count,
            "error": error,
            "credit_cost": credit_cost,
        }
        record.update(extra)
        line = json.dumps(record, separators=(",", ":"))
        self._fh.write(line + "\n")
        self._fh.flush()
        if self.also_stderr:
            print(f"[{self.phase}] {status} src={source} qid={query_id} doi={doi}",
                  file=sys.stderr)

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "PipelineLogger":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @property
    def log_path(self) -> Path:
        return self._path


def read_log(run_id: str, log_dir: Path = _LOGS_DIR) -> list[dict]:
    """Read all records for a run_id from its .jsonl file."""
    path = log_dir / f"{run_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
