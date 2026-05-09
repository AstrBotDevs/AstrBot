# 制作沙盒运行时插件

沙盒运行时插件负责告诉 AstrBot 如何启动并连接到一个沙盒服务。一个插件通常包含 provider、booter/client、配置 schema，以及截图、浏览器控制这类可选工具。

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

- `main.py`：注册 provider，也可以注册额外工具。
- `provider.py`：把你的 runtime 适配成 AstrBot 的 sandbox provider。
- `booters/`：放启动、连接、关闭沙盒的 client 代码。
- `tools/`：放截图、鼠标、键盘、浏览器或生命周期这类可选工具。
- `_conf_schema.json`：定义 WebUI 中展示的配置项。schema 格式见[插件配置](./plugin-config.md)。

## 1. 注册 provider

在 `main.py` 中创建 provider，并在插件加载时注册它。把插件配置传给 provider，这样 `provider.py` 就能读取 `_conf_schema.json` 生成的配置。

```python
from astrbot.api.star import Context, Star, register
from astrbot.core.computer.computer_client import (
    register_sandbox_provider,
    unregister_sandbox_provider,
)

from .provider import MySandboxProvider


@register("astrbot_sandbox_demo", "AstrBot Team", "Demo sandbox provider", "0.1.0")
class DemoSandboxPlugin(Star):
    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        self.provider = MySandboxProvider()
        self.provider.plugin_config = config or {}
        register_sandbox_provider(self.provider, replace=True)

    async def terminate(self) -> None:
        unregister_sandbox_provider(self.provider.provider_id, force=True)
```

建议插件目录名、`metadata.yaml` 里的 `name`、`@register(...)` 的名字保持一致，后续查找生成的配置文件会更直观。

## 2. 实现 `provider.py`

AstrBot 在创建、复用、重命名、销毁沙盒时会调用 provider。你需要实现这些字段和方法：

- `provider_id`
- `capabilities`
- `tool_names`
- `system_prompt`
- `build_create_config(context, session_id)`
- `build_connect_info(sandbox_name, config)`
- `update_connect_info(record, *, sandbox_name)`
- `get_idle_timeout(context, session_id)`
- `create_booter(context, session_id, sandbox_id, config)`
- `destroy_booter(booter, record)`

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

    def get_idle_timeout(self, context, session_id):
        return 0.0

    async def create_booter(self, context, session_id, sandbox_id, config):
        booter = MyBooter(**config)
        await booter.boot(session_id)
        return booter

    async def destroy_booter(self, booter, record):
        await booter.shutdown()
```

## 3. 添加 runtime 配置

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

如果 provider 还需要兼容旧的 `provider_settings.sandbox` 配置，可以在 `build_create_config()` 中把它们作为插件配置之上的 override。新的 provider 配置通常放在 `_conf_schema.json` 即可。

## 4. 添加可选工具

如果你的 runtime 除了 shell/python/filesystem 外还提供其他能力，在插件里注册对应工具，并把工具名写进 `provider.tool_names`。

常见工具包括：

- 截图工具
- 鼠标 / 键盘工具
- 浏览器工具
- runtime 专属生命周期工具

AstrBot 在 sandbox mode 下挂载工具时会读取 `tool_names`。这里的名字要和 `main.py` 中注册的工具名一致。

`system_prompt` 用来放稳定的 runtime 专属提示词，只要该 provider 被启用，就会注入到模型请求中。常见内容包括文件路径规则、GUI 截图流程、浏览器自动化约束，或 provider 专属的 skill 生命周期步骤。

## 5. 本地试跑

把插件放到 `data/plugins/<plugin_name>/` 后，启动 AstrBot，重点检查这些点：

- 插件加载时没有 import error。
- WebUI 配置页能看到 `_conf_schema.json` 里的字段。
- 沙盒 runtime 选择项里能看到你的 `provider_id`。
- 创建沙盒时会调用 `create_booter()`。
- 停止或卸载插件时会调用 `terminate()` 并注销 provider。
