
# Plugin Configuration

As plugin functionality grows, you may need to define configurations to allow users to customize plugin behavior.

AstrBot provides "powerful" configuration parsing and visualization features. Users can configure plugins directly in the management panel without modifying code.

## Configuration Definition

To register configurations, first add a `_conf_schema.json` JSON file in your plugin directory.

The file content is a `Schema` that represents the configuration. The Schema is in JSON format, for example:

```json
{
  "token": {
    "description": "Bot Token",
    "type": "string"
  },
  "sub_config": {
    "description": "Test nested configuration",
    "type": "object",
    "hint": "xxxx",
    "items": {
      "name": {
        "description": "testsub",
        "type": "string",
        "hint": "xxxx"
      },
      "id": {
        "description": "testsub",
        "type": "int",
        "hint": "xxxx"
      },
      "time": {
        "description": "testsub",
        "type": "int",
        "hint": "xxxx",
        "default": 123
      }
    }
  }
}
```

- `type`: **Required**. The type of the configuration. Supports `string`, `text`, `int`, `float`, `bool`, `object`, `list`, `dict`, `template_list`, `file`. When the type is `text`, it will be visualized as a larger resizable textarea component to accommodate large text.
- `description`: Optional. Description of the configuration. A one-sentence description of the configuration's behavior is recommended.
- `hint`: Optional. Hint information for the configuration, displayed in the question mark button on the right in the image above, shown when hovering over it.
- `obvious_hint`: Optional. Whether the configuration hint should be prominently displayed, like `token` in the image above.
- `default`: Optional. The default value of the configuration. If the user hasn't configured it, the default value will be used. Default values: int is 0, float is 0.0, bool is False, string is "", object is {}, list is [].
- `items`: Optional. If the configuration type is `object`, the `items` field needs to be added. The content of `items` is the sub-Schema of this configuration item. Theoretically, it can be nested infinitely, but excessive nesting is not recommended.
- `invisible`: Optional. Whether the configuration is hidden. Default is `false`. If set to `true`, it will not be displayed in the management panel.
- `options`: Optional. A list, such as `"options": ["chat", "agent", "workflow"]`. Provides dropdown list options.
- `editor_mode`: Optional. Whether to enable code editor mode. Requires AstrBot >= `v3.5.10`. Versions below this won't report errors but won't take effect. Default is false.
- `editor_language`: Optional. The code language for the code editor, defaults to `json`.
- `editor_theme`: Optional. The theme for the code editor. Options are `vs-light` (default) and `vs-dark`.
- `_special`: Optional. Used to call AstrBot's visualization features for provider selection, persona selection, knowledge base selection, etc. See details below.

### Configuration Internationalization (Optional)

Configuration `description`, `hint`, and select `labels` can follow the WebUI language. See [Plugin Internationalization](./plugin-i18n).

When the code editor is enabled, it looks like this:

