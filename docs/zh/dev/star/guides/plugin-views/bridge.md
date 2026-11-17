# 共享 Bridge API

所有视图使用 `window.AstrBotPluginView`。宿主自动注入 SDK；前端脚本使用外部 `type="module"` 文件，并在调用接口前等待 `bridge.ready()`。

## 可用能力 {#capabilities}

| 接口 | 独立页面 | 消息组件 |
| --- | --- | --- |
| `ready`、`getContext`、`onContext` | 支持 | 支持 |
| 主题 CSS tokens、国际化 | 支持 | 支持 |
| `view.subscribe`、`view.action` | — | 支持 |
| `apiGet`、`apiPost`、上传下载、SSE | 支持 | — |

未支持的操作返回 `UNSUPPORTED_CAPABILITY`。`AstrBotPluginPage` 是兼容别名，新代码使用 `AstrBotPluginView`。

## TypeScript 类型定义 {#typescript}

下载 [astrbot-plugin-view.d.ts](/types/astrbot-plugin-view.d.ts)，放入插件前端项目的 `src/`（或 `tsconfig.json` 的 `include` 范围）即可获得 `window.AstrBotPluginView` 类型提示。此文件只提供类型；运行时 SDK 仍由宿主注入，不需要导入 JavaScript 包。

下面是完整的公开方法签名；相关数据结构在后续章节定义。所有方法都存在于 bridge 对象上，但能否调用取决于[宿主能力](#capabilities)。`__setInitialContext` 是宿主内部接口，不属于插件 API。

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#bridge{ts}

<details>
<summary>基础类型</summary>

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#base{ts}

</details>

## 初始化 {#bridge-api}

视图 iframe 不能直接访问 Dashboard cookies、LocalStorage 或父页面 DOM。页面脚本必须通过 `window.AstrBotPluginView` bridge 调用后端和读取上下文。

```js
const bridge = window.AstrBotPluginView;
```

TypeScript 项目可以为快照数据和业务响应指定类型：

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

## 上下文

`ready()` 等待父页面发送初始上下文，返回 `Promise<BridgeContext>`。页面初始化时应先等待它。

```js
const context = await bridge.ready();
```

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#context{ts}

`target` 与 `view` 一起区分宿主：

| 宿主 | `target` | `view` |
| --- | --- | --- |
| 独立页面 | `plugin_page` | 无 |
| 消息组件 | `chat_message` | `ViewSnapshot` |

`view` 只有 `id`、`revision`、`data`，不包含 Python `UIInteraction.view` 的 `name`、`version`。视图注册名称读取 `context.pageName`。`i18n` 按 locale 分组，例如 `{ "zh-CN": { "views": { "counter": { "title": "计数器" } } } }`。`themeColors` 的额外键由宿主主题提供；页面配色优先使用下文列出的 CSS tokens。

上下文相关 API：

| API | 返回值 | 说明 |
| --- | --- | --- |
| `ready()` | `Promise<BridgeContext>` | 等待 bridge 就绪并返回当前上下文 |
| `getContext()` | `BridgeContext \| null` | 同步读取最近一次上下文 |
| `getLocale()` | `string` | 当前 WebUI 语言，默认 `zh-CN` |
| `getI18n()` | `I18nResources` | 当前插件 i18n 资源 |
| `t(key, fallback)` | `string` | 按点分隔 key 读取翻译，缺失时返回 fallback |
| `onContext(handler)` | `() => void` | 监听上下文变化，返回取消监听函数 |

`onContext()` 在已有上下文时会立即调用 handler，之后每次上下文更新都会通知；取消监听函数只移除本次订阅。`getContext()` 在就绪前返回 `null`。`t()` 按当前 locale → `zh-CN` → `en-US` 查找；全部缺失时返回 `fallback`，未提供则返回空字符串。

监听语言或主题变化：

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

## 插件 Web API

### 请求和返回值规则

`apiGet`、`apiPost`、`upload`、`download`、`subscribeSSE` 的 `endpoint` 都是插件内相对路径，例如 `stats`、`settings/save`、`files/export`。推荐不要以 `/` 开头；当前 bridge 会为了兼容旧写法去掉开头的 `/`。

`endpoint` 不能是空字符串，不能包含 `\`、URL scheme、query、hash，也不能包含空路径片段、`.` 或 `..`。

不要把 query string 拼进 endpoint：

```js
await bridge.apiGet("stats", { limit: 20 });
```

bridge 对 JSON 类请求的返回值有一个兼容规则：

- 当非错误响应包含非 `null` 的 `data` 字段时，Promise resolve 为该字段，不要求 `status` 为 `"ok"`。例如 `{ "data": 0 }` 返回 `0`。
- 响应没有 `data` 或 `data` 为 `null` 时，返回完整响应。例如 `{ "message": "pong" }` 原样返回，`{ "data": null }` 也原样返回。
- 如果后端返回 `{ "status": "error", "message": "..." }`，或 HTTP 请求失败，Promise reject 为 `Error`。

因此视图专用 API 推荐直接返回业务 JSON：

```python
return json_response({"message": "pong"})
```

需要表达错误时使用：

```python
return error_response("missing file", status_code=400)
```

视图端统一捕获错误：

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

```ts
apiPost<TResult = unknown>(endpoint: string, body?: JsonValue): Promise<TResult>
```

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

```ts
upload<TResult = unknown>(endpoint: string, file: UploadFile): Promise<TResult>
```

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

```ts
download(endpoint: string, params?: QueryParams, filename?: string): Promise<DownloadResult>
```

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

```ts
subscribeSSE<TData = unknown>(
  endpoint: string,
  handlers?: SSEHandlers<TData>,
  params?: SSEParams,
): Promise<string>
```

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#sse{ts}

订阅插件后端 SSE，返回 `Promise<subscriptionId>`。`handlers` 可以包含 `onOpen`、`onMessage`、`onClose`、`onError`。

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

`event.raw` 是原始字符串；如果内容是 JSON 字符串，`event.parsed` 会自动解析，否则等于原始字符串。`event.eventType` 对应 SSE 的 `event:` 字段，未设置时为 `message`。

流结束时调用 `onClose`，读取流失败时调用 `onError`。主动调用 `unsubscribeSSE` 不会触发这两个回调。桥接层不会自动重连；需要时请自行重新订阅。初始订阅失败时，返回的 Promise 会被拒绝。

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

## 消息视图交互

```ts
view.subscribe(handler: (snapshot: ViewSnapshot<TViewData>) => void): Unsubscribe
view.action(actionId: string, data?: JsonValue): Promise<void>
```

`view.subscribe()` 必须在 `ready()` 后调用。它立即传入当前快照的副本，后续收到相同或更高 revision 的快照时再次调用；取消函数只移除监听，不关闭 view。不要把每次通知都当作一次业务变更，也不要通过修改副本保存数据。

`view.action()` 的 `data` 缺省为 `null`。成功返回 `undefined`，不返回新的快照；更新后的数据通过 `view.subscribe()` 或 `getContext().view` 读取。Promise 在回调执行和状态保存完成后结束，不等待后续模型生成。动作名必须在 `ViewSpec.actions` 中声明。


## 返回值与错误类型 {#result-types}

<<< ../../../../../public/types/astrbot-plugin-view.d.ts#results{ts}

- `UploadFile` 可以直接使用浏览器的 `File` 或 `Blob`；缺省文件名为 `upload.bin`，缺省 MIME 为 `application/octet-stream`。
- `unsubscribeSSE(id)` 返回 `Promise<UnsubscribeSSEResult>`，成功结果为 `{ subscriptionId: id }`，即使连接已结束也可取消。
- `apiGet`、`apiPost`、`upload` 的泛型描述解包后的业务返回值；默认是 `unknown`。泛型不会验证服务端数据。
- SSE 的 `parsed` 在 JSON 解析成功时是解析结果，否则为原字符串。`eventType` 缺省为 `message`，`lastEventId` 初始为空字符串；未提供 `id:` 的后续事件沿用此前 ID。`onOpen`、`onClose`、`onError` 均不接收参数。
- `apiGet` / `download` 的 query 使用 Axios 序列化；`subscribeSSE` 则对每个参数调用 `String(value)`，不支持重复键或数组。SSE 可选参数应省略，不要传 `undefined` 或 `null`。
- `apiPost` 不传 body 或传入 `null`、`false`、`0`、空字符串时，当前宿主会发送 `{}`；推荐使用 JSON 对象作为请求体。

错误通常是 `Error`，`code` **不保证存在**。消息视图可返回 `UNSUPPORTED_CAPABILITY`、`ACTION_IN_PROGRESS`、`REVISION_CONFLICT` 等 code；插件 Web API 由宿主转发的错误只有 `message`，不能依赖 HTTP 状态码或后端附加字段。

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

`BridgeError` 是类型导入：`import type { BridgeError } from "./astrbot-plugin-view"`。`view.subscribe()` 能同步抛出错误；其余请求型方法通过 Promise 拒绝。`REVISION_CONFLICT` 会先同步最新快照再报错，不应盲目重复有副作用的 action。

## 亮暗主题

AstrBot 会把当前主题同步给插件视图。bridge SDK 会维护 `<html>` 的 `data-theme` 属性：

- 亮色模式：`<html data-theme="light">`
- 暗色模式：`<html data-theme="dark">`

bridge 同时将 CSS `color-scheme` 同步为 `light` 或 `dark`，让透明 iframe 的背景与宿主主题保持一致。

选择“跟随系统”时，视图收到的值仍然是 `light` 或 `dark`。

### 跟随用户配色

所有 target 使用同一个 `AstrBotPluginView` bridge。它在 `<html>` 上注入以下 CSS tokens，并在初始化、切换深浅色或主题配色变化时自动更新，无须手动监听再赋值。

| CSS token | 用途 |
| --- | --- |
| `--astrbot-color-primary` | 主题色 |
| `--astrbot-color-secondary` | 辅助色 |
| `--astrbot-color-on-primary` | 主题色背景上的文字 |
| `--astrbot-color-text` | 正文文字 |
| `--astrbot-color-text-secondary` | 次要文字 |
| `--astrbot-color-background` | 页面背景 |
| `--astrbot-color-surface` | 表面背景 |
| `--astrbot-color-border` | 边框 |
| `--astrbot-color-error` | 错误提示 |

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

bridge 只注入变量，不强制设置页面背景；聊天卡片可继续使用 `background: transparent`。现有 `themeColors.primary` / `secondary` 仍保留。需要额外逻辑时，所有 target 都使用 `bridge.onContext(({ isDark, themeColors, locale }) => { ... })`。

## 视图元数据与国际化

视图的标题、描述等元数据写在插件目录的 `.astrbot-plugin/i18n/<locale>.json` 中，并按 `views.<view_name>` 组织。`views` 是 locale JSON 的顶层字段，与 `metadata`、`config` 并列；`<view_name>` 必须与 `views/` 下的目录名完全一致。

例如 `bridge-demo` 视图的中文元数据位于：

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

`.astrbot-plugin/i18n/zh-CN.json`：

```json
{
  "views": {
    "bridge-demo": {
      "title": "Bridge 演示页",
      "description": "演示插件可视化视图如何读取 WebUI 语言和翻译资源。",
      "heading": "插件可视化视图",
      "refresh": "重新渲染"
    }
  }
}
```

字段说明：

| 字段 | 是否必填 | 用途 |
| --- | --- | --- |
| `title` | 否 | 侧边栏、WebUI 外壳标题和插件详情页中的视图名称。 |
| `description` | 否 | 插件详情页中的视图描述。 |
| 其他字段 | 否 | 视图自己的翻译文案，例如示例中的 `heading`、`refresh`；通过 `bridge.t()` 读取。 |

每种语言分别写入对应的 locale 文件，例如英文写入 `.astrbot-plugin/i18n/en-US.json`。推荐使用 `views`；旧的 `pages` 键仅作为兼容别名保留。修改 locale 文件后需要重载插件，才能确保 WebUI 获取到最新元数据。

当前语言未提供 `title` 时，未分组的侧边栏显示插件名称；按插件分组后显示视图目录名，因为分组标题已经显示了插件名称。视图内部使用 `bridge.t()` 渲染其他文案，并通过 `onContext()` 响应语言切换：

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

## 静态资源路径

正常使用相对路径即可：

```html
<link rel="stylesheet" href="./style.css" />
<script type="module" src="./app.js"></script>
<img src="./assets/logo.svg" alt="" />
```

AstrBot 通过路径令牌（path token）为视图资源鉴权：入口配置接口返回的 `content_path` 形如 `/api/v1/plugins/<插件>/views/<视图>/_t/<令牌>/`，页面内的相对路径会沿该前缀自然解析并继承令牌，内容按原样返回、不做重写。令牌与 Dashboard 会话同寿命，且只作用于对应插件的对应视图。

不要手动拼接内容 URL，不要自行追加 `asset_token`，也不要依赖 `..` 逃逸视图根目录。旧版 `/api/plugin/page/content/...?asset_token=...` 形式已被移除。

如果构建 SPA，建议使用 hash routing。静态资源服务按真实文件路径解析；history routing 刷新页面时需要对应路径上真的存在文件。

## 安全约束

插件可视化视图运行在受限 iframe 中：

```text
allow-scripts allow-forms allow-downloads
```

视图不能直接访问 Dashboard cookies、LocalStorage 或父页面 DOM，也不能绕过 bridge 复用 Dashboard auth。所有需要 Dashboard 身份的操作都应该走 bridge。

资源响应会带上安全头，包括：

- `X-Frame-Options: SAMEORIGIN`
- `Content-Security-Policy: frame-ancestors 'self'; object-src 'none'; base-uri 'self'`
- `Cache-Control: no-store`
- `X-Content-Type-Options: nosniff`

后端 handler 仍然要验证输入。不要信任视图传来的路径、文件名、格式或数值范围；文件落盘时应使用安全目录，并对文件名做白名单或重新命名。

## 调试建议

- 视图没出现：检查 `views/<view_name>/index.html` 是否存在、插件是否启用、插件详情页是否已刷新。
- bridge 不存在：确认脚本在 bridge SDK 注入之后运行；推荐使用外部 `type="module"` 脚本。
- API 未匹配：确认注册路由包含插件名前缀，例如 `/{PLUGIN_NAME}/stats`，而视图端 endpoint 是 `stats`。
- query 或 JSON 为空：GET 参数放到 `apiGet(endpoint, params)`，POST JSON 放到 `apiPost(endpoint, body)`。
- 文件上传为空：`upload()` 字段名固定为 `file`，后端用 `(await request.files()).get("file")` 读取。
- SSE 没消息：确认后端响应是 `text/event-stream`，每条消息以空行结尾，例如 `data: ...\n\n`。
- SSE 401：不要在视图中直接 `new EventSource("/api/v1/...")`，原生 `EventSource` 不能携带 `Authorization` header；请通过 `bridge.subscribeSSE()` 调用。
