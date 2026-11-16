# Interactive ChatUI cards

Plugins can create HTML cards from commands, message handlers, UI callbacks, or local LLM tools. Creation is not limited to tool calls. Register each card with `Star.chatui_views`, then yield or return `event.view_result()`.

`filter.ui_action` currently handles **view actions only**. Existing buttons continue to use `filter.button_action` and `ButtonInteraction`.

## Registration and creation

```python
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from astrbot.api import chatui
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Star


class IncrementInput(BaseModel):
    """Validated counter input."""

    model_config = ConfigDict(extra="forbid", strict=True)
    amount: int = Field(ge=1, le=10)


class ViewDemo(Star):
    """Create a card directly from a command."""

    chatui_views = [
        chatui.ViewSpec(
            name="counter",
            entry=Path("views/counter/index.html"),
            target="chat_message",
            version=1,
            actions=["view_demo:increment"],
        ),
    ]

    @filter.command("counter")
    async def counter(self, event: AstrMessageEvent):
        """Create a counter.

        Args:
            event: Incoming command.

        Yields:
            A new card.
        """
        yield event.view_result(
            name="counter", data={"count": 0}, text="Counter created at zero.",
        )

    @filter.ui_action("view_demo:increment")
    async def increment(self, event: AstrMessageEvent):
        """Update the card without invoking the model.

        Args:
            event: Authenticated UI event.

        Yields:
            The replacement card data.
        """
        interaction = event.get_ui_interaction()
        if interaction is None:
            return
        payload = IncrementInput.model_validate(interaction.data)
        yield event.view_result(
            data={"count": interaction.view.data["count"] + payload.amount},
        )
```

Keep the usual plugin `metadata.yaml`. The entry must be `views/<name>/index.html`, with relative scripts, styles, and assets inside that directory.

### Choosing the host

Set `target` on the registered `ViewSpec`, rather than on `event.view_result()`:

| `target` | Location | Creation and interaction |
| --- | --- | --- |
| `chat_message` (default) | Chat message body | Create with `event.view_result()`; use `AstrBotPluginView.view` and `filter.ui_action` |
| `plugin_page` | Independent plugin page in the existing WebUI navigation | Use `window.AstrBotPluginView` to call registered plugin Web APIs |

For example, add an independent page to the same plugin's `chatui_views`:

```python
chatui.ViewSpec(
    name="settings",
    entry=Path("views/settings/index.html"),
    target="plugin_page",
)
```

Chat message views are excluded from the independent page list and the WebUI sidebar. A plugin providing only chat message views has no sidebar page entry. Plugin pages cannot be created with `event.view_result()` or declare chat `actions`. Both targets share the same `AstrBotPluginView` bridge, initialization API, and theme context. Chat cards use `bridge.view`; independent pages use plugin Web APIs, file transfers, and SSE. Each host validates its supported operations.

Undeclared directories under `views/` (or the legacy `pages/`) continue to be discovered as independent pages. Existing `ViewSpec` declarations without `target` remain chat cards. See [plugin views](./plugin-pages.md) for independent page development.

Providing `name` creates a new card, including from a UI callback. Omitting `name` replaces the current interaction's card data and requires a UI event. Creation requires nonempty `text` as a fallback. A local tool can directly `return event.view_result(name=..., data=..., text=...)`: the model receives `text`, while display `data` is not automatically added to its context. Other platforms use the text result without creating an iframe.

## Frontend

Use this `index.html` with an adjacent `app.js`:

```html
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><title>Counter</title></head>
  <body>
    <p id="count"></p>
    <button id="increment" type="button">Add one</button>
    <p id="error" role="alert"></p>
    <script type="module" src="./app.js"></script>
  </body>
</html>
```

