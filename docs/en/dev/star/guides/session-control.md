# Session Control

Session control is useful for workflows that need several consecutive inputs
without sending every step to the LLM, such as surveys, games, or guided
configuration.

Use the `messages` capability on the `PluginContext` passed to the plugin. It
registers a wait for the current message's session without exposing internal
runtime registries:

```python
import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
```

This example waits for subsequent messages in the same session after receiving
`/idiom-chain`:

```python
@filter.command("idiom-chain")
async def idiom_chain(self, event: AstrMessageEvent):
    yield event.plain_result('Send a four-character idiom, or "exit" to stop.')

    async def waiter(controller, next_event: AstrMessageEvent) -> None:
        idiom = next_event.message_str.strip()

        if idiom == "exit":
            await next_event.send(next_event.plain_result("Idiom chain ended.").chain)
            controller.stop()
            return

        if len(idiom) != 4:
            await next_event.send(
                next_event.plain_result(
                    "The idiom must contain four characters. Try again."
                ).chain
            )
            controller.keep(timeout=60, reset_timeout=True)
            return

        result = next_event.make_result()
        result.chain = [Comp.Plain("先见之明")]
        await next_event.send(result.chain)

        # Wait for another message and restart the 60-second timeout.
        controller.keep(timeout=60, reset_timeout=True)

    try:
        await self.context.messages.wait_for(
            event,
            waiter,
            timeout_seconds=60,
            record_history_chains=False,
        )
    except TimeoutError:
        yield event.plain_result("The session timed out.")
    except Exception:
        logger.exception("Idiom-chain session failed")
        yield event.plain_result(
            "The session ended unexpectedly. Contact the administrator."
        )
    finally:
        event.stop_event()
```

The callback already handles a subsequent event, so it cannot use `yield`.
Send results with `await next_event.send(...)` instead. The
`await self.context.messages.wait_for(...)` call remains pending until
`controller.stop()`, a timeout, or an exception from the callback.

## Default Session Key

`messages.wait_for()` uses `event.unified_msg_origin` as its session key, not
only `sender_id`. This string identifies the platform instance and
corresponding conversation. Only later events that produce the same
`unified_msg_origin` enter the active wait.

Custom session filters are not part of the plugin SDK. Do not import
`astrbot.core.utils.session_waiter`; internal runtime interfaces may change.

## Wait Controller

The callback receives a controller for this one wait. Its type is intentionally
not imported by plugins; use the controller passed to the callback.

- `keep(timeout, reset_timeout=True)` keeps waiting and restarts the specified
  timeout from now.
- `keep(timeout, reset_timeout=False)` adds `timeout` to, or subtracts it from,
  the remaining time. A resulting timeout at or below zero ends the session.
- `stop()` ends the session immediately.
- `get_history_chains()` returns recorded message chains. Subsequent inputs are
  recorded only when `messages.wait_for()` uses `record_history_chains=True`.

When a wait times out, `await self.context.messages.wait_for(...)` raises
`TimeoutError`. Handle timeouts and other errors at the outer level, and stop
any other long-running tasks created by the plugin in `terminate()`.
