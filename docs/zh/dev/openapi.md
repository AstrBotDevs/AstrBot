---
outline: deep
---

# AstrBot HTTP API

从 v4.18.0 开始，AstrBot 提供基于 API Key 的 HTTP API，开发者可以通过标准 HTTP 请求访问核心能力。

## 快速开始

1. 在 WebUI - 设置中创建 API Key。
2. 在请求头中携带 API Key：

```http
Authorization: Bearer abk_xxx
```

也支持：

```http
X-API-Key: abk_xxx
```

3. 对于对话接口，`username` 为必填参数：

- `POST /api/v1/chat`：请求体必须包含 `username`
- `GET /api/v1/chat/sessions`：查询参数必须包含 `username`

本地 OpenAPI 描述文件地址为 `http://localhost:6185/api/v1/openapi.json`，交互式文档地址为 `http://localhost:6185/api/v1/docs`。

## Scope 权限说明

创建 API Key 时可配置 `scopes`。每个 scope 的作用、继承关系及完整接口清单见 [API Scope 与接口对照](./openapi-scopes.md)。

如果 API Key 未包含目标接口所需 scope，请求会返回 `403 Insufficient API key scope`。

- `config` 在 WebUI 中默认不选中，并自动包含 `bot` 和 `provider`。
- `config:edit_admin` 和 `chat:admin` 必须显式授予，不会随父 scope 隐式获得。
- WebUI 中取消 `bot` 或 `provider` 时，会同步取消依赖它们的 `config`。

当前开发者 API Key 开放 11 个顶级 scope 和 2 个敏感子权限。`tool`、`skills`、`kb`、`system` 暂不支持作为开发者 API Key scope。`/api/v1/skills/*` 接口使用单数 `skill` scope，不使用复数 `skills`。

交互式文档中的每个接口也会显示英文标签 `Required scope: ...`；涉及管理员能力时，还会显示 `Conditional sensitive scope: ...`。

## 常用接口

**对话类**

调用 AstrBot 内建的 Agent 进行对话交互。支持插件调用、工具调用等能力，与 IM 端对话能力一致。

- `POST /api/v1/chat`：发送对话消息（SSE 流式返回，不传 `session_id` 会自动创建 UUID）
- `GET /api/v1/chat/sessions`：分页获取指定 `username` 的会话
- `GET /api/v1/configs`：获取可用配置文件列表
- `POST /api/v1/file`：上传附件，之后可在消息段中引用

**机器人和模型提供商**

- `GET /api/v1/bots`：获取机器人/平台配置列表
- `POST /api/v1/bots`：创建机器人/平台配置
- `GET /api/v1/providers`：获取模型提供商配置列表
- `GET /api/v1/provider-sources`：获取提供商源配置列表

**人格、插件、MCP 和 Skills**

- `GET /api/v1/personas`：获取人格列表
- `GET /api/v1/plugins`：获取插件列表
- `GET /api/v1/mcp/servers`：获取 MCP 服务器列表
- `GET /api/v1/skills`：获取 Skills 列表

**IM 消息发送**

- `POST /api/v1/im/message`：按 UMO 主动发消息
- `GET /api/v1/im/bots`：获取 bot/platform ID 列表

## `message` 字段格式（重点）

`POST /api/v1/chat` 和 `POST /api/v1/im/message` 的 `message` 字段支持两种格式：

1. 字符串：纯文本消息
2. 数组：消息段（message chain）

### 1. 纯文本格式

```json
{
  "message": "Hello"
}
```

### 2. 消息段数组格式

```json
{
  "message": [
    { "type": "plain", "text": "请看这个文件" },
    { "type": "file", "attachment_id": "9a2f8c72-e7af-4c0e-b352-111111111111" }
  ]
}
```

支持的 `type`：

| type | 必填字段 | 可选字段 | 说明 |
| --- | --- | --- | --- |
| `plain` | `text` | - | 文本段 |
| `reply` | `message_id` | `selected_text` | 引用回复某条消息 |
| `image` | `attachment_id` | - | 图片附件段 |
| `record` | `attachment_id` | - | 音频附件段 |
| `file` | `attachment_id` | - | 通用文件段 |
| `video` | `attachment_id` | - | 视频附件段 |

* reply 消息段目前仅适配 `/api/v1/chat`，不适用于 `POST /api/v1/im/message`。


说明：

- `attachment_id` 来自已存在的附件记录，或使用 `file` scope 调用 `POST /api/v1/file` 上传附件后的返回值。
- `reply` 不能单独作为唯一内容，至少需要一个有实际内容的段（如 `plain/image/file/...`）。
- 仅 `reply` 或空内容会返回错误。

### Chat API 的 `message` 用法

`POST /api/v1/chat` 额外需要 `username`，可选 `session_id`（不传会自动创建 UUID）。

`username` 是调用方声明的 WebChat 用户标识，会作为本次消息的 sender 和会话 owner。只有 `chat` 的 Key 如果使用任一已配置管理员 ID，会被拒绝，并且消息管道也不会为其授予管理员角色。敏感子权限 `chat:admin` 会显式允许使用已配置的管理员 ID，但不会把任意用户名变成管理员。集成方仍应将外部用户映射为稳定、由应用控制的用户名。

```json
{
  "username": "alice",
  "session_id": "my_session_001",
  "message": [
    { "type": "plain", "text": "帮我总结这个 PDF" },
    { "type": "file", "attachment_id": "9a2f8c72-e7af-4c0e-b352-111111111111" }
  ],
  "enable_streaming": true
}
```

### IM Message API 的 `message` 用法

`POST /api/v1/im/message` 需要 `umo` + `message`。

```json
{
  "umo": "webchat:FriendMessage:openapi_probe",
  "message": [
    { "type": "plain", "text": "这是主动消息" },
    { "type": "image", "attachment_id": "9a2f8c72-e7af-4c0e-b352-222222222222" }
  ]
}
```

## 示例

```bash
curl -N 'http://localhost:6185/api/v1/chat' \
  -H 'Authorization: Bearer abk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello","username":"alice"}'
```

## 完整 API 文档

交互式 API 文档请查看：

- https://docs.astrbot.app/scalar.html
