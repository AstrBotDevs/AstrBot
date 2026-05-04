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
  "displayName": "Plugin Page Demo"
}
```

`endpoint` must be a plugin-local path. It must not be empty, contain `\`, contain a URL scheme, contain query strings or fragments, or contain `.` / `..` path segments.

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
