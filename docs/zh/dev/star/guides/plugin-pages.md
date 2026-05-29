# 插件 Pages

AstrBot 支持插件通过 `pages/` 目录暴露 Dashboard 页面。`pages/` 下的每个一级子目录都是一个独立 Page：

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

AstrBot 会扫描 `pages/<page_name>/index.html`；没有 `index.html` 的目录会被忽略。

如果只是让用户填写几个配置项，优先使用 [`_conf_schema.json`](./plugin-config.md)。插件 Pages 更适合复杂表单、Dashboard、日志、文件上传下载、SSE 和自定义交互流程。

一旦注册了 Pages，用户可以在：AstrBot WebUI 插件页中的插件卡片中，点击插件卡片进入插件详细页面，在插件详细页面中可以看到并进入注册的 Pages。

## 最小前端示例

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
  const result = await bridge.apiGet("ping");
  output.textContent = JSON.stringify(result, null, 2);
});
```

这里不需要手动引入 bridge SDK。AstrBot 会在返回的 HTML 里自动插入 `/api/plugin/page/bridge-sdk.js`。

## 注册后端 API

前端调用 `bridge.apiGet("ping")` 时，Dashboard 会转发到：

```text
/api/plug/<plugin_name>/ping
```

因此注册 Web API 时，路由必须带上插件名作为前缀：

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

插件 Page 中可直接使用 `window.AstrBotPluginPage`：

- `ready()`: 等待 bridge 就绪并返回上下文
- `getContext()`: 读取当前上下文
- `getLocale()`: 读取当前 WebUI 语言
- `getI18n()`: 读取当前插件的 i18n 资源
- `t(key, fallback)`: 从插件 i18n 资源中按 key 获取文案，缺失时返回 fallback
- `onContext(handler)`: 监听上下文变化，例如 WebUI 切换语言后重新渲染页面
- `apiGet(endpoint, params)`: 发送 GET 请求
- `apiPost(endpoint, body)`: 发送 POST 请求
- `upload(endpoint, file)`: 以 `multipart/form-data` 上传单个文件
- `download(endpoint, params, filename)`: 下载后端响应
- `subscribeSSE(endpoint, handlers, params)`: 订阅 SSE
- `unsubscribeSSE(subscriptionId)`: 取消 SSE 订阅

当前 `ready()` 上下文类似：

```json
{
  "pluginName": "astrbot_plugin_page_demo",
  "displayName": "Plugin Page Demo",
  "pageName": "bridge-demo",
  "pageTitle": "Bridge Demo",
  "locale": "zh-CN",
  "i18n": {}
}
```

`endpoint` 必须是插件内相对路径，不能为空，不能包含 `\`、URL scheme、query、hash，也不能包含 `.` 或 `..` 路径片段。

## Page 国际化

插件 Page 复用插件 i18n 资源文件。给 `.astrbot-plugin/i18n/<locale>.json` 增加 `pages.<page_name>` 即可：

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

`title` 会用于 WebUI 外壳标题和插件详情页的 Page 组件名称，`description` 会用于插件详情页的 Page 组件描述。

在 Page 内部使用 `t()` 渲染文案，并用 `onContext()` 响应语言切换：

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

切换 WebUI 语言后，Dashboard 会把新的 `locale` 和插件 i18n 资源通过 bridge 发送给 iframe；只要 Page 监听了 `onContext()`，通常不需要刷新页面。

如果你的内联脚本需要同步访问 `window.AstrBotPluginPage`，请把脚本放到外部 module 文件中，或在自己的脚本前显式引入：

```html
<script src="/api/plugin/page/bridge-sdk.js"></script>
```

## 静态资源路径规则

AstrBot 会重写相对资源路径，并自动补上短期 `asset_token`。你只需要正常写相对路径，不要自己拼接 `/api/plugin/page/content/...`。

AstrBot 会重写：

- HTML `src` 和 `href`
- CSS `url(...)`
- JavaScript `import`
- JavaScript `export ... from`
- JavaScript 动态 `import()`

建议把静态资源写成 `./style.css`、`./assets/logo.svg` 这类相对路径。不要手动追加 `asset_token`，也不要依赖 `..` 逃逸 Page 根目录。

如果你构建 SPA，建议使用 hash routing。静态资源服务按真实文件路径解析；history routing 刷新页面时需要对应路径上真的存在文件。

## 安全约束

插件 Pages 运行在受限 iframe 中：

```text
allow-scripts allow-forms allow-downloads
```

Page 不能直接访问 Dashboard cookies、LocalStorage 或同源 DOM，也不能绕过 bridge 复用 Dashboard auth。

AstrBot 还会给资源响应添加安全头，包括：

- `X-Frame-Options: SAMEORIGIN`
- `Content-Security-Policy: frame-ancestors 'self'; object-src 'none'; base-uri 'self'`
- `Cache-Control: no-store`

## 调试建议

- 新增或删除 Page 目录后重载插件
- 修改 `pages/<page_name>/` 下的大多数静态资源后，刷新 Page 即可
- 如果 Page 没出现，检查 `pages/<page_name>/index.html` 是否存在，以及插件是否启用

## 附录：Bridge API 详解

建议在页面脚本开始处保存 bridge 引用：

```js
const bridge = window.AstrBotPluginPage;
```

### `ready()`

等待父页面发送初始上下文，返回 `Promise<context>`。页面初始化时应先等待它，避免过早读取空上下文。

```js
const context = await bridge.ready();
console.log(context.pluginName, context.pageName, context.locale);
```

上下文通常包含：

```json
{
  "pluginName": "astrbot_plugin_page_demo",
  "displayName": "Plugin Page Demo",
  "pageName": "bridge-demo",
  "pageTitle": "Bridge Demo",
  "locale": "zh-CN",
  "i18n": {}
}
```

### `getContext()`

同步读取最近一次上下文。适合在 `ready()` 之后或 `onContext()` 回调中使用。

```js
function renderHeader() {
  const context = bridge.getContext();
  document.getElementById("title").textContent = context.pageTitle;
}
```

### `getLocale()`

同步读取当前 WebUI 语言。没有上下文时默认返回 `zh-CN`。

```js
document.documentElement.lang = bridge.getLocale();
```

### `getI18n()`

同步读取当前插件的完整 i18n 资源对象。一般优先用 `t()`，只有需要自定义遍历或调试时才直接读取。

```js
console.log(Object.keys(bridge.getI18n()));
```

### `t(key, fallback)`

按点分隔 key 从插件 i18n 中取文案。当前语言缺失时会尝试回退，仍缺失则返回 `fallback`。

```js
saveButton.textContent = bridge.t("pages.settings.save", "Save");
```

### `onContext(handler)`

监听上下文变化，返回取消监听函数。WebUI 切换语言时会触发该回调，所以需要响应语言切换的页面应在这里重新渲染。

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

向插件后端发送 GET 请求，返回 `Promise<data>`。`endpoint` 是插件内相对路径，Dashboard 会转发到 `/api/plug/<plugin_name>/<endpoint>`。

```js
const stats = await bridge.apiGet("stats", { limit: 20 });
```

后端注册示例：

```python
context.register_web_api(
    f"/{PLUGIN_NAME}/stats",
    self.get_stats,
    ["GET"],
    "Get stats",
)
```

### `apiPost(endpoint, body)`

向插件后端发送 POST 请求，`body` 会作为 JSON 请求体发送，返回 `Promise<data>`。

```js
await bridge.apiPost("settings/save", {
  enabled: true,
  threshold: 0.8,
});
```

### `upload(endpoint, file)`

以 `multipart/form-data` 上传单个文件，字段名为 `file`，返回 `Promise<data>`。

```js
const input = document.querySelector("input[type=file]");
const file = input.files[0];
const result = await bridge.upload("files/import", file);
```

### `download(endpoint, params, filename)`

请求插件后端文件接口并触发浏览器下载。`params` 会作为 query string，`filename` 可选；不传时会尝试使用响应头里的文件名。

```js
await bridge.download("files/export", { format: "json" }, "export.json");
```

### `subscribeSSE(endpoint, handlers, params)`

订阅插件后端 SSE，返回 `Promise<subscriptionId>`。`handlers` 可包含 `onOpen`、`onMessage`、`onError`。

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

`event.parsed` 会在消息内容是 JSON 字符串时自动解析，否则等于原始字符串。

### `unsubscribeSSE(subscriptionId)`

取消 SSE 订阅。

```js
await bridge.unsubscribeSSE(subscriptionId);
```

页面卸载时建议清理订阅：

```js
window.addEventListener("beforeunload", () => {
  bridge.unsubscribeSSE(subscriptionId);
});
```

### endpoint 规则

`apiGet`、`apiPost`、`upload`、`download`、`subscribeSSE` 的 `endpoint` 必须是插件内相对路径：

- 允许：`"stats"`、`"settings/save"`、`"files/export"`
- 不允许：空字符串、`"/stats"`、`"../stats"`、`"https://example.com"`、`"stats?x=1"`、`"stats#top"`

query 参数请通过 `params` 传递，不要拼进 `endpoint`。
