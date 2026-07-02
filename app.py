"""FastAPI service wrapping text_stats.py as REST. Localhost only.

GET  /health              -> {"ok": true}
POST /tools/text_stats    -> text statistics or structured error
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from config import EXECUTION_TIMEOUT_S, MAX_BODY_BYTES
from logging_setup import log_event, setup_logger
from text_stats import analyze_text

logger = setup_logger("fastapi")
_executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI(title="openclaw-local-verify")


class TextStatsRequest(BaseModel):
    text: str
    request_id: str | None = None


def _structured_error(status: int, request_id: str, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"ok": False, "request_id": request_id, "error": {"code": code, "message": message}},
    )


@app.middleware("http")
async def body_size_limit(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and int(cl) > MAX_BODY_BYTES:
        return _structured_error(413, "", "body_too_large", "request body too large")
    return await call_next(request)


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/tools/text_stats")
async def text_stats_endpoint(payload: dict):
    start = time.monotonic()

    # Validate input shape ourselves so we can return a structured error
    # (FastAPI's default 422 dumps a non-uniform body).
    try:
        req = TextStatsRequest(**payload)
    except ValidationError:
        request_id = ""
        if isinstance(payload, dict) and isinstance(payload.get("request_id"), str):
            request_id = payload["request_id"]
        dur = int((time.monotonic() - start) * 1000)
        log_event(logger, "fastapi", request_id, "text_stats", "error", dur, "invalid_input")
        return _structured_error(422, request_id, "invalid_input", "text must be a string")

    request_id = req.request_id or f"req_{uuid.uuid4().hex[:12]}"

    try:
        future = _executor.submit(analyze_text, req.text, request_id)
        result = future.result(timeout=EXECUTION_TIMEOUT_S)
    except FutureTimeout:
        dur = int((time.monotonic() - start) * 1000)
        log_event(logger, "fastapi", request_id, "text_stats", "error", dur, "execution_timeout")
        return _structured_error(504, request_id, "execution_timeout", "script execution timed out")
    except Exception:
        dur = int((time.monotonic() - start) * 1000)
        log_event(logger, "fastapi", request_id, "text_stats", "error", dur, "internal_error")
        return _structured_error(500, request_id, "internal_error", "internal error")

    dur = int((time.monotonic() - start) * 1000)
    status = "ok" if result["ok"] else "error"
    err_type = None if result["ok"] else result["error"]["code"]
    # Map business errors (too-long / invalid produced by analyze_text) to 422,
    # keeping the structured body.
    http_status = 200 if result["ok"] else 422
    log_event(logger, "fastapi", request_id, "text_stats", status, dur, err_type, input_length=len(req.text))
    return JSONResponse(status_code=http_status, content=result)
