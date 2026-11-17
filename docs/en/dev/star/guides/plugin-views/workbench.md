# Workbench page

> [!NOTE]
> Currently supported only in AstrBot ChatUI.

Use `target="chat_workbench"` to display an interface beside the conversation. Open file previews from messages or tools, or register resident pages such as notes and session analytics in the workbench **+** entry.

![Resident context-usage workbench with token estimates by source (Chinese UI)](/images/plugin-views/context-workbench.jpg)

Download the [context-usage example plugin](/examples/astrbot_plugin_context_workbench.zip). Open a ChatUI session, click the workbench **+**, and select **上下文用量 (Context usage)** from **New workbench**. No tool call is needed. The page receives the current `sessionId` through the bridge context and shows token estimates for system instructions, tool definitions, conversation, and tool results.

Send a message, then click **Refresh** to see the latest request breakdown. Sources not yet observed appear as unknown. Counts are estimates, not the model's billed token usage. See [Add a resident entry](#register-a-resident-page) for registration.

## Open from a message or tool

Register a `preview` view and return `event.view_result()` from a tool. Set the tab label with `title`; the message retains a reopening entry. Hosts without a workbench, such as thread panels, render the view inside the message.

```python
from pathlib import Path

from astrbot.api import chatui
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Star

class PreviewPlugin(Star):
    chatui_views = [
        chatui.ViewSpec(
            name="preview",
            entry=Path("views/preview/index.html"),
            target="chat_workbench",
        ),
    ]

    @filter.llm_tool(name="open_preview")
    async def open_preview(self, event: AstrMessageEvent):
        """Open a preview in the workbench.

        Args:
            event: Incoming tool event.

        Returns:
            A view and a text result for the model.
        """
        return event.view_result(
            name="preview",
            title="Notes",
            data={"content": "Notes to review."},
            text="Opened notes in the workbench.",
        )
```

Display the returned data in `views/preview/index.html` and an adjacent `app.js`:

```html
<!doctype html>
<html>
  <head><meta charset="utf-8" /><title>Notes</title></head>
  <body>
    <pre id="content"></pre>
    <script type="module" src="./app.js"></script>
  </body>
</html>
```

```javascript
const bridge = window.AstrBotPluginView;
await bridge.ready();
bridge.view.subscribe(({ data }) => {
  document.getElementById("content").textContent = data.content;
});
```

After the tool runs, the workbench displays a **Notes** tab with the returned text. For callbacks, declare `actions` and use `bridge.view.action()` as shown in [Interactive message component](./chat-message.md).

## Register a resident page

A launcher view needs no message or tool call:

```python
chatui.ViewSpec(
    name="context",
    entry=Path("views/context/index.html"),
    target="chat_workbench",
    launcher=True,
    title="Context usage",
    description="Inspect the current session's capacity and sources.",
)
```

Add this declaration to `Star.chatui_views`, create its entry file, and reload the plugin. Open the workbench from the ChatUI header, click **+**, then select **Context usage**. Each registered view has one tab per session.

Launcher views reuse the standalone plugin page host and its authenticated plugin Web APIs, file transfers, and SSE bridge. They do not declare message `actions` or receive a `context.view` snapshot. `sessionId` identifies the active chat session, or is `null` when none is open. Switching sessions mounts the selected session's views with their own context:

```javascript
const bridge = window.AstrBotPluginView;
await bridge.ready();
bridge.onContext(({ sessionId }) => {
  // Fetch session-specific aggregates from your authenticated plugin API.
  if (sessionId) bridge.apiGet("usage", { session_id: sessionId });
});
```

The plugin backend must validate session ownership against `request.username`; a client-supplied session ID is not authorization. Guard asynchronous requests against stale responses after a session switch. All targets share theme CSS tokens and `onContext()`.

## Fill or send a chat message from a resident view

These methods are available only to resident `chat_workbench` views without `context.view`. Bind them to user actions:

```javascript
await bridge.chat.fill("Please revise this passage.");
await bridge.chat.send("Please summarize my selection.");
```

`fill` appends text to the current draft and focuses the composer. `send` sends directly to the current session while preserving the existing draft and staged attachments. Sending is rejected if there is no session, the session changed, or generation is already running. The promise settles when the send request is accepted, rather than after the bot finishes replying.

For agent-assisted document editing, record the user's selection and revision in the plugin backend. Let the tool accept a selection ID and replacement text, and enforce the edit range in code. After saving, use plugin SSE to notify the resident view to reload the document while protecting unsaved local edits.

## Local preference storage

Tab lists, active tabs, and open/hidden state are stored in the browser per user and session. Switching sessions restores the corresponding workbench; reloading does not reopen closed tabs. Persist plugin business data in the plugin backend.

See the [shared Bridge API](./bridge.md) for themes, file transfers, and SSE, and [backend Web APIs](./web-api.md) for authentication and data access.
