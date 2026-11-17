# 后端 Web API

独立插件页面和常驻工作台页面通过 Bridge 调用这些接口。消息组件与消息创建的工作台页面使用 `@filter.ui_action`，见[消息交互组件](./chat-message.md)。

接口按当前登录用户鉴权。业务数据的归属和权限仍由插件校验；涉及会话时，根据 `request.username` 验证会话归属，不能只信任前端提交的 `session_id`。

## 路由注册

使用 `context.register_web_api(route, view_handler, methods, desc)` 注册插件 API。

```python
context.register_web_api(
    f"/{PLUGIN_NAME}/items/<item_id>",
    self.get_item,
    ["GET"],
    "Get item",
)
```

路由需要包含插件名作为前缀。视图端的 bridge endpoint 不需要包含插件名：

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

## 请求对象

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

# AstrBot v4.30.0 之前的导入方式：
# from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path
from astrbot.api.util import get_astrbot_plugin_data_path
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

## 响应对象

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

## Quart 兼容

为了兼容旧插件，通过 `context.register_web_api()` 注册的 handler 仍会进入 Quart 兼容请求上下文。旧代码可以继续使用：

```python
from quart import jsonify, request
```

新插件和新文档推荐使用：

```python
from astrbot.api.web import json_response, request
```

不要在同一个 handler 中混用两个 `request` 代理，迁移时按 handler 逐步替换即可。
