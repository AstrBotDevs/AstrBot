# ABP (AstrBot Plugin) 协议规范

## 概述

ABP 是 AstrBot 的插件通信协议，用于插件的注册、消息处理、工具调用和生命周期管理。
ABP 采用**插件作为独立服务**的设计，插件通过配置加载，可使用任意编程语言实现。

**核心原则**：
- **主进程不读取插件配置文件**：插件配置通过协议获取
- **数据目录由主进程分配**：插件的数据存储目录由主进程在握手时告知
- **零侵入性**：插件无需了解 AstrBot 内部结构

> **⚠️ 实现说明**：ABP 协议的核心实现（握手、消息路由、生命周期管理）在 Rust 核心运行时中。
> 插件本身可使用任意语言实现，只需遵循 ABP 协议即可。
> 进程内插件（`load_mode: in_process`）示例使用 Python，但核心逻辑由 Rust 承担。

## 实现状态

| 组件 | 状态 | 说明 |
|------|------|------|
| ABP 握手协议 | ⚠️ 待实现 | Rust 核心尚未提交源码 |
| out_of_process 插件加载 | ⚠️ 待实现 | stdio/Unix Socket/HTTP 传输 |
| in_process 插件接口 | ⚠️ 待实现 | Python 插件示例待迁移到 Rust |
| 配置 Schema 生成 | ⚠️ 待实现 | UI 配置表单生成 |
| 插件生命周期管理 | ⚠️ 待实现 | start/stop/reload |

> 相关协议: [MCP](mcp.md)（工具/数据源连接）, [agent-message](agent-message.md)（消息处理框架）

## 与 MCP 的关系

| 维度 | ABP | MCP |
|------|-----|-----|
| 定位 | 插件（功能扩展） | 工具/数据源连接 |
| 通信模式 | 双向（消息+工具+事件） | 单向（工具调用+资源访问） |
| 配置获取 | 通过协议握手获取 | 通过配置文件声明 |
| 数据目录 | 主进程分配 | 插件自行管理 |
| 消息处理 | 支持 | 不支持 |

## 插件加载配置

AstrBot 配置文件声明插件基本信息（不包含插件配置）：

```json
{
  "plugins": [
    {
      "name": "weather-plugin",
      "load_mode": "out_of_process",
      "command": "python",
      "args": ["/path/to/weather_server.py"]
    }
  ]
}
```

**配置字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 插件名称 |
| `load_mode` | string | 是 | `in_process` 或 `out_of_process` |
| `command` | string | 跨进程时必填 | 启动命令 |
| `args` | array | 跨进程时可选 | 命令参数 |
| `transport` | string | 跨进程时可选 | `stdio` / `unix_socket` / `http` |
| `url` | string | HTTP 传输时必填 | 服务器地址 |

## 初始化握手

插件配置通过 `initialize` 握手交换，**主进程不读取插件的配置文件**。

### Initialize（主进程 → 插件）

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
    },
    "pluginConfig": {
      "user_config": {}
    },
    "dataDirs": {
      "root": "/var/lib/astrbot",
      "plugin_data": "/var/lib/astrbot/data/plugins/my-plugin",
      "temp": "/var/cache/astrbot/temp"
    }
  }
}
```

### Initialize Response（插件 → 主进程）

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
      "events": true,
      "resources": false
    },
    "configSchema": {
      "type": "object",
      "properties": {
        "api_key": {
          "type": "string",
          "description": "Weather API Key",
          "required": true
        },
        "default_location": {
          "type": "string",
          "description": "默认查询城市",
          "default": "北京"
        }
      }
    },
    "metadata": {
      "display_name": "天气插件",
      "description": "提供天气查询功能",
      "author": "Author",
      "support_platforms": ["telegram", "discord"]
    }
  }
}
```

### 握手参数说明

**主进程 → 插件（Initialize params）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `pluginConfig.user_config` | object | 用户配置（来自 secrets.yaml 等） |
| `dataDirs.root` | string | AstrBot 数据根目录 |
| `dataDirs.plugin_data` | string | 插件专用数据目录 |
| `dataDirs.temp` | string | 插件临时文件目录 |

**插件 → 主进程（Initialize result）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `configSchema` | object | 插件配置 Schema（用于 UI 生成配置表单） |
| `metadata.*` | object | 插件元数据 |

## 数据目录

插件的数据存储目录由主进程分配，插件通过握手获取：

```
dataDirs.plugin_data/
├── config.json         # 插件配置（主进程写入）
├── data/               # 插件业务数据
└── cache/              # 插件缓存
```

**原则**：
- 插件不自行决定数据目录
- 配置由主进程管理，插件通过 `dataDirs.plugin_data/config.json` 读取
- 插件只需读写自己的目录，无需了解 AstrBot 目录结构

## 配置传递

### 1. 用户配置（主进程 → 插件）

用户通过 WebUI 或配置文件设置的配置，通过握手传递给插件：

