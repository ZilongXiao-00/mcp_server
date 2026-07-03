"""MCP Server (Streamable HTTP). Registers the `text_stats` tool, which
calls FastAPI's POST /tools/text_stats internally. Optional Bearer auth on
the public entry point is wired in via authed_app().

A factory (build_server) creates a fresh FastMCP per app so each server
instance gets its own StreamableHTTPSessionManager (that manager's .run()
can only be called once per instance, so the singleton approach breaks when
serving more than once, e.g. across tests or restarts).
"""
from __future__ import annotations

import json
import time
import uuid

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from config import FASTAPI_URL, MCP_AUTH_TOKEN, MCP_DOWNSTREAM_TIMEOUT_S, MCP_TUNNEL_MODE
from logging_setup import log_event, setup_logger

logger = setup_logger("mcp")

TOOL_NAME = "text_stats"
TOOL_DESCRIPTION = "Analyze text and return basic text statistics (character count and word count)."


def _new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def _tool_error(request_id: str, code: str, message: str) -> str:
    return json.dumps({
        "ok": False,
        "request_id": request_id,
        "error": {"code": code, "message": message},
    })


async def text_stats_impl(text: str, request_id: str | None = None) -> str:
    """Tool logic. Reads FASTAPI_URL / MCP_DOWNSTREAM_TIMEOUT_S as module
    globals at call time so tests can monkeypatch FASTAPI_URL."""
    rid = request_id if request_id else _new_request_id()
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


def _transport_security() -> TransportSecuritySettings | None:
    if MCP_TUNNEL_MODE:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return None


def build_server() -> FastMCP:
    """Factory: a fresh FastMCP with the text_stats tool registered."""
    server = FastMCP(
        name="openclaw-local-verify",
        host="127.0.0.1",
        port=8001,
        streamable_http_path="/mcp",
        transport_security=_transport_security(),
    )
    server.tool(name=TOOL_NAME, description=TOOL_DESCRIPTION)(text_stats_impl)
    return server


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


def authed_app():
    """ASGI app for the MCP streamable-http transport, with optional Bearer auth.

    Builds a fresh server each call (each gets its own session manager).
    When MCP_AUTH_TOKEN is set, the public /mcp entry point requires a matching
    Bearer token. Empty token = auth off.
    """
    app = build_server().streamable_http_app()
    if MCP_AUTH_TOKEN:
        app = BearerAuthMiddleware(app, MCP_AUTH_TOKEN)
    return app


def run() -> None:
    import uvicorn
    uvicorn.run(authed_app(), host="127.0.0.1", port=8001)


if __name__ == "__main__":
    run()
