---
outline: deep
---

# AstrBot HTTP API

AstrBot 提供基于 API Key 的 HTTP API，开发者可以通过标准 HTTP 请求访问核心能力。

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

本地 schema 包含完整的 `/api/v1` 契约，其中也包括依赖 Dashboard 登录态的接口。WebUI 内置文档中的 `/help/scalar.html` 是由同一份规范裁剪出来的开发者子集。

## Scope 权限说明

创建 API Key 时可配置 `scopes`。每个 scope 控制可访问的接口范围：

| Scope      | 作用                                               | 代表性接口                                                                                                                      |
| ---------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `bot`      | 管理机器人/平台配置                                | `GET/POST /api/v1/bots`、`PATCH /api/v1/bots/{bot_id}/enabled`                                                                  |
| `provider` | 管理模型和 Provider 来源                           | `GET/POST /api/v1/providers`、`GET/PUT/DELETE /api/v1/provider-sources/{source_id}`                                             |
| `persona`  | 管理 Persona 和 Persona 文件夹                     | `GET/POST /api/v1/personas`、`GET/POST /api/v1/persona-folders`                                                                 |
| `im`       | 主动发 IM 消息、查询 bot/platform 列表             | `POST /api/v1/im/messages`、`GET /api/v1/im/bots`                                                                               |
| `config`   | 管理配置档和系统配置，同时包含 `bot` 和 `provider` | `GET/PUT /api/v1/system-config`、`GET/POST /api/v1/config-profiles`、`GET /api/v1/subagents/config`                             |
| `chat`     | 调用对话能力、查询和维护 WebChat 会话              | `POST /api/v1/chat`、`GET /api/v1/chat/sessions`、`GET /api/v1/chat/configs`                                                    |
| `kb`       | 管理知识库、文档、分块和检索                       | `GET/POST /api/v1/knowledge-bases`、`POST /api/v1/knowledge-bases/{kb_id}/retrieve`                                             |
| `memory`   | 审计和维护长期记忆事实、画像及操作记录             | `GET/POST /api/v1/memory/facts`、`POST /api/v1/memory/facts/{fact_id}/delete`、`GET /api/v1/memory/operations`                  |
| `data`     | 管理会话状态、会话分组、会话规则和已保存对话       | `GET/POST /api/v1/sessions`、`GET/POST /api/v1/session-groups`、`GET/POST /api/v1/conversations`                                |
| `file`     | 上传和下载对话附件                                 | `POST/GET /api/v1/file`、`POST /api/v1/files`                                                                                   |
| `plugin`   | 管理插件、插件配置、插件源和市场                   | `GET /api/v1/plugins`、`GET/PUT /api/v1/plugins/{plugin_id}/config`、`POST /api/v1/plugins/install/url`                         |
| `mcp`      | 管理 MCP 服务器配置和服务端同步                    | `GET/POST /api/v1/mcp/servers`、`PATCH /api/v1/mcp/servers/{server_name}/enabled`、`POST /api/v1/mcp/providers/modelscope/sync` |
| `skill`    | 管理 Skills、压缩包、文件和 Shipyard Neo 流程      | `GET/POST /api/v1/skills`、`PUT /api/v1/skills/{skill_name}/files/{file_path}`、`POST /api/v1/skills/neo/sync`                  |

如果 API Key 未包含目标接口所需 scope，请求会返回 `403 Insufficient API key scope`。

`config` 是较大的管理 scope。创建 API Key 时如果包含 `config`，AstrBot 会同时授予该 Key `config`、`bot` 和 `provider` 访问权限。WebUI 的勾选逻辑也会体现这个依赖关系：选中 `config` 会同时选中 `bot` 和 `provider`；取消选中 `bot` 或 `provider` 时，会同步取消 `config`。

当前开发者 API Key 支持 13 个基础 scope。`/api/v1/skills/*` 接口使用单数 `skill` scope，不使用复数 `skills`。

