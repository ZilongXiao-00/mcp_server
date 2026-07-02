# OpenClaw 调用本地能力验证 — 设计文档

- 日期：2026-07-02
- 关联文档：`task.md`、`plan.md`
- 状态：设计已确认，待编写实现计划

## 1. 背景与目标

验证「本地脚本能力服务化后，通过 Cloudflare Tunnel 暴露给云端 OpenClaw 调用」的路线是否可行。本次只验证最小闭环，不追求生产化：

```text
本地脚本 (text_stats.py)
  ↓ import 调用
FastAPI 服务 (127.0.0.1:8000)
  ↓ httpx 调用
本地 MCP Server (127.0.0.1:8001, Streamable HTTP)
  ↓ cloudflared 隧道
云端 OpenClaw (HTTP 远程 MCP)
```

核心要回答的问题：

- OpenClaw 能否通过公网 HTTPS 地址访问本地 MCP Server。
- 本地脚本能否被稳定包装成受控 API。
- 三层（OpenClaw / MCP / FastAPI）日志能否通过 `request_id` 串起来。
- 请求、鉴权、超时、错误返回能否满足基本可用性。

## 2. 范围

### 本次包含

- 实现代码层：`text_stats.py`、FastAPI（`app.py`）、MCP Server（`mcp_server.py`）、`config.py`。
- 为上述三层编写单元测试（TDD）。
- 提供阶段 0 / 4 / 5 / 6 的可执行运行手册（`runbook.md`）和辅助脚本（启动脚本、日志对照脚本）。
- 阶段 1–3 的本地验证由我完成并跑通测试。
- 阶段 4（cloudflared tunnel）和阶段 5（OpenClaw 端到端）的代码/脚本/配置示例由我提供，实际执行由用户在外部环境完成（cloudflared 需用户安装；OpenClaw 是用户的云端账号）。

### 本次不包含

- 不让 OpenClaw 直接访问本地文件系统。
- 不做复杂权限系统。
- 不处理大规模并发。
- 不做完整生产监控。
- 不接入多个脚本，只验证 1 个测试工具 `text_stats`。

### 环境现状（阶段 0 探测结果）

- 运行环境：**A2A conda 环境**，Python **3.11.15**。已装 `fastapi 0.136.3`、`httpx 0.28.1`、`uvicorn 0.48.0`、`python-dotenv 1.2.2`；需补装 `mcp`、`pytest`、`pytest-asyncio`。
- base miniforge Python 3.13.13 + pip 26.1.1 可用，但本验证统一在 A2A 环境运行。
- git 2.54 ✓。项目已 `git init`，远端 `https://github.com/ZilongXiao-00/mcp_server.git`，默认分支 `main`。
- cloudflared：未安装 ✗（runbook 提供安装步骤，由用户执行）。
- 操作系统：Windows 11，PowerShell。

## 3. 架构（路径 A：双进程，MCP 调 FastAPI）

### 3.1 进程与端口

| 层 | 进程 | 绑定 | 说明 |
| --- | --- | --- | --- |
| FastAPI | `uvicorn app:app` | `127.0.0.1:8000` | 仅本机可达，包装 `text_stats.py` |
| MCP Server | FastMCP，Streamable HTTP | `127.0.0.1:8001`，路径 `/mcp` | 注册 `text_stats` 工具，内部 httpx 调 FastAPI |
| cloudflared | 临时 tunnel | 转发 `localhost:8001` → 公网 HTTPS | 公网只暴露 MCP 入口 |

公网入口唯一 = MCP Server。FastAPI 永远只在 localhost，不公网暴露。OpenClaw 配置的 MCP URL = `https://<随机>.trycloudflare.com/mcp`。

### 3.2 选型理由

采用双进程而非单进程（FastAPI 同时挂 MCP 端点）：

- 完全贴合 `plan.md`「为验证链路清晰，先让 MCP Server 调用 FastAPI」。
- 三层日志天然分离，可独立观察。
- FastAPI 不直接暴露公网，安全边界清晰。
- 代价仅是多起一个进程，由启动脚本承担。

