# Backend Web APIs

Standalone plugin pages call these endpoints through the Bridge. Message components use `@filter.ui_action`; see [Interactive message component](./chat-message.md).

Requests use the signed-in user's identity. Validate business permissions in the plugin. For session data, check ownership against `request.username`; a client-supplied `session_id` is not authorization.

## Route registration

Register plugin APIs with `context.register_web_api(route, view_handler, methods, desc)`.

```python
context.register_web_api(
    f"/{PLUGIN_NAME}/items/<item_id>",
    self.get_item,
    ["GET"],
    "Get item",
)
```

The registered route must include the plugin name prefix. The bridge endpoint used by the View does not include the plugin name:

```js
await bridge.apiGet("items/123");
```

The Dashboard forwards it to:

```text
/api/v1/plugins/extensions/<plugin_name>/items/123
```

The registered route `/<plugin_name>/items/<item_id>` matches the request, and `item_id` is passed to the handler as a keyword argument:

```python
async def get_item(self, item_id: str):
    return json_response({"item_id": item_id})
```

Supported dynamic segments:

- `<name>`: matches one path segment.
- `<path:name>`: matches the remaining multi-segment path.

## Request object

Recommended import:

```python
from astrbot.api.web import request
```

`request` is a context proxy for the current request and is only available while a plugin Web API handler is running. Common fields and methods:

| API | Description |
| --- | --- |
| `request.method` | HTTP method, such as `GET` or `POST` |
| `request.path` | Current Dashboard API path |
| `request.plugin_name` | Plugin name parsed from the extension path |
| `request.username` | Current Dashboard username, possibly `None` |
| `request.headers` | Request headers |
| `request.cookies` | Request cookies |
| `request.content_type` | Request Content-Type |
| `request.client_host` | Client address |
| `request.path_params` | Dynamic route parameters |
| `request.query` | Query parameters with `get()` and `getlist()` |
| `await request.body()` | Raw request body bytes |
| `await request.json(default={})` | JSON body, returning default on parse failure |
| `await request.form()` | Form fields without uploaded files |
| `await request.files()` | Uploaded files |

Query example:

```python
limit = request.query.get("limit", 20, type=int)
tags = request.query.getlist("tag")
```

JSON example:

```python
payload = await request.json(default={})
enabled = bool(payload.get("enabled"))
```

Upload example:

```python
from pathlib import Path

# Before AstrBot v4.30.0:
# from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path
from astrbot.api.util import get_astrbot_plugin_data_path
from astrbot.api.web import PluginUploadFile, error_response, json_response, request


async def import_file(self):
    form = await request.form()
    files = await request.files()
    upload: PluginUploadFile | None = files.get("file")
    if not isinstance(upload, PluginUploadFile):
        return error_response("missing file")

    target_dir = (
        Path(get_astrbot_plugin_data_path())
        / (request.plugin_name or "unknown_plugin")
        / "imports"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / Path(upload.filename).name
    await upload.save(target)
    return json_response(
        {
            "filename": upload.filename,
            "content_type": upload.content_type,
            "tag": form.get("tag"),
        }
    )
```

`request.form()` and `request.files()` cache the parsed multipart data, so calling both in the same handler is fine.

## Responses

Recommended response helpers:

```python
from astrbot.api.web import (
    error_response,
    file_response,
    json_response,
    stream_response,
)
```

JSON response:

```python
return json_response({"saved": True})
```

Error response:

```python
return error_response("invalid threshold", status_code=400)
```

File download response:

```python
return file_response(
    export_path,
    filename="export.json",
    content_type="application/json",
)
```

SSE response:

```python
import json

from astrbot.api.web import stream_response


async def stream_events(self):
    async def events():
        yield f"data: {json.dumps({'state': 'started'})}\n\n"
        yield f"data: {json.dumps({'state': 'done'})}\n\n"

    return stream_response(events())
```

Returning a `dict`, `list`, `(body, status_code)`, or a lower-level Response object still works. New plugins should prefer `astrbot.api.web` helpers so plugin code remains decoupled from the Dashboard's internal web framework.

## Quart compatibility

For backward compatibility, handlers registered through `context.register_web_api()` still run inside a Quart-compatible request context. Existing plugins can continue to use:

```python
from quart import jsonify, request
```

New plugins and new documentation should use:

```python
from astrbot.api.web import json_response, request
```

Do not mix the two `request` proxies in the same handler. Migrate one handler at a time.
