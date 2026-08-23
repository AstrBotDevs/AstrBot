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

AstrBot supports only `zh-CN.json` and `en-US.json`. Each file must contain a JSON object.

When the current locale has no translation, a field is missing, or the locale file does not exist, AstrBot falls back to the default text:

- Plugin names, card short descriptions, and descriptions fall back to `display_name`, `short_desc`, and `desc` in `metadata.yaml`.
- Configuration text falls back to `description` and `hint` in `_conf_schema.json`.

## Metadata

`metadata` overrides the plugin name, card short description, and description shown in plugin listings.

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
      "description": "模式"
    }
  }
}
```

`options` are stored configuration values and must not be translated. The current i18n resolver reliably returns strings only and cannot translate a `labels` array. Keep select `labels` directly in `_conf_schema.json`, or use the stored values as display text for now.

## Command Replies

`commands` holds runtime command replies. Read them with `context.i18n.t(event, message_key, **kwargs)`. Locale order is the event extra `locale`, then the session preference `locale`, then `zh-CN`. A missing key falls back to `en-US`, then to the key itself.

```json
{
  "commands": {
    "variable.set.ok": "Stored {key} for this session. Use /variable unset to remove it."
  }
}
```

```python
text = await self.context.i18n.t(event, "variable.set.ok", key=key)
```

Do not hardcode mixed Chinese/English user-visible strings in Python. Command handlers should `stop_event()` after they reply.

## Plugin Dashboard Pages

Titles and descriptions for plugin Dashboard Pages (custom WebUI pages a plugin provides under its `pages/` directory) can also be translated through the `pages` field, nested by page name:

```json
{
  "pages": {
    "overview": {
      "title": "Overview",
      "description": "View the plugin's runtime status and statistics."
    }
  }
}
```

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
      "hint": "silence: permission requests only; simple: plain text messages and system events; summary: recent N messages when a task completes; detail: all messages in real time"
    }
  }
}
```

## Constraints

Plugin internationalization reads only `.astrbot-plugin/i18n`. Locale files must use nested JSON objects; dot-key flat entries are not supported. The runtime skips a locale file unless its name is `zh-CN` or `en-US`, or when it exceeds 1 MiB, has an empty or longer-than-32-character locale name, contains invalid JSON, or has a non-object root.

Use strings for translated leaf values. Arrays and objects are not stable WebUI translation values today; in particular, do not override a `labels` array in a locale file.
