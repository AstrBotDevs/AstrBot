# Plugin Views


Plugin Views let a plugin ship its own pages inside the AstrBot WebUI. View files live under `views/` in the plugin directory (`pages/` is still accepted) and are loaded by the Dashboard in a restricted iframe. Scripts in a view talk to the Dashboard through the `window.AstrBotPluginView` bridge (alias `window.AstrBotPluginPage`), which the Dashboard forwards to the plugin's registered backend Web APIs.

If you only need a small set of editable settings, prefer [`_conf_schema.json`](./plugin-config.md). Views are a better fit for complex forms, runtime dashboards, logs, file upload/download, SSE streams, charts, and other custom workflows.

## Directory Layout

Each direct child directory under `views/` is one View. AstrBot only discovers `views/<page_name>/index.html`; directories without `index.html` are ignored.

```text
astrbot_plugin_view_demo/
├─ main.py
└─ views/
   ├─ bridge-demo/
   │  ├─ index.html
   │  ├─ app.js
   │  ├─ style.css
   │  └─ assets/
   │     └─ logo.svg
   └─ settings/
      └─ index.html
```

Use simple directory names for `page_name`, such as `settings` or `bridge-demo`. Do not use an empty name, `.`, `..`, a name starting with `.`, or a name containing `/` or `\`.

Users open views from the plugin detail page in the WebUI.

## Development Flow

1. Create `views/<page_name>/index.html` in the plugin directory.
2. Use the `window.AstrBotPluginView` bridge from the View.
3. Register backend APIs with `context.register_web_api()` in `main.py`.
4. Read requests and return responses with `astrbot.api.web`.
5. Reload the plugin after adding or removing View directories; refreshing the View is usually enough for static asset edits.

## Minimal Complete Example

### Backend

Plugin backend code should use `astrbot.api.web`. Avoid exposing raw FastAPI, Starlette, or Quart request objects as the public API for your plugin business logic.

```python
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request

PLUGIN_NAME = "astrbot_plugin_view_demo"


class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        context.register_web_api(
            f"/{PLUGIN_NAME}/ping",
            self.page_ping,
            ["GET"],
            "View ping",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/settings/save",
            self.save_settings,
            ["POST"],
            "Save View settings",
        )

    async def page_ping(self):
        limit = request.query.get("limit", 20, type=int)
        return json_response(
            {
                "message": "pong",
                "limit": limit,
                "username": request.username,
            }
        )

    async def save_settings(self):
        payload = await request.json(default={})
        if not isinstance(payload.get("enabled"), bool):
            return error_response("enabled must be a boolean")
        return json_response({"saved": True})
```

### Frontend

`views/bridge-demo/index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Plugin View Demo</title>
    <link rel="stylesheet" href="./style.css" />
  </head>
  <body>
    <button id="ping">Ping</button>
    <pre id="output"></pre>
    <script type="module" src="./app.js"></script>
  </body>
</html>
```

`views/bridge-demo/app.js`

```js
const bridge = window.AstrBotPluginView;
const output = document.getElementById("output");

const context = await bridge.ready();
output.textContent = JSON.stringify(context, null, 2);

document.getElementById("ping").addEventListener("click", async () => {
  const result = await bridge.apiGet("ping", { limit: 20 });
  output.textContent = JSON.stringify(result, null, 2);
});
```

You do not need to import the bridge SDK manually. AstrBot injects `/api/plugin/page/bridge-sdk.js` into returned HTML. If an inline script must access `window.AstrBotPluginView` synchronously, move it to an external module file or explicitly include the SDK before your script:

```html
<script src="/api/plugin/page/bridge-sdk.js"></script>
```

## Backend Web APIs

### Route Registration

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

### Request Object

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

from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path
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

### Responses

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

### Quart Compatibility

For backward compatibility, handlers registered through `context.register_web_api()` still run inside a Quart-compatible request context. Existing plugins can continue to use:

```python
from quart import jsonify, request
```

New plugins and new documentation should use:

```python
from astrbot.api.web import json_response, request
```

Do not mix the two `request` proxies in the same handler. Migrate one handler at a time.

## Bridge API

The View iframe cannot directly access Dashboard cookies, LocalStorage, or the parent DOM. View scripts must use `window.AstrBotPluginView` to call backend APIs and read context.

```js
const bridge = window.AstrBotPluginView;
```

### Context

`ready()` waits for the parent page to send the initial context and returns `Promise<context>`. Wait for it during page initialization.

```js
const context = await bridge.ready();
```

The context usually contains:

```json
{
  "pluginName": "astrbot_plugin_view_demo",
  "displayName": "Plugin View Demo",
  "pageName": "bridge-demo",
  "pageTitle": "Bridge Demo",
  "locale": "en-US",
  "i18n": {},
  "isDark": false
}
```

Context APIs:

| API | Returns | Description |
| --- | --- | --- |
| `ready()` | `Promise<context>` | Waits until the bridge is ready and returns the initial context |
| `getContext()` | `context \| null` | Synchronously reads the latest context |
| `getLocale()` | `string` | Current WebUI locale, defaulting to `zh-CN` |
| `getI18n()` | `object` | Current plugin i18n resources |
| `t(key, fallback)` | `string` | Reads a dot-separated translation key, returning fallback when missing |
| `onContext(handler)` | `() => void` | Listens for context changes and returns an unsubscribe function |

Respond to locale or theme changes:

```js
function render() {
  document.title = bridge.t("views.bridge-demo.title", "Bridge Demo");
  document.getElementById("locale").textContent = bridge.getLocale();
}

