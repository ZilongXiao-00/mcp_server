# 本地 Agent 能力服务化并暴露给云端 OpenClaw 调用 — 实践指南

> 本文档基于本仓库已验证的最小闭环整理，供其他团队复用与评审。  
> 验证结论：**可行** — 云端 OpenClaw 已通过 Cloudflare Tunnel 成功调用本地 `text_stats` 工具，并拿到结构化结果。

---

## 1. 方案目标

验证并示范以下链路是否可行：

```text
本地脚本/Agent 能力
  → FastAPI（本地 REST 包装）
  → MCP Server（工具化，Streamable HTTP）
  → Cloudflare Tunnel（公网 HTTPS 入口）
  → 云端 OpenClaw（远程 MCP 客户端）
```

**核心问题：**

- 云端 OpenClaw 能否通过公网调用本机能力？
- 本地能力能否以受控 API / MCP 工具形式稳定暴露？
- 请求能否跨层关联（`request_id`）、错误能否结构化返回？
- 安全边界是否可接受（尤其：**公网 URL 是否会被非预期方调用**）？

本仓库用无副作用的 `text_stats`（字符数/词数统计）完成端到端验证，**不包含**文件读写、命令执行、真实业务数据访问。

---

## 2. 架构总览

### 2.1 双进程 + 单公网入口

```text
┌─────────────────────────────────────────────────────────────────┐
│ 云端 OpenClaw                                                    │
│   transport: streamable-http                                     │
│   URL: https://<random>.trycloudflare.com/mcp                    │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS（公网）
┌────────────────────────────▼────────────────────────────────────┐
│ cloudflared quick tunnel（本机进程）                              │
│   转发到 http://127.0.0.1:8001                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ 仅本机回环
┌────────────────────────────▼────────────────────────────────────┐
│ MCP Server（mcp_server.py，127.0.0.1:8001，路径 /mcp）             │
│   - 注册 MCP 工具（如 text_stats）                                │
│   - 可选 Bearer Token 鉴权（MCP_AUTH_TOKEN）                      │
│   - MCP_TUNNEL_MODE=1 时允许 tunnel Host 头                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ httpx → localhost
┌────────────────────────────▼────────────────────────────────────┐
│ FastAPI（app.py，127.0.0.1:8000）                                │
│   - POST /tools/text_stats                                       │
│   - 请求体大小限制、执行超时、结构化错误                            │
└────────────────────────────┬────────────────────────────────────┘
                             │ 函数调用
┌────────────────────────────▼────────────────────────────────────┐
│ 纯函数模块（text_stats.py）                                       │
│   - 无 I/O、无网络、无副作用                                       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 关键设计选择

| 选择 | 说明 |
|------|------|
| **双进程**（FastAPI + MCP 分开） | 三层日志天然分离，便于排障；FastAPI 永不直接暴露公网 |
| **只 tunnel MCP 端口** | 公网唯一入口是 `/mcp`；后端 REST 仅在 `127.0.0.1` |
| **Streamable HTTP** | OpenClaw 支持 HTTP 远程 MCP；cloudflared 可直接转发 |
| **quick tunnel** | 零配置、适合验证；**不适合生产**（URL 随机、无 SLA） |

---

## 3. 仓库结构与职责

| 文件/目录 | 职责 |
|-----------|------|
| `text_stats.py` | 核心纯函数，`analyze_text()`，结构化成功/错误返回 |
| `config.py` | 环境变量集中配置（端口、限流、鉴权、tunnel 模式） |
| `app.py` | FastAPI：`GET /health`、`POST /tools/text_stats` |
| `mcp_server.py` | FastMCP + Streamable HTTP，注册工具，内部调 FastAPI |
| `logging_setup.py` | 统一行日志格式，仅记录输入长度，不记正文 |
| `scripts/start_fastapi.ps1` | 启动 FastAPI，日志写入 `logs/fastapi.log` |
| `scripts/start_mcp.ps1` | 启动 MCP（自动 `MCP_TUNNEL_MODE=1`） |
| `scripts/start_tunnel.ps1` | 启动 cloudflared quick tunnel |
| `scripts/correlate_logs.py` | 按 `request_id` 关联 MCP / FastAPI 日志 |
| `tests/` | 21 项自动化测试（纯函数、FastAPI、MCP、鉴权） |
| `.env.example` | 环境变量模板（**勿提交真实 `.env`**） |

---

## 4. 实现流程（从零到联调）

### 阶段 0：环境准备

**依赖：**

- Python 3.11+（本验证使用 conda 环境 `A2A`）
- `cloudflared`（`winget install --id Cloudflare.cloudflared`）
- 云端 OpenClaw 账号，支持 **HTTP 远程 MCP（streamable-http）**

```powershell
conda run -n A2A python -m pip install -r requirements.txt
cloudflared --version   # 期望输出版本号，如 2026.6.1
conda run -n A2A pytest -v   # 期望 21 passed
```

复制环境变量模板：

```powershell
copy .env.example .env
# 按需编辑 .env，生产验证建议设置 MCP_AUTH_TOKEN
```

### 阶段 1：本地纯函数（能力核心）

`text_stats.py` 实现 `analyze_text(text, request_id)`：

- 返回 `{"ok": true, "request_id", "result": {length, word_count}}`
- 非法输入、超长输入返回 `{"ok": false, "error": {code, message}}`
- **永不抛异常**，便于上层统一处理

### 阶段 2：FastAPI 包装（本地 REST）

- `GET /health` → `{"ok": true}`
- `POST /tools/text_stats` → 调用 `analyze_text`
- 中间件限制 `MAX_BODY_BYTES`
- 线程池 + `EXECUTION_TIMEOUT_S` 防止阻塞
- 所有错误统一 JSON 结构，不向客户端泄露堆栈

### 阶段 3：MCP Server（工具化）

- 使用 FastMCP，传输为 **Streamable HTTP**，路径 `/mcp`
- 注册工具 `text_stats(text, request_id?)`
- 内部 `httpx.post(FASTAPI_URL/tools/text_stats)`
- FastAPI 不可用时返回 `downstream_unavailable`
- **tunnel 模式**：`MCP_TUNNEL_MODE=1` 关闭 DNS rebinding 的 Host 校验（否则 cloudflared 域名会被 421 拒绝）

### 阶段 4：Cloudflare Tunnel

**三个终端分别启动（顺序：A → B → C）：**

```powershell
# 终端 A
.\scripts\start_fastapi.ps1

