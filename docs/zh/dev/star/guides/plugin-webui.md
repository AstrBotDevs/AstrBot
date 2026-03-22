# 插件 WebUI

AstrBot 允许插件在 Dashboard 中挂载一个单入口 WebUI 页面。用户在插件管理页点击 `WebUI` 后，AstrBot 会在 iframe 中加载你的静态资源，并自动注入 `window.AstrBotPluginWebUI` bridge，用于和插件后端通信。

如果你的需求只是让用户填写几个配置项，优先使用 [`_conf_schema.json`](./plugin-config.md)。插件 WebUI 更适合以下场景：

- 复杂表单或多步骤向导
- 数据看板、日志面板、实时状态页
- 文件上传、下载、SSE 实时推送
- 需要自定义交互，而不是单纯配置项

## 在 `metadata.yaml` 中声明

先在插件元数据里声明 WebUI：

```yaml
name: astrbot_plugin_webui_demo
author: AstrBot
desc: 插件 WebUI 示例
version: 1.0.0
display_name: Plugin WebUI Demo

webui:
  title: Bridge Capability Lab
  root_dir: webui
  entry_file: index.html
```

字段说明：

- `webui.title`: WebUI 入口展示名。默认值是 `WebUI`
- `root_dir`: 静态资源根目录。默认值是 `webui`
- `entry_file`: 入口文件。默认值是 `index.html`

`webui.title` 是独立的 WebUI 字段，不要复用插件顶层的 `display_name`。

> [!TIP]
> 如果入口文件不存在，AstrBot 不会在插件列表里暴露这个 WebUI 入口。

## 推荐目录结构

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

AstrBot 当前只注册一个 WebUI 入口，但这个入口内部可以继续做成单页应用。

## 最小前端示例

`index.html`

```html
<!doctype html>
<html lang="zh-CN">
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

这里不需要手动引入 bridge SDK。AstrBot 会在返回的 HTML 里自动插入 `/api/plugin/webui/bridge-sdk.js`。

## 注册后端接口

插件前端调用 `bridge.apiGet("ping")` 时，Dashboard 会把它转发到：

```text
/api/plug/<plugin_name>/ping
```

因此你注册的 Web API 路由必须带上插件名作为前缀。这里的 `plugin_name` 指的是 `metadata.yaml` 里的 `name`，不是目录名。

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

对应关系如下：

- 前端调用：`bridge.apiGet("ping")`
- 实际请求：`/api/plug/astrbot_plugin_webui_demo/ping`
- 后端注册：`"/astrbot_plugin_webui_demo/ping"`

## Bridge API

插件页面里可直接使用 `window.AstrBotPluginWebUI`：

- `ready()`: 等待 bridge 初始化完成，并返回上下文
- `getContext()`: 读取当前上下文
- `apiGet(endpoint, params)`: 发起 GET 请求
- `apiPost(endpoint, body)`: 发起 POST 请求
- `upload(endpoint, file)`: 上传文件
- `download(endpoint, params, filename)`: 下载文件
- `subscribeSSE(endpoint, handlers, params)`: 订阅 SSE
- `unsubscribeSSE(subscriptionId)`: 取消 SSE 订阅

`ready()` 返回的上下文结构当前包含：

```json
{
  "pluginName": "astrbot_plugin_webui_demo",
  "displayName": "Plugin WebUI Demo"
}
```

`endpoint` 必须是插件内部路径，要求：

- 不能为空
- 不能包含 `\`
- 不能包含协议头，例如 `https://`
- 不能包含查询串和 hash
- 不能包含 `.` 或 `..` 路径段

也就是说，应该写成 `ping`、`settings/save` 这种形式，不要写完整 URL。

### 常用请求形态

`apiPost(endpoint, body)` 会把 `body` 作为 JSON 请求体转发，后端通常这样读取：

```python
from quart import jsonify, request


async def webui_echo(self):
    payload = await request.get_json()
    return jsonify({"received": payload})
```

`upload(endpoint, file)` 会以 `multipart/form-data` 发起请求，文件字段名固定为 `file`，每次调用只上传一个文件：

```python
from quart import jsonify, request


async def webui_upload(self):
    files = await request.files
    uploaded = files["file"]
    return jsonify({"filename": uploaded.filename})
```

`download(endpoint, params, filename)` 会发起 GET 请求，`params` 会进入 query string。后端只需要返回文件响应，例如 `send_file(...)`。第三个参数 `filename` 用于覆盖浏览器保存时显示的文件名。

`subscribeSSE(endpoint, handlers, params)` 同样使用 GET 请求，`params` 会进入 query string。后端需要返回 `text/event-stream`：

```python
from quart import make_response


async def webui_events(self):
    async def stream():
        yield "data: hello\n\n"

    response = await make_response(
        stream(),
        {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    response.timeout = None
    return response
```

## 资源路径规则

AstrBot 会重写 WebUI 中的相对资源路径，并自动补上短期 `asset_token`。你只需要正常写相对路径，不要自己拼接 `/api/plugin/webui/content/...`。

会被重写的内容包括：

- HTML 中的 `src`、`href`
- CSS 中的 `url(...)`
- JavaScript 中的 `import`
- JavaScript 中的 `export ... from`
- JavaScript 中的动态 `import()`

建议：

- 静态资源统一使用相对路径，例如 `./style.css`、`./assets/logo.svg`
- 不要手动拼接 `asset_token`
- 不要依赖 `..` 逃逸 WebUI 根目录，AstrBot 会拦截这类路径

> [!TIP]
> 如果你要做 SPA，建议优先使用 hash 路由。当前静态资源服务按真实文件路径解析；如果你用 history 路由，刷新页面时需要自己保证对应路径上确实有文件可读。

## 安全限制

插件 WebUI 运行在受限 iframe 中，当前 sandbox 策略是：

```text
allow-scripts allow-forms allow-downloads
```

这意味着：

- 可以执行脚本
- 可以提交表单
- 可以触发下载
- 不能直接访问 Dashboard 的 Cookie、LocalStorage 和同源 DOM
- 不能绕过 bridge 直接复用管理面板登录态

同时，AstrBot 会为资源响应附加安全头，例如：

- `X-Frame-Options: SAMEORIGIN`
- `Content-Security-Policy: frame-ancestors 'self'; object-src 'none'; base-uri 'self'`
- `Cache-Control: no-store`

## 调试建议

- 改 `metadata.yaml` 后，重新加载插件
- 改 `webui/` 下的静态资源后，直接刷新 WebUI 页面即可验证大多数改动
- 如果页面按钮没有出现，先检查：
  - `metadata.yaml` 中是否声明了 `webui`
  - `name`、`root_dir`、`entry_file` 是否写对
  - 入口文件是否真实存在
  - 插件当前是否处于启用状态
