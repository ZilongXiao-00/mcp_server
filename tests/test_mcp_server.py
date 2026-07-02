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
    loop = asyncio.get_running_loop()
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