![editor_mode](https://files.astrbot.app/docs/source/images/plugin/image-6.png)

![editor_mode_fullscreen](https://files.astrbot.app/docs/source/images/plugin/image-7.png)

The **_special** field is only available after v4.0.0. Common values include `select_provider`, `select_provider_tts`, `select_provider_stt`, `select_persona`, and `select_knowledgebase`, allowing users to quickly select model providers, personas, knowledge bases, and other data already configured in the WebUI.

- `select_provider`, `select_provider_tts`, `select_provider_stt`, and `select_persona` return strings.
- `select_knowledgebase` returns a `list` and supports multiple selection, so the corresponding config item should use `type: list` with a default value of `[]`.

> [!NOTE]
> For reference, AstrBot Core also uses other internal `_special` values, such as `select_providers`, `provider_pool`, `persona_pool`, `select_plugin_set`, `t2i_template`, `get_embedding_dim`, and `select_agent_runner_provider:*` (where `*` is a placeholder for the runner type). These are internal implementations and may change at any time — please avoid using them in plugins.

Using `select_provider` as an example, it will display as follows:

![image](https://files.astrbot.app/docs/source/images/plugin/image-select-provider.png)

### `file` type schema

Introduced in v4.13.0, this allows plugins to define file-upload configuration items to guide users to upload files required by the plugin.

```json
{
  "demo_files": {
    "type": "file",
    "description": "Uploaded files for demo",
    "default": [],
    "file_types": ["pdf", "docx"]
  }
}
```

### `dict` type schema

Used to visualize editing a Python `dict` type configuration. For example, AstrBot Core's custom extra body parameter configuration:

```py
"custom_extra_body": {
  "description": "Custom request body parameters",
  "type": "dict",
  "items": {},
  "hint": "Used to add extra parameters to requests, such as temperature, top_p, max_tokens, etc.",
  "template_schema": {
      "temperature": {
          "name": "Temperature",
          "description": "Temperature parameter",
          "hint": "Controls randomness of output, typically 0-2. Higher is more random.",
          "type": "float",
          "default": 0.6,
          "slider": {"min": 0, "max": 2, "step": 0.1},
      },
      "top_p": {
          "name": "Top-p",
          "description": "Top-p sampling",
          "hint": "Nucleus sampling parameter, typically 0-1. Controls probability mass considered.",
          "type": "float",
          "default": 1.0,
          "slider": {"min": 0, "max": 1, "step": 0.01},
      },
      "max_tokens": {
          "name": "Max Tokens",
          "description": "Maximum tokens",
          "hint": "Maximum number of tokens to generate.",
          "type": "int",
          "default": 8192,
      },
  },
}
```

### `template_list` type schema

> [!NOTE]
> Introduced in v4.10.4. For more details see: [#4208](https://github.com/AstrBotDevs/AstrBot/pull/4208)

Plugin developers can add a template-style configuration to `_conf_schema` in the following format (somewhat similar to nested configs):

```json
 "field_id": {
  "type": "template_list",
  "description": "Template List Field",
  "templates": {
    "template_1": {
        "name": "Template One",
        "hint":"hint",
        "items": {
          "attr_a": {
            "description": "Attribute A",
            "type": "int",
            "default": 10
          },
          "attr_b": {
            "description": "Attribute B",
            "hint": "This is a boolean attribute",
            "type": "bool",
            "default": true
          }
        }
      },
    "template_2": {
      "name": "Template Two",
      "hint":"hint",
      "items": {
        "attr_c": {
          "description": "Attribute A",
          "type": "int",
          "default": 10
        },
        "attr_d": {
          "description": "Attribute B",
          "hint": "This is a boolean attribute",
          "type": "bool",
          "default": true
        }
      }
    }
  }
}
```

Saved config example:

```json
"field_id": [
    {
        "__template_key": "template_1",
        "attr_a": 10,
        "attr_b": true
    },
    {
        "__template_key": "template_2",
        "attr_c": 10,
        "attr_d": true
    }
]
```

<img width="1000" alt="image" src="https://github.com/user-attachments/assets/74876d30-11a4-491b-a7a0-8ebe8d603782" />


## Using Configuration in Plugins

When loading plugins, AstrBot will check if there's a `_conf_schema.json` file in the plugin directory. If it exists, it will automatically parse the configuration and save it under `data/config/<plugin_name>_config.json` (a configuration file entity created according to the Schema), and pass it to `__init__()` when instantiating the plugin class.

```py
from astrbot.api import AstrBotConfig

class ConfigPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig): # AstrBotConfig inherits from Dict and has all dictionary methods
        super().__init__(context)
        self.config = config
        print(self.config)

        # Supports direct configuration saving
        # self.config.save_config() # Save configuration
```

## Configuration Updates

When you update the Schema across different versions, AstrBot will recursively inspect the configuration items in the Schema, automatically adding default values for missing items and removing those that no longer exist.

Note that `default` is only applied when creating a new config file or when a field is missing from an existing config. If a field already exists in `data/config/<plugin_name>_config.json`, changing the Schema `default` later will not overwrite that saved value. This is intentional so plugin upgrades do not silently replace user-edited settings.

## Building a Sandbox Runtime Plugin

Starting from the generic sandbox architecture, concrete runtimes such as `CUA`, `Shipyard`, `Shipyard Neo`, or `Boxlite` should be implemented as **separate plugins**, not hard-coded in AstrBot Core.

Recommended structure:

```text
data/plugins/<plugin_name>/
  main.py
  metadata.yaml
  _conf_schema.json
  provider.py
  booters/
  tools/
```

Typical responsibilities are split like this:

- `main.py`: plugin entrypoint, provider registration, and optional extra tool registration.
- `provider.py`: sandbox provider implementation.
- `booters/`: runtime-specific sandbox client / booter implementation.
- `tools/`: optional runtime-specific tools, such as screenshot, mouse, keyboard, browser, or lifecycle helpers.
- `_conf_schema.json`: provider-specific configuration shown in WebUI.

### 1. Register the sandbox provider

In your plugin entrypoint, register and unregister the provider through the generic sandbox APIs exposed by core:

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

Use a stable plugin name, directory name, and metadata `name`, ideally all aligned.

### 2. Implement the provider contract

Your provider should implement the generic sandbox protocol from core (`astrbot.core.computer.sandbox_provider.SandboxProvider`). In practice, that means defining:

- `provider_id`
- `capabilities`
- `tool_names`
- `build_create_config(context, session_id)`
- `build_connect_info(sandbox_name, config)`
- `update_connect_info(record, *, sandbox_name)`
- `get_idle_timeout(context, session_id)`
- `create_booter(context, session_id, sandbox_id, config)`
- `destroy_booter(booter, record)`

Example skeleton:

```python
class MySandboxProvider:
    provider_id = "demo"
    capabilities = {"shell", "python", "filesystem"}
    tool_names = set()

    def build_create_config(self, context, session_id):
        plugin_cfg = getattr(self, "plugin_config", None) or {}
        return {
            "endpoint_url": plugin_cfg.get("demo_endpoint", ""),
            "ttl": plugin_cfg.get("demo_ttl", 3600),
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

### 3. Put runtime-specific config in `_conf_schema.json`

Core only keeps the generic selector:

- `provider_settings.computer_use_runtime`
- `provider_settings.sandbox.booter`

All runtime-specific config belongs to the plugin schema, for example:

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

That schema will be stored under `data/config/<plugin_name>_config.json` and passed to the plugin constructor as `config`.

### 4. Expose optional runtime tools through `tool_names`

If your runtime adds extra tools beyond the generic shell/python/filesystem stack, register them in the plugin and list their names in `tool_names`.

Typical examples:

- screenshot tools
- mouse / keyboard tools
- browser tools
- runtime-specific lifecycle helpers

Core uses `tool_names` to mount those tools automatically in sandbox mode, so avoid hard-coding provider names in core.

### 5. Keep runtime code out of core

When building a sandbox plugin:

- Put concrete runtime SDK imports in the plugin repo.
- Put provider-specific defaults and config schema in the plugin repo.
- Put runtime-specific tools in the plugin repo.
- Keep AstrBot Core limited to generic sandbox registration, lifecycle, persistence, and dashboard/API surfaces.

If you are unsure whether something belongs in core or a plugin, the rule of thumb is:

- generic behavior -> core
- concrete runtime behavior -> plugin
