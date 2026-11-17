# Shared Bridge API

All views use `window.AstrBotPluginView`. The host injects the SDK automatically. Use an external `type="module"` script and await `bridge.ready()` before calling its methods.

## Capabilities {#capabilities}

| API | Standalone page | Message component / message-created workbench | Resident workbench |
| --- | --- | --- | --- |
| `ready`, `getContext`, `onContext` | Supported | Supported | Supported |
| Theme CSS tokens and localization | Supported | Supported | Supported |
| `view.subscribe`, `view.action` | — | Supported | — |
| `apiGet`, `apiPost`, file transfers, SSE | Supported | — | Supported |
| `chat.fill`, `chat.send` | — | — | Supported |

Unsupported operations return `UNSUPPORTED_CAPABILITY`. `AstrBotPluginPage` remains a compatibility alias; use `AstrBotPluginView` in new code.

## TypeScript declarations {#typescript}

Download [astrbot-plugin-view.d.ts](/types/astrbot-plugin-view.d.ts) into your frontend project's `src/` directory, or another path covered by `tsconfig.json`'s `include`. It adds types for `window.AstrBotPluginView`; the host still injects the runtime SDK, so no JavaScript package import is needed.

These are all public method signatures. The following sections define their data structures. Every method exists on the bridge object, but availability depends on [host capabilities](#capabilities). `__setInitialContext` is internal to the host, not a plugin API.

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#bridge{ts}

<details>
<summary>Base types</summary>

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#base{ts}

</details>

## Initialize the bridge {#bridge-api}

The View iframe cannot directly access Dashboard cookies, LocalStorage, or the parent DOM. View scripts must use `window.AstrBotPluginView` to call backend APIs and read context.

```js
const bridge = window.AstrBotPluginView;
```

In TypeScript, specify your snapshot and business-response types:

```ts
import type { AstrBotPluginViewBridge } from "./astrbot-plugin-view";

type CounterData = { count: number };
const bridge = window.AstrBotPluginView as AstrBotPluginViewBridge<CounterData>;
const context = await bridge.ready();
if (context.view) {
  bridge.view.subscribe(({ data }) => console.log(data.count));
} else {
  const result = await bridge.apiGet<{ message: string }>("ping");
  console.log(result.message);
}
```

## Context

`ready()` waits for the parent page to send the initial context and returns `Promise<BridgeContext>`. Wait for it during page initialization.

```js
const context = await bridge.ready();
```

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#context{ts}

Use both `target` and `view` to identify the host:

| Host | `target` | `view` | `sessionId` |
| --- | --- | --- | --- |
| Standalone page | `plugin_page` | Absent | `null` |
| Message component | `chat_message` | `ViewSnapshot` | Absent |
| Message-created workbench | `chat_workbench` | `ViewSnapshot` | Absent |
| Resident workbench | `chat_workbench` | Absent | Active session ID, or `null` without a session |

`view` contains only `id`, `revision`, and `data`, not the `name` or `version` fields of Python's `UIInteraction.view`. Read the registered view name from `context.pageName`. `i18n` is keyed by locale, for example `{ "en-US": { "views": { "counter": { "title": "Counter" } } } }`. Additional `themeColors` keys come from the host theme; prefer the CSS tokens listed below for styling.

Context APIs:

| API | Returns | Description |
| --- | --- | --- |
| `ready()` | `Promise<BridgeContext>` | Waits until the bridge is ready and returns the current context |
| `getContext()` | `BridgeContext \| null` | Synchronously reads the latest context |
| `getLocale()` | `string` | Current WebUI locale, defaulting to `zh-CN` |
| `getI18n()` | `I18nResources` | Current plugin i18n resources |
| `t(key, fallback)` | `string` | Reads a dot-separated translation key, returning fallback when missing |
| `onContext(handler)` | `() => void` | Listens for context changes and returns an unsubscribe function |

`onContext()` invokes the handler immediately when context is available, then on every context update. Its unsubscribe function removes only that subscription. `getContext()` returns `null` before initialization. `t()` searches the current locale, then `zh-CN`, then `en-US`; if no value exists, it returns `fallback` or an empty string.

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

## Plugin Web APIs

### Request and return rules

The `endpoint` used by `apiGet`, `apiPost`, `upload`, `download`, and `subscribeSSE` is a plugin-local relative path, such as `stats`, `settings/save`, or `files/export`. Prefer not to start it with `/`; the current bridge strips leading `/` for compatibility.

`endpoint` must not be empty, contain `\`, contain a URL scheme, contain query strings or fragments, or contain empty, `.`, or `..` path segments.

Do not append query strings to endpoint:

```js
await bridge.apiGet("stats", { limit: 20 });
```

Bridge JSON calls use this compatibility rule:

- For successful responses, a non-null `data` field is unwrapped, regardless of whether `status` is `"ok"`. For example, `{ "data": 0 }` resolves to `0`.
- If `data` is absent or null, the complete response is returned. Both `{ "message": "pong" }` and `{ "data": null }` are returned unchanged.
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

```ts
apiGet<TResult = unknown>(endpoint: string, params?: QueryParams): Promise<TResult>
```

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

```ts
apiPost<TResult = unknown>(endpoint: string, body?: JsonValue): Promise<TResult>
```

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

```ts
upload<TResult = unknown>(endpoint: string, file: UploadFile): Promise<TResult>
```

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

```ts
download(endpoint: string, params?: QueryParams, filename?: string): Promise<DownloadResult>
```

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

```ts
subscribeSSE<TData = unknown>(
  endpoint: string,
  handlers?: SSEHandlers<TData>,
  params?: SSEParams,
): Promise<string>
```

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#sse{ts}

Subscribes to plugin backend SSE and returns `Promise<subscriptionId>`. `handlers` may include `onOpen`, `onMessage`, `onClose`, and `onError`.

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
    onClose() {
      console.log("SSE stream ended");
    },
    onError() {
      console.warn("SSE error");
    },
  },
  { topic: "logs" },
);
```

`event.raw` is the raw string. If the message is a JSON string, `event.parsed` is parsed automatically; otherwise it equals the raw string. `event.eventType` matches the SSE `event:` field and defaults to `message`.

`onClose` is called when the stream ends, and `onError` is called if reading it fails. Calling `unsubscribeSSE` triggers neither callback. The bridge does not reconnect automatically; subscribe again if needed. Initial subscription failures reject the returned promise.

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

## View actions and chat controls

```ts
view.subscribe(handler: (snapshot: ViewSnapshot<TViewData>) => void): Unsubscribe
view.action(actionId: string, data?: JsonValue): Promise<void>
chat.fill(text: string): Promise<ChatResult>
chat.send(text: string): Promise<ChatResult>
```

Call `view.subscribe()` after `ready()`. It immediately supplies a copy of the current snapshot and runs again when a snapshot with the same or a higher revision arrives. Unsubscribing removes the listener without closing the view. Notifications do not necessarily indicate a business-data change; mutating the copy does not save data.

The `data` argument of `view.action()` defaults to `null`. Success resolves to `undefined`, not a snapshot; read updated data through `view.subscribe()` or `getContext().view`. The promise settles after the callback and state commit, without waiting for subsequent model generation. Declare each action in `ViewSpec.actions`.

`chat.fill()` appends to the draft and focuses the composer. `chat.send()` sends to the current session while preserving the draft and attachments. Both resolve to `{ sessionId: string | null }`. Sending requires an open session with no running reply, and resolves when the request is accepted rather than when the answer finishes. Text must not be blank or exceed 100,000 UTF-16 code units. See [Workbench page](./workbench.md) for host requirements and examples.

## Result and error types {#result-types}

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#results{ts}

- Browser `File` and `Blob` objects satisfy `UploadFile`. The default filename is `upload.bin`; the default MIME type is `application/octet-stream`.
- `unsubscribeSSE(id)` returns `Promise<UnsubscribeSSEResult>`, resolving to `{ subscriptionId: id }` even if the connection has already ended.
- Generics on `apiGet`, `apiPost`, and `upload` describe the unwrapped business response and default to `unknown`. They do not validate server data.
- SSE `parsed` contains the JSON value when parsing succeeds, otherwise the original string. `eventType` defaults to `message`. `lastEventId` starts as an empty string and persists across events without an `id:` field. `onOpen`, `onClose`, and `onError` receive no arguments.
- `apiGet` / `download` use Axios query serialization. `subscribeSSE` calls `String(value)` for each parameter and does not support repeated keys or arrays. Omit optional SSE parameters instead of passing `undefined` or `null`.
- With an omitted body, `null`, `false`, `0`, or an empty string, the current `apiPost` host sends `{}`. Prefer JSON object request bodies.

Failures are generally `Error` objects; `code` is **optional**. Message views can report codes such as `UNSUPPORTED_CAPABILITY`, `ACTION_IN_PROGRESS`, and `REVISION_CONFLICT`. Host-forwarded plugin Web API and chat-control errors carry only a message, not an HTTP status or additional backend fields.

```ts
try {
  await window.AstrBotPluginView.view.action("reading_view:set_read", {
    book_id: "design",
    read: true,
  });
} catch (error: unknown) {
  if (error instanceof Error) {
    const code = (error as BridgeError).code;
    console.error(code ?? "BRIDGE_ERROR", error.message);
  }
}
```

Import the type with `import type { BridgeError } from "./astrbot-plugin-view"`. `view.subscribe()` can throw synchronously; request methods reject their promises. A `REVISION_CONFLICT` synchronizes the latest snapshot before rejecting; do not blindly retry actions with side effects.

## Light and dark themes {#light-dark-theme}

AstrBot syncs the current theme to Plugin Views. The bridge SDK maintains a `data-theme` attribute on `<html>`:

- Light mode: `<html data-theme="light">`
- Dark mode: `<html data-theme="dark">`

The bridge also synchronizes CSS `color-scheme` to `light` or `dark`, keeping transparent iframe backgrounds consistent with the host theme.

When **Follow System** is selected, the View still receives either `light` or `dark`.

### Following user-selected colors

All targets use the same `AstrBotPluginView` bridge. It injects these CSS tokens on `<html>` and updates them on initialization, light/dark changes, and palette changes. No manual listener or CSS assignment is needed.

| CSS token | Purpose |
| --- | --- |
| `--astrbot-color-primary` | Primary |
| `--astrbot-color-secondary` | Secondary |
| `--astrbot-color-on-primary` | Text on primary |
| `--astrbot-color-text` | Body text |
| `--astrbot-color-text-secondary` | Secondary text |
| `--astrbot-color-background` | Page background |
| `--astrbot-color-surface` | Surface background |
| `--astrbot-color-border` | Border |
| `--astrbot-color-error` | Error |

```css
body {
  color: var(--astrbot-color-text);
  background: var(--astrbot-color-background);
}
button {
  color: var(--astrbot-color-on-primary);
  background: var(--astrbot-color-primary);
  border: 1px solid var(--astrbot-color-border);
}
```

The bridge only injects variables; it does not force a page background. Chat cards can keep `background: transparent`. Existing `themeColors.primary` / `secondary` remain available. All targets use `bridge.onContext(({ isDark, themeColors, locale }) => { ... })` when additional JavaScript behavior is needed.

## View metadata and localization {#view-metadata-and-internationalization}

Put View metadata such as the title and description in `.astrbot-plugin/i18n/<locale>.json` inside the plugin directory, nested under `views.<view_name>`. `views` is a top-level locale JSON field alongside `metadata` and `config`; `<view_name>` must exactly match the directory name under `views/`.

For example, localized metadata for the `bridge-demo` View is stored as follows:

```text
astrbot_plugin_view_demo/
├─ views/
│  └─ bridge-demo/
│     └─ index.html
└─ .astrbot-plugin/
   └─ i18n/
      ├─ zh-CN.json
      └─ en-US.json
```

`.astrbot-plugin/i18n/en-US.json`:

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

Field reference:

| Field | Required | Purpose |
| --- | --- | --- |
| `title` | No | The View name in the sidebar, WebUI shell, and plugin detail page. |
| `description` | No | The View description on the plugin detail page. |
| Other fields | No | View-specific translations, such as `heading` and `refresh` in this example; read them with `bridge.t()`. |

Add each language to its matching locale file, such as `.astrbot-plugin/i18n/zh-CN.json` for Chinese. Use `views` for new plugins; the older `pages` key remains only as a compatibility alias. Reload the plugin after editing locale files so the WebUI receives the latest metadata.

If the current locale has no `title`, the ungrouped sidebar displays the plugin name. In grouped mode it displays the View directory name because the group already shows the plugin name. Render other text inside the View with `bridge.t()` and react to locale changes with `onContext()`:

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

## Static asset paths

Use normal relative paths:

```html
<link rel="stylesheet" href="./style.css" />
<script type="module" src="./app.js"></script>
<img src="./assets/logo.svg" alt="" />
```

AstrBot authenticates view assets with a path token: the `content_path` returned by the entry config endpoint looks like `/api/v1/plugins/<plugin>/views/<view>/_t/<token>/`, and relative URLs inside the page resolve under that prefix and inherit the token through normal URL resolution. Content is served as-is, without rewriting. The token lives as long as the dashboard session and is scoped to exactly that plugin and view.

Do not hardcode content URLs, append `asset_token` yourself, or rely on `..` to escape the View root. The legacy `/api/plugin/page/content/...?asset_token=...` form has been removed.

If you build a SPA, prefer hash routing. The static asset server resolves real file paths; with history routing, refreshing a page requires a real file at that path.

## Security constraints

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

## Troubleshooting {#debugging-tips}

- View is missing: check that `views/<view_name>/index.html` exists, the plugin is enabled, and the plugin detail page has been refreshed.
- Bridge is missing: make sure your script runs after the bridge SDK is injected; external `type="module"` scripts are recommended.
- API is not matched: make sure the registered route includes the plugin name prefix, such as `/{PLUGIN_NAME}/stats`, while the View endpoint is `stats`.
- Query or JSON is empty: pass GET values through `apiGet(endpoint, params)` and POST JSON through `apiPost(endpoint, body)`.
- Upload is empty: `upload()` always uses the field name `file`; read it with `(await request.files()).get("file")`.
- SSE has no messages: make sure the backend response is `text/event-stream` and each message ends with a blank line, such as `data: ...\n\n`.
- SSE returns 401: do not call `new EventSource("/api/v1/...")` directly from the View. Native `EventSource` cannot send the `Authorization` header; call through `bridge.subscribeSSE()` instead.
