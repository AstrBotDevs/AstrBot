# A2A (Agent-to-Agent) 协议规范

## 概述

A2A（Agent-to-Agent）是由 **Google Cloud** 发起的开放协议，旨在促进不同 AI Agent 之间的互操作性。
A2A 得到了超过 50 家技术合作伙伴（如 Atlassian, Box, Cohere, Langchain, MongoDB, PayPal, Salesforce, SAP, ServiceNow 等）的支持。

**核心目标**：让不同供应商构建或使用不同技术框架的 Agent 能在动态、多代理生态系统中进行有效通信和协作。

A2A 专注于"互联互通"，与 ACP（Agent Communication Protocol）形成互补关系。

## 实现状态

| 组件 | 状态 | 说明 |
|------|------|------|
| A2A Client | ❌ 不计划 | 作为参考协议，不做实现 |
| A2A Server | ❌ 不计划 | 参考文档 |
| AgentCard 发现 | ❌ 不计划 | - |

> 相关协议: [ACP](acp.md)（本地 Agent 通信）, [agent-message](agent-message.md)（消息处理框架）

## 与 ACP 的互补关系

| 维度 | A2A | ACP |
|------|-----|-----|
| 定位 | 跨平台、开放生态 | 本地优先、受控自治 |
| 目标 | 互联互通 | 紧密协同 |
| 场景 | 分布式任务调度、跨厂商系统 | IDE 编码助手、本地进程 |
| 网络 | 互联网、云端 | 本地进程、边缘设备 |
| 透明度 | 不透明（Agent 作为黑盒） | 透明（每步可见可控） |
| 控制权 | Agent 主导 | Client 主导 |

## 设计原则

- **拥抱代理能力**：允许 Agent 在自然的、非结构化模式下协作，无需共享内存、工具或上下文
- **基于现有标准**：建立在 HTTP, SSE, JSON-RPC 等广泛接受的标准之上
- **默认安全**：支持企业级身份验证和授权
- **支持长时间运行**：从快速任务到数小时甚至数天的复杂研究
- **模态无关**：支持文本、音频、视频流、表单、iframe 等

## 三层模型

### 第一层：数据模型

核心对象：
- **AgentCard** — 描述 Agent 能力的 JSON 文件
- **Task** — 有状态的任务实体
- **Message** — 传递指令、上下文、思考过程
- **Artifact** — 不可变的输出
- **Part** — 原子内容单元

### 第二层：抽象操作

| 方法 | 描述 |
|------|------|
| `SendMessage` | 发送消息 |
| `SendStreamingMessage` | 发送流式消息 |
| `GetTask` | 获取任务状态和结果 |
| `ListTasks` | 列出任务 |
| `CancelTask` | 取消任务 |
| `SubscribeToTask` | 订阅任务更新 |
| `GetExtendedAgentCard` | 获取扩展 AgentCard |

### 第三层：协议绑定

- **JSON-RPC over HTTP**（主要）
- **gRPC**（原生支持）
- **HTTP+JSON/REST**

## 参与者

- **User（用户）**：使用 Agent 系统完成任务的人类或服务
- **Client（客户端）**：代表用户向 Agent 请求操作的实体
- **Server（服务端）**：提供服务的不透明（黑盒）远程 Agent

## 核心数据模型

### AgentCard

托管在 `/.well-known/agent-card.json`，用于服务发现：

```json
{
  "name": "research-agent",
  "description": "专业的研究分析 Agent",
  "version": "1.0.0",
  "provider": {
    "organization": "Example Corp",
    "url": "https://example.com"
  },
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "extensions": []
  },
  "skills": [
    {
      "id": "web-search",
      "name": "Web Search",
      "tags": ["search", "research"],
      "examples": [
        {"user": "Search for recent AI news", "agent": "I'll search for recent AI news for you."}
      ]
    }
  ],
  "securitySchemes": {},
  "url": "https://api.example.com/a2a"
}
```

### Task

```json
{
  "id": "task-001",
  "contextId": "session-123",
  "status": {
    "state": "TASK_STATE_WORKING",
    "timestamp": "2024-01-01T00:00:00Z"
  },
  "artifacts": [
    {
      "artifactId": "artifact-001",
      "name": "report",
      "parts": [
        {"type": "text", "text": "分析报告内容..."}
      ]
    }
  ],
  "history": [
    {
      "messageId": "msg-001",
      "role": "ROLE_USER",
      "parts": [{"type": "text", "text": "分析一下最新 AI 趋势"}]
    }
  ],
  "metadata": {}
}
```

**任务状态机（8 个状态）**：

