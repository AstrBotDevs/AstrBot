# AstrBot Star

Starting from version `3.4.0`, AstrBot renamed plugins to `Star`. AstrBot is a highly modular project, and plugins leverage this modularity to implement various functionalities.

<span style="color: gray">~~Use `/plugin` to view all plugins.~~ (Archived: the `/plugin` and other extended commands have moved to the `builtin_commands_extension` plugin, which is not installed by default)</span> Manage plugins on the `Plugins` page in the WebUI sidebar.

The `Plugins` page contains the following tabs:

- `Plugins`: view, enable/disable, update, and uninstall installed plugins, and install local plugins.
- `Plugin Market`: browse the plugin market powered by AstrBot Cloud (<https://cloud.astrbot.app>), with sorting by downloads and update times shown in plugin details.
- `MCP`: manage MCP servers. See [MCP](/en/use/mcp) for details.
- `Skills`: manage Skills. See [Skills](/en/use/skills) for details.
- `Handlers`: centrally manage commands and function tools registered by plugins (command management).

## Installing Plugins

Click the + button in the bottom right corner of the `Plugins` page. The following installation methods are supported:

- One-click installation from the plugin market.
- A repository URL, including HTTP(S), SSH, and SCP-style Git repositories (since v4.27.0).
- A local directory, to install a local plugin (since v4.26.3).
- A manual file upload.

You can also manage plugins with the CLI. See [CLI Commands](/en/use/cli) for details.

## Managing Plugins

- A plugin's enabled state is independent of the enabled state of the LLM tools it registers (since v4.26.2). Both can be controlled individually in the `Handlers` tab, with per-tool permission configuration.
- Each plugin can have its own log level (since v4.26.8), which makes per-plugin troubleshooting easier.
- Plugin configuration supports one-click restore to defaults (since v4.27.3).
- Uninstalling a plugin also clears its KV storage data.

If you want to develop your own plugin, see [AstrBot Plugin Development Guide](/en/dev/star/plugin-new).
