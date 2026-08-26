# Plugin Configuration

A Star can provide `_conf_schema.json` at its plugin root. AstrBot uses the schema to create a plugin configuration file, render a WebUI form, and inject `AstrBotConfig` when instantiating the plugin.

The schema must be **strict JSON**: no comments, trailing commas, or Python `True` / `False` values.

## Minimal schema

```json
{
  "token": {
    "description": "Service token",
    "type": "string",
    "obvious_hint": true
  },
  "timeout": {
    "description": "Request timeout in seconds",
    "type": "int",
    "default": 30,
    "slider": {
      "min": 1,
      "max": 120,
      "step": 1
    }
  },
  "advanced": {
    "description": "Advanced settings",
    "type": "object",
    "items": {
      "enabled": {
        "type": "bool",
        "default": false
      }
    }
  }
}
```

## Supported types

The current runtime supports:

| `type`          | Default | WebUI and storage semantics                          |
| --------------- | ------- | ---------------------------------------------------- |
| `string`        | `""`    | Single-line string.                                  |
| `text`          | `""`    | Multi-line text.                                     |
| `int`           | `0`     | Integer; can use `slider`.                           |
| `float`         | `0.0`   | Floating-point number; can use `slider`.             |
| `bool`          | `false` | Switch.                                              |
| `list`          | `[]`    | JSON array; `items` can describe object entries.     |
| `file`          | `[]`    | A list of relative path strings produced by uploads. |
| `object`        | `{}`    | Nested object and must provide `items`.              |
| `dict`          | `{}`    | Open key-value object edited in the WebUI.           |
| `template_list` | `[]`    | Object list built from predefined templates.         |

`dict` is an open-ended key-value object. The WebUI provides a key-value editor for it; use `items: {}` for arbitrary values, or add `template_schema` when you want to offer predefined fields and types. Use `object` with explicit `items` when the plugin needs a fixed, structured schema. Plugins remain responsible for validating values beyond the editor metadata.

## Common metadata

- `description` is the field label or concise description.
- `hint` supplies additional help.
- `obvious_hint` makes the hint prominent in the form.
- `default` sets an explicit default of the same type.
- `invisible` hides the field from the WebUI while keeping it in configuration.
- `secret` applies to `string` and string `list` fields. When `true`, the dashboard masks the value and lets the user temporarily reveal it. This only affects the UI; it does not encrypt the stored configuration.
- `options` supplies a string or numeric choice list.
- `labels` supplies display text corresponding to `options`. See [Plugin Internationalization](./plugin-i18n) for current limitations.
- `slider` applies only to `int` / `float` and contains `min`, `max`, and `step`.
- `editor_mode`, `editor_language`, and `editor_theme` enable a code editor for text or structured input.
- `_special` selects a dynamic AstrBot picker.

When editing a plugin configuration in WebUI, a changed writable field can be
restored to this schema default. The control is intentionally limited to plugin
configuration: it is not shown for core settings. For an `object`, the runtime
builds the restored value recursively from `items`; an object-level `default`
does not replace that structure. Unknown types and `readonly` fields do not
offer restoration.

Common stable `_special` values for plugins include:

- `select_provider`, `select_provider_tts`, and `select_provider_stt`, returning a Provider ID string;
- `select_persona`, returning a Persona ID string;
- `select_knowledgebase`, returning a list of knowledge-base IDs, so the field should be `list`.

Core configuration uses additional `_special` values that are not a plugin SDK contract. Do not copy them from core metadata.

## Sensitive configuration fields

API keys, access tokens, and passwords should set `"secret": true`. The dashboard masks their contents by default and provides a control to temporarily reveal or hide them. String lists also support this field:

```json
{
  "api_key": {
    "description": "API Key",
    "type": "string",
    "default": "",
    "secret": true
  },
  "backup_api_keys": {
    "description": "Backup API keys",
    "type": "list",
    "default": [],
    "secret": true
  }
}
```

`secret` does not change the value or data type received by the plugin. It only masks the value in the dashboard; the original value is still stored in the plugin configuration file. Plugins should avoid logging, echoing, or otherwise exposing these values.

## File-upload fields

```json
{
  "reference_files": {
    "type": "file",
    "description": "Reference documents",
    "default": [],
    "file_types": ["pdf", "txt", "md"]
  }
}
```

The saved value is not an absolute path. It is a list such as:

```json
{
  "reference_files": ["files/reference_files/guide.pdf"]
}
```

Files live under `data/plugin_data/<plugin-root>/files/<config-key>/`. Paths and extensions are validated, and the current per-file limit is 500 MiB. Resolve a value through the public storage entry point:

```python
absolute_path = self.context.storage.data_directory() / config["reference_files"][0]
```

Do not treat an upload path as a URL or bypass relative-path validation to access another plugin's data.

## `template_list`

Use `template_list` when users can add any number of entries from fixed structures:

```json
{
  "endpoints": {
    "type": "template_list",
    "description": "Endpoints",
    "templates": {
      "http": {
        "name": "HTTP endpoint",
        "display_item": "name",
        "items": {
          "name": {
            "type": "string",
            "default": ""
          },
          "url": {
            "type": "string",
            "default": "https://example.com"
          },
          "timeout": {
            "type": "int",
            "default": 30
          }
        }
      }
    }
  }
}
```

The stored value includes its template key:

```json
{
  "endpoints": [
    {
      "__template_key": "http",
      "name": "primary",
      "url": "https://example.com",
      "timeout": 30
    }
  ]
}
```

- `display_item` points to a field shown in the collapsed-row title and supports nested paths such as `meta.name`.
- `hide_hint_in_list: true` hides only the template hint in the collapsed list.
- Every template needs `items`, and stored values are recursively validated against the selected template.

## Receiving configuration in a plugin

```python
from astrbot.api import AstrBotConfig
from astrbot.api.star import PluginContext, Star


class Main(Star):
    def __init__(self, context: PluginContext, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config

    async def initialize(self) -> None:
        timeout = int(self.config["timeout"])
        # Initialize clients with validated configuration.
        _ = timeout
```

The configuration filename comes from the plugin directory root name and is stored as `data/config/<root-name>_config.json`, not an arbitrary metadata display name. Saving in the WebUI validates and writes the data, then reloads the plugin. Every client, task, and file therefore needs correct `terminate()` cleanup.

When a plugin genuinely needs to update configuration at runtime from an async handler, modify `self.config` and await `self.config.save_config_async()`. Do not write on every message or store runtime state, caches, or user data in configuration; use [Plugin Storage](./storage) instead.

## Schema update rules

On a new version, AstrBot inserts missing schema defaults, adjusts the structure, and removes fields no longer in the schema. When publishing a schema change:

1. keep a key's type stable or perform an explicit migration during initialization;
2. do not rely on removed hidden fields as persistent storage;
3. parse `_conf_schema.json` as real JSON in tests;
4. test empty configuration, old configuration, and WebUI save/reload paths;
5. never include secret values in logs, examples, or error details.
