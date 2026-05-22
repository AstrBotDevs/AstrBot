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

## Scope Permissions

When creating an API Key, you can configure `scopes`. Each scope controls the range of accessible endpoints:

| Scope | Purpose | Accessible Endpoints |
| --- | --- | --- |
| `chat` | Access chat capabilities and query sessions | `POST /api/v1/chat`, `GET /api/v1/chat/sessions` |
| `config` | Retrieve available config file list | `GET /api/v1/configs` |
| `file` | Upload attachment files and get `attachment_id` | `POST /api/v1/file` |
| `im` | Send proactive IM messages, query bot/platform list | `POST /api/v1/im/message`, `GET /api/v1/im/bots` |

If the API Key does not include the required scope for the target endpoint, the request will return `403 Insufficient API key scope`.

## Common Endpoints

**Chat**

Interact with AstrBot's built-in Agent. Supports plugin calls, tool calls, and other capabilities — consistent with IM-side chat.

- `POST /api/v1/chat`: send chat message (SSE stream, server generates UUID when `session_id` is omitted)
- `GET /api/v1/chat/sessions`: list sessions for a specific `username` with pagination
- `GET /api/v1/configs`: list available config files

**File Upload**

- `POST /api/v1/file`: upload attachment

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

- `attachment_id` comes from the upload result of `POST /api/v1/file`.
- `reply` cannot be the only segment; at least one content segment (e.g. `plain/image/file/...`) is required.
- A request with only `reply` or empty content will return an error.

### `message` Usage in Chat API

`POST /api/v1/chat` additionally requires `username`, with optional `session_id` (a UUID is auto-generated if omitted).

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
