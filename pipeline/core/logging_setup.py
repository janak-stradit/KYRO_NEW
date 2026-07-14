"""
core/logging_setup.py — Structured JSON logging for the pipeline.
Logs to both stdout and a rotating file, with optional PostgreSQL sink.
Captures: execution time, memory, CPU, row counts, errors, warnings.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import platform
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON — machine-parseable and Loki-friendly."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        # Attach extra fields injected via logger.info(..., extra={...})
        for key in ("execution_id", "job_id", "pipeline", "rows", "stage", "entity"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        if record.exc_info:
            payload["exception"] = traceback.format_exception(*record.exc_info)

        return json.dumps(payload, default=str)


def setup_logging(
    level: str = "INFO",
    log_file: str = "logs/pipeline.log",
    json_format: bool = True,
) -> logging.Logger:
    """Configure root logger with console + rotating file handler.

    Args:
        level: Log level string (DEBUG/INFO/WARNING/ERROR/CRITICAL).
        log_file: Path for the rotating file sink.
        json_format: If True, emit JSON; otherwise plain text.

    Returns:
        Configured root logger instance.
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers on re-import
    if root.handlers:
        root.handlers.clear()

    formatter: logging.Formatter
    if json_format:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    root.addHandler(ch)

    # Rotating file handler (10 MB, keep 10 backups)
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8"
    )
    fh.setFormatter(formatter)
    root.addHandler(fh)

    return root


class PipelineTimer:
    """Context manager that times a code block and logs the duration."""

    def __init__(self, label: str, logger: logging.Logger | None = None) -> None:
        self.label = label
        self.logger = logger or logging.getLogger(__name__)
        self._start: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self) -> "PipelineTimer":
        self._start = time.perf_counter()
        self.logger.info("▶  Starting: %s", self.label)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.elapsed = time.perf_counter() - self._start
        if exc_type is None:
            self.logger.info("✔  Finished: %s in %.3fs", self.label, self.elapsed)
        else:
            self.logger.error(
                "✘  Failed: %s after %.3fs — %s", self.label, self.elapsed, exc_val
            )
        return False  # do not suppress exceptions


def new_execution_id() -> str:
    """Generate a unique pipeline execution ID."""
    return str(uuid.uuid4())


# Module-level logger
log = logging.getLogger("kyro.pipeline")
