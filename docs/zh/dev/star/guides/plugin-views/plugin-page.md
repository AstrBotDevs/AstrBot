# 独立插件页面

使用 `target="plugin_page"` 提供不依附聊天消息的设置页或管理面板。用户从 WebUI 插件入口打开，页面通过插件 Web API 读取和保存数据。

![Meme Manager 的独立表情包管理页面](/images/plugin-views/meme-manager.jpg)

[Meme Manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) 将表情包浏览、分类和管理放在独立页面中。安装插件后，从 WebUI 的「扩展功能 → 表情包管理器」打开。页面通过插件 Web API 读写数据，不需要先创建聊天消息。

## 创建视图文件 {#目录结构}

将页面资源放在 `views/<view_name>/` 下。AstrBot 只扫描 `views/<view_name>/index.html`，没有 `index.html` 的目录会被忽略。

示例基于已有插件，`PLUGIN_NAME` 必须与 `metadata.yaml` 中的 `name` 一致。

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

`view_name` 应使用简单目录名，例如 `settings`、`bridge-demo`。不要使用空目录名、`.`、`..`、以 `.` 开头的目录名，或包含 `/`、`\` 的名称。

用户可以在 WebUI 的插件页点击插件卡片进入插件详情页，然后打开插件声明的可视化视图。

未声明 `ViewSpec` 的目录仍可自动发现为独立页面。显式注册时必须设置 `target="plugin_page"`；这个 target 不使用 `event.view_result()`，也不声明 `actions`。

## 注册页面与接口 {#注册页面}

插件后端推荐使用 `astrbot.api.web`，不要把 FastAPI、Starlette 或 Quart 的原始请求对象作为插件公共 API 暴露给自己的业务代码。

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

## 调用接口 {#前端}

`views/bridge-demo/index.html`

```html
<!doctype html>
<html lang="zh-CN">
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

重载插件，打开 `bridge-demo` 页面并点击 **Ping**，应显示包含 `message: "pong"` 的响应。SDK 由宿主自动注入。主题和上下文见[共享 Bridge API](./bridge.md)，路由、请求与响应格式见[后端 Web API](./web-api.md)。
