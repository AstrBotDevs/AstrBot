# HTTP API 服务器规范

## 概述

AstrBot 提供 HTTP API 服务器，用于第三方应用集成。支持 API Key 认证，采用 RESTful 风格设计。

**特性**：
- API Key 认证
- SSE 流式响应
- 文件上传/下载
- 主动消息推送

> ⚠️ **实现说明**：实际 HTTP 服务器使用 **Quart + Hypercorn**（ASGI），非 FastAPI。
> API 路由位于 `astrbot/dashboard/routes/open_api.py`。
> api.md 描述的是**目标规范**，当前实现可能存在偏差，需逐步对齐。

## 实现状态

| 端点 | 状态 | 实际路径 |
|------|------|----------|
| `GET /api/v1/im/bots` | ✅ 已实现 | `open_api.py` |
| `POST /api/v1/file` | ✅ 已实现 | `open_api.py` |
| `GET /api/v1/file` | ✅ 已实现 | `open_api.py` |
| `POST /api/v1/chat` | ✅ 已实现 | `open_api.py` |
| `GET /api/v1/chat/sessions` | ✅ 已实现 | `open_api.py` |
| `POST /api/v1/im/message` | ✅ 已实现 | `open_api.py` |
| `GET /api/v1/configs` | ✅ 已实现 | `open_api.py` |
| SSE 流式响应 | ✅ 已实现 | `open_api.py` |
| Webhook 回调 | ⚠️ 待实现 | - |
| API Key 权限体系 | ⚠️ 部分实现 | 仅基础校验 |
| SSL/TLS | ⚠️ 待实现 | - |
| 速率限制 | ⚠️ 待实现 | - |

> 相关: [path.md](path.md)（路径规范）, [env.md](env.md)（环境变量）, [config.md](config.md)（配置规范）

## 服务器配置

### 启动参数

| 参数 | 环境变量 | 说明 |
|------|----------|------|
| `--host` | `ASTRBOT_HOST` | 绑定地址，默认 `0.0.0.0` |
| `--port` | `ASTRBOT_PORT` | 绑定端口，默认 `6185` |
| `--ssl` | `ASTRBOT_SSL_ENABLE` | 启用 SSL/TLS |
| `--ssl-cert` | `ASTRBOT_SSL_CERT` | SSL 证书路径 |
| `--ssl-key` | `ASTRBOT_SSL_KEY` | SSL 私钥路径 |

### 配置示例

```yaml
# system.yaml
api:
  host: "0.0.0.0"
  port: 6185
  ssl:
    enable: true
    cert: "/etc/astrbot/certs/fullchain.pem"
    key: "/etc/astrbot/certs/privkey.pem"
  # API 请求超时（秒）
  timeout: 60
  # 最大请求体大小（MB）
  max_body_size: 100
```

## 认证

### API Key 认证

所有 `/api/v1/*` 端点需要 API Key 认证：

| 方式 | 头部 | 示例 |
|------|------|------|
| Header | `X-API-Key` | `X-API-Key: sk-xxxxx` |
| Bearer | `Authorization` | `Authorization: Bearer sk-xxxxx` |

**API Key 配置**：

```yaml
# secrets.yaml
api:
  keys:
    - id: "my-app"
      key: "sk-xxxxxxxxxxxx"
      name: "My Application"
      permissions:
        - "chat"
        - "file"
        - "message"
      rate_limit:
        requests: 100
        period: 60  # seconds
```

### 权限说明

| 权限 | 说明 |
|------|------|
| `chat` | 聊天功能（发送消息、查询会话） |
| `file` | 文件上传/下载 |
| `message` | 主动消息推送 |
| `admin` | 管理功能（预留） |

## 错误响应

### 错误格式

```json
{
  "status": "error",
  "code": 401,
  "message": "Invalid API key",
  "request_id": "req-abc123"
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| `200` | 请求成功 |
| `400` | 请求参数错误 |
| `401` | 未授权（API Key 无效） |
| `403` | 禁止访问（权限不足） |
| `404` | 资源不存在 |
| `429` | 请求过于频繁（限流） |
| `500` | 服务器内部错误 |
| `503` | 服务不可用 |

### 错误码

| 码值 | 说明 |
|------|------|
| `invalid_api_key` | API Key 无效 |
| `expired_api_key` | API Key 已过期 |
| `insufficient_permissions` | 权限不足 |
| `rate_limit_exceeded` | 请求频率超限 |
| `invalid_parameter` | 参数错误 |
| `session_not_found` | 会话不存在 |
| `config_not_found` | 配置不存在 |
| `file_not_found` | 文件不存在 |
| `upload_failed` | 文件上传失败 |
| `platform_error` | 平台错误 |

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/im/bots` | 获取机器人列表 |
| `POST` | `/api/v1/file` | 上传文件 |
| `GET` | `/api/v1/file` | 下载文件 |
| `POST` | `/api/v1/chat` | 发送聊天消息（SSE） |
| `GET` | `/api/v1/chat/sessions` | 获取会话列表 |
| `POST` | `/api/v1/im/message` | 发送主动消息 |
| `GET` | `/api/v1/configs` | 获取配置列表 |

