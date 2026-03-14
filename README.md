# AstrBot SDK

面向 AstrBot 插件作者的 v4 SDK。它提供三件核心能力：

- 用 `Star`、`Context`、`MessageEvent` 编写插件
- 用 `astrbot-sdk dev --local` / `--watch` 做本地调试
- 用 `astrbot_sdk.testing` 写不依赖真实 Core 的插件测试

## 5 分钟跑通第一个插件

### 1. 创建插件骨架

```bash
astrbot-sdk init my_plugin
cd my_plugin
```

生成后的目录结构：

```text
my_plugin/
├── README.md
├── plugin.yaml
├── requirements.txt
├── main.py
└── tests
    └── test_plugin.py
```

### 2. 校验插件

```bash
astrbot-sdk validate --plugin-dir .
```

### 3. 本地运行一次

```bash
astrbot-sdk dev --local --plugin-dir . --event-text hello
```

### 4. 开启热重载

```bash
astrbot-sdk dev --local --watch --plugin-dir . --event-text hello
```

保存 `main.py` 后，本地 harness 会自动重载并重新派发这条消息。

## 最小插件示例

```python
from astrbot_sdk import Context, MessageEvent, Star, on_command


class MyPlugin(Star):
    @on_command("hello", description="发送问候")
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply("Hello, World!")
```

对应 `plugin.yaml`：

```yaml
name: my_plugin
display_name: My Plugin
desc: 一个最小可运行的 AstrBot SDK 插件
author: your-name
version: 0.1.0
runtime:
  python: "3.12"
components:
  - class: main:MyPlugin
```

## 插件作者最常用的 API

### 事件和上下文

- `MessageEvent.text`: 当前消息文本
- `MessageEvent.reply(text)`: 回复文本
- `Context.plugin_id`: 当前插件 ID
- `Context.logger`: 已绑定插件 ID 的日志器

### 平台能力

- `ctx.platform.send(session, text)`
- `ctx.platform.send_image(session, image_url)`
- `ctx.platform.send_chain(session, chain)`
- `ctx.platform.get_members(session)`

### LLM

- `ctx.llm.chat(prompt)`
- `ctx.llm.chat_raw(prompt, ...)`
- `ctx.llm.stream_chat(prompt, ...)`

### 存储

- `ctx.db.get/set/delete/list`
- `ctx.memory.save/get/delete/search`

### 插件元数据和 HTTP

- `ctx.metadata.get_current_plugin()`
- `ctx.metadata.get_plugin_config()`
- `ctx.http.register_api(...)`
- `ctx.http.unregister_api(...)`
- `ctx.http.list_apis()`

## 本地调试

### 单次派发

```bash
astrbot-sdk dev --local --plugin-dir . --event-text hello
```

### 交互模式

```bash
astrbot-sdk dev --local --plugin-dir . --interactive
```

交互模式支持：

- `/session <id>`
- `/user <id>`
- `/platform <name>`
- `/group <id>`
- `/private`
- `/event <type>`
- `/exit`

### 热重载

```bash
astrbot-sdk dev --local --watch --plugin-dir . --interactive
```

适合边改边测。代码变更后会自动重建插件运行时。

## 测试插件

最小测试示例：

```python
import pytest

from astrbot_sdk.testing import MockContext, MockMessageEvent
from main import MyPlugin


@pytest.mark.asyncio
async def test_hello_handler():
    plugin = MyPlugin()
    ctx = MockContext(plugin_id="my_plugin")
    event = MockMessageEvent(text="/hello", context=ctx)

    await plugin.hello(event, ctx)

    assert event.replies == ["Hello, World!"]
    ctx.platform.assert_sent("Hello, World!")
```

运行：

```bash
python -m pytest tests/test_plugin.py -v
```

## 示例插件

面向插件作者的最小示例在：

- [examples/hello_plugin/README.md](examples/hello_plugin/README.md)

仓库里的 `test_plugin/new` 是运行时/集成测试夹具，不是作者入门模板。

## 常见问题

### 1. `validate` 通过了，但 `dev` 还是失败

通常是组件导入或实例化阶段异常。现在错误信息会包含：

- 插件名
- `plugin.yaml` 路径
- `components[i].class`
- 原始异常原因

优先检查：

- `plugin.yaml` 的 `components`
- 导入路径是否真实存在
- 组件类是否继承 `astrbot_sdk.Star`
- `__init__()` 是否做了会抛异常的工作

### 2. handler 参数为什么无法注入

默认支持：

- 按类型注入：`MessageEvent`、`Context`
- 按名字注入：`event`、`ctx`、`context`
- 命令参数字典中的同名字段

如果参数不在这几类里，请自己从 `event` 或 `ctx` 取。

### 3. capability schema 校验失败怎么看

错误会明确指出：

- 哪个 capability
- 输入还是输出校验失败
- 具体字段路径
- 期望类型和实际类型

## 下一步

1. 先跑通 [examples/hello_plugin/README.md](examples/hello_plugin/README.md)
2. 再看 `src-new/astrbot_sdk/testing.py` 里的 `PluginHarness` / `MockContext`
3. 需要更复杂的 capability、HTTP、metadata 示例时，再参考 `test_plugin/new`
