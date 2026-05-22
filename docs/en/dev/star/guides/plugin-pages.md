# Plugin Pages

AstrBot lets a plugin expose Dashboard pages by placing static assets under `pages/`. Each direct child directory is one Page:

```text
astrbot_plugin_page_demo/
├─ main.py
└─ pages/
   ├─ bridge-demo/
   │  ├─ index.html
   │  ├─ app.js
   │  ├─ style.css
   │  └─ assets/
   │     └─ logo.svg
   └─ settings/
      └─ index.html
```

AstrBot scans `pages/<page_name>/index.html`; directories without `index.html` are ignored.

If you only need a few editable settings, prefer [`_conf_schema.json`](./plugin-config.md). Plugin Pages are more suitable for complex forms, dashboards, logs, file transfer, SSE, and custom interaction flows.

Once Pages are registered, users can open the AstrBot WebUI Plugins page, click the plugin card to enter the plugin detail page, and then view and open the registered Pages from that detail page.

## Minimal Frontend Example

`pages/bridge-demo/index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Plugin Page Demo</title>
    <link rel="stylesheet" href="./style.css" />
  </head>
  <body>
    <button id="ping">Ping</button>
    <pre id="output"></pre>
    <script type="module" src="./app.js"></script>
  </body>
</html>
```

`pages/bridge-demo/app.js`

```js
const bridge = window.AstrBotPluginPage;
const output = document.getElementById("output");

const context = await bridge.ready();
output.textContent = JSON.stringify(context, null, 2);

document.getElementById("ping").addEventListener("click", async () => {
  const result = await bridge.apiGet("ping");
  output.textContent = JSON.stringify(result, null, 2);
});
```

You do not need to import the bridge SDK manually. AstrBot injects `/api/plugin/page/bridge-sdk.js` into returned HTML.

## Register Backend APIs

When the frontend calls `bridge.apiGet("ping")`, the Dashboard forwards it to:

```text
/api/plug/<plugin_name>/ping
```

The registered Web API route must include the plugin name as a prefix:

```python
from quart import jsonify
from astrbot.api.star import Context, Star

PLUGIN_NAME = "astrbot_plugin_page_demo"


class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        context.register_web_api(
            f"/{PLUGIN_NAME}/ping",
            self.page_ping,
            ["GET"],
            "Page ping",
        )

    async def page_ping(self):
        return jsonify({"message": "pong"})
```

## Bridge API

Inside a plugin Page, use `window.AstrBotPluginPage` directly:

- `ready()`: Wait until the bridge is ready and return the context
- `getContext()`: Read the current context
- `getLocale()`: Read the current WebUI locale
- `getI18n()`: Read the current plugin i18n resources
- `t(key, fallback)`: Read text from plugin i18n resources by key, returning fallback when missing
- `onContext(handler)`: Listen for context changes, such as rerendering after the WebUI locale changes
- `apiGet(endpoint, params)`: Send a GET request
- `apiPost(endpoint, body)`: Send a POST request
- `upload(endpoint, file)`: Upload one file as `multipart/form-data`
- `download(endpoint, params, filename)`: Download a backend response
- `subscribeSSE(endpoint, handlers, params)`: Subscribe to SSE
- `unsubscribeSSE(subscriptionId)`: Cancel an SSE subscription

The current `ready()` context looks like this:

```json
{
  "pluginName": "astrbot_plugin_page_demo",
  "displayName": "Plugin Page Demo",
  "pageName": "bridge-demo",
  "pageTitle": "Bridge Demo",
  "locale": "en-US",
  "i18n": {}
}
```

`endpoint` must be a plugin-local path. It must not be empty, contain `\`, contain a URL scheme, contain query strings or fragments, or contain `.` / `..` path segments.

## Page Internationalization

Plugin Pages reuse plugin i18n resource files. Add `pages.<page_name>` to `.astrbot-plugin/i18n/<locale>.json`:

```json
{
  "pages": {
    "bridge-demo": {
      "title": "Bridge Demo",
      "description": "Shows how a plugin page reads the WebUI locale and translations.",
      "heading": "Plugin Page",
      "refresh": "Render again"
    }
  }
}
```

`title` is used by the WebUI shell title and the Page component name on the plugin detail page. `description` is used by the Page component description on the plugin detail page.

Inside the Page, render text with `t()` and react to language changes with `onContext()`:

```js
const bridge = window.AstrBotPluginPage;

function render() {
  document.title = bridge.t("pages.bridge-demo.title", "Bridge Demo");
  document.getElementById("heading").textContent = bridge.t(
    "pages.bridge-demo.heading",
    "Plugin Page",
  );
  document.getElementById("locale").textContent = bridge.getLocale();
}