# 终端 B
.\scripts\start_mcp.ps1

# 终端 C
.\scripts\start_tunnel.ps1
```

在终端 C 输出中找到（**在 CONNECTIVITY PRE-CHECKS 之前**）：

```text
|  https://<random>.trycloudflare.com  |
```

**OpenClaw 配置 URL：**

```text
https://<random>.trycloudflare.com/mcp
```

> ⚠️ quick tunnel 每次重启子域名都会变；**保持终端 C 窗口常开**，关闭即公网不可用。

### 阶段 5：OpenClaw 配置与调用

**CLI 配置示例（无鉴权）：**

```powershell
openclaw mcp set local-verify "{\"url\":\"https://<random>.trycloudflare.com/mcp\",\"transport\":\"streamable-http\"}"
```

**有 Bearer Token 时：**

```powershell
openclaw mcp set local-verify "{\"url\":\"https://<random>.trycloudflare.com/mcp\",\"transport\":\"streamable-http\",\"headers\":{\"Authorization\":\"Bearer <MCP_AUTH_TOKEN>\"}}"
```

验证：

```powershell
openclaw mcp list
openclaw mcp show local-verify --json
```

在 OpenClaw 对话中调用 `text_stats`，例如文本 `"hello openclaw"`。

**本仓库实测成功响应：**

```json
{
  "ok": true,
  "request_id": "req_e5a075bc268e",
  "result": {
    "length": 14,
    "word_count": 2
  }
}
```

### 阶段 6：日志串联验证

```powershell
conda run -n A2A python scripts\correlate_logs.py logs\fastapi.log logs\mcp.log
```

同一 `request_id` 应同时出现在 `mcp` 与 `fastapi` 两层。

**日志格式：**

```text
<ISO8601> | <layer> | <request_id> | <tool> | <status> | <duration_ms>ms | [<error_type>] | in_len=<n>
```

---

## 5. 配置项说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `FASTAPI_HOST` / `FASTAPI_PORT` | `127.0.0.1` / `8000` | FastAPI 仅本机 |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `8001` | MCP 监听（tunnel 转发目标） |
| `FASTAPI_URL` | `http://127.0.0.1:8000` | MCP 调 FastAPI 的地址 |
| `MCP_AUTH_TOKEN` | 空 | 非空时 `/mcp` 需 `Authorization: Bearer <token>` |
| `MCP_TUNNEL_MODE` | `0`（`start_mcp.ps1` 自动设 `1`） | 允许 cloudflared Host 头 |
| `MAX_BODY_BYTES` | `1048576` | 请求体上限 |
| `MAX_INPUT_CHARS` | `100000` | 文本输入字符上限 |
| `EXECUTION_TIMEOUT_S` | `5` | FastAPI 包裹脚本超时 |
| `MCP_DOWNSTREAM_TIMEOUT_S` | `10` | MCP 调 FastAPI 超时 |