MCP 传输方式选 **Streamable HTTP**（官方 `mcp` SDK / FastMCP），因用户已确认 OpenClaw 支持 HTTP 远程 MCP，且 Streamable HTTP 可被 cloudflared 隧道直接转发。

## 4. 模块设计

### 4.1 `text_stats.py` — 核心纯函数

职责：统计文本字符数与词数，返回结构化 JSON。无副作用、无 I/O、无网络。

接口：

```python
def analyze_text(text: str, request_id: str | None = None) -> dict
```

返回结构：

```json
{
  "ok": true,
  "request_id": "test-001",
  "result": { "length": 14, "word_count": 2 }
}
```

错误返回结构（`ok: false`）：

```json
{
  "ok": false,
  "request_id": "req_...",
  "error": { "code": "invalid_input", "message": "text must be a string" }
}
```

行为约定：

- 正常输入：返回 `length`（字符数）、`word_count`（按空白分词）。
- 空字符串：合法空结果，`length=0, word_count=0`，`ok=true`。
- 非字符串参数：`ok=false`，`error.code="invalid_input"`，不抛异常。
- 超长文本（超过 `MAX_INPUT_CHARS`，默认 100000）：`ok=false`，`error.code="input_too_long"`。
- `request_id` 缺省时函数内生成 `req_<uuid>`。
- 词数定义：`len(text.split())`（连续空白视为一个分隔符，空串为 0）。

### 4.2 `app.py` — FastAPI 服务

接口：

- `GET /health` → `{"ok": true}`
- `POST /tools/text_stats` → 调用 `analyze_text`，返回其结果。

请求体（Pydantic 校验）：

```json
{ "text": "hello openclaw", "request_id": "test-001" }
```

响应体：与 `analyze_text` 返回结构一致。

关键约束：

- `text` 字段必须为字符串且长度 ≤ `MAX_INPUT_CHARS`，否则 Pydantic 422。
- 未传 `request_id` 时服务端生成 `req_<uuid>`。
- 每次请求记录日志（见 §6）。
- 所有异常（含 422、超时、未预期异常）统一转成 `{ok:false, request_id, error:{code,message}}` 形状，HTTP 状态码仍按语义（422/413/500 等），但响应体永远不暴露 traceback。
- 超时：用线程池 `future.result(timeout=EXECUTION_TIMEOUT_S)` 包裹 `analyze_text`（脚本本身 O(n) 极快，这是兜底）。超时返回 `error.code="execution_timeout"`。
- 请求体大小上限：中间件按 `Content-Length` 拒绝超过 `MAX_BODY_BYTES`（默认 1MB）的请求，返回结构化错误。

### 4.3 `mcp_server.py` — MCP Server（Streamable HTTP）

职责：把 `text_stats` 声明为 MCP 工具，内部 httpx 调 FastAPI。

工具定义：

```text
tool name: text_stats
description: Analyze text and return basic text statistics.
input schema:
  text: string (required)
  request_id: string (optional)
```

行为约定：

- 工具被调用时，用 httpx `POST {FASTAPI_URL}/tools/text_stats` 透传参数。
- 透传或生成 `request_id`，保证与 FastAPI 同一 ID。
- FastAPI 成功（`ok:true`）→ 原样返回其 JSON。
- FastAPI 返回 `ok:false`（业务错误）→ 原样透传错误结构。
- FastAPI 不可用（连接拒绝 / 超时）→ 返回结构化 `downstream_unavailable` 错误，`ok:false`。
- 鉴权（可选）：若环境变量 `MCP_AUTH_TOKEN` 已设置，校验请求头 `Authorization: Bearer <token>`，不匹配返回 401。未设置则不鉴权（仅本地验证阶段）。
- 每次调用记录日志（见 §6）。

### 4.4 `config.py` — 集中配置

从环境变量读取，提供默认值：