await bridge.ready();
render();
bridge.onContext(render);
```

After the WebUI locale changes, the Dashboard sends the new `locale` and plugin i18n resources to the iframe through the bridge. If the Page listens with `onContext()`, it usually does not need a refresh.

If an inline script needs to access `window.AstrBotPluginPage` synchronously, move the code to an external module file or explicitly include the bridge SDK before your script:

```html
<script src="/api/plugin/page/bridge-sdk.js"></script>
```

## Asset Path Rules

AstrBot rewrites relative asset URLs and appends a short-lived `asset_token`. Write normal relative paths and do not hardcode `/api/plugin/page/content/...` yourself.

AstrBot rewrites:

- HTML `src` and `href`
- CSS `url(...)`
- JavaScript `import`
- JavaScript `export ... from`
- JavaScript dynamic `import()`

Keep static assets on relative paths such as `./style.css` and `./assets/logo.svg`. Do not manually append `asset_token`, and do not rely on `..` to escape the Page root directory.

If you build a SPA, prefer hash routing. The static asset server resolves real file paths; with history routing, refreshing a page requires an actual file to exist at that path.

## Security Constraints

Plugin Pages run inside a restricted iframe:

```text
allow-scripts allow-forms allow-downloads
```

The page cannot directly access Dashboard cookies, LocalStorage, or same-origin DOM, and it cannot bypass the bridge to reuse Dashboard auth directly.

AstrBot also adds security headers to asset responses, including:

- `X-Frame-Options: SAMEORIGIN`
- `Content-Security-Policy: frame-ancestors 'self'; object-src 'none'; base-uri 'self'`
- `Cache-Control: no-store`

## Debugging Tips

- Reload the plugin after adding or removing a Page directory
- For most edits under `pages/<page_name>/`, refreshing the Page is enough
- If a Page does not appear, check that `pages/<page_name>/index.html` exists and the plugin is enabled

## Appendix: Bridge API Details

Start page scripts by keeping a bridge reference:

```js
const bridge = window.AstrBotPluginPage;
```

### `ready()`

Waits for the parent page to send the initial context and returns `Promise<context>`. Page initialization should wait for this before reading context-dependent values.

```js
const context = await bridge.ready();
console.log(context.pluginName, context.pageName, context.locale);
```

The context usually contains:

```json
{
  "pluginName": "astrbot_plugin_page_demo",
  "displayName": "Plugin Page Demo",
  "pageName": "bridge-demo",
  "pageTitle": "Bridge Demo",
  "locale": "en-US",
  "i18n": {}
}
```

### `getContext()`

Synchronously reads the latest context. Use it after `ready()` or inside an `onContext()` callback.

```js
function renderHeader() {
  const context = bridge.getContext();
  document.getElementById("title").textContent = context.pageTitle;
}
```

### `getLocale()`

Synchronously reads the current WebUI locale. It returns `zh-CN` when no context exists yet.

```js
document.documentElement.lang = bridge.getLocale();
```

### `getI18n()`

Synchronously reads the full plugin i18n resource object. Prefer `t()` for normal rendering; use this for custom traversal or debugging.

```js
console.log(Object.keys(bridge.getI18n()));
```

### `t(key, fallback)`

Reads text from plugin i18n by dot-separated key. If the current locale is missing, the bridge tries fallbacks; if still missing, it returns `fallback`.

```js
saveButton.textContent = bridge.t("pages.settings.save", "Save");
```

### `onContext(handler)`

Listens for context changes and returns an unsubscribe function. The callback runs when the WebUI locale changes, so pages that need live language switching should rerender here.

```js
function render() {
  document.title = bridge.t("pages.settings.title", "Settings");
}

await bridge.ready();
render();

const off = bridge.onContext(render);

window.addEventListener("beforeunload", () => {
  off();
});
```

### `apiGet(endpoint, params)`

Sends a GET request to the plugin backend and returns `Promise<data>`. `endpoint` is a plugin-local relative path; the Dashboard forwards it to `/api/plug/<plugin_name>/<endpoint>`.

```js
const stats = await bridge.apiGet("stats", { limit: 20 });
```

Backend registration example:

```python
context.register_web_api(
    f"/{PLUGIN_NAME}/stats",
    self.get_stats,
    ["GET"],
    "Get stats",
)
```

### `apiPost(endpoint, body)`

Sends a POST request to the plugin backend. `body` is sent as JSON and the method returns `Promise<data>`.

```js
await bridge.apiPost("settings/save", {
  enabled: true,
  threshold: 0.8,
});
```

### `upload(endpoint, file)`

Uploads one file as `multipart/form-data` with the field name `file`, returning `Promise<data>`.

```js
const input = document.querySelector("input[type=file]");
const file = input.files[0];
const result = await bridge.upload("files/import", file);
```

### `download(endpoint, params, filename)`

Requests a plugin backend file endpoint and triggers a browser download. `params` are sent as query parameters. `filename` is optional; when omitted, the bridge tries to use the response filename header.

```js
await bridge.download("files/export", { format: "json" }, "export.json");
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

`event.parsed` is automatically parsed when the message is a JSON string; otherwise it equals the raw string.

### `unsubscribeSSE(subscriptionId)`

Cancels an SSE subscription.

```js
await bridge.unsubscribeSSE(subscriptionId);
```

Clean up subscriptions when the page unloads:

```js
window.addEventListener("beforeunload", () => {
  bridge.unsubscribeSSE(subscriptionId);
});
```

### endpoint Rules

The `endpoint` used by `apiGet`, `apiPost`, `upload`, `download`, and `subscribeSSE` must be a plugin-local relative path:

- Allowed: `"stats"`, `"settings/save"`, `"files/export"`
- Not allowed: empty string, `"/stats"`, `"../stats"`, `"https://example.com"`, `"stats?x=1"`, `"stats#top"`

Pass query parameters through `params`; do not append them to `endpoint`.
