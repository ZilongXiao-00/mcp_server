# OpenClaw Local-Capability Verification Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal verification pipeline so cloud OpenClaw can call a local `text_stats` tool through Cloudflare Tunnel → MCP Server → FastAPI → local script, with `request_id` correlation across all layers and structured error handling.

**Architecture:** Dual-process path A. `text_stats.py` is a pure function module. FastAPI (`app.py`, `127.0.0.1:8000`) imports and wraps it as REST, localhost-only. MCP Server (`mcp_server.py`, `127.0.0.1:8001`, Streamable HTTP) registers `text_stats` as a tool and calls FastAPI via httpx internally. cloudflared tunnels only the MCP port. Three layers share `request_id` and a unified log format.

**Tech Stack:** Python 3.11 (A2A conda env), FastAPI 0.136, uvicorn, mcp 1.28.1 (FastMCP, streamable-http), httpx, pytest + pytest-asyncio. Windows / PowerShell.

**Run env:** All `python`/`pytest` commands run in the A2A conda env. Use `conda run -n A2A python ...` or `conda run -n A2A pytest ...` (these do not require activating the env first).

**Spec:** `docs/superpowers/specs/2026-07-02-openclaw-local-verify-design.md`

---

## File Structure

| File | Responsibility |
| --- | --- |
| `text_stats.py` | Pure function `analyze_text(text, request_id) -> dict`. No I/O, no network. |
| `config.py` | Central config loaded from env vars (ports, URLs, limits, token). |
| `app.py` | FastAPI app: `GET /health`, `POST /tools/text_stats`. Wraps `analyze_text`, logs, error handling. |
| `mcp_server.py` | FastMCP app: `text_stats` tool, calls FastAPI via httpx, optional Bearer auth. |
| `logging_setup.py` | Shared structured line-logger used by app + mcp_server. |
| `tests/conftest.py` | Shared fixtures (FastAPI ASGI client). |
| `tests/test_text_stats.py` | Unit tests for `analyze_text`. |
| `tests/test_app.py` | ASGI tests for FastAPI endpoints. |
| `tests/test_mcp_server.py` | Loopback-server tests for the tool + auth + downstream failure. |
| `scripts/start_fastapi.ps1` | Start FastAPI in A2A. |
| `scripts/start_mcp.ps1` | Start MCP Server in A2A. |
| `scripts/start_tunnel.ps1` | Start cloudflared temp tunnel to MCP port. |
| `scripts/correlate_logs.py` | Group multi-layer logs by `request_id`. |
| `requirements.txt` | Pinned dependency list. |
| `.env.example` | Documented env-var template. |
| `runbook.md` | Phases 0/4/5/6 executable steps + OpenClaw config example. |
| `README.md` | Quick start. |

---

## Conventions

**Unified log format** (stdout, one line per event):

```
<ISO8601> | <layer> | <request_id> | <tool> | <status> | <duration_ms>ms | [<error_type>]
```

- `layer` ∈ `fastapi`, `mcp`
- `status` ∈ `ok`, `error`
- `error_type` only present when status=`error`
- Input is logged as length only (truncated summary, max 200 chars), never full text or tokens.

**Error response shape** (identical at FastAPI and MCP layers):

```json
{"ok": false, "request_id": "...", "error": {"code": "...", "message": "..."}}
```

**Success response shape:**

```json
{"ok": true, "request_id": "...", "result": {"length": 14, "word_count": 2}}
```

---

## Task 1: Dependencies and project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `pytest.ini`

- [ ] **Step 1: Write `requirements.txt`**

```text
fastapi>=0.115
uvicorn[standard]>=0.30
mcp>=1.6
httpx>=0.27
python-dotenv>=1.0
pytest>=8
pytest-asyncio>=0.23
```

- [ ] **Step 2: Write `.env.example`**

```text
# FastAPI service
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=8000

# MCP Server
MCP_HOST=127.0.0.1
MCP_PORT=8001

# URL MCP uses to reach FastAPI (localhost only)
FASTAPI_URL=http://127.0.0.1:8000

# Optional Bearer token for the public MCP entry point.
# Leave empty to disable auth (local verification only).
MCP_AUTH_TOKEN=

# Limits
MAX_BODY_BYTES=1048576
MAX_INPUT_CHARS=100000
EXECUTION_TIMEOUT_S=5
MCP_DOWNSTREAM_TIMEOUT_S=10
```