await bridge.ready();
render();

const off = bridge.onContext(render);
window.addEventListener("beforeunload", off);
```

### Request and Return Rules

The `endpoint` used by `apiGet`, `apiPost`, `upload`, `download`, and `subscribeSSE` is a plugin-local relative path, such as `stats`, `settings/save`, or `files/export`. Prefer not to start it with `/`; the current bridge strips leading `/` for compatibility.

`endpoint` must not be empty, contain `\`, contain a URL scheme, contain query strings or fragments, or contain empty, `.`, or `..` path segments.

Do not append query strings to endpoint:

```js
await bridge.apiGet("stats", { limit: 20 });
```

Bridge JSON calls use this compatibility rule:

- If the backend returns `{ "status": "ok", "data": value }`, the Promise resolves to `value`.
- If the backend returns plain JSON, such as `{ "message": "pong" }`, the Promise resolves to that full JSON body.
- If the backend returns `{ "status": "error", "message": "..." }`, or the HTTP request fails, the Promise rejects with `Error`.

For View-only APIs, prefer returning plain business JSON:

```python
return json_response({"message": "pong"})
```

Use this for errors:

```python
return error_response("missing file", status_code=400)
```

Handle errors on the View:

```js
try {
  await bridge.apiPost("settings/save", { enabled: true });
} catch (error) {
  console.error(error.message);
}
```

### `apiGet(endpoint, params)`

Sends a GET request. `params` are sent as query parameters.

```js
const stats = await bridge.apiGet("stats", { limit: 20, tag: "today" });
```

Backend:

```python
async def stats(self):
    limit = request.query.get("limit", 20, type=int)
    tag = request.query.get("tag")
    return json_response({"limit": limit, "tag": tag})
```

### `apiPost(endpoint, body)`

Sends a POST JSON request.

```js
const result = await bridge.apiPost("settings/save", {
  enabled: true,
  threshold: 0.8,
});
```

Backend:

```python
async def save_settings(self):
    payload = await request.json(default={})
    return json_response({"saved": True, "enabled": payload.get("enabled")})
```

### `upload(endpoint, file)`

Uploads one file as `multipart/form-data`. The field name is always `file`.

```js
const input = document.querySelector("input[type=file]");
const file = input.files[0];
const result = await bridge.upload("files/import", file);
```

Backend:

```python
from astrbot.api.web import PluginUploadFile, error_response, json_response, request


async def import_file(self):
    files = await request.files()
    upload: PluginUploadFile | None = files.get("file")
    if not isinstance(upload, PluginUploadFile):
        return error_response("missing file", status_code=400)
    return json_response({"filename": upload.filename})
```

If you need extra structured fields, send them through a separate `apiPost` call or use query parameters to select import behavior. The current `upload()` bridge method sends one file.

### `download(endpoint, params, filename)`

Requests a plugin backend file endpoint and triggers a browser download. `params` are sent as query parameters. `filename` is optional; when omitted, the bridge tries to read it from response headers.

```js
await bridge.download("files/export", { format: "json" }, "export.json");
```

Backend:

```python
async def export_file(self):
    fmt = request.query.get("format", "json")
    return file_response(
        export_path,
        filename=f"export.{fmt}",
        content_type="application/json",
    )
```

`download()` resolves to:

```json
{ "filename": "export.json" }
```

### `subscribeSSE(endpoint, handlers, params)`

Subscribes to plugin backend SSE and returns `Promise<subscriptionId>`. `handlers` may include `onOpen`, `onMessage`, and `onError`.

```js
const subscriptionId = await bridge.subscribeSSE(
  "events",
  {
    onOpen() {
      console.log("SSE opened");
    },
    onMessage(event) {
      console.log(event.raw, event.parsed, event.lastEventId);
    },
    onError() {
      console.warn("SSE error");
    },
  },
  { topic: "logs" },
);
```

`event.raw` is the raw string. If the message is a JSON string, `event.parsed` is parsed automatically; otherwise it equals the raw string. `event.eventType` matches the SSE `event:` field and defaults to `message`.

The backend must return `text/event-stream`:

```python
async def events(self):
    async def stream():
        yield 'data: {"message": "ready"}\n\n'

    return stream_response(stream())
