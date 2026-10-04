# AstrBot Star

Starting from version `3.4.0`, AstrBot renamed plugins to `Star`. AstrBot is a highly modular project, and plugins leverage this modularity to implement various functionalities.

Use `/plugin` to view all plugins. You can also manage installed plugins in the admin panel under `Extensions → Plugins` (`/extension/plugins`). Open `AstrBot Plugin Market` (`/extension/plugins/market`) to search for and install plugins. Skills, MCP servers, and handlers have their own tabs at the top of the Extensions workspace.

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