---

## API 端点详情

### GET /api/v1/im/bots

获取已配置的机器人/平台 ID 列表。

**请求**

```
GET /api/v1/im/bots
X-API-Key: sk-xxxxx
```

**响应**

```json
{
  "status": "ok",
  "data": {
    "bot_ids": [
      "telegram:bot:123456789",
      "discord:bot:987654321",
      "webchat:FriendMessage:openapi_probe"
    ]
  }
}
```

---

### POST /api/v1/file

上传文件，获取 `attachment_id` 供后续使用。

**请求**

```
POST /api/v1/file
X-API-Key: sk-xxxxx
Content-Type: multipart/form-data

file: <binary>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | binary | 是 | 上传的文件 |

**响应**

```json
{
  "status": "ok",
  "data": {
    "attachment_id": "9a2f8c72-e7af-4c0e-b352-111111111111",
    "filename": "document.pdf",
    "type": "application/pdf",
    "size": 102400
  }
}
```

**限制**：
- 最大文件大小：100MB
- 支持格式：图片、音频、视频、文档等

---

### GET /api/v1/file

下载已上传的文件。

**请求**

```
GET /api/v1/file?attachment_id=9a2f8c72-e7af-4c0e-b352-111111111111
X-API-Key: sk-xxxxx
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `attachment_id` | string | 是 | 上传时返回的附件 ID |

**响应**

```
200 OK
Content-Type: application/octet-stream

<binary>
```

---

### POST /api/v1/chat

发送聊天消息，支持 SSE 流式响应。

**请求**

```
POST /api/v1/chat
X-API-Key: sk-xxxxx
Content-Type: application/json

{
  "message": "Hello, how are you?",
  "username": "alice",
  "session_id": "my_session_001",
  "enable_streaming": true,
  "selected_provider": "openai_chat_completion",
  "selected_model": "gpt-4.1-mini"
}
```

**请求体参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string \| array | 是 | 消息内容或消息链 |
| `username` | string | 是 | 用户名 |
| `session_id` | string | 否 | 会话 ID，不提供则自动创建 UUID |
| `conversation_id` | string | 否 | `session_id` 的别名 |
| `selected_provider` | string | 否 | 指定 LLM 提供商 |
| `selected_model` | string | 否 | 指定模型 |
| `enable_streaming` | boolean | 否 | 启用 SSE 流式响应，默认 `true` |
| `config_id` | string | 否 | 指定配置文件 ID |
| `config_name` | string | 否 | 指定配置文件名称（当 config_id 未提供时） |

**消息链格式**

```json
{
  "message": [
    { "type": "plain", "text": "Please analyze this file" },
    { "type": "file", "attachment_id": "9a2f8c72-e7af-4c0e-b352-111111111111" }
  ]
}
```

**消息类型**

| 类型 | 说明 | 字段 |
|------|------|------|
| `plain` | 文本消息 | `text` |
| `reply` | 回复消息 | `text`, `message_id` |
| `image` | 图片 | `attachment_id` 或 `url` |
| `file` | 文件 | `attachment_id`, `filename` |
| `record` | 语音 | `attachment_id` |
| `video` | 视频 | `attachment_id` |

**SSE 流式响应**

```
200 OK
Content-Type: text/event-stream

event: message
data: {"type": "message", "content": "Hello"}

event: message
data: {"type": "message", "content": " world"}

event: done
data: {"type": "done", "message_id": "msg-123"}

event: error
data: {"type": "error", "message": "Error description"}
```

**SSE 事件类型**

| 事件 | 说明 | 数据格式 |
|------|------|----------|
| `message` | 消息片段 | `{"type": "message", "content": "..."}` |
| `tool_call` | 工具调用 | `{"type": "tool_call", "tool": "name", "args": {...}}` |
| `tool_result` | 工具结果 | `{"type": "tool_result", "tool": "name", "result": {...}}` |
| `done` | 完成 | `{"type": "done", "message_id": "..."}` |
| `error` | 错误 | `{"type": "error", "message": "..."}` |

**完整响应（非流式）**

```json
{
  "status": "ok",
  "data": {
    "message_id": "msg-123",
    "content": "Hello! How can I help you today?",
    "sender": {
      "user_id": "alice",
      "nickname": "Alice"
    },
    "timestamp": "2026-03-26T10:00:00Z"
  }
}
```

---

### GET /api/v1/chat/sessions

获取用户的会话列表（分页）。

**请求**

