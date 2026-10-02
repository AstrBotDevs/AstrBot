# MCP (Model Context Protocol) 协议规范

## 概述

MCP（Model Context Protocol）是由 **Anthropic** 创建的开放协议，用于将 AI 模型连接到外部工具和数据源。

**核心定位**：MCP 为 AI 模型提供标准化的工具调用和上下文获取能力，类似于 USB 协议为设备提供的标准化连接方式。

## 实现状态

| 组件 | 状态 | 说明 |
|------|------|------|
| MCP Client (Python) | ✅ 部分实现 | `astrbot/api/mcp.py` 有简单封装，非完整实现 |
| MCP Client (Rust) | ⚠️ 待实现 | 应迁移到 Rust 核心 |
| MCP Server | ❌ 不计划 | AstrBot 不托管 MCP 服务器 |
| Stdio 传输 | ⚠️ 待实现 | - |
| HTTP/SSE 传输 | ⚠️ 待实现 | - |
| Tools/Resources/Prompts | ⚠️ 待实现 | - |

> 相关协议: [ABP](abp.md)（插件协议）, [ACP](acp.md)（Agent 通信）, [agent-message](agent-message.md)（消息处理框架）

## 核心功能

MCP 服务器通过三个构建块提供功能：

| 功能 | 说明 | 示例 | 控制方 |
|------|------|------|--------|
| **Tools** | LLM 可以主动调用的函数 | 搜索航班、发送消息、创建日历事件 | 模型 |
| **Resources** | 被动数据源，为上下文提供信息 | 检索文档、访问知识库、读取日历 | 应用程序 |
| **Prompts** | 预构建的指令模板 | 规划假期、总结会议内容、起草电子邮件 | 用户 |

## 与 A2A/ACP 的关系

| 协议 | 定位 | 关系 |
|------|------|------|
| **MCP** | AI 模型与外部工具/数据源的连接 | 专注于"工具和上下文" |
| **A2A** | Agent 之间的通信和协作 | 专注于"互操作" |
| **ACP** | IDE 与本地 Agent 的紧密集成 | 专注于"本地控制" |

**互补关系**：
- MCP 为 Agent 提供工具和数据访问能力
- A2A/ACP 处理 Agent 之间的通信
- 三者共同构成完整的 AI Agent 通信栈

## 架构

```
┌─────────────────────────────────────────┐
│           AI 应用 (Client)               │
│  - 模型                                 │
│  - 上下文管理                           │
└─────────────────────────────────────────┘
                      │ MCP 协议
                      ▼
┌─────────────────────────────────────────┐
│           MCP 服务器                     │
│  - Tools (工具)                         │
│  - Resources (资源)                     │
│  - Prompts (提示)                       │
└─────────────────────────────────────────┘
```

## 传输层

### Stdio（本地）

- **适用场景**：基于本地子进程的 MCP 服务器
- **协议**：通过 stdin/stdout 的 JSON-RPC 2.0
- **启动方式**：使用配置的 command 启动子进程

```
{"jsonrpc":"2.0","method":"initialize","params":{...},"id":1}
```

### HTTP/SSE（远程）

- **适用场景**：远程 MCP 服务器
- **协议**：HTTP + Server-Sent Events (SSE) 用于服务器→客户端
- **端点**：RESTful JSON-RPC over HTTP POST

## 核心方法

### 工具 (Tools)

**协议操作**：

| 方法 | 目的 | 返回 |
|------|------|------|
| `tools/list` | 发现可用工具 | 带有架构的工具定义数组 |
| `tools/call` | 执行特定工具 | 工具执行结果 |

**工具定义示例**：

```json
{
  "name": "searchFlights",
  "description": "Search for available flights",
  "inputSchema": {
    "type": "object",
    "properties": {
      "origin": { "type": "string", "description": "Departure city" },
      "destination": { "type": "string", "description": "Arrival city" },
      "date": { "type": "string", "format": "date", "description": "Travel date" }
    },
    "required": ["origin", "destination", "date"]
  }
}
```

**用户交互模型**：工具由模型控制，但强调人工监督：
- UI 中显示可用工具，允许用户定义是否可用
- 针对单个工具执行的确认对话框
- 预先批准某些安全操作的权限设置
- 显示所有工具执行情况的活动日志

### 资源 (Resources)

**协议操作**：

