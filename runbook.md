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
