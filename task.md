# OpenClaw 调用本地能力验证任务清单

## 使用方式

按阶段从上到下执行。每完成一项，就把 `[ ]` 改成 `[x]`。

建议每个阶段完成后都记录：

- 当前结论
- 遇到的问题
- 关键日志或截图
- 下一步动作

## 阶段 0：准备工作

### 目标

准备本地开发和验证所需的最小环境。

### 功能点

- [ ] 确认本地 Python 环境可用。
- [ ] 确认可以安装或已安装 FastAPI 相关依赖。
- [ ] 确认可以安装或已安装 MCP Server 相关依赖。
- [ ] 确认本地可以运行 `cloudflared`。
- [ ] 确认云端 OpenClaw 支持配置外部 MCP Server 或外部工具服务。
- [ ] 确认当前验证不需要访问本地真实业务文件。

### 检查项

- [ ] `python --version` 能正常返回版本。
- [ ] 本地能启动一个简单 Python 脚本。
- [ ] `cloudflared --version` 能正常返回版本。
- [ ] 已确认 OpenClaw 侧的工具接入方式。
- [ ] 已明确本次只验证 1 个无副作用测试工具。

### 产出物

- [ ] 记录本地 Python 版本。
- [ ] 记录 `cloudflared` 版本。
- [ ] 记录 OpenClaw 工具接入方式。

## 阶段 1：本地测试脚本

### 目标

准备一个最简单、无副作用、输出稳定的本地脚本。

### 功能点

- [ ] 新建 `text_stats.py`。
- [ ] 脚本接收文本输入。
- [ ] 脚本返回字符数。
- [ ] 脚本返回词数。
- [ ] 脚本返回结构化 JSON。
- [ ] 脚本支持 `request_id`。
- [ ] 脚本处理空文本输入。
- [ ] 脚本处理超长文本输入。
- [ ] 脚本处理非法参数。

### 检查项

- [ ] 正常输入 `"hello openclaw"` 可以返回结果。
- [ ] 返回结果中包含 `ok`。
- [ ] 返回结果中包含 `result.length`。
- [ ] 返回结果中包含 `result.word_count`。
- [ ] 返回结果中包含 `request_id`。
- [ ] 空文本不会导致进程崩溃。
- [ ] 非法参数不会导致进程崩溃。
- [ ] 输出始终是 JSON。

### 建议测试用例

- [ ] 输入：`hello openclaw`，预期：成功返回字符数和词数。
- [ ] 输入：空字符串，预期：返回明确错误或合法空结果。
- [ ] 输入：很长的字符串，预期：返回结果或明确拒绝。
- [ ] 输入：非字符串参数，预期：返回结构化错误。

### 产出物

- [ ] `text_stats.py`
- [ ] 本地脚本测试记录

## 阶段 2：FastAPI 服务

### 目标

把本地脚本包装成 REST API。

### 功能点

- [ ] 新建 FastAPI 服务入口文件，例如 `app.py` 或 `main.py`。
- [ ] 添加 `GET /health` 接口。
- [ ] 添加 `POST /tools/text_stats` 接口。
- [ ] 在接口中调用 `text_stats.py` 的核心函数。
- [ ] 请求体使用 JSON。
- [ ] 响应体使用 JSON。
- [ ] 支持传入 `request_id`。
- [ ] 没有传入 `request_id` 时自动生成。
- [ ] 增加请求参数校验。
- [ ] 增加请求体大小限制。
- [ ] 增加单次脚本执行超时。
- [ ] 捕获脚本异常。
- [ ] 返回结构化错误。
- [ ] 增加基础调用日志。

### 检查项