---

## 6. 安全边界与风险项（必读）

### 6.1 公网暴露：拿到 URL 的人都能尝试调用

**风险：** cloudflared quick tunnel 会生成一个**公开的 HTTPS 地址**。任何知道该 URL 的人（不限于 OpenClaw、不限于公司员工）都可以向 `https://<random>.trycloudflare.com/mcp` 发起 MCP 协议请求。

**影响：**

- 若 **未设置 `MCP_AUTH_TOKEN`**：等同于**无鉴权公网 API**，外人可调用已注册的全部 MCP 工具（本仓库仅 `text_stats`，但仍属暴露）。
- URL 可能通过日志、截图、聊天记录、浏览器历史**泄露**。
- 安全扫描器可能探测到 trycloudflare 子域并发起请求（日志中可见多 IP 的 `GET /mcp` 406 等探测）。

**缓解措施（按优先级）：**

1. **务必设置 `MCP_AUTH_TOKEN`**，并在 OpenClaw 配置相同 Bearer Token。
2. **不要把 tunnel URL 发到公开渠道**；验证结束立即 `Ctrl+C` 关闭 tunnel。
3. 工具层**仅暴露固定参数**，禁止文件路径、命令、任意 URL 等（本仓库 `text_stats` 仅 `text` + `request_id`）。
4. FastAPI **绑定 127.0.0.1**，不直接暴露公网。
5. 输入长度、请求体大小、执行超时均已限制。
6. 日志**不记录 token、不记录完整用户输入**（仅 `in_len`）。

### 6.2 quick tunnel 的其他风险

| 风险 | 说明 |
|------|------|
| URL 不固定 | 每次重启变化，易配错、旧 URL 失效 |
| 无 uptime SLA | Cloudflare 明确标注 account-less tunnel 无可用性保证 |
| 公司网络干扰 | 可能出现 `invalid UUID length: 0`，需重试或换网络 |
| 数据经 Cloudflare 边缘转发 | 流量路径：调用方 → Cloudflare → 本机 cloudflared → MCP；需符合公司数据出境/第三方传输合规要求 |

### 6.3 本仓库已验证的安全边界

- [x] 无任意文件读取接口
- [x] 无任意命令执行接口
- [x] 工具参数固定（`text`, `request_id`）
- [x] 超长输入 / 超大 body 拒绝
- [x] 可选 Bearer 鉴权（测试覆盖 401）
- [x] FastAPI 仅 localhost；公网仅 MCP 入口

### 6.4 生产环境建议（超出本验证范围）

若其他团队要用于真实 Agent/业务：

