# ABP (AstrBot Plugin) 协议规范

## 概述

ABP 是 AstrBot 的插件通信协议，用于插件的注册、消息处理、工具调用和生命周期管理。
ABP 采用**插件作为独立服务**的设计，插件通过配置加载，可使用任意编程语言实现。

**核心定位**：ABP 定义了 AstrBot 编排器与插件之间的交互接口，支持进程内和跨进程两种加载模式。

## 与 MCP 的关系

| 维度 | ABP | MCP |
|------|-----|-----|
| 定位 | 插件（功能扩展） | 工具/数据源连接 |
| 通信模式 | 双向（消息+工具+事件） | 单向（工具调用+资源访问） |
| 消息处理 | 支持 | 不支持 |
| 生命周期 | 完整 | 轻量 |
| 编程语言 | 任意 | 任意 |

## 加载方式

### 1. 进程内加载（In-Process）

- **直接函数调用**：无序列化开销，零拷贝
- **适用场景**：内置插件、高频调用、对延迟敏感

### 2. 跨进程加载（Out-of-Process）

- **独立进程运行**：插件崩溃不影响主进程
- **协议**：JSON-RPC 2.0 over Unix Socket / HTTP
- **适用场景**：第三方插件、需要资源隔离

## 插件配置

类似 MCP 服务器配置，在 AstrBot 配置文件中声明插件：

```json
{
  "plugins": [
    {
      "name": "weather-plugin",
      "version": "1.0.0",
      "load_mode": "out_of_process",
      "command": "python",
      "args": ["/path/to/weather_server.py"],
      "env": {
        "API_KEY": "xxx"
      }
    },
    {
      "name": "code-analysis",
      "load_mode": "out_of_process",
      "command": "./code-analysis-server",
      "transport": "http",
      "url": "http://localhost:9001"
    }
  ]
}
```

**配置字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 插件名称 |
| `version` | string | 否 | 插件版本 |
| `load_mode` | string | 是 | `in_process` 或 `out_of_process` |
| `command` | string | 跨进程时必填 | 启动命令 |
| `args` | array | 跨进程时可选 | 命令参数 |
| `env` | object | 否 | 环境变量 |
| `transport` | string | 跨进程时可选 | `stdio` / `unix_socket` / `http` |
| `url` | string | HTTP 传输时必填 | 服务器地址 |

## 传输协议

### Stdio（进程启动）

用于进程内加载或通过 stdio 启动的外部插件：

```
{"jsonrpc":"2.0","method":"initialize","params":{...},"id":1}
{"jsonrpc":"2.0","method":"plugin.handle_event","params":{...}}
```

### Unix Socket

```
Content-Length: <字节数>\r\n
\r\n
<json_body>
```

### HTTP/SSE

用于远程插件或需要 Webhook 通知的场景。

## 消息格式

所有消息均为 JSON-RPC 2.0：

### 1. 初始化（initialize）

**请求**：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "1.0.0",
    "clientInfo": {
      "name": "astrbot",
      "version": "4.16.0"
    },
    "capabilities": {
      "streaming": true,
      "events": true
    }
  }
}
```

**响应**：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "1.0.0",
    "serverInfo": {
      "name": "weather-plugin",
      "version": "1.0.0"
    },
    "capabilities": {
      "tools": true,
      "handlers": true,
      "events": true
    },
    "metadata": {
      "display_name": "天气插件",
      "description": "提供天气查询功能",
      "author": "Author"
    }
  }
}
```

### 2. 插件能力

```json
{
  "capabilities": {
    "tools": true,        // 支持工具调用
    "handlers": true,      // 支持消息处理器
    "events": true,         // 支持事件订阅
    "resources": false      // 是否提供资源
  }
}
```

### 3. 工具调用（跨进程）

**请求**：

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": {
      "location": "北京"
    }
  }
}
```

**响应**：

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "北京天气：晴，25°C"
      }
    ]
  }
}
```

### 4. 消息处理

**请求**：

```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "method": "plugin.handle_event",
  "params": {
    "event_type": "message",
    "event": {
      "message_id": "msg-123",
      "unified_msg_origin": "telegram:private:12345",
      "message_str": "/weather 北京",
      "sender": {
        "user_id": "12345",
        "nickname": "用户"
      },
      "message_chain": [
        { "type": "plain", "text": "/weather 北京" }
      ]
    }
  }
}
```

**响应**：

