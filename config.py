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

# When using cloudflared quick tunnel, set to 1 to allow non-localhost Host headers.
# FastAPI stays localhost-only; optional MCP_AUTH_TOKEN still protects the entry.
MCP_TUNNEL_MODE: bool = os.getenv("MCP_TUNNEL_MODE", "").lower() in ("1", "true", "yes")

# Convenience: the base URL FastAPI binds to.
FASTAPI_BASE_URL: str = f"http://{FASTAPI_HOST}:{FASTAPI_PORT}"
