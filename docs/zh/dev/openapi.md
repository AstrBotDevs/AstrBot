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

创建 API Key 时可配置 `scopes`。每个 scope 控制可访问的接口范围：

| Scope | 作用 | 可访问接口 |
| --- | --- | --- |
| `bot` | 管理机器人/平台配置 | `GET /api/v1/bot-types`、`GET/POST /api/v1/bots`、`PATCH /api/v1/bots/enabled` |
| `provider` | 管理模型提供商和提供商源 | `GET/POST /api/v1/providers`、`GET/PUT/DELETE /api/v1/provider-sources/by-id` |
| `persona` | 管理人格和人格文件夹 | `GET/POST /api/v1/personas`、`GET/POST /api/v1/persona-folders` |
| `im` | 主动发 IM 消息、查询 bot/platform 列表 | `POST /api/v1/im/message`、`GET /api/v1/im/bots` |
| `config` | 管理配置文件、系统配置和通用配置。该 scope 同时包含 `bot` 和 `provider` 访问权限。 | `GET /api/v1/configs`、`GET/PUT /api/v1/system-config`、`GET/POST /api/v1/config-profiles` |
| `chat` | 调用对话能力、查询对话会话 | `POST /api/v1/chat`、`GET /api/v1/chat/sessions` |
| `file` | 上传和下载对话附件 | `POST /api/v1/file`、`GET /api/v1/file`、`POST /api/v1/files` |
| `plugin` | 管理插件、插件配置、插件源和插件市场 | `GET /api/v1/plugins`、`GET/PUT /api/v1/plugins/config`、`POST /api/v1/plugins/install/url` |
| `mcp` | 管理 MCP 服务器配置和服务端同步 | `GET/POST /api/v1/mcp/servers`、`PATCH /api/v1/mcp/servers/{server_name}/enabled`、`POST /api/v1/mcp/providers/modelscope/sync` |
| `skill` | 管理 Skills、Skill 压缩包、Skill 文件和 Shipyard Neo Skill 流程 | `GET/POST /api/v1/skills`、`PUT /api/v1/skills/{skill_name}/files/{file_path}`、`POST /api/v1/skills/neo/sync` |

如果 API Key 未包含目标接口所需 scope，请求会返回 `403 Insufficient API key scope`。

`config` 是较大的管理 scope。创建 API Key 时如果包含 `config`，AstrBot 会同时授予该 Key `config`、`bot` 和 `provider` 访问权限。WebUI 的勾选逻辑也会体现这个依赖关系：选中 `config` 会同时选中 `bot` 和 `provider`；取消选中 `bot` 或 `provider` 时，会同步取消 `config`。

当前开发者 API Key 仅开放以上 10 个 scope。`tool`、`skills`、`kb`、`data`、`system` 暂不支持作为开发者 API Key scope。`/api/v1/skills/*` 接口使用单数 `skill` scope，不使用复数 `skills`。公开 OpenAPI 文档只包含这些开发者 API Key scope 覆盖的接口。

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

`username` 是调用方声明的 WebChat 用户标识，会作为本次消息的 sender 和会话 owner 进入消息管道，并参与基于 sender ID 的指令权限判断。因此，带有 `chat` scope 的 API Key 应仅发放给可信后端服务。如果需要面向终端用户开放，请在自己的服务端将外部用户映射到受控的 `username`，不要允许客户端直接传入管理员 ID 或其他保留 sender ID。

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
