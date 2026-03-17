# Plugin WebUI

AstrBot allows a plugin to mount a single-entry WebUI page inside the Dashboard. When the user clicks `WebUI` on the plugin page, AstrBot loads your static assets inside an iframe and injects the `window.AstrBotPluginWebUI` bridge for communication with the plugin backend.

If you only need a few editable settings, prefer [`_conf_schema.json`](./plugin-config.md). Plugin WebUI is more suitable for:

- Complex forms or multi-step flows
- Dashboards, logs, and live status pages
- File upload, download, and SSE push
- Custom interactions that are more than plain config fields

## Declare It In `metadata.yaml`

Add a `webui` section to your plugin metadata:

```yaml
name: astrbot_plugin_webui_demo
author: AstrBot
desc: Plugin WebUI demo
version: 1.0.0

webui:
  display_name: Demo Panel
  root_dir: webui
  entry_file: index.html
```

Field notes:

- `display_name`: Display name shown in the Dashboard. Default: `WebUI`
- `root_dir`: Static asset root directory. Default: `webui`
- `entry_file`: Entry file name. Default: `index.html`

> [!TIP]
> If the entry file does not exist, AstrBot will not expose the WebUI entry in the plugin list.

## Recommended Layout

```text
astrbot_plugin_webui_demo/
├─ metadata.yaml
├─ main.py
└─ webui/
   ├─ index.html
   ├─ app.js
   ├─ style.css
   └─ assets/
      └─ logo.svg
```

AstrBot currently exposes one WebUI entry per plugin, but that entry can still host a SPA.

## Minimal Frontend Example

`index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Plugin WebUI Demo</title>
    <link rel="stylesheet" href="./style.css" />
  </head>
  <body>
    <button id="ping">Ping</button>
    <pre id="output"></pre>
    <script type="module" src="./app.js"></script>
  </body>
</html>
```

`app.js`

```js
const bridge = window.AstrBotPluginWebUI;
const output = document.getElementById("output");

const context = await bridge.ready();
output.textContent = JSON.stringify(context, null, 2);

document.getElementById("ping").addEventListener("click", async () => {
  const result = await bridge.apiGet("ping");
  output.textContent = JSON.stringify(result, null, 2);
});
```

`style.css`

```css
body {
  font-family: sans-serif;
  background: url("./assets/logo.svg") no-repeat top right;
}
```

You do not need to import the bridge SDK manually. AstrBot automatically injects `/api/plugin/webui/bridge-sdk.js` into the returned HTML.

## Register Backend APIs

When the frontend calls `bridge.apiGet("ping")`, the Dashboard forwards it to:

```text
/api/plug/<plugin_name>/ping
```

Because of that, the registered Web API route must include the plugin name as a prefix. Here `plugin_name` means the `name` field in `metadata.yaml`, not the folder name.

```python
from quart import jsonify
from astrbot.api.star import Context, Star

PLUGIN_NAME = "astrbot_plugin_webui_demo"


class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        context.register_web_api(
            f"/{PLUGIN_NAME}/ping",
            self.webui_ping,
            ["GET"],
            "WebUI ping",
        )

    async def webui_ping(self):
        return jsonify({"message": "pong"})
```

Mapping summary:

- Frontend call: `bridge.apiGet("ping")`
- Actual request: `/api/plug/astrbot_plugin_webui_demo/ping`
- Backend route: `"/astrbot_plugin_webui_demo/ping"`

## Bridge API

Inside the plugin page you can use `window.AstrBotPluginWebUI` directly:

- `ready()`: Wait until the bridge is ready and return the context
- `getContext()`: Read the current context
- `apiGet(endpoint, params)`: Send a GET request
- `apiPost(endpoint, body)`: Send a POST request
- `upload(endpoint, file)`: Upload a file
- `download(endpoint, params, filename)`: Download a file
- `subscribeSSE(endpoint, handlers, params)`: Subscribe to SSE
- `unsubscribeSSE(subscriptionId)`: Cancel an SSE subscription

The current `ready()` context looks like this:

```json
{
  "pluginName": "astrbot_plugin_webui_demo",
  "displayName": "Plugin WebUI Demo"
}
```

`endpoint` must be a plugin-local path. It:

- must not be empty
- must not contain `\`
- must not contain a scheme such as `https://`
- must not contain query strings or hash fragments
- must not contain `.` or `..` path segments

So use values like `ping` or `settings/save`, not a full URL.

## Asset Path Rules

AstrBot rewrites relative asset URLs in the WebUI and automatically appends a short-lived `asset_token`. Write normal relative paths and do not hardcode `/api/plugin/webui/content/...` yourself.

AstrBot rewrites:

- HTML `src` and `href`
- CSS `url(...)`
- JavaScript `import`
- JavaScript `export ... from`
- JavaScript dynamic `import()`

Recommendations:

- Keep static assets on relative paths such as `./style.css` and `./assets/logo.svg`
- Do not manually append `asset_token`
- Do not rely on `..` to escape the WebUI root directory, AstrBot blocks that

> [!TIP]
> If you build a SPA, prefer hash routing. The static asset server resolves real file paths; with history routing, refreshing a page requires an actual file to exist at that path.

## Security Constraints

The plugin WebUI runs inside a restricted iframe. The current sandbox policy is:

```text
allow-scripts allow-forms allow-downloads
```

That means:

- scripts can run
- forms can be submitted
- downloads can be triggered
- the page cannot directly access Dashboard cookies, LocalStorage, or same-origin DOM
- the page cannot bypass the bridge and reuse Dashboard auth directly

AstrBot also adds security headers to asset responses, including:

- `X-Frame-Options: SAMEORIGIN`
- `Content-Security-Policy: frame-ancestors 'self'; object-src 'none'; base-uri 'self'`
- `Cache-Control: no-store`

## Debugging Tips

- Reload the plugin after changing `metadata.yaml`
- For most edits under `webui/`, refreshing the WebUI page is enough
- If the `WebUI` button does not appear, check:
  - whether `webui` exists in `metadata.yaml`
  - whether `name`, `root_dir`, and `entry_file` are correct
  - whether the entry file really exists
  - whether the plugin is currently enabled
