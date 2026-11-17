# Plugin views

Build HTML interfaces in your plugin and connect them to AstrBot through the Bridge. Choose `target` in metadata based on where users work with the interface:

| Interface | `target` | Use cases | How it opens |
| --- | --- | --- | --- |
| [Standalone plugin page](./plugin-page.md) | `plugin_page` | Settings, dashboards, logs | WebUI plugin entry |
| [Interactive message component](./chat-message.md) | `chat_message` | Result lists, selectors, confirmation forms | A command, message handler, or tool returns `event.view_result()` |
| [Workbench page](./workbench.md) | `chat_workbench` | File previews, notes, session analysis | `event.view_result()` |
| [Workbench with launcher](./workbench.md#register-a-resident-page) | `chat_workbench_with_launcher` | Notes, session analysis | `event.view_result()` or the workbench **+** entry |

## Register a view

Declare views under `views` in the plugin's `metadata.yaml`. Names must be unique within the plugin. Entry files follow `views/<name>/index.html`; no `entry` field is needed. Python creates instances, handles actions, and provides Web APIs.

```yaml
views:
  - name: context_usage
    target: chat_workbench_with_launcher
    title: Context usage
    description: Inspect token usage for the current session
```

The default target is `plugin_page`, preserving existing page declarations. Set `chat_message` for message components, `chat_workbench` for plugin-opened workbench views, or `chat_workbench_with_launcher` to also offer the view in the **+** launcher. ChatUI targets stay out of the standalone page list. Undeclared directories remain discoverable as standalone pages.

`title` and `description` provide default labels; i18n overrides each field as described in [View labels](./bridge.md#view-labels). `version` defaults to `1`. `actions` lists permitted callbacks for message-created instances and defaults to an empty list. Standalone pages cannot declare actions.

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
