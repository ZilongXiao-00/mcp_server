# OpenClaw 调用本地能力验证计划

## 1. 验证目标

验证“本地脚本或 agent 能力服务化后，通过 Cloudflare Tunnel 暴露给云端 OpenClaw 调用”的路线是否可行。

本次验证不追求完整生产化，只验证最小闭环：

```text
本地脚本
  ↓
FastAPI 服务
  ↓
本地 MCP Server
  ↓
Cloudflare Tunnel
  ↓
云端 OpenClaw
```

核心问题：

- OpenClaw 是否能通过公网地址访问本地暴露的服务。
- 本地脚本是否能被稳定包装成受控 API。
- MCP Server 是否能把本地能力描述成 OpenClaw 可调用的工具。
- 请求、鉴权、超时、错误返回是否能满足基本可用性。

## 2. 验证范围

### 本次验证包含

- 选择 1 个最简单的本地脚本作为测试能力。
- 用 FastAPI 包装该脚本，提供 REST 接口。
- 用本地 MCP Server 包装同一个能力，暴露为工具。
- 使用 Cloudflare Tunnel 将本地服务暴露为 HTTPS 地址。
- 在云端 OpenClaw 中配置并调用该工具。
- 记录调用日志、输入、输出、错误和耗时。

### 本次验证不包含

- 不让 OpenClaw 直接访问本地文件系统。
- 不做复杂权限系统。
- 不处理大规模并发。
- 不做完整生产监控和自动扩缩容。
- 不接入所有现有脚本，只验证 1 到 2 个代表性脚本。

## 3. 最小测试能力

建议先选一个无副作用、结果稳定、容易排查的脚本，例如：

```text
输入：一段文本
处理：统计字符数、词数，或返回摘要占位结果
输出：结构化 JSON
```

示例返回：

```json
{
  "ok": true,
  "input": "hello openclaw",
  "result": {
    "length": 14,
    "word_count": 2
  },
  "request_id": "test-001"
}
```

这个脚本的作用不是体现业务价值，而是降低验证复杂度，先确认链路能打通。

## 4. 验证架构

### 4.1 FastAPI 层

FastAPI 负责把本地脚本包装成 HTTP 服务。

建议接口：

- `GET /health`：健康检查。
- `POST /tools/text_stats`：调用本地脚本。

基本要求：

- 请求和响应使用 JSON。
- 每次请求生成或透传 `request_id`。
- 捕获脚本异常，并返回结构化错误。
- 设置单次执行超时，例如 30 秒。
- 日志记录调用时间、入参摘要、出参摘要、错误信息。

### 4.2 MCP Server 层

MCP Server 负责把本地能力声明成工具，供 OpenClaw 以工具方式调用。

建议先只暴露 1 个工具：

```text
tool name: text_stats
description: Analyze text and return basic text statistics.
input schema:
  text: string
  request_id: string, optional
```

MCP Server 内部可以调用本地 FastAPI 接口，也可以直接调用脚本。为了验证链路清晰，建议先让 MCP Server 调用 FastAPI。

### 4.3 Cloudflare Tunnel 层

Cloudflare Tunnel 负责把本地 MCP Server 或 FastAPI 服务暴露成公网 HTTPS 地址。

验证阶段可以使用临时 tunnel：

```text
cloudflared tunnel --url http://localhost:<port>
```

如果临时地址验证通过，再考虑固定域名和长期 tunnel。

### 4.4 OpenClaw 层

OpenClaw 通过 Cloudflare Tunnel 提供的 HTTPS 地址调用本地 MCP Server。

需要验证：

- OpenClaw 是否能连接服务。
- OpenClaw 是否能识别工具定义。
- OpenClaw 是否能传入参数。
- OpenClaw 是否能收到结构化结果。
- OpenClaw 端是否能看到清晰的错误信息。

## 5. 分阶段执行计划

### 阶段 1：本地脚本验证

目标：确认脚本本身可以独立运行。

步骤：

1. 准备一个简单脚本，例如 `text_stats.py`。
2. 使用固定输入运行脚本。
3. 确认输出为结构化 JSON。
4. 故意输入空字符串、超长字符串、非法参数，观察错误处理。

验收标准：

- 正常输入可以返回正确结果。
- 异常输入不会导致进程崩溃。
- 输出格式稳定。

### 阶段 2：FastAPI 验证

目标：确认本地脚本可以通过 REST API 调用。

步骤：

1. 创建 FastAPI 服务。
2. 添加 `GET /health`。
3. 添加 `POST /tools/text_stats`。
4. 在本机通过 `curl` 或 Postman 调用。
5. 查看服务日志。

验收标准：

- `GET /health` 返回正常。
- `POST /tools/text_stats` 返回脚本结果。
- 脚本异常时 API 返回结构化错误。
- 日志中能查到请求和结果。

### 阶段 3：本地 MCP Server 验证

目标：确认能力可以被 MCP 形式暴露。

步骤：

1. 创建 MCP Server。
2. 注册 `text_stats` 工具。
3. 工具内部调用 FastAPI 的 `POST /tools/text_stats`。
4. 使用本地 MCP 客户端或调试工具调用该工具。
5. 验证 MCP 工具返回值。

验收标准：

