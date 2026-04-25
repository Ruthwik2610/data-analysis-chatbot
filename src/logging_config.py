from __future__ import annotations

import json
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "[email-redacted]"),
    (re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b"), "[number-redacted]"),
]


def redact(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    cleaned = value
    for pattern, replacement in PII_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def setup_named_logger(name: str, log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    handler = RotatingFileHandler(log_dir / f"{name}.log", maxBytes=2_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def setup_loggers(log_dir: Path) -> dict[str, logging.Logger]:
    return {name: setup_named_logger(name, log_dir) for name in ["app", "llm", "query", "cache", "errors"]}


def log_event(logger: logging.Logger, event: str, **payload: Any) -> None:
    safe_payload = {key: redact(value) for key, value in payload.items()}
    logger.info("%s %s", event, json.dumps(safe_payload, default=str, sort_keys=True))
