---
outline: deep
---

# AstrBot HTTP API

AstrBot provides API-key-based HTTP APIs for programmatic access.

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

The local schema contains the full `/api/v1` contract, including dashboard-session routes. The public docs site at `https://docs.astrbot.app/scalar.html` is a filtered developer-facing subset generated from the same source spec.

## Scope Permissions

When creating an API Key, you can configure `scopes`. Each scope controls the range of accessible endpoints:

| Scope      | Purpose                                                                      | Representative endpoints                                                                                                        |
| ---------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `bot`      | Manage bot/platform configurations                                           | `GET/POST /api/v1/bots`, `PATCH /api/v1/bots/{bot_id}/enabled`                                                                  |
| `provider` | Manage models and Provider sources                                           | `GET/POST /api/v1/providers`, `GET/PUT/DELETE /api/v1/provider-sources/{source_id}`                                             |
| `persona`  | Manage Personas and Persona folders                                          | `GET/POST /api/v1/personas`, `GET/POST /api/v1/persona-folders`                                                                 |
| `im`       | Send proactive IM messages and query the bot/platform list                   | `POST /api/v1/im/messages`, `GET /api/v1/im/bots`                                                                               |
| `config`   | Manage profiles and system configuration; also includes `bot` and `provider` | `GET/PUT /api/v1/system-config`, `GET/POST /api/v1/config-profiles`, `GET /api/v1/subagents/config`                             |
| `chat`     | Use chat and inspect or maintain WebChat sessions                            | `POST /api/v1/chat`, `GET /api/v1/chat/sessions`, `GET /api/v1/chat/configs`                                                    |
| `kb`       | Manage knowledge bases, documents, chunks, and retrieval                     | `GET/POST /api/v1/knowledge-bases`, `POST /api/v1/knowledge-bases/{kb_id}/retrieve`                                             |
| `memory`   | Audit and maintain long-term-memory facts, profiles, and operations          | `GET/POST /api/v1/memory/facts`, `POST /api/v1/memory/facts/{fact_id}/delete`, `GET /api/v1/memory/operations`                  |
| `data`     | Manage session state, session groups, rules, and stored conversations        | `GET/POST /api/v1/sessions`, `GET/POST /api/v1/session-groups`, `GET/POST /api/v1/conversations`                                |
| `file`     | Upload and download chat attachments                                         | `POST/GET /api/v1/file`, `POST /api/v1/files`                                                                                   |
| `plugin`   | Manage plugins, plugin configuration, sources, and marketplace data          | `GET /api/v1/plugins`, `GET/PUT /api/v1/plugins/{plugin_id}/config`, `POST /api/v1/plugins/install/url`                         |
| `mcp`      | Manage MCP server configuration and provider sync                            | `GET/POST /api/v1/mcp/servers`, `PATCH /api/v1/mcp/servers/{server_name}/enabled`, `POST /api/v1/mcp/providers/modelscope/sync` |
| `skill`    | Manage Skills, archives, files, and Shipyard Neo workflows                   | `GET/POST /api/v1/skills`, `PUT /api/v1/skills/{skill_name}/files/{file_path}`, `POST /api/v1/skills/neo/sync`                  |

If the API Key does not include the required scope for the target endpoint, the request will return `403 Insufficient API key scope`.

`config` is a broad management scope. When an API key is created with `config`, AstrBot grants the key `config`, `bot`, and `provider` access together. The WebUI mirrors this dependency: selecting `config` selects `bot` and `provider`; deselecting `bot` or `provider` removes `config`.

Developer API keys support the 13 baseline scopes. Use the singular `skill` scope for `/api/v1/skills/*` endpoints.

