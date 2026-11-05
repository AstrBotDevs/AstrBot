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

README files can also be provided per language. AstrBot checks the full locale first, then the short language, and finally falls back to `README.md`:

```text
README.md
README_zh-CN.md
README_zh.md
README.zh.md
README_en-US.md
README_en.md
```

The `README_<locale>.md`, `README-<locale>.md`, and `README.<locale>.md` forms are supported, and filename matching is case-insensitive. If there is no default README but the plugin provides exactly one localized README, AstrBot displays that file. For uninstalled GitHub plugins in the marketplace, AstrBot checks the default branch using the same order. Non-GitHub repositories must provide a `readme_url` from the plugin registry.

When the current locale has no translation, a field is missing, or the locale file does not exist, AstrBot falls back to the default text:

- Plugin names, card short descriptions, and descriptions fall back to `display_name`, `short_desc`, and `desc` in `metadata.yaml`.
- Configuration text falls back to `description`, `hint`, `labels`, and `subtitles` in `_conf_schema.json`.
- Page text falls back to the Page directory name, default Page title, or fallback text provided by page code.

## Metadata

`metadata` overrides the plugin name, card short description, and description shown on plugin pages.

Sidebar plugin group headings, hover cards, and default titles that use the plugin name also read `metadata.display_name` for the current locale and update immediately when the language changes. The sidebar accepts only nonempty strings; missing, blank, or invalid translations fall back to the original `display_name`, then `name`. The existing precedence of `views.<view>.title` over `pages.<view>.title` stays unchanged; grouped views without a valid title still show their directory name. Routes, pinned items, and expanded groups use stable plugin IDs or view paths and do not change with translated names.

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
    "labels": ["Fast", "Safe"],
    "subtitles": ["Faster responses", "More conservative processing"]
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
      "labels": ["快速", "安全"],
      "subtitles": ["更快响应", "更保守的处理"]
    }
  }
}
```

`options` are stored configuration values and should usually not be translated. Use `labels` for select display text. Use `subtitles` for descriptions below each option, aligned with `options` by index.

## Plugin Views

`views` overrides plugin Dashboard View titles, descriptions, and custom text inside plugin views (`pages` is accepted as an alias). The structure is nested by view directory name.

Example plugin view directory:

```text
views/
  settings/
    index.html
```

Corresponding `.astrbot-plugin/i18n/en-US.json`:

```json
{
  "views": {
    "settings": {
      "title": "Settings",
      "description": "Manage advanced settings for this plugin.",
      "save": "Save",
      "reset": "Reset"
    }
  }
}
```

`title` is used by the sidebar, the WebUI shell title, and the view component name on the plugin detail page. `description` is used by the view component description on the plugin detail page. Other fields are read by the page through the bridge:

```js
const bridge = window.AstrBotPluginView;

function render() {
  document.getElementById("save").textContent = bridge.t(
    "views.settings.save",
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