```json
{
  "pluginConfig": {
    "user_config": {
      "api_key": "xxx",
      "default_location": "上海"
    }
  }
}
```

### 2. 配置更新（主进程 → 插件）

配置变更时，主进程通知插件：

```json
{
  "jsonrpc": "2.0",
  "method": "plugin.config_update",
  "params": {
    "user_config": {
      "api_key": "yyy"
    }
  }
}
```

### 3. 配置 Schema（插件声明）

插件声明配置 Schema，用于主进程生成配置 UI：

```json
{
  "configSchema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "description": "API Key",
        "secret": true
      },
      "default_location": {
        "type": "string",
        "description": "默认城市"
      }
    },
    "required": ["api_key"]
  }
}
```

## 传输协议

### Stdio（进程启动）

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

### 1. 工具调用

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
      { "type": "text", "text": "北京天气：晴，25°C" }
    ]
  }
}
```

### 2. 消息处理

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
      "sender": { "user_id": "12345", "nickname": "用户" },
      "message_chain": [{ "type": "plain", "text": "/weather 北京" }]
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
    "results": [{ "type": "plain", "text": "北京天气：晴，25°C" }],
    "stop_propagation": false
  }
}
```

### 3. 事件订阅

**通知**（主进程 → 插件）：

```json
{
  "jsonrpc": "2.0",
  "method": "plugin.subscribe",
  "params": { "event_type": "llm_request" }
}
```

**通知**（插件 → 主进程）：

```json
{
  "jsonrpc": "2.0",
  "method": "plugin.notify",
  "params": {
    "event_type": "tool_called",
    "data": { "tool": "get_weather", "args": { "location": "北京" } }
  }
}
```

## 核心方法

### 生命周期

| 方法 | 方向 | 描述 |
|------|------|------|
| `initialize` | C→P | 初始化连接，交换配置和数据目录 |
| `initialized` | P→C | 初始化完成通知 |
| `plugin.start` | C→P | 启动插件 |
| `plugin.stop` | C→P | 停止插件 |
| `plugin.reload` | C→P | 重载插件 |
| `plugin.config_update` | C→P | 配置更新通知 |

### 工具

| 方法 | 方向 | 描述 |
|------|------|------|
| `tools/list` | C→P | 列出可用工具 |
| `tools/call` | C→P | 调用工具 |

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

插件在 `initialize` 响应中返回元数据：

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
  "configSchema": {
    "type": "object",
    "properties": {
      "api_key": { "type": "string", "secret": true }
    }
  },
  "metadata": {
    "display_name": "天气插件",
    "description": "提供天气查询功能",
    "author": "Author",
    "support_platforms": ["telegram", "discord"]
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

对于进程内插件（load_mode: in_process），主进程直接调用插件方法：

```python
class MyPlugin:
    def __init__(self, context, user_config: dict, data_dirs: dict):
        self.context = context
        self.user_config = user_config
        self.data_dir = data_dirs["plugin_data"]

    async def handle_event(self, event):
        return [PlainResult("Hello!")]

    def get_tools(self):
        return [MyTool()]

    def get_metadata(self):
        return {
            "name": "my-plugin",
            "version": "1.0.0",
            "capabilities": {"tools": True, "handlers": True, "events": False},
            "configSchema": {...}
        }
```

## 设计原则

1. **主进程不读取插件配置**：插件配置通过协议传递
2. **数据目录由主进程分配**：插件通过握手获取 `dataDirs`
3. **配置 Schema 声明**：插件声明配置结构，主进程生成 UI
4. **插件无侵入性**：插件无需了解 AstrBot 内部结构
5. **热重载支持**：配置更新通过 `plugin.config_update` 通知

## 序列化与校验（RFC #3210）

参考 RFC #3210，定义序列化格式和数据校验规范。

### 序列化格式

| 格式 | 适用场景 | 说明 |
|------|---------|------|
| **JSON** | 调试、跨语言 | 兼容性优先，文本可读 |
| **MessagePack** | 高性能、大数据量 | 二进制，更小数据包 |

### 数据校验

| 层级 | 说明 |
|------|------|
| **消息格式** | 序列化时内建校验 |
| **配置数据** | pydantic v2 数据模型 |
| **工具参数** | JSON Schema Draft-07 |

## 与 RFC #3210 的关系

本规范与 [RFC #3210](https://github.com/AstrBot/AstrBot/issues/3210) 保持一致：

| RFC #3210 提案 | ABP 规范对应 |
|---------------|-------------|
| 进程间隔离（stdio/websocket） | ✅ `out_of_process` 传输层 |
| JSON-RPC / MessagePack | ✅ RPC 协议 + 序列化 |
| 高性能序列化 | ✅ MessagePack 方案 |
| pydantic 数据校验 | ✅ 配置模型校验 |
| SDK 解耦 | 插件开发依赖 SDK，与本体解耦 |
| 与旧插件共存 | ✅ Stars 迁移下阶段 |