- MCP Server 可以启动。
- 工具列表中可以看到 `text_stats`。
- 调用工具后能拿到 FastAPI 返回的结果。
- FastAPI 和 MCP 两侧日志中的 `request_id` 可以对应起来。

### 阶段 4：Cloudflare Tunnel 验证

目标：确认云端可以访问本地服务入口。

步骤：

1. 启动 FastAPI 和 MCP Server。
2. 启动 Cloudflare Tunnel。
3. 获得公网 HTTPS 地址。
4. 在非本机网络环境中访问 `/health` 或 MCP 入口。
5. 查看本地服务是否收到请求。

验收标准：

- 公网 HTTPS 地址可以访问。
- 本地服务能收到来自 tunnel 的请求。
- 请求耗时在可接受范围内。
- tunnel 断开后，云端访问会明确失败。

### 阶段 5：OpenClaw 端到端验证

目标：确认 OpenClaw 可以调用本地工具并获得结果。

步骤：

1. 在 OpenClaw 中配置 MCP Server 地址。
2. 让 OpenClaw 识别 `text_stats` 工具。
3. 从 OpenClaw 发起一次正常调用。
4. 从 OpenClaw 发起一次异常调用，例如空输入。
5. 对照 OpenClaw、MCP Server、FastAPI 三处日志。

验收标准：

- OpenClaw 可以发现或调用工具。
- 正常调用能返回结构化结果。
- 异常调用能返回可理解的错误。
- 三层日志可以通过 `request_id` 串起来。
- 整条链路耗时可以被记录。

## 6. 验证用例

| 用例 | 输入 | 预期结果 |
| --- | --- | --- |
| 健康检查 | `GET /health` | 返回 `ok: true` |
| 正常文本 | `"hello openclaw"` | 返回字符数和词数 |
| 空文本 | `""` | 返回明确错误或合法空结果 |
| 超长文本 | 超过设定长度的文本 | 返回结果或明确拒绝 |
| 脚本异常 | 构造会触发异常的输入 | 返回结构化错误 |
| tunnel 中断 | 停止 Cloudflare Tunnel 后调用 | OpenClaw 侧出现明确连接失败 |
| 服务中断 | 停止 FastAPI 后调用 MCP | MCP 返回明确下游服务不可用 |

## 7. 安全控制

验证阶段至少需要做到：

- 不暴露任意文件读取能力。
- 不提供任意命令执行接口。
- 每个工具只允许固定参数和固定行为。
- 限制请求体大小。
- 设置脚本执行超时。
- 日志中不要打印密钥、token 或完整敏感输入。
- tunnel 地址不要公开传播。

如果 OpenClaw 支持请求头鉴权，建议增加一个简单的 shared token：

```text
Authorization: Bearer <test-token>
```

## 8. 观察指标

每次调用记录：

- `request_id`
- 调用入口：OpenClaw / MCP / FastAPI
- 请求时间
- 返回时间
- 总耗时
- 工具名称
- 是否成功
- 错误类型
- 错误信息摘要

建议重点观察：

- 端到端平均耗时。
- tunnel 是否稳定。
- OpenClaw 对 MCP 工具 schema 的兼容性。
- 错误信息是否能从本地传回 OpenClaw。

## 9. 风险与处理

| 风险 | 表现 | 处理方式 |
| --- | --- | --- |
| OpenClaw 不支持当前 MCP 暴露方式 | 工具无法注册或调用 | 先退回 REST API 直连验证，再调整 MCP 协议适配 |
| Cloudflare Tunnel 不稳定 | 偶发断连或延迟过高 | 使用固定 tunnel，必要时增加重连和健康检查 |
| 本地脚本执行时间过长 | OpenClaw 调用超时 | 增加任务队列或异步任务模式 |
| 输入参数不可控 | 脚本异常或安全风险 | 使用严格 schema 校验和白名单工具 |
| 本地机器不可用 | 云端无法调用工具 | 后续考虑部署到内网服务器或轻量云主机 |

## 10. 成功标准

本路线可初步认为打通，需要同时满足：

- OpenClaw 能通过 Cloudflare Tunnel 调用本地 MCP 工具。
- 本地 MCP 工具能成功调用 FastAPI。
- FastAPI 能成功执行本地脚本。
- OpenClaw 能拿到结构化结果。
- 异常情况下能返回可理解的错误。
- 日志能串联完整调用链路。

## 11. 后续演进

如果验证通过，可以进入下一步：

1. 将临时 Cloudflare Tunnel 改为固定 tunnel 和固定域名。
2. 增加鉴权、限流、请求大小限制。
3. 将多个脚本统一注册为 MCP tools。
4. 增加任务队列，支持长耗时任务。
5. 增加工具调用审计日志。
6. 为高价值脚本补充测试用例。
7. 评估是否需要从个人电脑迁移到稳定的内网机器或云主机。

## 12. 建议的最小结论模板

验证完成后，可以用下面格式记录结论：

```text
结论：可行 / 部分可行 / 暂不可行

已打通链路：
- OpenClaw -> Cloudflare Tunnel -> MCP Server -> FastAPI -> 本地脚本

主要问题：
- 

性能观察：
- 平均耗时：
- 最大耗时：
- 失败次数：

下一步：
- 
```