```
GET /api/v1/chat/sessions?username=alice&page=1&page_size=20
X-API-Key: sk-xxxxx
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 用户名 |
| `page` | integer | 否 | 页码，默认 `1` |
| `page_size` | integer | 否 | 每页数量，默认 `20`，最大 `100` |
| `platform_id` | string | 否 | 平台过滤器 |

**响应**

```json
{
  "status": "ok",
  "data": {
    "sessions": [
      {
        "session_id": "my_session_001",
        "platform_id": "webchat:FriendMessage:openapi_probe",
        "creator": "alice",
        "display_name": "Alice",
        "is_group": 0,
        "created_at": "2026-03-26T10:00:00Z",
        "updated_at": "2026-03-26T10:30:00Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
}
```

---

### POST /api/v1/im/message

向平台机器人发送主动消息。

**请求**

```
POST /api/v1/im/message
X-API-Key: sk-xxxxx
Content-Type: application/json

{
  "umo": "webchat:FriendMessage:openapi_probe",
  "message": "ping from api"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `umo` | string | 是 | 统一消息源地址 |
| `message` | string \| array | 是 | 消息内容或消息链 |

**UMO 格式**

```
platform:message_type:session_id
```

| 平台 | 示例 |
|------|------|
| `webchat` | `webchat:FriendMessage:openapi_probe` |
| `telegram` | `telegram:private:123456789` |
| `telegram` | `telegram:group:-123456789` |
| `discord` | `discord:channel:987654321` |

**消息类型**

| 类型 | 说明 |
|------|------|
| `private` | 私聊 |
| `group` | 群聊 |
| `FriendMessage` | WebChat 好友消息 |

**响应**

```json
{
  "status": "ok",
  "message": "Message sent successfully"
}
```

---

### GET /api/v1/configs

获取可用的聊天配置文件列表。

**请求**

```
GET /api/v1/configs
X-API-Key: sk-xxxxx
```

**响应**

```json
{
  "status": "ok",
  "data": {
    "configs": [
      {
        "id": "default",
        "name": "默认配置",
        "path": "/var/lib/astrbot/data/configs/default.yaml",
        "is_default": true
      },
      {
        "id": "coding-assistant",
        "name": "编程助手",
        "path": "/var/lib/astrbot/data/configs/coding-assistant.yaml",
        "is_default": false
      }
    ]
  }
}
```

---

## 速率限制

| 等级 | 请求数 | 窗口 |
|------|--------|------|
| 默认 | 100 | 60 秒 |
| 高级 | 1000 | 60 秒 |

**限流响应**

```
429 Too Many Requests
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1742992060

{
  "status": "error",
  "code": 429,
  "message": "Rate limit exceeded. Try again in 30 seconds."
}
```

---

## Webhook 回调

### 配置

```yaml
# system.yaml
callback_api_base: "https://your-server.com/callback"
```

### 回调事件

| 事件 | 说明 |
|------|------|
| `message.received` | 收到消息 |
| `message.sent` | 消息发送成功 |
| `session.created` | 会话创建 |
| `session.updated` | 会话更新 |
| `error` | 错误发生 |

### 回调签名

```
X-AstrBot-Signature: sha256=xxxxx
X-AstrBot-Timestamp: 1742992060
```

验证签名：

```python
import hmac
import hashlib

def verify_signature(payload: bytes, timestamp: str, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

---

## 健康检查

### GET /health

```
GET /health
```

**响应**

```json
{
  "status": "healthy",
  "version": "4.16.0",
  "uptime": 3600
}
```

### GET /ready

```
GET /ready
```

**响应**

```json
{
  "status": "ready",
  "components": {
    "api": "ok",
    "platforms": {
      "telegram": "ok",
      "discord": "ok"
    },
    "llm_providers": {
      "openai": "ok"
    }
  }
}
```

---

## 客户端 SDK

### Python

```python
from astrbot.api.http import AstrBotClient

client = AstrBotClient(api_key="sk-xxxxx", base_url="http://localhost:6185")

# 发送消息
async def main():
    async for event in client.chat("Hello!", username="alice", session_id="test"):
        print(event)

    # 或非流式
    result = await client.chat_one("Hello!", username="alice")
    print(result)
```

### JavaScript

```javascript
import { AstrBotClient } from "@astrbot/sdk";

const client = new AstrBotClient({
  apiKey: "sk-xxxxx",
  baseUrl: "http://localhost:6185"
});

// 流式
for await (const event of client.chat({ message: "Hello!", username: "alice" })) {
  console.log(event);
}

// 非流式
const result = await client.chatOne({ message: "Hello!", username: "alice" });
```

---

## 目录结构

```
$XDG_CONFIG_HOME/astrbot/
├── config.yaml                  # 主配置入口
├── secrets.yaml                 # 安全配置（包含 API Keys）
└── ...
```

---

## 安全建议

1. **API Key 安全**
   - API Key 仅通过 HTTPS 传输
   - 定期轮换 API Key
   - 不同应用使用不同 Key

2. **网络隔离**
   - 生产环境使用 SSL/TLS
   - 限制 API 服务器访问范围
   - 使用防火墙或 VPN

3. **权限控制**
   - 按最小权限原则分配 API Key 权限
   - 避免使用 `admin` 权限
   - 记录 API 调用日志

4. **限流配置**
   - 根据业务需求调整限流参数
   - 监控限流触发情况
   - 合理设置不同等级的限流策略