- [ ] **Step 3: Write `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: Verify deps are installed in A2A**

Run:
```powershell
conda run -n A2A python -m pip install -r requirements.txt
conda run -n A2A python -m pip show fastapi mcp httpx pytest pytest-asyncio python-dotenv | Select-String "^(Name|Version):"
```
Expected: all packages report present; versions >= the floors above (mcp 1.28.1, fastapi 0.136.x, etc.).

- [ ] **Step 5: Commit**

```powershell
git add requirements.txt .env.example pytest.ini
git commit -m "chore: add dependencies and pytest config"
```

---

## Task 2: `config.py` — central configuration

**Files:**
- Create: `config.py`

- [ ] **Step 1: Write `config.py`**

```python
"""Central configuration. All values come from environment variables
(.env is loaded for convenience), with sensible defaults for local
verification.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


FASTAPI_HOST: str = _env_str("FASTAPI_HOST", "127.0.0.1")
FASTAPI_PORT: int = _env_int("FASTAPI_PORT", 8000)

MCP_HOST: str = _env_str("MCP_HOST", "127.0.0.1")
MCP_PORT: int = _env_int("MCP_PORT", 8001)

FASTAPI_URL: str = _env_str("FASTAPI_URL", "http://127.0.0.1:8000")

# Empty string = auth disabled.
MCP_AUTH_TOKEN: str = os.getenv("MCP_AUTH_TOKEN", "")

MAX_BODY_BYTES: int = _env_int("MAX_BODY_BYTES", 1_048_576)
MAX_INPUT_CHARS: int = _env_int("MAX_INPUT_CHARS", 100_000)
EXECUTION_TIMEOUT_S: int = _env_int("EXECUTION_TIMEOUT_S", 5)
MCP_DOWNSTREAM_TIMEOUT_S: int = _env_int("MCP_DOWNSTREAM_TIMEOUT_S", 10)

# Convenience: the base URL FastAPI binds to.
FASTAPI_BASE_URL: str = f"http://{FASTAPI_HOST}:{FASTAPI_PORT}"
```

- [ ] **Step 2: Verify it imports and reads defaults**

Run:
```powershell
conda run -n A2A python -c "import config; print(config.FASTAPI_PORT, config.MCP_PORT, config.MAX_INPUT_CHARS, repr(config.MCP_AUTH_TOKEN))"
```
Expected: `8000 8001 100000 ''`

- [ ] **Step 3: Commit**

```powershell
git add config.py
git commit -m "feat: add central config module"
```

---

## Task 3: `text_stats.py` — core pure function (TDD)

**Files:**
- Create: `tests/test_text_stats.py`
- Create: `text_stats.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_text_stats.py`:

```python
from text_stats import analyze_text


def test_normal_input():
    r = analyze_text("hello openclaw", request_id="t-1")
    assert r["ok"] is True
    assert r["request_id"] == "t-1"
    assert r["result"] == {"length": 14, "word_count": 2}


def test_empty_string_is_valid():
    r = analyze_text("", request_id="t-2")
    assert r["ok"] is True
    assert r["result"] == {"length": 0, "word_count": 0}


def test_whitespace_only_counts_as_zero_words():
    r = analyze_text("   \t\n  ")
    assert r["ok"] is True
    assert r["result"]["length"] == 6
    assert r["result"]["word_count"] == 0


def test_non_string_input_is_invalid():
    r = analyze_text(123, request_id="t-3")  # type: ignore[arg-type]
    assert r["ok"] is False
    assert r["request_id"] == "t-3"
    assert r["error"]["code"] == "invalid_input"


def test_none_input_is_invalid():
    r = analyze_text(None)  # type: ignore[arg-type]
    assert r["ok"] is False
    assert r["error"]["code"] == "invalid_input"


def test_too_long_input_is_rejected():
    from config import MAX_INPUT_CHARS
    r = analyze_text("a" * (MAX_INPUT_CHARS + 1), request_id="t-4")
    assert r["ok"] is False
    assert r["error"]["code"] == "input_too_long"


def test_request_id_auto_generated_when_missing():
    r = analyze_text("hi")
    assert r["ok"] is True
    assert r["request_id"].startswith("req_")
    assert len(r["request_id"]) > len("req_")


def test_non_string_input_does_not_raise():
    # Must return a structured error, never raise.
    for bad in (123, None, ["a list"], {"a": "dict"}):
        r = analyze_text(bad)  # type: ignore[arg-type]
        assert r["ok"] is False
        assert r["request_id"].startswith("req_")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
conda run -n A2A pytest tests/test_text_stats.py -v
```
Expected: collection error / FAIL — `ModuleNotFoundError: No module named 'text_stats'`.

- [ ] **Step 3: Write `text_stats.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
conda run -n A2A pytest tests/test_text_stats.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_text_stats.py text_stats.py
git commit -m "feat: add text_stats pure function with structured errors"
```

---

## Task 4: `logging_setup.py` — shared structured logger

**Files:**
- Create: `logging_setup.py`

- [ ] **Step 1: Write `logging_setup.py`**

```python
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
```

- [ ] **Step 2: Verify it imports and prints a line**

Run:
```powershell
conda run -n A2A python -c "from logging_setup import setup_logger, log_event; lg = setup_logger('fastapi'); log_event(lg, 'fastapi', 'req_abc', 'text_stats', 'ok', 12, input_length=14)"
```
Expected: a single line printed to stdout, e.g.:
`2026-07-02T... | fastapi | req_abc | text_stats | ok | 12ms | in_len=14`

- [ ] **Step 3: Commit**

```powershell
git add logging_setup.py
git commit -m "feat: add shared structured logger"
```

---

## Task 5: `app.py` — FastAPI service (TDD)

**Files:**
- Create: `tests/test_app.py`
- Create: `tests/conftest.py`
- Create: `app.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
```

- [ ] **Step 2: Write the failing tests**

`tests/test_app.py`:

```python
import pytest

from config import MAX_BODY_BYTES, MAX_INPUT_CHARS


pytestmark = pytest.mark.asyncio


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_text_stats_normal(client):
    r = await client.post("/tools/text_stats", json={"text": "hello openclaw", "request_id": "t-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["request_id"] == "t-1"
    assert body["result"] == {"length": 14, "word_count": 2}


async def test_text_stats_empty_is_valid(client):
    r = await client.post("/tools/text_stats", json={"text": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"] == {"length": 0, "word_count": 0}
    assert body["request_id"].startswith("req_")


async def test_text_stats_request_id_auto_generated(client):
    r = await client.post("/tools/text_stats", json={"text": "hi"})
    assert r.status_code == 200
    assert r.json()["request_id"].startswith("req_")


async def test_text_stats_non_string_returns_structured_error(client):
    r = await client.post("/tools/text_stats", json={"text": 123})
    # Pydantic rejects non-string -> 422, but body is structured.
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    assert "traceback" not in r.text.lower()


async def test_text_stats_missing_text_field_returns_structured_error(client):
    r = await client.post("/tools/text_stats", json={})
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"


async def test_text_stats_too_long_returns_structured_error(client):
    r = await client.post(
        "/tools/text_stats",
        json={"text": "a" * (MAX_INPUT_CHARS + 1)},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "input_too_long"


async def test_oversized_body_rejected(client):
    big = "x" * (MAX_BODY_BYTES + 10)
    r = await client.post(
        "/tools/text_stats",
        json={"text": big},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "body_too_large"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```powershell
conda run -n A2A pytest tests/test_app.py -v
```
Expected: collection error / FAIL — `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 4: Write `app.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```powershell
conda run -n A2A pytest tests/test_app.py -v
```
Expected: all 8 tests pass.

- [ ] **Step 6: Run full suite so far**

Run:
```powershell
conda run -n A2A pytest -v
```
Expected: all tests in test_text_stats + test_app pass.

- [ ] **Step 7: Commit**

```powershell
git add tests/conftest.py tests/test_app.py app.py
git commit -m "feat: add FastAPI service with health and text_stats endpoints"
```

---

## Task 6: `mcp_server.py` — MCP Server (TDD)

**Files:**
- Create: `tests/test_mcp_server.py`
- Create: `mcp_server.py`

**Testing approach:** Start the MCP streamable-http app on a real loopback port (uvicorn), connect a real MCP client (`streamablehttp_client` + `ClientSession`) to it, and run a tiny stub FastAPI on another loopback port to stand in for the real FastAPI. Point the MCP server at the stub via `mcp_server.FASTAPI_URL`. This exercises the real httpx call path without monkeypatching the global `httpx` (which the MCP client itself uses for its transport). For the downstream-unavailable test, the stub is left unbound so the MCP server's httpx call raises `ConnectError` naturally.

- [ ] **Step 1: Write the failing tests**

`tests/test_mcp_server.py`:

```python
import asyncio
import contextlib
import json
import socket

import httpx
import pytest
import uvicorn
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

import mcp_server


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _no_auth_by_default(monkeypatch):
    """Most tests run with auth off. The auth test overrides this."""
    monkeypatch.setattr(mcp_server, "MCP_AUTH_TOKEN", "")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port), timeout=0.25
            )
            writer.close()
            await writer.wait_closed()
            return
        except Exception:
            await asyncio.sleep(0.05)
    raise RuntimeError(f"port {port} not ready")


@contextlib.asynccontextmanager
async def _serve(app, port: int):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    await _wait_for_port(port)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


@contextlib.asynccontextmanager
async def mcp_server_url():
    """Start the MCP server (authed_app) on an ephemeral port; yield its base URL."""
    async with _serve(mcp_server.authed_app(), _free_port()) as base:
        yield base


@contextlib.asynccontextmanager
async def stub_fastapi(responder):
    """Tiny stub standing in for the real FastAPI.

    `responder`: async (request) -> (status: int, body: dict). If `responder`
    is None, the port is NOT bound, so the MCP server's httpx call fails with
    ConnectError (used to test downstream_unavailable).
    """
    port = _free_port()
    if responder is None:
        yield f"http://127.0.0.1:{port}"  # unbound -> ConnectError
        return

    async def stats(request: Request):
        status, body = await responder(request)
        return JSONResponse(body, status_code=status)

    app = Starlette(routes=[Route("/tools/text_stats", stats, methods=["POST"])])
    async with _serve(app, port) as base:
        yield base


@contextlib.asynccontextmanager
async def mcp_client(base: str):
    async with streamablehttp_client(url=base + "/mcp") as (read, write, _get_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def test_tool_list_contains_text_stats():
    async with mcp_server_url() as base, mcp_client(base) as session:
        tools = await session.list_tools()
        names = [t.name for t in tools.tools]
        assert "text_stats" in names


async def test_call_text_stats_normal(monkeypatch):
    async def responder(request):
        body = await request.json()
        return 200, {
            "ok": True,
            "request_id": body["request_id"],
            "result": {"length": 14, "word_count": 2},
        }

    async with stub_fastapi(responder) as fastapi_base:
        monkeypatch.setattr(mcp_server, "FASTAPI_URL", fastapi_base)
        async with mcp_server_url() as base, mcp_client(base) as session:
            result = await session.call_tool("text_stats", {"text": "hello openclaw", "request_id": "t-1"})
            data = json.loads(result.content[0].text)
            assert data["ok"] is True
            assert data["result"] == {"length": 14, "word_count": 2}
            assert data["request_id"] == "t-1"


async def test_call_text_stats_downstream_unavailable(monkeypatch):
    # No stub bound -> MCP's httpx call raises ConnectError.
    async with stub_fastapi(None) as fastapi_base:
        monkeypatch.setattr(mcp_server, "FASTAPI_URL", fastapi_base)
        async with mcp_server_url() as base, mcp_client(base) as session:
            result = await session.call_tool("text_stats", {"text": "hi"})
            data = json.loads(result.content[0].text)
            assert data["ok"] is False
            assert data["error"]["code"] == "downstream_unavailable"


async def test_request_id_propagated_to_fastapi(monkeypatch):
    captured = {}

    async def responder(request):
        body = await request.json()
        captured["request_id"] = body["request_id"]
        return 200, {
            "ok": True,
            "request_id": body["request_id"],
            "result": {"length": 2, "word_count": 1},
        }

    async with stub_fastapi(responder) as fastapi_base:
        monkeypatch.setattr(mcp_server, "FASTAPI_URL", fastapi_base)
        async with mcp_server_url() as base, mcp_client(base) as session:
            await session.call_tool("text_stats", {"text": "hi", "request_id": "shared-99"})
    assert captured["request_id"] == "shared-99"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
conda run -n A2A pytest tests/test_mcp_server.py -v
```
Expected: collection error / FAIL — `ModuleNotFoundError: No module named 'mcp_server'`.

- [ ] **Step 3: Write `mcp_server.py`**

```python
"""MCP Server (Streamable HTTP). Registers the `text_stats` tool, which
calls FastAPI's POST /tools/text_stats internally. Optional Bearer auth on
the public entry point is wired in Task 7 via authed_app().
"""
from __future__ import annotations

import json
import time
import uuid

import httpx
from mcp.server.fastmcp import FastMCP

from config import FASTAPI_URL, MCP_AUTH_TOKEN, MCP_DOWNSTREAM_TIMEOUT_S
from logging_setup import log_event, setup_logger

logger = setup_logger("mcp")

mcp = FastMCP(
    name="openclaw-local-verify",
    host="127.0.0.1",
    port=8001,
    streamable_http_path="/mcp",
)


def _tool_error(request_id: str, code: str, message: str) -> str:
    return json.dumps({
        "ok": False,
        "request_id": request_id,
        "error": {"code": code, "message": message},
    })


@mcp.tool(
    name="text_stats",
    description="Analyze text and return basic text statistics (character count and word count).",
)
async def text_stats(text: str, request_id: str | None = None) -> str:
    rid = request_id if request_id else f"req_{uuid.uuid4().hex[:12]}"
    start = time.monotonic()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FASTAPI_URL}/tools/text_stats",
                json={"text": text, "request_id": rid},
                timeout=MCP_DOWNSTREAM_TIMEOUT_S,
            )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        dur = int((time.monotonic() - start) * 1000)
        log_event(logger, "mcp", rid, "text_stats", "error", dur, "downstream_unavailable")
        return _tool_error(rid, "downstream_unavailable", "FastAPI unavailable")

    dur = int((time.monotonic() - start) * 1000)
    body = resp.json()
    status = "ok" if body.get("ok") else "error"
    err_type = None if body.get("ok") else body.get("error", {}).get("code")
    log_event(logger, "mcp", rid, "text_stats", status, dur, err_type)
    return json.dumps(body)


def authed_app():
    """ASGI app for the MCP streamable-http transport.

    Task 6: returns the plain FastMCP app (no auth). Task 7 wraps this with
    BearerAuthMiddleware when MCP_AUTH_TOKEN is set. Both serving and tests
    go through this function so auth is applied consistently.
    """
    return mcp.streamable_http_app()


def run() -> None:
    import uvicorn
    uvicorn.run(authed_app(), host="127.0.0.1", port=8001)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
conda run -n A2A pytest tests/test_mcp_server.py -v
```
Expected: 4 passed (tool list, normal call, downstream unavailable, request_id propagation). If a test hangs, confirm the loopback ports are free and uvicorn started (check for a "port not ready" RuntimeError — means `_wait_for_port` timed out; retry usually resolves ephemeral-port races).

- [ ] **Step 5: Commit**

```powershell
git add tests/test_mcp_server.py mcp_server.py
git commit -m "feat: add MCP server with text_stats tool calling FastAPI"
```

---

## Task 7: MCP Bearer-token auth (TDD)

**Files:**
- Modify: `mcp_server.py` (add `BearerAuthMiddleware`, wrap in `authed_app`)
- Modify: `tests/test_mcp_server.py` (add raw-HTTP auth test)

**Approach:** Auth is enforced by an ASGI middleware wrapping the FastMCP app (NOT a `@mcp.custom_route` on `/mcp`, which would shadow FastMCP's own streamable-http handler). The test checks the gate at the raw HTTP level: no `Authorization` header → 401 with the structured `unauthorized` body; correct header → not 401 (FastMCP then handles the request normally).

- [ ] **Step 1: Add the failing auth test**

Append to `tests/test_mcp_server.py`:

```python
async def test_unauthorized_when_token_required(monkeypatch):
    # Force auth on for this test (overrides the autouse "" default).
    monkeypatch.setattr(mcp_server, "MCP_AUTH_TOKEN", "secret-token")

    async with mcp_server_url() as base:
        async with httpx.AsyncClient() as http:
            # No Authorization header -> rejected at the gate.
            r = await http.post(
                base + "/mcp",
                headers={"Content-Type": "application/json"},
                content=b"{}",
            )
            assert r.status_code == 401
            assert r.json()["error"]["code"] == "unauthorized"

            # Correct header -> passes the gate (FastMCP handles it next).
            # We only assert it is NOT a 401.
            r2 = await http.post(
                base + "/mcp",
                headers={"Content-Type": "application/json", "Authorization": "Bearer secret-token"},
                content=b"{}",
            )
            assert r2.status_code != 401
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
conda run -n A2A pytest tests/test_mcp_server.py::test_unauthorized_when_token_required -v
```
Expected: FAIL — the no-header request is not rejected (status != 401), because `authed_app()` still returns the plain app.

- [ ] **Step 3: Add `BearerAuthMiddleware` and update `authed_app()` in `mcp_server.py`**

Add the middleware class after the imports (below `logger`/`mcp`), and replace the existing `authed_app()` body. The `text_stats` tool and `run()` are unchanged.

Add this class (after the `mcp = FastMCP(...)` block):

```python
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """ASGI middleware enforcing an optional Bearer token on the /mcp path.

    When `token` is empty, all requests pass through unchanged (auth off).
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return

        if scope.get("path", "").startswith("/mcp"):
            auth = ""
            for k, v in scope.get("headers", []):
                if k.decode("latin-1").lower() == "authorization":
                    auth = v.decode("latin-1")
            token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
            if token != self.token:
                body = json.dumps({
                    "ok": False,
                    "request_id": "",
                    "error": {"code": "unauthorized", "message": "invalid or missing token"},
                }).encode()
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
```

Replace the existing `authed_app()` with:

```python
def authed_app():
    """ASGI app for the MCP streamable-http transport, with optional Bearer auth.

    When MCP_AUTH_TOKEN is set, the public /mcp entry point requires a matching
    Bearer token. Empty token = auth off.
    """
    app = mcp.streamable_http_app()
    if MCP_AUTH_TOKEN:
        app = BearerAuthMiddleware(app, MCP_AUTH_TOKEN)
    return app
