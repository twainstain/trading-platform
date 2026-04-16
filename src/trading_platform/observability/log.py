"""Centralized logging setup for trading systems.

Configures console + file + JSONL structured logging.
Products call setup_logging() once at startup, then use get_logger()
for module-level loggers.

The structured JSON logger ("platform_data") writes one JSON object per
line — products use it for scan events, decisions, and executions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

_CONFIGURED = False


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that serializes Decimal as string to preserve precision."""

    def default(self, o: object) -> object:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def setup_logging(
    level: int = logging.INFO,
    log_dir: str | Path | None = None,
    log_prefix: str = "bot",
) -> Path | None:
    """Configure root logger with console + file + JSONL handlers.

    Call once at startup. Safe to call multiple times — subsequent calls
    are no-ops.

    Args:
        level: Logging level.
        log_dir: Directory for log files. If None, only console logging.
        log_prefix: Prefix for log file names.

    Returns:
        Path to the log file, or None if log_dir was not set.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return None
    _CONFIGURED = True

    fmt = "%(asctime)s  %(name)-25s  %(levelname)-7s  %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(console)

    if log_dir is None:
        return None

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

    # Human-readable file
    log_file = log_path / f"{log_prefix}_{timestamp}.log"
    file_h = logging.FileHandler(str(log_file), encoding="utf-8")
    file_h.setLevel(level)
    file_h.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(file_h)

    # Structured JSONL file
    json_file = log_path / f"{log_prefix}_{timestamp}.jsonl"
    json_h = logging.FileHandler(str(json_file), encoding="utf-8")
    json_h.setLevel(logging.INFO)
    json_h.setFormatter(logging.Formatter("%(message)s"))
    json_logger = logging.getLogger("platform_data")
    json_logger.addHandler(json_h)
    json_logger.propagate = False

    return log_file


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name."""
    return logging.getLogger(name)


def get_data_logger() -> logging.Logger:
    """Return the structured data logger for JSONL output."""
    return logging.getLogger("platform_data")


def log_json(event: str, **fields) -> None:
    """Write a structured JSON event to the data log."""
    record = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    get_data_logger().info(json.dumps(record, cls=DecimalEncoder))
