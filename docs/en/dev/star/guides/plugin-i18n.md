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

## Multilingual command names and descriptions

Besides pages and config text, plugin **command names** and **descriptions** can also be
localized.

### Command aliases (multilingual names)

Use `multi_alias()` exported from `astrbot.api.star` to register multilingual aliases:

```python
from astrbot.api.star import multi_alias

@filter.command(
    "weather",
    desc="Get weather",
    alias=multi_alias(zh="天气", ru="погода", jp="天気"),
)
async def weather(self, event, city: str): ...
```

- `/weather`, `/天气`, `/погода` and `/天気` all trigger the same handler.
- **The main command (`/weather`) is always available**, regardless of language.
- Which aliases are accepted depends on the WebUI toggle
  "Other settings → All-language aliases":
  - **Off (default)**: only aliases matching the **current session language** are
    accepted (e.g. with `zh-CN`, `/天气` works but `/погода` does not);
  - **On**: aliases in every language are accepted.
- A plain `set` (legacy form, `alias={"天气"}`) carries no language information and is
  therefore treated as an all-language alias, unaffected by the toggle.

### Command descriptions (multilingual)

`@filter.command` supports the `desc_i18n` field for per-language descriptions:

```python
@filter.command(
    "weather",
    desc="Get weather",  # fallback text
    desc_i18n={
        "zh-CN": "获取天气",
        "en-US": "Get weather",
        "ru-RU": "Узнать погоду",
        "ja-JP": "天気を取得",
    },
)
async def weather(self, event, city: str): ...
```

Resolution order: `desc_i18n[current language]` → `desc` → function docstring.
The WebUI **command management page** and **plugin detail page** render the description
in the current WebUI locale. (The built-in `/help` command only lists built-in commands,
so plugin descriptions do not appear there.)

### Getting the current language at runtime (localized results)

To localize **reply content**, use `get_lang()`:

```python
from astrbot.api.star import get_lang

@filter.command("weather")
async def weather(self, event, city: str):
    lang = await get_lang(self.context, event.unified_msg_origin)
    # lang: "zh-CN" | "en-US" | "ru-RU" | "ja-JP"
    text = LOCALE["sunny"].get(lang, LOCALE["sunny"]["en-US"])
    yield event.plain_result(text.format(city=city))
```

- `context.get_lang(umo)` is equivalent and can be called directly on the plugin context.
- The framework does not translate plugin text; maintain your own translation table and
  fall back to `en-US` or `zh-CN` when a language is missing.
- The language comes from the **global `language` config**
  (`data/cmd_config.json`, default `en-US`).

### User-facing language setting

The language is a **global setting** shared by all sessions; per-session overrides are
not supported. Users view or change it with the built-in `/lang` command (built-in
command names stay in English):

```text
/lang              → show the current global language
/lang zh|en|ru|jp  → set the global language (admin only)
/lang reset        → restore the default language en-US (admin only)
```

Administrators can also edit the `language` field in `data/cmd_config.json`
(default `en-US`). An unrecognized value falls back to `en-US`, with a startup warning
and a hint in `/lang`.

> In the WebUI, **command names** follow this global setting (the matching
> `multi_alias` alias), while **command descriptions** follow the WebUI locale.

## Compatibility with older AstrBot versions

`multi_alias()`, `get_lang()` and `desc_i18n` are only available in newer AstrBot
releases. Installing such a plugin on an older AstrBot makes
`from astrbot.api.star import get_lang` raise `ImportError`, so the plugin fails to load
(only that plugin is affected; AstrBot and other plugins keep running).

Pick one of the following:

### 1. Declare the minimum required version (recommended)

Add `astrbot_version` to `metadata.yaml`; AstrBot validates it before loading and shows a
clear message:

```yaml
astrbot_version: ">=4.28.0"
```

### 2. Graceful degradation in code (works on both old and new versions)

```python
try:
    from astrbot.api.star import get_lang, multi_alias
except ImportError:  # older AstrBot without these APIs

    async def get_lang(context, umo=None):
        return "zh-CN"  # fall back to a fixed language

    def multi_alias(**langs):
        return set(langs.values())  # aliases still work (without language info)
```

The plugin then loads on older versions too, just without multilingual behavior.