Keys stored before explicit scopes used `NULL` to mean the fixed baseline scope set. It is not a wildcard and does not gain sensitive scopes. Runtime authorization uses explicit capabilities only and does not expand `*` or `NULL` onto new high-risk actions. See [Architecture](/en/dev/architecture#unified-authorization).

`tool`, `system`, and data-file-manager routes still exist in the full local `/api/v1/openapi.json` schema, but they are Dashboard-session routes rather than developer API key scopes. Data-file routes use the `Data Files` tag and are excluded from the public OpenAPI document.

## Common Endpoints

**Chat**

Interact with AstrBot's built-in Agent. Supports plugin calls, tool calls, and other capabilities — consistent with IM-side chat.

- `POST /api/v1/chat`: send chat message (SSE stream, server generates UUID when `session_id` is omitted)
- `GET /api/v1/chat/sessions`: list sessions for a specific `username` with pagination
- `GET /api/v1/chat/configs`: list chat-selectable profiles; the current runtime requires the `chat` scope
- `POST /api/v1/file`: upload an attachment for later use in message segments

**Bots and Providers**

- `GET /api/v1/bots`: list bot/platform configurations
- `POST /api/v1/bots`: create a bot/platform configuration
- `GET /api/v1/providers`: list model provider configurations
- `GET /api/v1/provider-sources`: list provider source configurations

**Personas, Knowledge Base, Long-term Memory, Data, Plugins, MCP, and Skills**

- `GET /api/v1/personas`: list personas
- `GET /api/v1/knowledge-bases`: list knowledge bases
- `GET /api/v1/memory/facts`: page through long-term-memory facts
- `GET /api/v1/sessions`: list session state and rules
- `GET /api/v1/conversations`: list stored conversations
- `GET /api/v1/plugins`: list plugins
- `GET /api/v1/mcp/servers`: list MCP servers
- `GET /api/v1/skills`: list skills

**Proactive IM Messages**

- `POST /api/v1/im/messages`: send a proactive message via UMO
- `GET /api/v1/im/bots`: list bot/platform IDs

## `message` Field Format (Important)

The `message` field in `POST /api/v1/chat` and `POST /api/v1/im/messages` supports two formats:

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

| type     | Required Fields | Optional Fields | Description              |
| -------- | --------------- | --------------- | ------------------------ |
| `plain`  | `text`          | -               | Text segment             |
| `reply`  | `message_id`    | `selected_text` | Quote-reply a message    |
| `image`  | `attachment_id` | -               | Image attachment segment |
| `record` | `attachment_id` | -               | Audio attachment segment |
| `file`   | `attachment_id` | -               | Generic file segment     |
| `video`  | `attachment_id` | -               | Video attachment segment |

- The `reply` segment is currently only supported for `/api/v1/chat`, not for `POST /api/v1/im/messages`.

Notes:

- `attachment_id` comes from an existing attachment record, or from `POST /api/v1/file` after uploading an attachment with the `file` scope.
- `reply` cannot be the only segment; at least one content segment (e.g. `plain/image/file/...`) is required.
- A request with only `reply` or empty content will return an error.

### `message` Usage in Chat API

`POST /api/v1/chat` additionally requires `username`, with optional `session_id` (a UUID is auto-generated if omitted).

`username` is a caller-declared WebChat identity. It is compatibility data only and never grants Dashboard or administrator authority. If you expose chat access to end users, proxy requests through your own service and map each external user to an allowed `username`.

When an authenticated Dashboard session calls `/api/v1/chat`, the server separately carries the signed account, session, and current authentication strength so authorization uses the real Dashboard principal. It never trusts `username` to elevate permissions. API-key calls remain authorized only by that key's scopes and never inherit Dashboard roles or high-risk permissions.

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

`POST /api/v1/im/messages` requires `umo` + `message`.

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

## JSON response envelope and streaming exceptions

Ordinary JSON APIs use a common envelope:

```json
{
  "status": "ok",
  "message": null,
  "data": {}
}
```

Business errors normally use `status: "error"` with a readable `message`. A client should check `status` as well as the HTTP status code.

Responses governed by another protocol do not use the ordinary JSON envelope, including:

- Chat Server-Sent Events (SSE) streams;
- the actual file response returned by attachment-download routes;
- conversation exports, log streams, webhooks, and static or other binary responses.

Handle those routes according to their OpenAPI content type instead of calling `response.json()` unconditionally.

## Contract maintenance workflow

The source specification is `openspec/openapi-v1.yaml` at the repository root. Runtime routes and Pydantic request models live in `astrbot/dashboard/api/` and `astrbot/dashboard/schemas.py`. When routes, request/response schemas, scopes, or the source spec change, update those sources together and regenerate both consumers:

```bash
cd dashboard
pnpm generate:api
cd ..
node node_modules/prettier/bin/prettier.cjs --write --ignore-path .gitignore "dashboard/src/api/generated/openapi-v1/**/*.ts"
uv run python docs/scripts/update_openapi_json.py
node node_modules/prettier/bin/prettier.cjs --write docs/public/openapi.json
```

Do not hand-edit `dashboard/src/api/generated/openapi-v1/` or `docs/public/openapi.json`. The repository `.prettierignore` normally excludes generated clients, so the explicit `--ignore-path .gitignore` is required to reproduce their checked-in formatting. Both formatting commands are mechanical. Before committing, verify the local `/api/v1/openapi.json`, source spec, frontend call sites, both language versions of this page, and relevant tests agree.

## Full API Reference

Use the interactive docs:

- <https://docs.astrbot.app/scalar.html>