```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "result": {
    "handled": true,
    "results": [
      { "type": "plain", "text": "北京天气：晴，25°C" }
    ],
    "stop_propagation": false
  }
}
```

### 5. 事件订阅

**通知**（客户端 → 插件）：

```json
{
  "jsonrpc": "2.0",
  "method": "plugin.subscribe",
  "params": {
    "event_type": "llm_request"
  }
}
```

**通知**（插件 → 客户端）：

```json
{
  "jsonrpc": "2.0",
  "method": "plugin.notify",
  "params": {
    "event_type": "tool_called",
    "data": {
      "tool": "get_weather",
      "args": { "location": "北京" }
    }
  }
}
```

### 6. 工具列表

**请求**：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

**响应**：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "get_weather",
        "description": "获取天气信息",
        "inputSchema": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "城市名称"
            }
          },
          "required": ["location"]
        }
      }
    ]
  }
}
```

### 7. 资源（可选）

```json
{
  "jsonrpc": "2.0",
  "method": "resources/list",
  "params": {}
}
```

## 核心方法

### 初始化

| 方法 | 方向 | 描述 |
|------|------|------|
| `initialize` | C→P | 初始化连接 |
| `initialized` | P→C | 初始化完成通知 |

### 生命周期

| 方法 | 方向 | 描述 |
|------|------|------|
| `plugin.start` | C→P | 启动插件 |
| `plugin.stop` | C→P | 停止插件 |
| `plugin.reload` | C→P | 重载插件 |

### 工具

| 方法 | 方向 | 描述 |
|------|------|------|
| `tools/list` | C→P | 列出可用工具 |
| `tools/call` | C→P | 调用工具 |
| `tools/metadata` | P→C | 工具元数据更新 |

### 消息处理

| 方法 | 方向 | 描述 |
|------|------|------|
| `plugin.handle_event` | C→P | 处理事件 |
| `plugin.handle_command` | C→P | 处理命令 |
| `plugin.handle_message` | C→P | 处理消息 |

### 事件

| 方法 | 方向 | 描述 |
|------|------|------|
| `plugin.subscribe` | C→P | 订阅事件 |
| `plugin.unsubscribe` | C→P | 取消订阅 |
| `plugin.notify` | P→C | 发送事件通知 |

## 插件元数据

插件通过 `initialize` 响应返回元数据：

```json
{
  "serverInfo": {
    "name": "weather-plugin",
    "version": "1.0.0"
  },
  "capabilities": {
    "tools": true,
    "handlers": true,
    "events": true
  },
  "metadata": {
    "display_name": "天气插件",
    "description": "提供天气预报功能",
    "author": "Author Name",
    "homepage": "https://github.com/author/weather-plugin",
    "support_platforms": ["telegram", "discord"],
    "astrbot_version": ">=4.16,<5"
  }
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
| -32200 | Plugin Not Found | 未找到插件 |
| -32201 | Plugin Not Ready | 插件未就绪 |
| -32202 | Plugin Crashed | 插件崩溃 |
| -32203 | Tool Not Found | 未找到工具 |
| -32204 | Tool Call Failed | 工具调用失败 |
| -32205 | Handler Not Found | 未找到处理器 |
| -32206 | Handler Error | 处理器执行错误 |
| -32207 | Event Subscribe Failed | 事件订阅失败 |
| -32208 | Permission Denied | 权限不足 |
| -32209 | Config Error | 配置错误 |
| -32210 | Dependency Missing | 依赖缺失 |
| -32211 | Version Mismatch | 版本不兼容 |

## 进程内插件

对于进程内插件（load_mode: in_process），编排器直接调用插件方法，无需序列化：

```python
# 插件直接实现为类
class MyPlugin:
    def __init__(self, context):
        self.context = context

    async def handle_event(self, event):
        return [PlainResult("Hello!")]

    def get_tools(self):
        return [MyTool()]

    def get_metadata(self):
        return {
            "name": "my-plugin",
            "version": "1.0.0",
            "capabilities": {
                "tools": True,
                "handlers": True,
                "events": False
            }
        }
```

## 实现注意事项

- 插件是独立服务，通过配置声明式加载
- 支持任意编程语言实现（Python、Go、Rust、JavaScript 等）
- 跨进程插件使用标准 JSON-RPC 2.0 通信
- 插件元数据通过 `initialize` 响应动态获取
- 支持热重载：配置更新后可在线重载插件
- 事件通知采用异步机制，不阻塞主流程
