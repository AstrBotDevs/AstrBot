# 制作沙盒运行时插件

沙盒运行时插件负责告诉 AstrBot 如何启动并连接到一个沙盒服务。一个插件通常包含驱动实现、booter/client、配置 schema，以及截图、浏览器控制这类可选工具。

如果你要把一个现有运行时迁移成插件，先把配置边界分清：AstrBot Core 只管“什么时候用、用哪个、怎么回收”，真正要填哪些地址、令牌、镜像和超时，应该放在插件自己的配置里。

## 先看整体结构

一个沙盒运行时插件通常会被拆成四块：

- **provider**：告诉 AstrBot 这个运行时能做什么、怎么创建沙盒、怎么销毁沙盒。
- **booter / client**：负责和真实沙盒服务交互，创建、连接和关闭实例。
- **tools**：补充截图、鼠标、键盘、浏览器或生命周期类工具。
- **配置 schema**：把用户需要改的项暴露到 WebUI。

分工看起来不复杂，但把边界拆清楚之后，后面做迁移、排障和补新能力都会轻松很多。

可以先按这个结构创建目录：

```text
data/plugins/<plugin_name>/
  main.py
  metadata.yaml
  _conf_schema.json
  provider.py
  booters/
  tools/
```

各文件大致这样分工：

- `main.py`：注册沙盒驱动，也可以注册额外工具。
- `provider.py`：把你的运行时适配成 AstrBot 的沙盒驱动。
- `booters/`：放启动、连接、关闭沙盒的 client 代码。
- `tools/`：放截图、鼠标、键盘、浏览器或生命周期这类可选工具。
- `_conf_schema.json`：定义 WebUI 中展示的配置项。schema 格式见[插件配置](./plugin-config.md)。

## 1. 注册沙盒驱动

在 `main.py` 中创建驱动实例，并在插件加载时注册它。把插件配置传给驱动，这样 `provider.py` 就能读取 `_conf_schema.json` 生成的配置。

```python
from astrbot.api.star import Context, Star, register
from astrbot.core.computer.computer_client import (
    register_sandbox_provider,
    unregister_sandbox_provider,
)

from .provider import MySandboxProvider
from .tools import DemoMouseClickTool


@register("astrbot_sandbox_demo", "AstrBot Team", "Demo 沙盒驱动", "0.1.0")
class DemoSandboxPlugin(Star):
    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        self.provider = MySandboxProvider()
        self.provider.plugin_config = config or {}
        register_sandbox_provider(
            self.provider,
            replace=True,
            tools=[DemoMouseClickTool()],
        )

    async def terminate(self) -> None:
        unregister_sandbox_provider(self.provider.provider_id, force=True)
```

建议插件目录名、`metadata.yaml` 里的 `name`、`@register(...)` 的名字保持一致，后续查找生成的配置文件会更直观。

## 2. 实现 `provider.py`

AstrBot 在创建、复用、重命名、销毁沙盒时会调用这个驱动。你需要实现这些字段和方法：

- `provider_id`
- `capabilities`
- `tool_names`
- `system_prompt`
- `build_create_config(context, session_id)`
- `build_connect_info(sandbox_name, config)`
- `update_connect_info(record, *, sandbox_name)`
- `create_booter(context, session_id, sandbox_id, config)`
- `destroy_booter(booter, record)`

如果驱动支持持久化沙盒复连，还需要设置
`supports_persistent_reconnect = True` 并实现
`check_persistent_sandbox_exists(record)`。AstrBot 会在恢复持久化沙盒前调用
这个方法；声明支持复连但没有实现存在性探针的 provider 会被拒绝，避免产生
“幽灵沙盒”记录。`create_booter()` 收到 `config.get("resume") is True` 时，应
连接 `record["connect_info"]` 指向的现有沙盒，而不是创建新的外部沙盒。

## 2.1 配置迁移怎么做

如果旧版本已经把配置写在 `provider_settings.sandbox` 里，迁移时可以先把它当成兼容输入，再逐步迁到插件配置：

- 新的可编辑项优先放到 `_conf_schema.json`。
- `build_create_config()` 负责把插件配置和旧配置合并成真正的创建参数。
- `provider_settings.sandbox` 只适合作为过渡层，不建议继续扩展新字段。
- `tool_names`、`capabilities`、`system_prompt` 不是用户配置入口，它们更像运行时能力声明。

下面是一个最小骨架：