| 方法 | 目的 | 返回 |
|------|------|------|
| `resources/list` | 列出可用的直接资源 | 资源描述符数组 |
| `resources/templates/list` | 发现资源模板 | 资源模板定义数组 |
| `resources/read` | 检索资源内容 | 带有元数据的资源数据 |
| `resources/subscribe` | 监控资源变化 | 订阅确认 |

**资源模板示例**：

```json
{
  "uriTemplate": "weather://forecast/{city}/{date}",
  "name": "weather-forecast",
  "title": "Weather Forecast",
  "description": "Get weather forecast for any city and date",
  "mimeType": "application/json"
}
```

**参数补全**：动态资源支持参数补全，例如输入 "Par" 可能会提示 "Paris" 或 "Park City"。

**用户交互模型**：资源是应用程序驱动的：
- 文件夹式结构的树状或列表视图
- 用于查找特定资源的搜索和过滤界面
- 基于启发式方法或 AI 选择的自动上下文包含

### 提示 (Prompts)

**协议操作**：

| 方法 | 目的 | 返回 |
|------|------|------|
| `prompts/list` | 发现可用提示词 | 提示词描述符数组 |
| `prompts/get` | 检索提示词详情 | 带有参数的完整提示词定义 |

**提示词示例**：

```json
{
  "name": "plan-vacation",
  "title": "Plan a vacation",
  "description": "Guide through vacation planning process",
  "arguments": [
    { "name": "destination", "type": "string", "required": true },
    { "name": "duration", "type": "number", "description": "days" },
    { "name": "budget", "type": "number", "required": false },
    { "name": "interests", "type": "array", "items": { "type": "string" } }
  ]
}
```

**用户交互模型**：提示由用户控制，需要显式调用：
- 斜杠命令（输入 "/" 查看可用提示词）
- 操作面板 (Command palettes)
- 常用提示词的专用 UI 按钮

## 消息格式

### 请求

```json
{
  "jsonrpc": "2.0",
  "id": "unique-id",
  "method": "tools/call",
  "params": {
    "name": "searchFlights",
    "arguments": {
      "origin": "NYC",
      "destination": "Barcelona",
      "date": "2024-06-15"
    }
  }
}
```

### 响应

```json
{
  "jsonrpc": "2.0",
  "id": "unique-id",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 3 flights..."
      }
    ]
  }
}
```

### 通知

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/resources/updated",
  "params": {
    "uri": "calendar://events/2024"
  }
}
```

## 能力 (Capabilities)

### 客户端能力

```json
{
  "roots": {
    "listChanged": true
  },
  "sampling": {}
}
```

### 服务器能力

```json
{
  "tools": { "listChanged": true },
  "resources": { "subscribe": true, "listChanged": true },
  "prompts": { "listChanged": true }
}
```

## 多服务器整合

MCP 的真正威力在多服务器协同工作时显现。

**示例：多服务器差旅规划**

```
┌─────────────────────────────────────────┐
│         AI 差旅规划应用                   │
└─────────────────────────────────────────┘
          │          │          │
          ▼          ▼          ▼
┌────────────┐ ┌──────────┐ ┌─────────────┐
│ 旅行服务器  │ │天气服务器 │ │日历/邮件服务器│
│ - 航班搜索  │ │ - 气候数据│ │ - 日程管理   │
│ - 酒店预订  │ │ - 预报    │ │ - 发送邮件   │
└────────────┘ └──────────┘ └─────────────┘
```

**完整流程**：

1. 用户调用提示词：`plan-vacation(destination: "Barcelona", date: "2024-06-15")`
2. 用户选择资源：`calendar://my-calendar/June-2024`、`travel://preferences/europe`
3. AI 读取资源收集上下文
4. AI 执行工具：`searchFlights()`、`checkWeather()`
5. AI 请求用户批准：`bookHotel()`、`createCalendarEvent()`
6. 结果：量身定制的巴塞罗那之旅规划和预订

## 错误码

| 码值 | 名称 | 描述 |
|------|------|------|
| -32700 | Parse Error | 无效的 JSON |
| -32600 | Invalid Request | 格式错误的请求 |
| -32601 | Method Not Found | 未知方法 |
| -32602 | Invalid Params | 无效参数 |
| -32603 | Internal Error | 服务器内部错误 |

## 实现注意事项

- MCP 客户端使用指数退避管理重连
- 工具调用结果序列化为 JSON
- 资源可订阅变更通知
- 工具执行前可能需要用户授权
- 支持参数补全以帮助用户发现有效值