1. 使用 **Cloudflare Named Tunnel + 固定域名**，替代 quick tunnel。
2. **强制 MCP_AUTH_TOKEN**，并定期轮换。
3. 增加 **限流、IP 白名单**（若 OpenClaw 出口 IP 固定）。
4. 增加 **审计日志**（谁、何时、调用了什么工具）。
5. 长耗时任务改为 **异步任务队列**，避免 OpenClaw 调用超时。
6. 高价值工具补充 **自动化测试 + 安全评审**。
7. 评估是否迁移到 **内网可达的跳板机/云主机**，减少个人 PC 暴露面。

---

## 7. 常见问题排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `cloudflared` 找不到 | PATH 未刷新 | 用 `start_tunnel.ps1`（已内置路径查找）或重装后重开终端 |
| `invalid UUID length: 0` | trycloudflare API 偶发失败 / 公司网络 | 等待 5–10s 重试；换热点；脚本已内置 3 次重试 |
| `421 Invalid Host header` | MCP 未开 tunnel 模式 | 用 `start_mcp.ps1` 或设 `MCP_TUNNEL_MODE=1` 后重启 MCP |
| `401 unauthorized` | Token 不一致 | 对齐 `.env` 与 OpenClaw `headers.Authorization` |
| `downstream_unavailable` | FastAPI 未启动 | 先起 `start_fastapi.ps1` |
| OpenClaw 连不上 | tunnel 已关或 URL 过期 | 重新 `start_tunnel.ps1`，更新 OpenClaw URL |
| 找不到公网 URL | 日志被滚到下方 | 向上搜 `Your quick Tunnel has been created` 或 `trycloudflare.com` |

---

## 8. 验证清单（给其他团队复用）

### 自动化（CI / 本地）

```powershell
conda run -n A2A pytest -v
# 期望：21 passed
```

### 手动端到端

- [ ] 三进程启动：FastAPI、MCP、tunnel
- [ ] 公网 URL 可访问 `/mcp`（MCP 握手 200/202）
- [ ] OpenClaw 工具列表含 `text_stats`
- [ ] 正常调用返回 `length` / `word_count`
- [ ] 空文本、非法参数返回结构化错误
- [ ] 停 FastAPI 后返回 `downstream_unavailable`
- [ ] 停 tunnel 后 OpenClaw 连接失败
- [ ] `correlate_logs.py` 可串联 `request_id`

### 本仓库已完成的实测

- 公网 MCP 调用成功（`request_id: req_e5a075bc268e`，`length: 14, word_count: 2`）
- MCP 与 FastAPI 日志 `request_id` 一致
- tunnel 中断后公网不可用

---

## 9. 扩展到更多本地 Agent 能力

复用本模式的步骤：

1. 在独立模块实现**纯函数**能力（无副作用、结构化返回）。
2. 在 `app.py` 增加对应 `POST /tools/<name>` 端点。
3. 在 `mcp_server.py` 的 `build_server()` 注册新 MCP 工具，内部 httpx 调 FastAPI。
4. 补充 `tests/test_*.py`。
5. **安全评审**：新工具是否引入文件/命令/网络外联？参数是否可收敛？
6. 重新走 tunnel + OpenClaw 联调。

建议每个工具保持：**固定 schema、固定实现路径、可测试、可限流、可鉴权**。

---

## 10. 参考文档

| 文档 | 用途 |
|------|------|
| `README.md` | 快速开始 |
| `runbook.md` | 分阶段操作步骤 |
| `docs/superpowers/specs/2026-07-02-openclaw-local-verify-design.md` | 技术设计细节 |
| `.env.example` | 环境变量模板 |

---

## 11. 结论

| 维度 | 结论 |
|------|------|
| 技术可行性 | **可行** — 云端 OpenClaw → Tunnel → MCP → FastAPI → 本地脚本 全链路打通 |
| 验证场景 | 最小无副作用工具 `text_stats` |
| 适用阶段 | POC / 内部验证 / 方案评审 |
| 生产就绪 | **否** — 需 Named Tunnel、固定域名、强鉴权、合规评审 |

**给其他团队的一句话建议：** 可以借鉴本架构做「本地 Agent 能力 MCP 化 + 受控公网入口」验证；上线前必须补齐鉴权、固定隧道、合规与工具安全评审，并默认假设 **tunnel URL 泄露 = 可被外人调用**。
