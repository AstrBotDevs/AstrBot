---
outline: deep
---

# AstrBot HTTP API

Starting from v4.18.0, AstrBot provides API Key based HTTP APIs for programmatic access.

## Quick Start

1. Create an API key in WebUI - Settings.
2. Include the API key in request headers:

```http
Authorization: Bearer abk_xxx
```

Also supported:

```http
X-API-Key: abk_xxx
```

3. For chat endpoints, `username` is required:

- `POST /api/v1/chat`: request body must include `username`
- `GET /api/v1/chat/sessions`: query params must include `username`

The local OpenAPI schema is available at `http://localhost:6185/api/v1/openapi.json`, and the interactive docs are available at `http://localhost:6185/api/v1/docs`.

## Scope Permissions

When creating an API Key, you can configure `scopes`. Each scope controls the range of accessible endpoints:

| Scope | Purpose | Accessible Endpoints |
| --- | --- | --- |
| `bot` | Manage bot/platform configurations | `GET /api/v1/bot-types`, `GET/POST /api/v1/bots`, `PATCH /api/v1/bots/enabled` |
| `provider` | Manage model providers and provider sources | `GET/POST /api/v1/providers`, `GET/PUT/DELETE /api/v1/provider-sources/by-id` |
| `persona` | Manage personas and persona folders | `GET/POST /api/v1/personas`, `GET/POST /api/v1/persona-folders` |
| `im` | Send proactive IM messages and query bot/platform list | `POST /api/v1/im/message`, `GET /api/v1/im/bots` |
| `config` | Manage config profiles, system config, and shared configuration. This scope also includes `bot` and `provider` access. | `GET /api/v1/configs`, `GET/PUT /api/v1/system-config`, `GET/POST /api/v1/config-profiles` |
| `chat` | Access chat capabilities and query sessions | `POST /api/v1/chat`, `GET /api/v1/chat/sessions` |
| `file` | Upload and download chat attachments | `POST /api/v1/file`, `GET /api/v1/file`, `POST /api/v1/files` |
| `plugin` | Manage plugins, plugin config, plugin sources, and marketplace entries | `GET /api/v1/plugins`, `GET/PUT /api/v1/plugins/config`, `POST /api/v1/plugins/install/url` |
| `mcp` | Manage MCP server configurations and provider sync | `GET/POST /api/v1/mcp/servers`, `PATCH /api/v1/mcp/servers/{server_name}/enabled`, `POST /api/v1/mcp/providers/modelscope/sync` |
| `skill` | Manage skills, skill archives, skill files, and Shipyard Neo skill workflows | `GET/POST /api/v1/skills`, `PUT /api/v1/skills/{skill_name}/files/{file_path}`, `POST /api/v1/skills/neo/sync` |

If the API Key does not include the required scope for the target endpoint, the request will return `403 Insufficient API key scope`.

`config` is a broad management scope. When an API key is created with `config`, AstrBot grants the key `config`, `bot`, and `provider` access together. The WebUI mirrors this dependency: selecting `config` selects `bot` and `provider`; deselecting `bot` or `provider` removes `config`.

Developer API keys currently support only the 10 scopes listed above. `tool`, `skills`, `kb`, `data`, and `system` are not valid developer API key scopes. Use the singular `skill` scope for `/api/v1/skills/*` endpoints. The public OpenAPI reference only includes endpoints covered by supported developer API key scopes.

## Common Endpoints

**Chat**

Interact with AstrBot's built-in Agent. Supports plugin calls, tool calls, and other capabilities — consistent with IM-side chat.

- `POST /api/v1/chat`: send chat message (SSE stream, server generates UUID when `session_id` is omitted)
- `GET /api/v1/chat/sessions`: list sessions for a specific `username` with pagination
- `GET /api/v1/configs`: list available config files
- `POST /api/v1/file`: upload an attachment for later use in message segments

**Bots and Providers**

- `GET /api/v1/bots`: list bot/platform configurations
- `POST /api/v1/bots`: create a bot/platform configuration
- `GET /api/v1/providers`: list model provider configurations
- `GET /api/v1/provider-sources`: list provider source configurations

**Personas, Plugins, MCP, and Skills**

- `GET /api/v1/personas`: list personas
- `GET /api/v1/plugins`: list plugins
- `GET /api/v1/mcp/servers`: list MCP servers
- `GET /api/v1/skills`: list skills

**Proactive IM Messages**

- `POST /api/v1/im/message`: send a proactive message via UMO
- `GET /api/v1/im/bots`: list bot/platform IDs

## `message` Field Format (Important)

The `message` field in `POST /api/v1/chat` and `POST /api/v1/im/message` supports two formats:

1. String: plain text message
2. Array: message segments (message chain)

### 1. Plain Text Format

```json
{
  "message": "Hello"
}
```

### 2. Message Segment Array Format

```json
{
  "message": [
    { "type": "plain", "text": "Please see this file" },
    { "type": "file", "attachment_id": "9a2f8c72-e7af-4c0e-b352-111111111111" }
  ]
}
```

Supported `type` values:

| type | Required Fields | Optional Fields | Description |
| --- | --- | --- | --- |
| `plain` | `text` | - | Text segment |
| `reply` | `message_id` | `selected_text` | Quote-reply a message |
| `image` | `attachment_id` | - | Image attachment segment |
| `record` | `attachment_id` | - | Audio attachment segment |
| `file` | `attachment_id` | - | Generic file segment |
| `video` | `attachment_id` | - | Video attachment segment |

* The `reply` segment is currently only supported for `/api/v1/chat`, not for `POST /api/v1/im/message`.

Notes:

- `attachment_id` comes from an existing attachment record, or from `POST /api/v1/file` after uploading an attachment with the `file` scope.
- `reply` cannot be the only segment; at least one content segment (e.g. `plain/image/file/...`) is required.
- A request with only `reply` or empty content will return an error.

### `message` Usage in Chat API

`POST /api/v1/chat` additionally requires `username`, with optional `session_id` (a UUID is auto-generated if omitted).

`username` is a caller-declared WebChat identity. It is used as the message sender and session owner in the message pipeline, including sender-ID-based command permission checks. Treat API keys with the `chat` scope as trusted backend credentials. If you expose chat access to end users, proxy requests through your own service and map each external user to an allowed `username`; do not let clients submit administrator IDs or other reserved sender IDs directly.

```json
{
  "username": "alice",
  "session_id": "my_session_001",
  "message": [
    { "type": "plain", "text": "Please summarize this PDF" },
    { "type": "file", "attachment_id": "9a2f8c72-e7af-4c0e-b352-111111111111" }
  ],
  "enable_streaming": true
}
```

### `message` Usage in IM Message API

`POST /api/v1/im/message` requires `umo` + `message`.

```json
{
  "umo": "webchat:FriendMessage:openapi_probe",
  "message": [
    { "type": "plain", "text": "This is a proactive message" },
    { "type": "image", "attachment_id": "9a2f8c72-e7af-4c0e-b352-222222222222" }
  ]
}
```

## Example

```bash
curl -N 'http://localhost:6185/api/v1/chat' \
  -H 'Authorization: Bearer abk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello","username":"alice"}'
```

## Full API Reference

Use the interactive docs:

- https://docs.astrbot.app/scalar.html
