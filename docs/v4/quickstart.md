# AstrBot SDK v4 Quickstart

这份 quickstart 只覆盖当前已经落地的能力：`Star`、`Context`、`MessageEvent`、`astr dev --local`、`astrbot_sdk.testing`。

## 1. 创建插件目录

现在可以直接生成一个符合当前 loader 契约的骨架：

```bash
astrbot-sdk init my-plugin
```

生成结果大致是：

```text
my-plugin/
├── plugin.yaml
├── requirements.txt
├── main.py
└── tests/
    └── test_plugin.py
```

如果你想手动创建，目录结构也至少应包含这些文件。`requirements.txt` 可以先留空。

## 2. 编写 `plugin.yaml`

```yaml
name: my_plugin
display_name: My Plugin
desc: 我的第一个 AstrBot SDK v4 插件
author: you
version: 0.1.0
runtime:
  python: "3.12"
components:
  - class: main:MyPlugin
```

## 3. 编写 `main.py`

```python
from astrbot_sdk import Context, MessageEvent, Star, on_command


class MyPlugin(Star):
    @on_command("hello")
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        reply = await ctx.llm.chat("say hello")
        await event.reply(reply)
```

## 4. 本地运行

安装当前仓库后，可以直接用本地 mock core 跑插件：

```bash
astr dev --local --plugin-dir my-plugin --event-text "hello"
```

或者：

```bash
astrbot-sdk dev --local --plugin-dir my-plugin --event-text "hello"
```

进入交互模式：

```bash
astr dev --local --plugin-dir my-plugin --interactive
```

交互模式下支持这些元命令：

- `/session <id>` 切换 session
- `/user <id>` 切换 user
- `/platform <name>` 切换 platform
- `/group <id>` 切换为群消息
- `/private` 切回私聊
- `/event <type>` 切换事件类型
- `/exit` 退出

## 4.1 校验与打包

本地写完插件后，可以先做静态校验，再构建 zip 包：

```bash
astrbot-sdk validate --plugin-dir my-plugin
astrbot-sdk build --plugin-dir my-plugin
```

默认构建产物会写到 `my-plugin/dist/`。

## 5. 直接写 handler 单元测试

如果你不想每次都起完整 harness，可以直接用 `MockContext` 和 `MockMessageEvent`：

```python
import pytest

from astrbot_sdk.testing import MockContext, MockMessageEvent


@pytest.mark.asyncio
async def test_hello_handler():
    ctx = MockContext(plugin_id="demo")
    event = MockMessageEvent(text="hello", context=ctx)
    ctx.llm.mock_response("你好！")

    async def handler(event, ctx):
        text = await ctx.llm.chat("hello")
        await event.reply(text)

    await handler(event, ctx)

    assert event.replies == ["你好！"]
    ctx.platform.assert_sent("你好！")
```

## 6. 用 `PluginHarness` 跑真实插件

如果你想复用真实的 `loader` / `HandlerDispatcher` / compat 链路，用 `PluginHarness`：

```python
import pytest
from pathlib import Path

from astrbot_sdk.testing import LocalRuntimeConfig, PluginHarness


@pytest.mark.asyncio
async def test_plugin_directory():
    harness = PluginHarness(
        LocalRuntimeConfig(plugin_dir=Path("my-plugin")),
    )

    async with harness:
        records = await harness.dispatch_text("hello")

    assert any(item.text for item in records)
```

## 7. 当前边界

当前 quickstart 对应的是已经存在的能力，不包含这些后续项：

- `ctx.http` / `ctx.cache` / `ctx.storage` / `ctx.i18n`
- 完整宿主调度下的 schedule 执行器

如果你需要查看当前架构与兼容边界，请看 [ARCHITECTURE.md](../../ARCHITECTURE.md)。
