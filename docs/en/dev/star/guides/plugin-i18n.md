# Plugin Internationalization

Plugins can provide `.astrbot-plugin/i18n/*.json` files in their own directory so the WebUI can display plugin names, descriptions, and configuration text in the current language.

## Directory Structure

```text
your_plugin/
  metadata.yaml
  _conf_schema.json
  .astrbot-plugin/
    i18n/
      zh-CN.json
      en-US.json
```

Locale file names use WebUI locales, such as `zh-CN.json` and `en-US.json`. Each file must contain a JSON object.

When the current locale has no translation, a field is missing, or the locale file does not exist, AstrBot falls back to the default text:

- Plugin names, card short descriptions, and descriptions fall back to `display_name`, `short_desc`, and `desc` in `metadata.yaml`.
- Configuration text falls back to `description`, `hint`, and `labels` in `_conf_schema.json`.
- Page text falls back to the Page directory name, default Page title, or fallback text provided by page code.

## Metadata

`metadata` overrides the plugin name, card short description, and description shown on plugin pages.

```json
{
  "metadata": {
    "display_name": "Weather Assistant",
    "short_desc": "One-line weather lookup.",
    "desc": "Query weather and provide travel suggestions."
  }
}
```

## Configuration

`config` overrides text from `_conf_schema.json`. The structure is nested by configuration item name.

Example `_conf_schema.json`:

```json
{
  "enable": {
    "description": "Enable",
    "type": "bool",
    "hint": "Whether to enable this plugin.",
    "default": true
  },
  "mode": {
    "description": "Mode",
    "type": "string",
    "options": ["fast", "safe"],
    "labels": ["Fast", "Safe"]
  }
}
```

Corresponding `.astrbot-plugin/i18n/zh-CN.json`:

```json
{
  "config": {
    "enable": {
      "description": "启用",
      "hint": "是否启用这个插件。"
    },
    "mode": {
      "description": "模式",
      "labels": ["快速", "安全"]
    }
  }
}
```

`options` are stored configuration values and should usually not be translated. Use `labels` for select display text.

## Plugin Pages

`pages` overrides plugin Dashboard Page titles, descriptions, and custom text inside plugin pages. The structure is nested by Page directory name.

Example plugin page directory:

```text
pages/
  settings/
    index.html
```

Corresponding `.astrbot-plugin/i18n/en-US.json`:

```json
{
  "pages": {
    "settings": {
      "title": "Settings",
      "description": "Manage advanced settings for this plugin.",
      "save": "Save",
      "reset": "Reset"
    }
  }
}
```

`title` is used by the WebUI shell title and the Page component name on the plugin detail page. `description` is used by the Page component description on the plugin detail page. Other fields are read by the page through the bridge:

```js
const bridge = window.AstrBotPluginPage;

function render() {
  document.getElementById("save").textContent = bridge.t(
    "pages.settings.save",
    "Save",
  );
}

await bridge.ready();
render();
bridge.onContext(render);
```

Use `onContext()` to react to WebUI language changes; with this listener, the Page usually does not need a refresh.

## Nested Configuration

For `object` items in `_conf_schema.json`, translations use the same nested field structure.

```json
{
  "config": {
    "sub_config": {
      "name": {
        "description": "Name",
        "hint": "The name shown in messages."
      }
    }
  }
}
```

## Template Lists

`template_list` template names and fields can also be translated. Put template names under `templates.<template>.name`, then continue nesting for fields inside the template.

```json
{
  "config": {
    "rules": {
      "description": "Rules",
      "templates": {
        "default": {
          "name": "Default template",
          "threshold": {
            "description": "Threshold",
            "hint": "Triggers the rule after reaching this value."
          }
        }
      }
    }
  }
}
```

## Complete Example

Here is an English translation example for a real configuration:

```json
{
  "metadata": {
    "display_name": "HAPI Vibe Coding Remote",
    "desc": "Connect to a HAPI service and control coding agent sessions from chat platforms."
  },
  "config": {
    "hapi_endpoint": {
      "description": "HAPI service URL",
      "hint": "Example: http://localhost:3006"
    },
    "output_level": {
      "description": "SSE delivery level",
      "hint": "silence: permission requests only; simple: plain text messages and system events; summary: recent N messages when a task completes; detail: all messages in real time",
      "labels": ["Silence", "Simple", "Summary", "Detail"]
    }
  }
}
```

## Constraints

Plugin internationalization only reads the `.astrbot-plugin/i18n` directory. Locale files must use nested JSON objects; dot-key flat entries are not supported.
