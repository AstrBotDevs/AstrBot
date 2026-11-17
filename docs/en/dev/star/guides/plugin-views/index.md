# Plugin views

Build HTML interfaces in your plugin and connect them to AstrBot through the Bridge. Choose `ViewSpec.target` based on where users work with the interface:

| Interface | `target` | Use cases | How it opens |
| --- | --- | --- | --- |
| [Standalone plugin page](./plugin-page.md) | `plugin_page` | Settings, dashboards, logs | WebUI plugin entry |
| [Interactive message component](./chat-message.md) | `chat_message` | Result lists, selectors, confirmation forms | A command, message handler, or tool returns `event.view_result()` |
| [Workbench page](./workbench.md) | `chat_workbench` | File previews, notes, session analysis | `event.view_result()` or the workbench **+** entry |

## Register a view

Declare a `chatui.ViewSpec` in your plugin's `Star.chatui_views`. Each `name` must be unique within the plugin, with an entry at `views/<name>/index.html`. Set `target` at registration, not on `event.view_result()`.

The default target is `chat_message`. Message and workbench views do not appear in the standalone plugin page list. Undeclared directories under `views/` are still discovered as standalone pages.

For a few configuration fields, use [plugin configuration](../plugin-config.md).

## Choose an interaction API

- **Message components and message-created workbench pages**: call `@filter.ui_action` through `bridge.view.action()`. Replace view data with `event.view_result(data=...)`.
- **Standalone pages and resident workbench pages**: call the plugin's [backend Web APIs](./web-api.md) through `bridge.apiGet()`, `apiPost()`, and related methods.

All interfaces share initialization, themes, and localization through the [Bridge API](./bridge.md). See the [capability table](./bridge.md#capabilities) for the operations available in each host.

::: details Previous documentation entries

| Previous entry | Current entry |
| --- | --- |
| Plugin Views (`plugin-pages.md`) | Standalone plugin page, Shared Bridge API, and Backend Web APIs in this section |
| Interactive ChatUI cards (`chatui-views.md`) | Interactive message component and Workbench page in this section |

Previous links redirect to the corresponding page.
:::