- [ ] `GET /health` 返回 `ok: true`。
- [ ] `POST /tools/text_stats` 正常输入时返回成功结果。
- [ ] `POST /tools/text_stats` 空文本时返回预期结果。
- [ ] `POST /tools/text_stats` 非法参数时返回结构化错误。
- [ ] 接口异常不会暴露 Python 堆栈给调用方。
- [ ] 日志中可以看到 `request_id`。
- [ ] 日志中可以看到工具名称。
- [ ] 日志中可以看到成功或失败状态。
- [ ] 日志中可以看到耗时。

### 建议接口

```text
GET /health
POST /tools/text_stats
```

### 建议请求体

```json
{
  "text": "hello openclaw",
  "request_id": "test-001"
}
```

### 建议响应体

```json
{
  "ok": true,
  "request_id": "test-001",
  "result": {
    "length": 14,
    "word_count": 2
  }
}
```

### 产出物

- [ ] FastAPI 服务文件
- [ ] REST API 本地调用记录
- [ ] 错误处理测试记录

## 阶段 3：本地 MCP Server

### 目标

把 FastAPI 暴露的本地能力包装成 MCP 工具。

### 功能点

- [ ] 新建 MCP Server 入口文件。
- [ ] 注册 `text_stats` 工具。
- [ ] 为 `text_stats` 编写工具描述。
- [ ] 为 `text_stats` 编写 input schema。
- [ ] MCP 工具内部调用 FastAPI 的 `POST /tools/text_stats`。
- [ ] MCP 工具透传或生成 `request_id`。
- [ ] MCP 工具处理 FastAPI 成功响应。
- [ ] MCP 工具处理 FastAPI 错误响应。
- [ ] MCP 工具处理 FastAPI 不可用。
- [ ] MCP Server 增加基础日志。

### 检查项

- [ ] MCP Server 可以在本地启动。
- [ ] 工具列表中可以看到 `text_stats`。
- [ ] 本地 MCP 调试工具可以调用 `text_stats`。
- [ ] 调用 MCP 工具后，FastAPI 可以收到请求。
- [ ] MCP 返回内容和 FastAPI 返回内容一致。
- [ ] MCP 日志中可以看到 `request_id`。
- [ ] FastAPI 日志中可以看到同一个 `request_id`。
- [ ] FastAPI 停止后，MCP 返回明确的下游服务不可用错误。

### 建议工具定义

```text
tool name: text_stats
description: Analyze text and return basic text statistics.
input:
  text: string
  request_id: string, optional
```

### 产出物

- [ ] MCP Server 文件
- [ ] MCP 工具定义
- [ ] MCP 本地调用记录

## 阶段 4：Cloudflare Tunnel

### 目标

通过 Cloudflare Tunnel 给云端 OpenClaw 提供公网 HTTPS 入口。

### 功能点

- [ ] 确认本地 FastAPI 已启动。
- [ ] 确认本地 MCP Server 已启动。
- [ ] 使用 `cloudflared tunnel --url http://localhost:<port>` 启动临时 tunnel。
- [ ] 记录 Cloudflare Tunnel 生成的 HTTPS 地址。
- [ ] 从非本机环境访问 tunnel 地址。
- [ ] 验证 tunnel 可以把请求转发到本地服务。
- [ ] 验证 tunnel 中断时的错误表现。

### 检查项

- [ ] Cloudflare Tunnel 可以启动。
- [ ] 可以拿到公网 HTTPS 地址。
- [ ] 公网地址可以访问健康检查接口或 MCP 入口。
- [ ] 本地日志能看到来自公网地址的请求。
- [ ] tunnel 停止后，公网地址不可用。
- [ ] tunnel 停止后的错误表现可理解。

### 产出物

- [ ] tunnel HTTPS 地址
- [ ] tunnel 连通性测试记录
- [ ] tunnel 中断测试记录

## 阶段 5：OpenClaw 端到端调用

### 目标

让云端 OpenClaw 通过 Cloudflare Tunnel 调用本地 MCP 工具。

### 功能点

