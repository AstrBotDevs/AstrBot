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
  "displayName": "Plugin Page Demo"
}
```

`endpoint` 必须是插件内相对路径，不能为空，不能包含 `\`、URL scheme、query、hash，也不能包含 `.` 或 `..` 路径片段。

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