在显式 scope 存储出现前，数据库中的 `NULL` 表示固定的基础 scope 集，不是通配符，且不会获得敏感 scope。运行时授权只认显式 capability，不再把 `*` 或 `NULL` 扩权到新的高风险动作。授权模型见[项目架构](/dev/architecture#统一授权系统)。

`tool`、`system` 和数据文件管理器等接口仍然会出现在本地完整的 `/api/v1/openapi.json` 规范里，但它们属于依赖 Dashboard 登录态的接口，不是开发者 API Key scope。数据文件路由使用 `Data Files` tag，不会进入公开 OpenAPI 文档。

## 常用接口

**对话类**

调用 AstrBot 内建的 Agent 进行对话交互。支持插件调用、工具调用等能力，与 IM 端对话能力一致。

- `POST /api/v1/chat`：发送对话消息（SSE 流式返回，不传 `session_id` 会自动创建 UUID）
- `GET /api/v1/chat/sessions`：分页获取指定 `username` 的会话
- `GET /api/v1/chat/configs`：获取 Chat 可选配置档；当前运行时要求 `chat` scope
- `POST /api/v1/file`：上传附件，之后可在消息段中引用

**机器人和模型提供商**

- `GET /api/v1/bots`：获取机器人/平台配置列表
- `POST /api/v1/bots`：创建机器人/平台配置
- `GET /api/v1/providers`：获取模型提供商配置列表
- `GET /api/v1/provider-sources`：获取提供商源配置列表

**Persona、知识库、长期记忆、数据、插件、MCP 和 Skills**

- `GET /api/v1/personas`：获取人格列表
- `GET /api/v1/knowledge-bases`：获取知识库列表
- `GET /api/v1/memory/facts`：分页查询长期记忆事实
- `GET /api/v1/sessions`：获取会话状态与规则
- `GET /api/v1/conversations`：获取已保存对话
- `GET /api/v1/plugins`：获取插件列表
- `GET /api/v1/mcp/servers`：获取 MCP 服务器列表
- `GET /api/v1/skills`：获取 Skills 列表

**IM 消息发送**

- `POST /api/v1/im/messages`：按 UMO 主动发消息
- `GET /api/v1/im/bots`：获取 bot/platform ID 列表

## `message` 字段格式（重点）

`POST /api/v1/chat` 和 `POST /api/v1/im/messages` 的 `message` 字段支持两种格式：

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

| type     | 必填字段        | 可选字段        | 说明             |
| -------- | --------------- | --------------- | ---------------- |
| `plain`  | `text`          | -               | 文本段           |
| `reply`  | `message_id`    | `selected_text` | 引用回复某条消息 |
| `image`  | `attachment_id` | -               | 图片附件段       |
| `record` | `attachment_id` | -               | 音频附件段       |
| `file`   | `attachment_id` | -               | 通用文件段       |
| `video`  | `attachment_id` | -               | 视频附件段       |

- reply 消息段目前仅适配 `/api/v1/chat`，不适用于 `POST /api/v1/im/messages`。

说明：

- `attachment_id` 来自已存在的附件记录，或使用 `file` scope 调用 `POST /api/v1/file` 上传附件后的返回值。
- `reply` 不能单独作为唯一内容，至少需要一个有实际内容的段（如 `plain/image/file/...`）。
- 仅 `reply` 或空内容会返回错误。

### Chat API 的 `message` 用法

`POST /api/v1/chat` 额外需要 `username`，可选 `session_id`（不传会自动创建 UUID）。

`username` 是调用方声明的 WebChat 用户标识，仅用于兼容现有接口，不会因此获得 Dashboard 或管理员权限。若需要面向终端用户开放，请在自己的服务端将外部用户映射到受控的 `username`。

使用已登录 Dashboard 的 session 调用 `/api/v1/chat` 时，服务端会额外传递已签名的账户、session 和当前认证强度，以便按实际 Dashboard 权限执行授权；它不会信任 `username` 来提升权限。使用 API Key 时仍只按该 Key 的 scope 授权，绝不会继承 Dashboard 角色或高风险权限。

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

`POST /api/v1/im/messages` 需要 `umo` + `message`。

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

## JSON 响应封装与流式例外

普通 JSON API 使用统一封装：

```json
{
  "status": "ok",
  "message": null,
  "data": {}
}
```

业务错误通常返回 `status: "error"` 和可读的 `message`。客户端不能只依赖 HTTP 2xx 判断业务成功，应同时检查 `status`。

以下响应遵循协议自身格式，不使用普通 JSON 封装：

- Chat 的 Server-Sent Events（SSE）流；
- 文件上传后的实际文件下载响应；
- 会话导出、日志流、Webhook 和静态资源等二进制、流式或原生协议响应。

调用这些接口时应根据 OpenAPI 的 content type 和具体路由处理，不要无条件执行 `response.json()`。

## 契约维护流程

本仓库的源规范是根目录 `openspec/openapi-v1.yaml`。运行时路由和 Pydantic 请求模型位于 `astrbot/dashboard/api/` 与 `astrbot/dashboard/schemas.py`。修改路由、请求/响应 schema、scope 或规范时，必须同步这些来源并重新生成：

```bash
cd dashboard
pnpm generate:api
cd ..
node node_modules/prettier/bin/prettier.cjs --write --ignore-path .gitignore "dashboard/src/api/generated/openapi-v1/**/*.ts"
uv run python docs/scripts/update_openapi_json.py
node node_modules/prettier/bin/prettier.cjs --write docs/public/openapi.json
```

不要手工编辑 `dashboard/src/api/generated/openapi-v1/` 或 `docs/public/openapi.json`。仓库 `.prettierignore` 默认排除生成客户端，因此必须用上面的 `--ignore-path .gitignore` 显式应用其已提交格式；两个格式化命令都只是机械处理。提交前还应验证本地 `/api/v1/openapi.json`、源码规范、前端调用点、中英文本文档及相关测试一致。

## 完整 API 文档

交互式 API 文档请查看：

- `/help/scalar.html`