| 配置项 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| FastAPI 绑定 | `FASTAPI_HOST` | `127.0.0.1` | |
| FastAPI 端口 | `FASTAPI_PORT` | `8000` | |
| MCP 绑定 | `MCP_HOST` | `127.0.0.1` | |
| MCP 端口 | `MCP_PORT` | `8001` | |
| FastAPI URL | `FASTAPI_URL` | `http://127.0.0.1:8000` | MCP 调用 FastAPI 用 |
| MCP 鉴权 token | `MCP_AUTH_TOKEN` | （空=不鉴权） | |
| 请求体上限 | `MAX_BODY_BYTES` | `1048576`（1MB） | |
| 输入字符上限 | `MAX_INPUT_CHARS` | `100000` | |
| 执行超时 | `EXECUTION_TIMEOUT_S` | `5` | FastAPI 包裹脚本用 |
| MCP 调 FastAPI 超时 | `MCP_DOWNSTREAM_TIMEOUT_S` | `10` | httpx 超时 |

## 5. request_id 与日志串联

- 三层都接受外部 `request_id`，缺省时各自生成 `req_<uuid>`。
- 调用链：OpenClaw（可带可不带）→ MCP（缺省则生成）→ 透传给 FastAPI。同一请求三层同一 ID。
- 统一日志格式，stdout 一行一条：

  ```text
  2026-07-02T10:00:00.000 | fastapi | req_abc123 | text_stats | ok | 12ms |
  2026-07-02T10:00:00.000 | mcp     | req_abc123 | text_stats | error | timeout | 10012ms |
  ```

  字段：`ISO时间 | 层(fastapi/mcp) | request_id | 工具名 | 状态(ok/error) | 耗时ms | [错误类型]`

- 入参只记录长度/摘要，超长截断到 200 字符；不记录 token、不记录完整敏感正文。
- `scripts/correlate_logs.py`：读多份日志文件，按 `request_id` 分组输出三层对照表，供阶段 5 使用。

## 6. 错误码汇总

| 错误码 | 产生层 | 含义 | HTTP 状态 |
| --- | --- | --- | --- |
| `invalid_input` | text_stats / FastAPI | text 非字符串或格式非法 | 422 |
| `input_too_long` | text_stats / FastAPI | 输入超过 `MAX_INPUT_CHARS` | 422 |
| `body_too_large` | FastAPI | 请求体超过 `MAX_BODY_BYTES` | 413 |
| `execution_timeout` | FastAPI | 脚本执行超过 `EXECUTION_TIMEOUT_S` | 504 |
| `internal_error` | FastAPI | 未预期异常 | 500 |
| `downstream_unavailable` | MCP | FastAPI 连接失败或超时 | —（MCP 工具返回） |
| `unauthorized` | MCP | Bearer token 不匹配 | 401 |

所有错误响应体统一形状：`{"ok": false, "request_id": "...", "error": {"code": "...", "message": "..."}}`。

## 7. 安全边界（对应阶段 6）

- 工具固定参数、固定逻辑；无文件读取、无命令执行。
- FastAPI 绑 127.0.0.1，不公网暴露。
- MCP 公网入口可选 Bearer Token 鉴权。
- 请求体大小上限 + 单次执行超时。
- 日志脱敏：不打印 token、密钥、完整敏感正文。
- tunnel 地址不公开传播。

## 8. 测试计划（TDD）

实现阶段红-绿循环。依赖 `pytest`、`pytest-asyncio`、`httpx`。

### `tests/test_text_stats.py`
- 正常输入 `"hello openclaw"` → length=14, word_count=2。
- 空字符串 → ok=true, length=0, word_count=0。
- 超长字符串 → ok=false, code=input_too_long。
- 非字符串（如 None / int）→ ok=false, code=invalid_input。
- 透传 request_id；缺省自动生成。

### `tests/test_app.py`（httpx ASGI transport，不占真实端口）
- `GET /health` → ok=true。
- `POST /tools/text_stats` 正常 → 返回结果，含 request_id。
- 空文本 → ok=true 空结果。
- 非字符串 → 结构化错误，HTTP 422，无 traceback。
- 超长 → 结构化错误。
- 超大请求体 → 结构化错误，HTTP 413。
- request_id 自动生成。
- 未预期异常不泄露 traceback（构造可触发异常的输入）。

