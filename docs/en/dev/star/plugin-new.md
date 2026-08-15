---
outline: deep
---

# AstrBot Plugin Development Guide

AstrBot plugins, also called Stars, are Python packages loaded into the AstrBot
process. A plugin should depend only on the public SDK under `astrbot.api`. Do
not import internal objects from `astrbot.core`, concrete platform adapters, or
provider implementations.

## Prepare the Environment

This repository and its plugins target Python 3.14+. Prepare an AstrBot source
checkout first:

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

Keep the plugin in a separate Git repository outside the AstrBot checkout, then
link it into `data/plugins/` with an editable install:

```bash
uv run astrbot plug install --editable ../astrbot_plugin_example
uv run main.py
```

An editable install creates a directory symlink, so source changes do not need
to be copied repeatedly. On Windows, enable Developer Mode or run with the
permissions required to create that link.

A minimal plugin layout is:

```text
astrbot_plugin_example/
  metadata.yaml
  main.py
  README.md
  requirements.txt  # Only needed for third-party dependencies
```

## Plugin Metadata

`metadata.yaml` must contain `name`, `desc`, `version`, and `author`:

```yaml
name: astrbot_plugin_example
desc: A minimal AstrBot plugin
version: 0.1.0
author: Your Name
repo: https://github.com/your-org/astrbot_plugin_example
```

`name` is used both as a Python module name and as the installed plugin
directory. It must therefore:

- be a valid Python identifier and not a Python keyword such as `class` or
  `from`;
- contain no slash, backslash, hyphen, space, or other invalid identifier
  character;
- preferably use a lowercase `astrbot_plugin_<name>` form, with the repository
  directory using the same name.

For example, `astrbot_plugin_weather` is valid, while
`astrbot-plugin-weather` and `astrbot/plugin/weather` are not. AstrBot rejects
a plugin that omits a required field or has an invalid `name`.

### Display Information (Optional)

`display_name` is the readable name shown in the WebUI and plugin marketplace.
`short_desc` is the one-line card description and falls back to `desc` when
omitted:

```yaml
display_name: Example Plugin
short_desc: Describe the plugin in one line.
```

Names and descriptions can also follow the WebUI language. See
[Plugin Internationalization](./guides/plugin-i18n).

### Logo (Optional)

Place `logo.png` in the plugin root to provide a logo. A 1:1 aspect ratio and a
256×256 image are recommended.

![Plugin logo example](https://files.astrbot.app/docs/source/images/plugin/plugin_logo.png)

### Declare Supported Platforms (Optional)

`support_platforms` is a list of platform adapter IDs displayed by the WebUI:

```yaml
support_platforms:
  - webchat
  - telegram
  - discord
```

The currently recognized IDs are:

- `aiocqhttp`
- `qq_official`
- `qq_official_webhook`
- `telegram`
- `wecom`
- `wecom_ai_bot`
- `lark`
- `dingtalk`
- `discord`
- `slack`
- `kook`
- `vocechat`
- `weixin_official_account`
- `weixin_oc`
- `satori`
- `misskey`
- `line`
- `matrix`
- `mattermost`
- `webchat`

This field declares compatibility; it does not automatically prevent handlers
from receiving other platforms. Use public event filters when a runtime
restriction is required.

### Declare an AstrBot Version Range (Optional)

`astrbot_version` uses a PEP 440 version specifier without a `v` prefix:

```yaml
astrbot_version: '>=4.26,<5'
```

AstrBot normally blocks the plugin when the running version does not satisfy
the constraint. The WebUI install flow can explicitly override that warning,
so plugin code should still avoid relying on undeclared internal behavior.

### Bundle Skills (Optional)

A plugin can provide a `skills/` directory. AstrBot registers valid Skills
inside it as read-only sources managed by that plugin:

```text
astrbot_plugin_example/
  metadata.yaml
  main.py
  skills/
    web-search-helper/
      SKILL.md
    report-writer/
      SKILL.md
```

If `skills/` itself is one Skill, place `skills/SKILL.md` directly inside it.
Plugin-provided Skills can be enabled or disabled in the WebUI, but they cannot
be edited or deleted as Local Skills. They change with the plugin files when
the plugin is updated or removed.

## Minimal Plugin

The plugin class in `main.py` inherits from the public `Star` class and accepts
a capability-scoped `PluginContext`:

```python
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import PluginContext, Star


class ExamplePlugin(Star):
    def __init__(self, context: PluginContext):
        super().__init__(context)

    async def initialize(self) -> None:
        """Called after the plugin is loaded and activated."""
        logger.info("ExamplePlugin initialized")

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        """Reply with a greeting."""
        yield event.plain_result(f"Hello, {event.get_sender_name()}!")

    async def terminate(self) -> None:
        """Called when the plugin stops, reloads, or AstrBot shuts down."""
        logger.info("ExamplePlugin terminated")
```

Use `initialize()` to create runtime resources such as clients or tasks.
`terminate()` must release them by cancelling background work, closing HTTP
clients, and releasing file handles. Do not replace explicit lifecycle cleanup
with the deprecated destructor path.

## Plugin Logging

Use `self.logger` inside a `Star` instance or `from astrbot.api import logger`
from plugin modules. AstrBot routes both forms to the live plugin's dedicated
logger. In the Dashboard's plugin configuration dialog, select a level for the
plugin or choose **Follow Global**. The setting takes effect immediately and
survives restarts; it is cleared when **Follow Global** is selected.

Before adding parameters, subcommands, or options, read the
[Orbit Command Design Specification](./guides/listen-message-event#orbit-command-design-specification).
It defines command-header naming, deterministic argument syntax, supported
handler signatures, and Telegram/Discord native-command constraints.

## Debug the Plugin

After changing plugin code, open the plugin menu in the WebUI and select
**Reload Plugin**. If loading fails, inspect the startup log or the error shown
on the management page, fix the code, and use the one-click reload action.

The first two handler parameters must be `self` and `event`. Business logic may
live in other modules in the plugin package, but event handlers themselves must
be registered on the plugin class.

## Dependencies and Data

Add `requirements.txt` to the plugin root when third-party packages are needed.
Those packages must support Python 3.14; do not add compatibility branches for
Python 3.10–3.13.

Do not write persistent data into the plugin source directory because an update
or reinstall can replace it. Use `self.context.storage.data_directory()` as
described in [Plugin Storage](./guides/storage).

## Development Principles

- Test features and regressions.
- Use only the public plugin interfaces under `astrbot.api`.
- Give long-lived tasks, clients, and files an explicit termination path.
- Use asynchronous HTTP clients such as `aiohttp` or `httpx`; do not call
  synchronous `requests` inside the event loop.
- Run Ruff formatting and checks before committing Python code.
- Prefer contributing an extension to an existing plugin unless it is no
  longer maintained.
- When a plugin directly draws on another project's design, feature ideas, or
  implementation approach, acknowledge that source in the README and link to
  the relevant project.
- When using, modifying, or porting another project's code or assets, follow
  its license and retain the required copyright and license notices.