```
SUBMITTED → WORKING → {
  COMPLETED (终态)
  FAILED (终态)
  CANCELED (终态)
  REJECTED (终态)
  INPUT_REQUIRED (中断态)
  AUTH_REQUIRED (中断态)
}
```

### Message + Part

```json
{
  "messageId": "msg-001",
  "role": "ROLE_USER",
  "parts": [
    {"type": "text", "text": "Hello"},
    {"type": "file", "file": {"name": "doc.pdf", "uri": "https://..."}},
    {"type": "data", "data": {"key": "value"}}
  ],
  "referenceTaskIds": []
}
```

## 消息格式

### SendMessage

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "SendMessage",
  "params": {
    "message": {
      "role": "ROLE_USER",
      "parts": [{"type": "text", "text": "分析最新 AI 趋势"}]
    },
    "taskId": "optional-existing-task-id",
    "sessionId": "session-123"
  }
}
```

### SendStreamingMessage

```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "method": "SendStreamingMessage",
  "params": {
    "message": {
      "role": "ROLE_USER",
      "parts": [{"type": "text", "text": "写一段 Python 代码"}]
    }
  }
}
```

### 流式响应

```
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: message
data: {"task":{"id":"task-1","status":{"state":"TASK_STATE_WORKING"}}}

event: message
data: {"message":{"parts":[{"type":"text","text":"我来帮你"}]}}

event: task
data: {"task":{"id":"task-1","status":{"state":"TASK_STATE_COMPLETED"},"artifacts":[...]}}
```

**v1.0 重要变化**：流式结束不再依赖 `final` 字段，而应依据任务状态和流关闭。

## 传输层

### HTTP(S)/WSS（主要）

```
POST /a2a HTTP/1.1
Host: api.example.com
Content-Type: application/json
A2A-Version: 1.0.0

{"jsonrpc":"2.0","id":"req-001","method":"SendMessage",...}
```

### gRPC

完整的 gRPC 服务定义，适用于高性能场景。

### 服务发现

```
GET /.well-known/agent-card.json HTTP/1.1
Host: api.example.com

{
  "name": "research-agent",
  ...
}
```

## 安全认证

### 支持的认证方式

- **OAuth 2.0**：authorization_code, client_credentials, device_code
- **OpenID Connect**：discovery_url
- **API Key**：query, header, cookie
- **HTTP Auth**：Bearer, Basic
- **Mutual TLS (mTLS)**

### AgentCard 安全声明

```json
{
  "securitySchemes": {
    "oauth2": {
      "type": "oauth2",
      "flows": ["authorization_code"],
      "authorizationUrl": "https://auth.example.com"
    }
  },
  "securityRequirements": [
    {"oauth2": ["read", "write"]}
  ]
}
```

## 错误码

| 码值 | 名称 | 描述 |
|------|------|------|
| -32700 | Parse Error | 无效的 JSON |
| -32600 | Invalid Request | 格式错误的请求 |
| -32601 | Method Not Found | 未知方法 |
| -32602 | Invalid Params | 无效参数 |
| -32603 | Internal Error | 服务器内部错误 |
| -32100 | Agent Not Found | 未找到 Agent |
| -32101 | Agent Not Ready | Agent 未就绪 |
| -32102 | Task Not Found | 任务不存在 |
| -32103 | Task Timeout | 任务超时 |
| -32104 | Task Canceled | 任务已取消 |
| -32105 | Capability Not Supported | Agent 不支持该能力 |
| -32106 | Authentication Failed | 认证失败 |
| -32107 | Authorization Failed | 授权失败 |

## 适用场景

### 1. 智能客服

- 多轮对话管理
- 知识库集成
- 自动化工单处理

### 2. 开发协作

- 代码审查辅助
- 文档自动化
- 测试用例生成

### 3. 数据分析

- 数据清洗与转换
- 可视化报表生成
- 异常检测与告警

### 4. 企业级 Agent 网络

```
                    认证网关
                       ↓
           ┌──────────┼──────────┐
           ↓          ↓          ↓
       HR Agent   IT Agent   财务 Agent
```

### 5. Agent Marketplace

```
开发者发布 Agent → AgentCard 注册 → 用户发现和调用
```

## v1.0 迁移注意事项

- **流式结束**：不再依赖 `final` 字段，应依据任务状态和流关闭
- **术语统一**：使用 `canceled`（不是 `cancelled`）
- **服务参数**：A2A-Version、A2A-Extensions 等需要显式处理
- **taskId 生成**：新任务的 taskId 由服务端生成，客户端不应自造

## 相关资源

- [GitHub 仓库](https://github.com/google-a2a)
- [技术规范](https://google-a2a.github.io/)
- [API 文档](https://a2acn.com/docs/introduction/)