### `tests/test_mcp_server.py`（FastMCP 内存 client + 用 monkeypatch 桩 FastAPI 响应）
- 工具列表包含 `text_stats`。
- 正常调用 → 返回 FastAPI 结果。
- FastAPI 宕机（httpx 连接失败）→ downstream_unavailable。
- request_id 透传到 FastAPI。
- （若设了 token）未授权调用 → 401。

## 9. 文件结构

```text
server/
  text_stats.py            # 核心纯函数
  app.py                   # FastAPI
  mcp_server.py            # MCP Server (Streamable HTTP)
  config.py                # 集中配置
  tests/
    test_text_stats.py
    test_app.py
    test_mcp_server.py
    conftest.py
  scripts/
    start_fastapi.ps1      # 起 FastAPI
    start_mcp.ps1          # 起 MCP Server
    start_tunnel.ps1       # 起 cloudflared 临时 tunnel
    correlate_logs.py      # 按 request_id 串日志
  requirements.txt
  .env.example             # 端口 / FASTAPI_URL / MCP_AUTH_TOKEN
  runbook.md               # 阶段 0/4/5/6 可执行步骤 + OpenClaw 配置示例
  README.md                # 快速开始
  docs/superpowers/specs/
    2026-07-02-openclaw-local-verify-design.md   # 本文档
  task.md                  # 已存在
  plan.md                  # 已存在
```

## 10. 依赖

`requirements.txt`：

```text
fastapi
uvicorn[standard]
mcp            # 官方 SDK，含 FastMCP，支持 streamable-http
httpx
pytest
pytest-asyncio
python-dotenv  # 读取 .env（可选，配置也可走环境变量）
```

Python 3.11（A2A conda 环境）。A2A 已含 fastapi/httpx/uvicorn/python-dotenv，只需补装 `mcp`、`pytest`、`pytest-asyncio`。运行命令统一用 `conda run -n A2A ...` 或先 `conda activate A2A`。

## 11. 运行手册覆盖（用户执行的阶段）

`runbook.md` 将包含：

- **阶段 0**：创建 venv、`pip install -r requirements.txt`；用 winget 或手动安装 cloudflared 的步骤；`cloudflared --version` 验证。
- **阶段 4**：`start_tunnel.ps1` 起隧道、记录公网地址、非本机访问 `/mcp` 验证、中断测试。
- **阶段 5**：OpenClaw 配置 MCP URL（`https://<...>.trycloudflare.com/mcp`）+ Bearer Token 的示例；正常/空/非法/停 FastAPI/停 tunnel 的调用步骤；三层日志对照（`correlate_logs.py`）。
- **阶段 6**：安全检查清单逐项对照。
- **阶段 7**：填结论模板。

## 12. 实现顺序（供后续 writing-plans 展开）

1. `requirements.txt` + venv + 依赖安装。
2. `text_stats.py` + `tests/test_text_stats.py`（红-绿）。
3. `config.py`。
4. `app.py` + `tests/test_app.py`（红-绿）。
5. `mcp_server.py` + `tests/test_mcp_server.py`（红-绿）。
6. 启动脚本 + `correlate_logs.py`。
7. `runbook.md` + `README.md` + `.env.example`。
8. 全量 `pytest` 通过，更新 `task.md` 阶段 1–3 勾选项。

## 13. 成功标准（验收）

- 阶段 1–3 全部测试通过，本地 `POST /tools/text_stats` 和 MCP 工具调用均返回正确结果。
- 三层日志可通过 `request_id` 串起来。
- 异常输入返回结构化错误，无 traceback 泄露。
- 用户按 runbook 能完成阶段 4–5 端到端打通。
- 阶段 6 安全检查清单全部满足。

## 14. 风险与处理

| 风险 | 处理 |
| --- | --- |
| OpenClaw 对 Streamable HTTP MCP 兼容性未实测 | runbook 准备 REST 直连兜底说明；阶段 5 实测后确认 |
| cloudflared 未安装 | runbook 提供安装步骤，由用户执行 |
| cloudflared 临时地址不固定 | 本次验证可接受；后续扩展改固定 tunnel |
