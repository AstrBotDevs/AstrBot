# Building a Sandbox Runtime Plugin

A sandbox runtime plugin teaches AstrBot how to start and connect to a sandbox service. The plugin usually contains a provider, a booter/client, a config schema, and optional tools for features such as screenshots or browser control.

If you are migrating an existing runtime, focus on the config boundary first: AstrBot Core handles routing, reuse, and cleanup, while the plugin owns the actual endpoint, token, image, and timeout settings.

Start with this structure:

```text
data/plugins/<plugin_name>/
  main.py
  metadata.yaml
  _conf_schema.json
  provider.py
  booters/
  tools/
```

Use the files like this:

- `main.py`: register the provider, and register any extra tools.
- `provider.py`: adapt your runtime to AstrBot's sandbox provider methods.
- `booters/`: put the client code that starts, connects to, and shuts down the sandbox.
- `tools/`: add optional runtime tools such as screenshot, mouse, keyboard, browser, or lifecycle helpers.
- `_conf_schema.json`: define the settings shown in WebUI. See [Plugin Configuration](./plugin-config.md) for the schema format.

## 1. Register the provider

In `main.py`, create your provider and register it when the plugin loads. Pass the plugin config into the provider so `provider.py` can read values from `_conf_schema.json`.

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

Use a stable name for the plugin directory, `metadata.yaml`, and `@register(...)`. Keeping them aligned makes the generated config file easy to find.

## 2. Implement `provider.py`

AstrBot calls the provider whenever it needs to create, reuse, rename, or destroy a sandbox. Implement these fields and methods:

- `provider_id`
- `capabilities`
- `tool_names`
- `system_prompt`
- `build_create_config(context, session_id)`
- `build_connect_info(sandbox_name, config)`
- `update_connect_info(record, *, sandbox_name)`
- `create_booter(context, session_id, sandbox_id, config)`
- `destroy_booter(booter, record)`

If your provider supports persistent sandbox reconnects, also set
`supports_persistent_reconnect = True` and implement
`check_persistent_sandbox_exists(record)`. AstrBot calls this method before
resuming a persistent sandbox; providers that declare reconnect support but do
not implement the existence probe are rejected to avoid ghost sandbox records.
When `config.get("resume") is True` in `create_booter()`, reconnect to the
existing sandbox identified by `record["connect_info"]` instead of creating a new
external sandbox.

## 2.1 How config migration works

If older versions already stored settings in `provider_settings.sandbox`, treat that as a compatibility input and move new editable values into the plugin config:

- Put new user-facing fields in `_conf_schema.json` first.
- Use `build_create_config()` to merge plugin config with any legacy overrides.
- Keep `provider_settings.sandbox` as a transition layer only.
- Treat `tool_names`, `capabilities`, and `system_prompt` as runtime capability declarations rather than user config entries.

This is a minimal provider skeleton:

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
        # Only required when supports_persistent_reconnect=True.
        return await self.client.sandbox_exists(record["connect_info"]["sandbox_id"])

    async def create_booter(self, context, session_id, sandbox_id, config):
        booter = MyBooter(**config)
        await booter.boot(session_id)
        return booter

    async def destroy_booter(self, booter, record):
        await booter.shutdown()
```

## 3. Add runtime config

Create `_conf_schema.json` for values that users should edit in WebUI, such as API endpoints, access tokens, profiles, image names, or timeouts.

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

AstrBot stores the saved values in `data/config/<plugin_name>_config.json` and passes them to the plugin constructor as `config`.

If your provider still supports older values under `provider_settings.sandbox`, read them in `build_create_config()` as overrides on top of the plugin config. New provider settings should normally live in `_conf_schema.json`.

## 4. Add optional tools

If your runtime exposes extra abilities, register those tools in the plugin and list the tool names in `provider.tool_names`.

Common examples:

- screenshot tools
- mouse / keyboard tools
- browser tools
- runtime-specific lifecycle helpers

AstrBot uses `tool_names` when mounting tools in sandbox mode. Make sure the names match the tools you register in `main.py`.

Use `system_prompt` as provider metadata for stable runtime-specific instructions. Core exposes it through provider info so dashboards or higher-level integrations can show the provider rules, but it is not automatically appended to every model request.

## 5. Try it locally

After adding the plugin under `data/plugins/<plugin_name>/`, start AstrBot and check these items:

- The plugin loads without import errors.
- The WebUI config page shows fields from `_conf_schema.json`.
- The sandbox runtime selector includes your `provider_id`.
- Creating a sandbox calls `create_booter()`.
- Stopping or unloading the plugin calls `terminate()` and unregisters the provider.