```javascript
const bridge = window.AstrBotPluginView;
await bridge.ready();
const view = bridge.view;
const button = document.querySelector("#increment");
const error = document.querySelector("#error");

view.subscribe(({ data }) => {
  document.querySelector("#count").textContent = String(data.count);
});
bridge.onContext(({ locale }) => {
  document.documentElement.lang = locale;
});

button.onclick = async () => {
  button.disabled = true;
  error.textContent = "";
  try {
    await view.action("view_demo:increment", { amount: 1 });
  } catch (failure) {
    error.textContent = failure.message;
  } finally {
    button.disabled = false;
  }
};
```

Both hosts inject the same `/api/plugin/page/bridge-sdk.js`. Await `bridge.ready()` for context. `bridge.view.subscribe()` immediately supplies a snapshot and reports snapshot changes; it returns an unsubscribe function. Use the common `bridge.onContext()` for theme and locale updates. `bridge.view.action()` supplies instance, revision, and request identifiers automatically. Its Promise settles after callback execution and state commit, independently of any subsequent model generation. Errors have `code` and `message` fields.

The bridge injects `--astrbot-color-*` CSS tokens and updates `data-theme` automatically. See [Following user-selected colors](./plugin-pages.md#following-user-selected-colors) for the token list. Theme changes do not start generation or change the card revision. To migrate earlier examples, replace `window.astrbot.view.connect()` with `await AstrBotPluginView.ready()` and then use `AstrBotPluginView.view`. Move `theme` / `locale` subscriptions to the shared `onContext()` API; CSS-only styling can use the tokens directly.

```css
body { color: var(--astrbot-color-text); background: transparent; }
button { color: var(--astrbot-color-primary); border-color: var(--astrbot-color-border); }
```

Bundled Vue or React applications can also be used. Cards run in a sandbox without access to the parent DOM, dashboard credentials, management APIs, or iframe local storage.

## Interaction contract

`event.get_ui_interaction()` returns a `UIInteraction`, or `None` for ordinary messages and buttons:

| Field | Meaning |
| --- | --- |
| `action_id` | Business action name |
| `interaction_id` | Stable identifier for this submission |
| `data` | Untrusted input to validate in the plugin |
| `source` | Currently `view` |
| `source_message_id` | Source message ID, possibly absent before persistence |
| `view.id`, `view.name` | Instance ID and registered name |
| `view.version` | Data/action contract version |
| `view.revision` | Persisted data revision |
| `view.data` | Backend-loaded snapshot, not supplied by the action request |

Actor and conversation information remains on `AstrMessageEvent`. Treat `view.data` as read-only; yield `event.view_result(data=...)` to replace it. Display data is limited to one MiB and action input to 64 KiB. Both must be JSON-compatible.

Handlers can also yield ordinary message results or explicitly request a model response with `event.request_llm(prompt=...)`. A handler chain can update its source card once and request the model once. These results are staged until successful callback completion; already sent messages and external side effects cannot be rolled back. Callbacks have a 120-second execution budget. An ID-less `@filter.ui_action()` receives only the owning plugin's view actions.

## Persistence and boundaries

- Main chat, standalone chat, and threads share the card renderer. Reloading restores data without executing the original command, tool, or callback.
- Increment `version` for incompatible contracts. Older incompatible cards fall back to text; there is no automatic migration. Successful data replacement increments `revision`.
- The backend checks session ownership, source message, plugin availability, session plugin configuration, and declared actions. Plugins must still enforce business permissions.
- Concurrent actions reserve the instance exclusively. Stale input gets `REVISION_CONFLICT` and the latest snapshot. Completed duplicate requests replay their outcome; reusing an ID with different input fails.
- Use `interaction_id` for external business idempotency. An unknown outcome is never automatically executed again. The first version does not recover interrupted callbacks, archive old bundles, push background task updates, or route button events. Model generation uses the existing run lifecycle and is not automatically restarted after process failure.
- Session deletion removes its view records. Removed or edited-away source messages can no longer authorize a card.

The `chat` scope covers `GET /api/v1/chat/views/{view_id}`, `POST .../actions`, and `GET .../actions/{interaction_id}`. Frontend plugins should use the SDK rather than manage authentication themselves.