```python
class MySandboxProvider:
    provider_id = "demo"
    capabilities = {"shell", "python", "filesystem"}
    tool_names = set()
    system_prompt = (
        "When using this sandbox provider, follow its runtime-specific path, "
        "GUI, browser, and lifecycle rules."
    )

    def build_create_config(self, context, session_id):
        config = context.get_config(umo=session_id)
        sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
        plugin_cfg = getattr(self, "plugin_config", None) or {}
        return {
            "endpoint_url": sandbox_cfg.get(
                "demo_endpoint", plugin_cfg.get("demo_endpoint", "")
            ),
            "ttl": sandbox_cfg.get("demo_ttl", plugin_cfg.get("demo_ttl", 3600)),
        }

    def build_connect_info(self, sandbox_name, config):
        return {"name": sandbox_name, **config}

    def update_connect_info(self, record, *, sandbox_name):
        info = dict(record.get("connect_info") or {})
        info["name"] = sandbox_name
        return info

    async def check_persistent_sandbox_exists(self, record):
        # 只有 supports_persistent_reconnect=True 时才需要实现。
        return await self.client.sandbox_exists(record["connect_info"]["sandbox_id"])

    async def create_booter(self, context, session_id, sandbox_id, config):
        booter = MyBooter(**config)
        await booter.boot(session_id)
        return booter

    async def destroy_booter(self, booter, record):
        await booter.shutdown()
```

## 3. 添加运行时配置

如果用户需要在 WebUI 中填写 API 地址、访问令牌、profile、镜像名或超时时间，把这些字段写进 `_conf_schema.json`。

```json
{
  "demo_endpoint": {
    "description": "Demo API Endpoint",
    "type": "string",
    "default": "",
    "hint": "API endpoint for the demo sandbox service."
  },
  "demo_ttl": {
    "description": "Sandbox TTL",
    "type": "int",
    "default": 3600,
    "hint": "Sandbox lifetime in seconds."
  }
}
```

AstrBot 会把用户保存的值写到 `data/config/<plugin_name>_config.json`，并在插件实例化时作为 `config` 传入。

如果驱动还需要兼容旧的 `provider_settings.sandbox` 配置，可以在 `build_create_config()` 中把它们作为插件配置之上的 override。新的驱动配置通常放在 `_conf_schema.json` 即可。

## 4. 添加可选工具

如果你的运行时除了 shell/python/filesystem 外还提供其他能力，在插件里注册对应工具，并把工具名写进 `provider.tool_names`。

常见工具包括：

- 截图工具
- 鼠标 / 键盘工具
- 浏览器工具
- 运行时专属生命周期工具

AstrBot 在沙盒模式下挂载工具时会读取 `tool_names`。这里的名字要和 `main.py` 中注册的工具名一致。

运行时专属工具应该通过沙盒 provider 注册路径注册，不要当作普通全局工具注册。这样 Core 才能做 provider 级别的工具过滤，并在 provider 卸载时一起清理这些工具。

```python
from dataclasses import dataclass, field

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.computer.sandbox_tool_binding import sandbox_provider_tool


@sandbox_provider_tool("demo")
@dataclass
class DemoMouseClickTool(FunctionTool):
    name: str = "demo_mouse_click"
    description: str = "Click inside the demo sandbox."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["x", "y"],
        }
    )

    async def call(self, context, x: int, y: int):
        return await self.client.click(x=x, y=y)
```

然后保持 `provider.tool_names = {"demo_mouse_click"}`，并在 `main.py` 里把 `tools=[DemoMouseClickTool()]` 传给 `register_sandbox_provider(...)`。

`system_prompt` 可以作为 provider 元数据保存稳定的运行时提示词。Core 会在 provider info 中暴露它，方便 WebUI 或上层集成展示驱动规则，但不会自动把它追加到每次模型请求里。

## 4.1 一次沙盒请求是怎么走的

可以把它理解成下面这条链路：

1. 插件加载时，`main.py` 先把 provider 注册到 AstrBot。
2. 用户发起沙盒请求后，AstrBot 先看当前会话有没有可复用的沙盒。
3. 如果能复用，AstrBot 直接接回现有 booter。
4. 如果不能复用，AstrBot 会调用 provider 生成创建配置，再让 booter/client 去启动新沙盒。
5. 沙盒创建成功后，AstrBot 会把它写回 registry，并按 capability 和 `tool_names` 挂载对应工具。

这里最容易忽略的一点是：AstrBot 并不知道某个运行时自己该怎么工作，它只认识 provider 提供的抽象能力。路径规则、浏览器约束、持久化目录、是否支持某些工具，这些都应该由 provider 讲清楚。

## 4.2 迁移旧运行时时的几个注意点

- 如果旧配置里已经有 `provider_settings.sandbox`，可以先把它当成兼容层，新的可编辑项尽量放到 `_conf_schema.json`。
- `tool_names` 要和 `main.py` 里实际注册的工具名一致，不然工具挂载会对不上。
- `system_prompt` 如果提供，最好直接写清楚路径规则和使用约束，别只写“请遵守运行时规则”这种空话。
- 如果运行时有持久化数据，最好在文档里明确写出它的根目录、生命周期和是否会在重建后保留。
- 迁移完成后，先验证最基础的创建、复用、销毁，再去看截图、浏览器和上传下载这些扩展能力。

## 5. 本地试跑

把插件放到 `data/plugins/<plugin_name>/` 后，启动 AstrBot，重点检查这些点：

- 插件加载时没有 import error。
- WebUI 配置页能看到 `_conf_schema.json` 里的字段。
- 沙盒驱动选择项里能看到你的 `provider_id`。
- 创建沙盒时会调用 `create_booter()`。
- 停止或卸载插件时会调用 `terminate()` 并注销驱动。
