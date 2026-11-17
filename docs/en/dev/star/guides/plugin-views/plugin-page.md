# Standalone plugin page

Use `target="plugin_page"` for settings or dashboards that do not belong to a chat message. Users open the page from the WebUI plugin entry. The page reads and saves data through plugin Web APIs.

![Meme Manager's standalone meme management page (Chinese UI)](/images/plugin-views/meme-manager.jpg)

[Meme Manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) provides a standalone page for browsing, categorizing, and managing memes. Install the plugin, then open **Extensions → 表情包管理器 (Meme Manager)** in the WebUI. The page reads and writes data through plugin Web APIs without creating a chat message.

## Create the view files {#directory-layout}

Place the page assets under `views/<view_name>/`. AstrBot discovers `views/<view_name>/index.html`; directories without `index.html` are ignored.

Start with an existing plugin. `PLUGIN_NAME` must match `name` in its `metadata.yaml`.

```text
astrbot_plugin_view_demo/
├─ metadata.yaml
├─ main.py
└─ views/
   ├─ bridge-demo/
   │  ├─ index.html
   │  └─ app.js
   └─ settings/
      └─ index.html
```

Use simple directory names for `view_name`, such as `settings` or `bridge-demo`. Do not use an empty name, `.`, `..`, a name starting with `.`, or a name containing `/` or `\`.

Users open views from the plugin detail page in the WebUI.

Undeclared directories can still be discovered as standalone pages. Explicit declarations must set `target="plugin_page"`; this target does not use `event.view_result()` or declare `actions`.

## Register the page and endpoint {#register-the-page}

Plugin backend code should use `astrbot.api.web`. Avoid exposing raw FastAPI, Starlette, or Quart request objects as the public API for your plugin business logic.

```python
from pathlib import Path

from astrbot.api import chatui
from astrbot.api.star import Context, Star
from astrbot.api.web import json_response, request

PLUGIN_NAME = "astrbot_plugin_view_demo"


class MyPlugin(Star):
    chatui_views = [
        chatui.ViewSpec(
            name="bridge-demo",
            entry=Path("views/bridge-demo/index.html"),
            target="plugin_page",
        ),
    ]

    def __init__(self, context: Context):
        super().__init__(context)
        context.register_web_api(
            f"/{PLUGIN_NAME}/ping",
            self.page_ping,
            ["GET"],
            "View ping",
        )

    async def page_ping(self):
        """Return a response for the view's ping request.

        Returns:
            JSON containing the message, limit, and authenticated username.
        """
        limit = request.query.get("limit", 20, type=int)
        return json_response(
            {
                "message": "pong",
                "limit": limit,
                "username": request.username,
            }
        )
```

## Call the endpoint {#frontend}

`views/bridge-demo/index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Plugin View Demo</title>
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

Reload the plugin, open `bridge-demo`, and click **Ping**. The response should contain `message: "pong"`. The host injects the SDK automatically. See the [shared Bridge API](./bridge.md) for themes and context, and [backend Web APIs](./web-api.md) for routes, requests, and responses.
