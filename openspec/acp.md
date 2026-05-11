# ACP (Agent Communication Protocol) 协议规范

## 概述

ACP 是一个开放协议，用于多智能体系统中的智能体间通信。
AstrBot 将 ACP 实现为**客户端**，连接到暴露智能体能力的 ACP 服务器/服务。

**参考**: 受 [Google A2A](https://google-a2a.10140099
.io/) (Agent-to-Agent Protocol) 启发

## 实现状态

| 组件 | 状态 | 说明 |
|------|------|------|
| ACP 客户端 | ⚠️ 待实现 | 尚未在 Rust 核心中实现，Python 层无 ACP 客户端 |
| JSON-RPC 2.0 编解码 | ⚠️ 待实现 | - |
| 连接池管理 | ⚠️ 待实现 | - |
| 流式响应 | ⚠️ 待实现 | - |

> 相关协议: [A2A](a2a.md)（Google 发起，定位互补）, [agent-message](agent-message.md)（消息处理框架）

## 架构

```
┌─────────────────────────────────────┐
│        AstrBot (ACP 客户端)          │
└─────────────────────────────────────┘
                  │ JSON-RPC 2.0
                  ▼
┌─────────────────────────────────────┐
│         ACP 服务器/服务               │
│  - 智能体注册表                      │
│  - 任务委托                          │
│  - 状态同步                          │
└─────────────────────────────────────┘
```

## 传输层

### TCP 传输

- **适用场景**: 本地或云端智能体服务
- **协议**: 基于 TCP 的 JSON-RPC 2.0
- **头部**: `Content-Length` 前缀（与 LSP 相同）

### Unix Socket 传输

- **适用场景**: 高性能本地进程间通信
- **协议**: 通过 Unix 域套接字的 JSON-RPC 2.0

## 消息格式

所有消息均为 JSON-RPC 2.0，带 Content-Length 头：

```
Content-Length: <字节数>\r\n
\r\n
<json_body>
```

### 请求

```json
{
  "jsonrpc": "2.0",
  "id": "唯一标识",
  "method": "agent/call",
  "params": {
    "agent": "智能体名称",
    "action": "动作名称",
    "args": { ... }
  }
}
```

### 响应

```json
{
  "jsonrpc": "2.0",
  "id": "唯一标识",
  "result": {
    "status": "success",
    "data": { ... }
  }
}
```

### 错误

```json
{
  "jsonrpc": "2.0",
  "id": "唯一标识",
  "error": {
    "code": -32600,
    "message": "无效请求",
    "data": { ... }
  }
}
```

## 核心方法

### 智能体管理

| 方法 | 描述 |
|------|------|
| `agent/list` | 列出可用智能体 |
| `agent/info` | 获取智能体能力和状态 |
| `agent/call` | 调用智能体的动作 |
| `agent/subscribe` | 订阅智能体事件 |

### 任务操作

| 方法 | 描述 |
|------|------|
| `task/create` | 创建新任务 |
| `task/status` | 获取任务状态 |
| `task/result` | 获取任务结果 |
| `task/cancel` | 取消运行中的任务 |

### 通信

| 方法 | 描述 |
|------|------|
| `message/send` | 向智能体发送消息 |
| `message/broadcast` | 向所有智能体广播 |

## 错误码

| 码值 | 名称 | 描述 |
|------|------|------|
| -32700 | Parse Error | 无效的 JSON |
| -32600 | Invalid Request | 格式错误的请求 |
| -32601 | Method Not Found | 未知方法 |
| -32602 | Invalid Params | 无效参数 |
| -32603 | Internal Error | 服务器错误 |
| -32000 | Agent Not Found | 未找到智能体 |
| -32001 | Agent Busy | 智能体正在处理另一请求 |
| -32002 | Task Not Found | 未找到任务 |

## 智能体发现

智能体公布其能力：

```json
{
  "agent": "code-reviewer",
  "version": "1.0.0",
  "capabilities": ["review", "lint", "suggest"],
  "endpoints": {
    "tcp": "127.0.0.1:9001",
    "unix": "/var/run/acp/code-reviewer.sock"
  }
}
```

## 实现注意事项

- ACP 客户端维护多个智能体的连接池
- 请求可按智能体名称或能力路由
- 通过分块传输支持流式响应
- 心跳机制保持连接健康