```

Unsubscribe:

```js
await bridge.unsubscribeSSE(subscriptionId);
```

Clean up on unload:

```js
window.addEventListener("beforeunload", () => {
  bridge.unsubscribeSSE(subscriptionId);
});
```

## View Internationalization

Plugin Views reuse plugin i18n resource files. Add `views.<page_name>` to `.astrbot-plugin/i18n/<locale>.json`:

```json
{
  "views": {
    "bridge-demo": {
      "title": "Bridge Demo",
      "description": "Shows how a plugin page reads the WebUI locale and translations.",
      "heading": "Plugin View",
      "refresh": "Render again"
    }
  }
}
```

`title` is used by the WebUI shell title and the view component name on the plugin detail page. `description` is used by the view component description. Inside the view, render text with `bridge.t()` and react to locale changes with `onContext()`.

```js
function render() {
  document.title = bridge.t("views.bridge-demo.title", "Bridge Demo");
  document.getElementById("heading").textContent = bridge.t(
    "views.bridge-demo.heading",
    "Plugin View",
  );
}

await bridge.ready();
render();
bridge.onContext(render);
```

## Light/Dark Theme

AstrBot syncs the current theme to Plugin Views. The bridge SDK maintains a `data-theme` attribute on `<html>`:

- Light mode: `<html data-theme="light">`
- Dark mode: `<html data-theme="dark">`

When **Follow System** is selected, the View still receives either `light` or `dark`.

CSS variables are recommended:

```css
:root {
  --bg: #ffffff;
  --text: #1a1a1a;
}

[data-theme="dark"] {
  --bg: #1a1a1a;
  --text: #e0e0e0;
}

body {
  background: var(--bg);
  color: var(--text);
}
```

The server injects `data-theme` into returned HTML to reduce initial flashing. If JavaScript needs to react to theme changes, read `bridge.getContext()?.isDark` and listen with `onContext()`.

## Static Asset Paths

Use normal relative paths:

```html
<link rel="stylesheet" href="./style.css" />
<script type="module" src="./app.js"></script>
<img src="./assets/logo.svg" alt="" />
```

AstrBot authenticates view assets with a path token: the `content_path` returned by the entry config endpoint looks like `/api/v1/plugins/<plugin>/views/<view>/_t/<token>/`, and relative URLs inside the page resolve under that prefix and inherit the token through normal URL resolution. Content is served as-is, without rewriting. The token lives as long as the dashboard session and is scoped to exactly that plugin and view.

Do not hardcode content URLs, append `asset_token` yourself, or rely on `..` to escape the View root. The legacy `/api/plugin/page/content/...?asset_token=...` form has been removed.

If you build a SPA, prefer hash routing. The static asset server resolves real file paths; with history routing, refreshing a page requires a real file at that path.

## Security Constraints

Plugin Views run inside a restricted iframe:

```text
allow-scripts allow-forms allow-downloads
```

The View cannot directly access Dashboard cookies, LocalStorage, or the parent DOM, and it cannot bypass the bridge to reuse Dashboard auth. All operations that need Dashboard identity should go through the bridge.

Asset responses include security headers such as:

- `X-Frame-Options: SAMEORIGIN`
- `Content-Security-Policy: frame-ancestors 'self'; object-src 'none'; base-uri 'self'`
- `Cache-Control: no-store`
- `X-Content-Type-Options: nosniff`

Backend handlers must still validate input. Do not trust paths, filenames, formats, or numeric ranges sent by the View. Store files only in safe directories and prefer whitelisted or regenerated filenames.

## Debugging Tips

- View is missing: check that `views/<page_name>/index.html` exists, the plugin is enabled, and the plugin detail page has been refreshed.
- Bridge is missing: make sure your script runs after the bridge SDK is injected; external `type="module"` scripts are recommended.
- API is not matched: make sure the registered route includes the plugin name prefix, such as `/{PLUGIN_NAME}/stats`, while the View endpoint is `stats`.
- Query or JSON is empty: pass GET values through `apiGet(endpoint, params)` and POST JSON through `apiPost(endpoint, body)`.
- Upload is empty: `upload()` always uses the field name `file`; read it with `(await request.files()).get("file")`.
- SSE has no messages: make sure the backend response is `text/event-stream` and each message ends with a blank line, such as `data: ...\n\n`.
- SSE returns 401: do not call `new EventSource("/api/v1/...")` directly from the View. Native `EventSource` cannot send the `Authorization` header; call through `bridge.subscribeSSE()` instead.
