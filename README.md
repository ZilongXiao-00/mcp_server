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
