"""Core text-statistics function. Pure: no I/O, no network, never raises.
Returns a structured dict for both success and error cases.
"""
from __future__ import annotations

import uuid

from config import MAX_INPUT_CHARS


def _new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def _ok(request_id: str, length: int, word_count: int) -> dict:
    return {
        "ok": True,
        "request_id": request_id,
        "result": {"length": length, "word_count": word_count},
    }


def _err(request_id: str, code: str, message: str) -> dict:
    return {
        "ok": False,
        "request_id": request_id,
        "error": {"code": code, "message": message},
    }


def analyze_text(text, request_id: str | None = None) -> dict:
    """Return text statistics as a structured dict.

    Never raises. Non-string or over-limit input yields an `ok: false`
    error envelope with a stable `error.code`.
    """
    rid = request_id if request_id else _new_request_id()

    if not isinstance(text, str):
        return _err(rid, "invalid_input", "text must be a string")

    if len(text) > MAX_INPUT_CHARS:
        return _err(
            rid,
            "input_too_long",
            f"text exceeds {MAX_INPUT_CHARS} characters",
        )

    return _ok(rid, length=len(text), word_count=len(text.split()))
