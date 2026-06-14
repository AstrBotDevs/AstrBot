# 插件 Pages

插件 Pages 允许插件在 AstrBot WebUI 中提供自己的页面。页面文件放在插件目录的 `pages/` 下，由 Dashboard 以受限 iframe 的方式加载；页面里的脚本通过 `window.AstrBotPluginPage` bridge 和 Dashboard 通信，再由 Dashboard 转发到插件注册的后端 Web API。

如果只是让用户填写少量配置项，优先使用 [`_conf_schema.json`](./plugin-config.md)。Pages 更适合复杂表单、运行状态面板、日志查看、文件上传下载、SSE 实时流、图表和其他需要自定义交互的场景。

## 目录结构

`pages/` 下的每个一级子目录是一个独立 Page。AstrBot 只扫描 `pages/<page_name>/index.html`，没有 `index.html` 的目录会被忽略。

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

`page_name` 应使用简单目录名，例如 `settings`、`bridge-demo`。不要使用空目录名、`.`、`..`、以 `.` 开头的目录名，或包含 `/`、`\` 的名称。

用户可以在 WebUI 的插件页点击插件卡片进入插件详情页，然后打开插件声明的 Pages。

## 开发流程

1. 在插件目录下创建 `pages/<page_name>/index.html`。
2. 在 Page 中通过 `window.AstrBotPluginPage` bridge 调用后端能力。
3. 在 `main.py` 中使用 `context.register_web_api()` 注册插件后端 API。
4. 后端 handler 使用 `astrbot.api.web` 读取请求并返回响应。
5. 新增或删除 Page 目录后重载插件；修改静态资源通常刷新 Page 即可。

## 最小完整示例

### 后端

插件后端推荐使用 `astrbot.api.web`，不要把 FastAPI、Starlette 或 Quart 的原始请求对象作为插件公共 API 暴露给自己的业务代码。

```python
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request

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
        context.register_web_api(
            f"/{PLUGIN_NAME}/settings/save",
            self.save_settings,
            ["POST"],
            "Save Page settings",
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

### 前端

`pages/bridge-demo/index.html`

```html
<!doctype html>
<html lang="zh-CN">
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
  const result = await bridge.apiGet("ping", { limit: 20 });
  output.textContent = JSON.stringify(result, null, 2);
});
```

不需要手动引入 bridge SDK。AstrBot 返回 HTML 时会自动插入 `/api/plugin/page/bridge-sdk.js`。如果内联脚本必须同步访问 `window.AstrBotPluginPage`，请把脚本改成外部 module 文件，或在自己的脚本前显式引入：

```html
<script src="/api/plugin/page/bridge-sdk.js"></script>
```

## 后端 Web API

### 路由注册

使用 `context.register_web_api(route, view_handler, methods, desc)` 注册插件 API。

```python
context.register_web_api(
    f"/{PLUGIN_NAME}/items/<item_id>",
    self.get_item,
    ["GET"],
    "Get item",
)
```

路由需要包含插件名作为前缀。Page 端的 bridge endpoint 不需要包含插件名：

```js
await bridge.apiGet("items/123");
```

Dashboard 会把它转发到：

```text
/api/v1/plugins/extensions/<plugin_name>/items/123
```

注册路由 `/<plugin_name>/items/<item_id>` 会匹配该请求，`item_id` 作为 handler 的关键字参数传入：

```python
async def get_item(self, item_id: str):
    return json_response({"item_id": item_id})
```

支持的动态片段：

- `<name>`：匹配单个路径片段。
- `<path:name>`：匹配后续多级路径。

### 请求对象

推荐导入：

```python
from astrbot.api.web import request
```

`request` 是当前请求的上下文代理，只能在插件 Web API handler 执行期间访问。常用字段和方法：

| API | 说明 |
| --- | --- |
| `request.method` | HTTP 方法，例如 `GET`、`POST` |
| `request.path` | 当前 Dashboard API 路径 |
| `request.plugin_name` | 从扩展路径解析出的插件名 |
| `request.username` | 当前 Dashboard 用户名，可能为 `None` |
| `request.headers` | 请求头 |
| `request.cookies` | 请求 cookies |
| `request.content_type` | 请求 Content-Type |
| `request.client_host` | 客户端地址 |
| `request.path_params` | 路由动态参数字典 |
| `request.query` | query 参数，支持 `get()` 和 `getlist()` |
| `await request.body()` | 原始请求体 bytes |
| `await request.json(default={})` | JSON 请求体，解析失败返回 default |
| `await request.form()` | 表单字段，不含上传文件 |
| `await request.files()` | 上传文件 |

query 参数使用示例：

```python
limit = request.query.get("limit", 20, type=int)
tags = request.query.getlist("tag")
```

JSON 请求体使用示例：

```python
payload = await request.json(default={})
enabled = bool(payload.get("enabled"))
```

文件上传使用示例：

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

`request.form()` 和 `request.files()` 会缓存解析结果，可以在同一个 handler 中各调用一次。

### 响应对象

推荐从 `astrbot.api.web` 导入响应 helper：

```python
from astrbot.api.web import (
    error_response,
    file_response,
    json_response,
    stream_response,
)
```

JSON 响应：

```python
return json_response({"saved": True})
```

错误响应：

```python
return error_response("invalid threshold", status_code=400)
```

文件下载响应：

```python
return file_response(
    export_path,
    filename="export.json",
    content_type="application/json",
)
```

SSE 响应：

```python
import json

from astrbot.api.web import stream_response


async def stream_events(self):
    async def events():
        yield f"data: {json.dumps({'state': 'started'})}\n\n"
        yield f"data: {json.dumps({'state': 'done'})}\n\n"

    return stream_response(events())
```

直接返回 `dict`、`list`、`(body, status_code)` 或底层 Response 对象仍然可用；文档和新插件推荐优先使用 `astrbot.api.web` helper，让插件代码和 Dashboard 内部框架解耦。

### Quart 兼容

为了兼容旧插件，通过 `context.register_web_api()` 注册的 handler 仍会进入 Quart 兼容请求上下文。旧代码可以继续使用：

```python
from quart import jsonify, request
```

新插件和新文档推荐使用：

```python
from astrbot.api.web import json_response, request
```

不要在同一个 handler 中混用两个 `request` 代理，迁移时按 handler 逐步替换即可。

## Bridge API

Page iframe 不能直接访问 Dashboard cookies、LocalStorage 或父页面 DOM。页面脚本必须通过 `window.AstrBotPluginPage` bridge 调用后端和读取上下文。

```js
const bridge = window.AstrBotPluginPage;
```

### 上下文

`ready()` 等待父页面发送初始上下文，返回 `Promise<context>`。页面初始化时应先等待它。

```js
const context = await bridge.ready();
```

上下文通常包含：

```json
{
  "pluginName": "astrbot_plugin_page_demo",
  "displayName": "Plugin Page Demo",
  "pageName": "bridge-demo",
  "pageTitle": "Bridge Demo",
  "locale": "zh-CN",
  "i18n": {},
  "isDark": false
}
```

上下文相关 API：

| API | 返回值 | 说明 |
| --- | --- | --- |
| `ready()` | `Promise<context>` | 等待 bridge 就绪并返回初始上下文 |
| `getContext()` | `context \| null` | 同步读取最近一次上下文 |
| `getLocale()` | `string` | 当前 WebUI 语言，默认 `zh-CN` |
| `getI18n()` | `object` | 当前插件 i18n 资源 |
| `t(key, fallback)` | `string` | 按点分隔 key 读取翻译，缺失时返回 fallback |
| `onContext(handler)` | `() => void` | 监听上下文变化，返回取消监听函数 |

监听语言或主题变化：

```js
function render() {
  document.title = bridge.t("pages.bridge-demo.title", "Bridge Demo");
  document.getElementById("locale").textContent = bridge.getLocale();
}

await bridge.ready();
render();

const off = bridge.onContext(render);
window.addEventListener("beforeunload", off);
```

### 请求和返回值规则

`apiGet`、`apiPost`、`upload`、`download`、`subscribeSSE` 的 `endpoint` 都是插件内相对路径，例如 `stats`、`settings/save`、`files/export`。推荐不要以 `/` 开头；当前 bridge 会为了兼容旧写法去掉开头的 `/`。

`endpoint` 不能是空字符串，不能包含 `\`、URL scheme、query、hash，也不能包含空路径片段、`.` 或 `..`。

不要把 query string 拼进 endpoint：

```js
await bridge.apiGet("stats", { limit: 20 });
```

bridge 对 JSON 类请求的返回值有一个兼容规则：

- 如果后端返回 `{ "status": "ok", "data": value }`，Promise resolve 为 `value`。
- 如果后端返回普通 JSON，例如 `{ "message": "pong" }`，Promise resolve 为完整 JSON。
- 如果后端返回 `{ "status": "error", "message": "..." }`，或 HTTP 请求失败，Promise reject 为 `Error`。

因此 Page-only API 推荐直接返回业务 JSON：

```python
return json_response({"message": "pong"})
```

需要表达错误时使用：

```python
return error_response("missing file", status_code=400)
```

Page 端统一捕获错误：

```js
try {
  await bridge.apiPost("settings/save", { enabled: true });
} catch (error) {
  console.error(error.message);
}
```

### `apiGet(endpoint, params)`

发送 GET 请求。`params` 会作为 query 参数传递。

```js
const stats = await bridge.apiGet("stats", { limit: 20, tag: "today" });
```

后端读取：

```python
async def stats(self):
    limit = request.query.get("limit", 20, type=int)
    tag = request.query.get("tag")
    return json_response({"limit": limit, "tag": tag})
```

### `apiPost(endpoint, body)`

发送 POST JSON 请求。

```js
const result = await bridge.apiPost("settings/save", {
  enabled: true,
  threshold: 0.8,
});
```

后端读取：

```python
async def save_settings(self):
    payload = await request.json(default={})
    return json_response({"saved": True, "enabled": payload.get("enabled")})
```

### `upload(endpoint, file)`

以 `multipart/form-data` 上传单个文件，字段名固定为 `file`。

```js
const input = document.querySelector("input[type=file]");
const file = input.files[0];
const result = await bridge.upload("files/import", file);
```

后端读取：

```python
from astrbot.api.web import PluginUploadFile, error_response, json_response, request


async def import_file(self):
    files = await request.files()
    upload: PluginUploadFile | None = files.get("file")
    if not isinstance(upload, PluginUploadFile):
        return error_response("missing file", status_code=400)
    return json_response({"filename": upload.filename})
```

如果还需要普通字段，请单独使用 `apiPost` 传配置，或在后端根据 query 参数区分导入行为。当前 bridge 的 `upload()` 只发送一个文件。

### `download(endpoint, params, filename)`

请求插件后端文件接口并触发浏览器下载。`params` 会作为 query 参数发送；`filename` 可选，缺省时 bridge 会尝试从响应头读取文件名。

```js
await bridge.download("files/export", { format: "json" }, "export.json");
```

后端返回文件：

```python
async def export_file(self):
    fmt = request.query.get("format", "json")
    return file_response(
        export_path,
        filename=f"export.{fmt}",
        content_type="application/json",
    )
```

`download()` resolve 为：

```json
{ "filename": "export.json" }
```

### `subscribeSSE(endpoint, handlers, params)`

订阅插件后端 SSE，返回 `Promise<subscriptionId>`。`handlers` 可以包含 `onOpen`、`onMessage`、`onError`。

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

`event.raw` 是原始字符串；如果内容是 JSON 字符串，`event.parsed` 会自动解析，否则等于原始字符串。`event.eventType` 对应 SSE 的 `event:` 字段，未设置时为 `message`。

后端必须返回 `text/event-stream`：

```python
async def events(self):
    async def stream():
        yield 'data: {"message": "ready"}\n\n'

    return stream_response(stream())
```

取消订阅：

```js
await bridge.unsubscribeSSE(subscriptionId);
```

页面卸载时建议清理：

```js
window.addEventListener("beforeunload", () => {
  bridge.unsubscribeSSE(subscriptionId);
});
```

## Page 国际化

插件 Pages 复用插件 i18n 资源文件。给 `.astrbot-plugin/i18n/<locale>.json` 增加 `pages.<page_name>`：

```json
{
  "pages": {
    "bridge-demo": {
      "title": "Bridge 演示页",
      "description": "演示插件页面如何读取 WebUI 语言和翻译资源。",
      "heading": "插件页面",
      "refresh": "重新渲染"
    }
  }
}
```

`title` 用于 WebUI 外壳标题和插件详情页的 Page 组件名称；`description` 用于插件详情页的 Page 组件描述。Page 内部使用 `bridge.t()` 渲染文案，并通过 `onContext()` 响应语言切换。

```js
function render() {
  document.title = bridge.t("pages.bridge-demo.title", "Bridge Demo");
  document.getElementById("heading").textContent = bridge.t(
    "pages.bridge-demo.heading",
    "Plugin Page",
  );
}

await bridge.ready();
render();
bridge.onContext(render);
```

## 亮暗主题

AstrBot 会把当前主题同步给插件 Page。bridge SDK 会维护 `<html>` 的 `data-theme` 属性：

- 亮色模式：`<html data-theme="light">`
- 暗色模式：`<html data-theme="dark">`

选择“跟随系统”时，Page 收到的值仍然是 `light` 或 `dark`。

推荐使用 CSS 变量：

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

服务端返回 HTML 时会预先注入 `data-theme`，减少初始闪烁。需要在 JavaScript 中响应主题变化时，读取 `bridge.getContext()?.isDark` 并监听 `onContext()`。

## 静态资源路径

正常使用相对路径即可：

```html
<link rel="stylesheet" href="./style.css" />
<script type="module" src="./app.js"></script>
<img src="./assets/logo.svg" alt="" />
```

AstrBot 会重写相对资源路径并追加短期 `asset_token`。不要手动拼接 `/api/plugin/page/content/...`，不要自行追加 `asset_token`，也不要依赖 `..` 逃逸 Page 根目录。

会被重写的资源引用包括：

- HTML `src` 和 `href`
- CSS `url(...)`
- JavaScript `import`
- JavaScript `export ... from`
- JavaScript 动态 `import()`

如果构建 SPA，建议使用 hash routing。静态资源服务按真实文件路径解析；history routing 刷新页面时需要对应路径上真的存在文件。

## 安全约束

插件 Pages 运行在受限 iframe 中：

```text
allow-scripts allow-forms allow-downloads
```

Page 不能直接访问 Dashboard cookies、LocalStorage 或父页面 DOM，也不能绕过 bridge 复用 Dashboard auth。所有需要 Dashboard 身份的操作都应该走 bridge。

资源响应会带上安全头，包括：

- `X-Frame-Options: SAMEORIGIN`
- `Content-Security-Policy: frame-ancestors 'self'; object-src 'none'; base-uri 'self'`
- `Cache-Control: no-store`
- `X-Content-Type-Options: nosniff`

后端 handler 仍然要验证输入。不要信任 Page 传来的路径、文件名、格式或数值范围；文件落盘时应使用安全目录，并对文件名做白名单或重新命名。

## 调试建议

- Page 没出现：检查 `pages/<page_name>/index.html` 是否存在、插件是否启用、插件详情页是否已刷新。
- bridge 不存在：确认脚本在 bridge SDK 注入之后运行；推荐使用外部 `type="module"` 脚本。
- API 未匹配：确认注册路由包含插件名前缀，例如 `/{PLUGIN_NAME}/stats`，而 Page 端 endpoint 是 `stats`。
- query 或 JSON 为空：GET 参数放到 `apiGet(endpoint, params)`，POST JSON 放到 `apiPost(endpoint, body)`。
- 文件上传为空：`upload()` 字段名固定为 `file`，后端用 `(await request.files()).get("file")` 读取。
- SSE 没消息：确认后端响应是 `text/event-stream`，每条消息以空行结尾，例如 `data: ...\n\n`。
- SSE 401：不要在 Page 中直接 `new EventSource("/api/v1/...")`，原生 `EventSource` 不能携带 `Authorization` header；请通过 `bridge.subscribeSSE()` 调用。