```

- [ ] **Step 4: Run the auth test to verify it passes**

Run:
```powershell
conda run -n A2A pytest tests/test_mcp_server.py::test_unauthorized_when_token_required -v
```
Expected: PASS.

- [ ] **Step 5: Run the full MCP test suite**

Run:
```powershell
conda run -n A2A pytest tests/test_mcp_server.py -v
```
Expected: 5 passed (4 from Task 6 with auth off + 1 auth). Confirm the other 4 still pass (the autouse `_no_auth_by_default` fixture keeps auth off for them).

- [ ] **Step 6: Commit**

```powershell
git add mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add optional Bearer-token auth to MCP entry point"
```

---

## Task 8: Startup scripts + log correlation script

**Files:**
- Create: `scripts/start_fastapi.ps1`
- Create: `scripts/start_mcp.ps1`
- Create: `scripts/start_tunnel.ps1`
- Create: `scripts/correlate_logs.py`

- [ ] **Step 1: Write `scripts/start_fastapi.ps1`**

```powershell
# Start the FastAPI service in the A2A conda env on 127.0.0.1:8000.
# Pipe stdout to a log file so correlate_logs.py can read it.
$logDir = Join-Path $PSScriptRoot ".." | Join-Path -ChildPath "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "fastapi.log"
Write-Host "Starting FastAPI -> $logFile"
conda run -n A2A --no-capture-output python -m uvicorn app:app --host 127.0.0.1 --port 8000 2>&1 | Tee-Object -FilePath $logFile
```

- [ ] **Step 2: Write `scripts/start_mcp.ps1`**

```powershell
# Start the MCP Server in the A2A conda env on 127.0.0.1:8001.
$logDir = Join-Path $PSScriptRoot ".." | Join-Path -ChildPath "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "mcp.log"
Write-Host "Starting MCP Server -> $logFile"
conda run -n A2A --no-capture-output python mcp_server.py 2>&1 | Tee-Object -FilePath $logFile
```

- [ ] **Step 3: Write `scripts/start_tunnel.ps1`**

```powershell
# Start a temporary cloudflared tunnel to the local MCP port (8001).
# Prints the public HTTPS URL. Requires cloudflared on PATH.
# Install: winget install --id Cloudflare.cloudflared
$port = 8001
Write-Host "Starting cloudflared tunnel -> http://localhost:$port"
Write-Host "Look for the line: 'https://<random>.trycloudflare.com'"
Write-Host "OpenClaw MCP URL = https://<random>.trycloudflare.com/mcp"
cloudflared tunnel --url http://localhost:$port
```

- [ ] **Step 4: Write `scripts/correlate_logs.py`**

```python
"""Correlate fastapi and mcp logs by request_id.

Usage:
    conda run -n A2A python scripts/correlate_logs.py [logs/fastapi.log logs/mcp.log ...]

Reads each log file, extracts lines containing a request_id, groups them by
request_id, and prints a table showing which layer saw each request and its
status. Helps verify the three-layer correlation required in phase 5.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict

LINE_RE = re.compile(
    r"^(?P<ts>[^|]+)\s*\|\s*(?P<layer>[^|]+)\s*\|\s*(?P<rid>[^|]+)\s*\|\s*"
    r"(?P<tool>[^|]+)\s*\|\s*(?P<status>[^|]+)\s*\|\s*(?P<dur>[^|]+)"
)


def main(paths: list[str]) -> None:
    events: dict[str, list[dict]] = defaultdict(list)
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = LINE_RE.search(line)
                    if not m:
                        continue
                    d = m.groupdict()
                    rid = d["rid"].strip()
                    if not rid:
                        continue
                    events[rid].append(d)
        except FileNotFoundError:
            print(f"[warn] missing log file: {path}", file=sys.stderr)

    print(f"{'request_id':<28} {'layer':<8} {'tool':<12} {'status':<8} {'dur':<10}")
    print("-" * 70)
    for rid, evs in events.items():
        for e in evs:
            print(
                f"{rid:<28} {e['layer'].strip():<8} {e['tool'].strip():<12} "
                f"{e['status'].strip():<8} {e['dur'].strip():<10}"
            )
        print()


if __name__ == "__main__":
    paths = sys.argv[1:] or ["logs/fastapi.log", "logs/mcp.log"]
    main(paths)
```

- [ ] **Step 5: Verify scripts are valid / importable**

Run:
```powershell
conda run -n A2A python -c "import ast; ast.parse(open('scripts/correlate_logs.py', encoding='utf-8').read()); print('correlate_logs.py OK')"
Test-Path scripts\start_fastapi.ps1, scripts\start_mcp.ps1, scripts\start_tunnel.ps1
```
Expected: `correlate_logs.py OK` and all three `.ps1` paths exist.

- [ ] **Step 6: Commit**

```powershell
git add scripts/start_fastapi.ps1 scripts/start_mcp.ps1 scripts/start_tunnel.ps1 scripts/correlate_logs.py
git commit -m "chore: add startup and log-correlation scripts"
```

---

## Task 9: Run full test suite + manual smoke test

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run:
```powershell
conda run -n A2A pytest -v
```
Expected: all tests pass (text_stats + app + mcp_server, including auth).

- [ ] **Step 2: Start FastAPI and smoke-test /health**

In one terminal:
```powershell
conda run -n A2A --no-capture-output python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
In another:
```powershell
conda run -n A2A python -c "import httpx; print(httpx.get('http://127.0.0.1:8000/health').json())"
```
Expected: `{'ok': True}`

- [ ] **Step 3: Smoke-test /tools/text_stats**

Run:
```powershell
conda run -n A2A python -c "import httpx; print(httpx.post('http://127.0.0.1:8000/tools/text_stats', json={'text':'hello openclaw','request_id':'smoke-1'}).json())"
```
Expected: `{'ok': True, 'request_id': 'smoke-1', 'result': {'length': 14, 'word_count': 2}}`

- [ ] **Step 4: Start MCP Server and smoke-test tool discovery + call**

In a terminal:
```powershell
conda run -n A2A --no-capture-output python mcp_server.py
```
In another (list tools + call via a tiny client):
```powershell
conda run -n A2A python -c "import asyncio; from mcp.client.session import ClientSession; from mcp.client.streamable_http import streamablehttp_client; exec('''\nasync def main():\n    async with streamablehttp_client(\"http://127.0.0.1:8001/mcp\") as (r,w,_):\n        async with ClientSession(r,w) as s:\n            await s.initialize()\n            tools = await s.list_tools()\n            print([t.name for t in tools.tools])\n            res = await s.call_tool(\"text_stats\", {\"text\":\"hello openclaw\",\"request_id\":\"smoke-2\"})\n            print(res.content[0].text)\nasyncio.run(main())\n''')"
```
Expected: `['text_stats']` and a JSON string with `ok: True`, `length: 14`, `word_count: 2`, `request_id: smoke-2`.

- [ ] **Step 5: Stop both servers (Ctrl+C in their terminals)**

- [ ] **Step 6: Commit** (only if tracking notes changed; otherwise skip)

No code change this task. If nothing was added, skip the commit.

---

## Task 10: `runbook.md` + `README.md` + `.gitignore` update

**Files:**
- Create: `runbook.md`
- Create: `README.md`
- Modify: `.gitignore` (add `logs/`)

- [ ] **Step 1: Update `.gitignore` to ignore `logs/`**

Append to `.gitignore`:

```text

# Local run logs (generated by start scripts)
logs/
```

- [ ] **Step 2: Write `runbook.md`**

````markdown
# Runbook — OpenClaw Local-Capability Verification

Executable steps for phases 0, 4, 5, 6. Code phases 1–3 are covered by the
test suite (`pytest`). All commands assume the A2A conda env.

## Phase 0 — Environment

1. Python: `conda run -n A2A python --version` → expect 3.11.x.
2. Install Python deps: `conda run -n A2A python -m pip install -r requirements.txt`.
3. Install cloudflared (one-time):
   ```powershell
   winget install --id Cloudflare.cloudflared
   ```
   Then: `cloudflared --version` → expect a version string.
4. Copy `.env.example` to `.env` and edit as needed (set `MCP_AUTH_TOKEN` for auth).

## Phase 1–3 — Code (automated by tests)

```powershell
conda run -n A2A pytest -v
```
All green = phases 1–3 done.

## Phase 4 — Cloudflare Tunnel

1. Start FastAPI (terminal A):
   ```powershell
   .\scripts\start_fastapi.ps1
   ```
2. Start MCP Server (terminal B):
   ```powershell
   .\scripts\start_mcp.ps1
   ```
3. Start tunnel (terminal C):
   ```powershell
   .\scripts\start_tunnel.ps1
   ```
   Note the printed `https://<random>.trycloudflare.com` URL.
4. From a non-localhost environment (phone, another machine, or curl from a
   cloud shell), hit the MCP endpoint:
   ```bash
   curl -i https://<random>.trycloudflare.com/mcp
   ```
   Expect an HTTP response (FastMCP responds to the streamable-http handshake).
5. Verify local logs (`logs/mcp.log`, `logs/fastapi.log`) show the request.
6. **Interruption test:** Ctrl+C the tunnel (terminal C). Re-curl the URL →
   expect connection failure (DNS/no route). Record the error.

## Phase 5 — OpenClaw end-to-end

1. In OpenClaw, configure a remote MCP server:
   - URL: `https://<random>.trycloudflare.com/mcp`
   - If `MCP_AUTH_TOKEN` is set, add header: `Authorization: Bearer <your token>`
2. Confirm `text_stats` appears in OpenClaw's tool list.
3. **Normal call:** invoke `text_stats(text="hello openclaw")`. Expect structured
   result `{length: 14, word_count: 2}`.
4. **Empty text:** `text_stats(text="")`. Expect `{length: 0, word_count: 0}`.
5. **Invalid param:** call with a non-string `text` or missing `text`. Expect a
   structured `invalid_input` error.
6. **Downstream down:** stop FastAPI (terminal A). Call from OpenClaw. Expect MCP
   to return `downstream_unavailable`. Restart FastAPI.
7. **Tunnel down:** stop the tunnel (terminal C). Call from OpenClaw. Expect
   OpenClaw-side connection failure.
8. **Log correlation:** run
   ```powershell
   conda run -n A2A python scripts\correlate_logs.py logs\fastapi.log logs\mcp.log
   ```
   Confirm each `request_id` appears in both `fastapi` and `mcp` layers.

## Phase 6 — Security & boundary checks

- [ ] Tool only accepts fixed params (`text`, `request_id`). No file/command paths.
- [ ] No file-read or command-exec endpoint exists anywhere.
- [ ] `MAX_INPUT_CHARS` rejects overlong input (tested).
- [ ] `MAX_BODY_BYTES` rejects oversized bodies (tested).
- [ ] `EXECUTION_TIMEOUT_S` caps script runtime (tested).
- [ ] With `MCP_AUTH_TOKEN` set, unauthenticated requests get 401 (tested).
- [ ] Logs contain no token, no full sensitive input (length summary only).
- [ ] FastAPI binds 127.0.0.1; only MCP is public via tunnel.

## Phase 7 — Final acceptance

Fill in `task.md` phase-7 conclusion template and check the success criteria.
````

- [ ] **Step 3: Write `README.md`**

````markdown
# OpenClaw Local-Capability Verification

Minimal pipeline proving cloud OpenClaw can call a local tool through
Cloudflare Tunnel → MCP Server → FastAPI → local script.

```
OpenClaw (cloud) → cloudflared tunnel → MCP Server (127.0.0.1:8001)
                                        → FastAPI (127.0.0.1:8000)
                                        → text_stats.py
```

## Quick start

```powershell
# 1. deps
conda run -n A2A python -m pip install -r requirements.txt

# 2. tests (phases 1–3)
conda run -n A2A pytest -v

# 3. run locally
.\scripts\start_fastapi.ps1     # terminal A
.\scripts\start_mcp.ps1         # terminal B
.\scripts\start_tunnel.ps1      # terminal C (needs cloudflared)
```

See `runbook.md` for phases 4–7 (tunnel + OpenClaw config + security).
See `docs/superpowers/specs/2026-07-02-openclaw-local-verify-design.md` for the design.

## Config

All knobs via env vars / `.env` — see `.env.example`. Key ones:
- `FASTAPI_PORT` / `MCP_PORT`
- `MCP_AUTH_TOKEN` (empty = no auth)
- `MAX_INPUT_CHARS`, `MAX_BODY_BYTES`, `EXECUTION_TIMEOUT_S`
````

- [ ] **Step 4: Commit**

```powershell
git add .gitignore runbook.md README.md
git commit -m "docs: add runbook, README, ignore logs/"
```

---

## Task 11: Update task.md checkboxes for phases 1–3

**Files:**
- Modify: `task.md`

- [ ] **Step 1: Mark phase-0 and phase-1–3 verified items in `task.md`**

Open `task.md` and change `[ ]` → `[x]` for the items below (these are the ones the code + tests now satisfy):

Phase 0 (already known):
- `[x]` 确认本地 Python 环境可用
- `[x]` 确认可以安装或已安装 FastAPI 相关依赖
- `[x]` 确认可以安装或已安装 MCP Server 相关依赖
- `[x]` 确认云端 OpenClaw 支持配置外部 MCP Server (HTTP 远程 MCP, 用户已确认)
- `[x]` 确认当前验证不需要访问本地真实业务文件
- `[x]` `python --version` 能正常返回版本
- `[x]` 本地能启动一个简单 Python 脚本
- `[x]` 已明确本次只验证 1 个无副作用测试工具
- `[x]` 记录本地 Python 版本 (3.11.15 / A2A)
- `[x]` 记录 OpenClaw 工具接入方式 (HTTP 远程 MCP)

(Leave cloudflared items `[ ]` — not installed yet.)

Phase 1:
- `[x]` 新建 `text_stats.py`
- `[x]` 脚本接收文本输入
- `[x]` 脚本返回字符数
- `[x]` 脚本返回词数
- `[x]` 脚本返回结构化 JSON
- `[x]` 脚本支持 `request_id`
- `[x]` 脚本处理空文本输入
- `[x]` 脚本处理超长文本输入
- `[x]` 脚本处理非法参数
- all Phase-1 检查项 and 测试用例 → `[x]`
- `[x]` `text_stats.py`

Phase 2:
- all FastAPI 功能点 / 检查项 → `[x]`
- `[x]` FastAPI 服务文件
- `[x]` REST API 本地调用记录 (smoke test in Task 9)
- `[x]` 错误处理测试记录

Phase 3:
- all MCP 功能点 → `[x]` (auth 功能点 with note "如 OpenClaw 支持" — implemented as optional)
- all MCP 检查项 that are testable locally → `[x]`
- `[x]` MCP Server 文件
- `[x]` MCP 工具定义
- `[x]` MCP 本地调用记录 (smoke test in Task 9)

(Leave phase 4–7 items `[ ]` — they depend on cloudflared + OpenClaw, executed by user via runbook.)

- [ ] **Step 2: Commit**

```powershell
git add task.md
git commit -m "docs: check off phases 0-3 in task.md"
```

---

## Task 12: Final full-suite run and push

**Files:** none

- [ ] **Step 1: Run the full suite one final time**

Run:
```powershell
conda run -n A2A pytest -v
```
Expected: all green.

- [ ] **Step 2: Push everything to remote**

```powershell
git push origin main
```
Expected: push succeeds; remote `origin/main` advances.

- [ ] **Step 3: Report**

Summarize: phases 1–3 implemented and tested; runbook ready for phases 4–7; cloudflared install + OpenClaw config are the remaining manual steps for the user.
