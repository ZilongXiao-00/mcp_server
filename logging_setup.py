"""Shared structured line-logger for fastapi and mcp layers.

Format: <ISO8601> | <layer> | <request_id> | <tool> | <status> | <duration_ms>ms | [<error_type>]
Input is logged as a length summary only, never full text or tokens.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone


def setup_logger(layer: str) -> logging.Logger:
    logger = logging.getLogger(f"verify.{layer}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}"


def log_event(
    logger: logging.Logger,
    layer: str,
    request_id: str,
    tool: str,
    status: str,
    duration_ms: int,
    error_type: str | None = None,
    input_length: int | None = None,
) -> None:
    parts = [_now_iso(), layer, request_id, tool, status, f"{duration_ms}ms"]
    if error_type:
        parts.append(error_type)
    line = " | ".join(parts)
    if input_length is not None:
        line += f" | in_len={input_length}"
    logger.info(line)