- [ ] 在 OpenClaw 中配置 MCP Server 地址。
- [ ] 在 OpenClaw 中确认 `text_stats` 工具可见。
- [ ] 从 OpenClaw 发起一次正常工具调用。
- [ ] 从 OpenClaw 发起一次空文本调用。
- [ ] 从 OpenClaw 发起一次非法参数调用。
- [ ] 停止 FastAPI 后，从 OpenClaw 发起调用。
- [ ] 停止 Cloudflare Tunnel 后，从 OpenClaw 发起调用。
- [ ] 对照 OpenClaw、MCP Server、FastAPI 三侧日志。

### 检查项

- [ ] OpenClaw 可以连接 Cloudflare Tunnel 地址。
- [ ] OpenClaw 可以识别 `text_stats` 工具。
- [ ] OpenClaw 可以传入 `text` 参数。
- [ ] OpenClaw 可以收到结构化成功结果。
- [ ] OpenClaw 可以收到结构化错误结果。
- [ ] 三层日志可以通过 `request_id` 串起来。
- [ ] 可以记录端到端总耗时。
- [ ] 可以判断失败发生在哪一层。

### 产出物

- [ ] OpenClaw 配置记录
- [ ] OpenClaw 正常调用记录
- [ ] OpenClaw 异常调用记录
- [ ] 三层日志对照记录

## 阶段 6：安全与边界检查

### 目标

确认验证链路不会暴露不必要的本地风险。

### 功能点

- [ ] 工具只允许固定参数。
- [ ] 工具只执行固定脚本逻辑。
- [ ] 不提供任意文件读取接口。
- [ ] 不提供任意命令执行接口。
- [ ] 不在日志中打印密钥。
- [ ] 不在日志中打印完整敏感输入。
- [ ] 限制请求体大小。
- [ ] 限制单次执行时间。
- [ ] 如 OpenClaw 支持，增加 shared token 鉴权。

### 检查项

- [ ] 外部调用方不能读取本地任意文件。
- [ ] 外部调用方不能传入任意命令。
- [ ] 超长输入会被处理或拒绝。
- [ ] 超时任务会被中断或返回超时错误。
- [ ] 未授权请求会被拒绝。
- [ ] 日志中没有 token、密钥或敏感正文。

### 产出物

- [ ] 安全检查记录
- [ ] 已知风险列表

## 阶段 7：最终验收

### 目标

判断这条路线是否可以进入下一阶段。

### 成功标准

- [ ] OpenClaw 能通过 Cloudflare Tunnel 调用本地 MCP 工具。
- [ ] MCP 工具能成功调用 FastAPI。
- [ ] FastAPI 能成功执行本地脚本。
- [ ] OpenClaw 能拿到结构化结果。
- [ ] 异常情况下能返回可理解的错误。
- [ ] 日志能串联完整调用链路。
- [ ] 基础安全边界符合验证要求。

### 结论选项

- [ ] 可行：链路完整打通，可以继续扩展更多工具。
- [ ] 部分可行：核心链路可行，但某些环节需要替换或适配。
- [ ] 暂不可行：关键环节无法接通，需要换方案。

### 最终记录模板

```text
结论：

已打通链路：
- OpenClaw -> Cloudflare Tunnel -> MCP Server -> FastAPI -> 本地脚本

未打通环节：
-

主要问题：
-

平均耗时：

最大耗时：

失败次数：

安全风险：
-

下一步：
-
```

## 后续扩展任务

这些任务不属于最小验证闭环，等阶段 7 通过后再做。

- [ ] 把临时 tunnel 改成固定 tunnel。
- [ ] 绑定固定域名。
- [ ] 增加正式鉴权。
- [ ] 增加限流。
- [ ] 增加调用审计日志。
- [ ] 增加任务队列，支持长耗时任务。
- [ ] 增加更多本地脚本工具。
- [ ] 为高价值工具补充自动化测试。
- [ ] 评估是否迁移到稳定内网服务器或云主机。
