# Plugin feature patterns

Load only the section that matches the requested feature. The examples are
patterns, not permission to import AstrBot internals.

## Command

```python
from astrbot.api.event import AstrMessageEvent, filter


@filter.command("hello")
async def hello(self, event: AstrMessageEvent):
    """Reply to a simple command."""
    yield event.plain_result(f"Hello, {event.get_sender_name()}!")
```

Use `filter.command_group()` for a resource with subcommands. Follow Orbit
Command Syntax: use lowercase explicit command names, typed scalar parameters,
`GreedyStr` for trailing free text, and `filter.option()` for named options.
Never re-split `event.message_str` or implement shell expansion in a handler.

Source: [events and Orbit commands](https://github.com/Xero-Team/AstrBot/blob/master/docs/zh/dev/star/guides/listen-message-event.md).

## Messages and sessions

- Yield `event.plain_result()` or `event.chain_result()` for a passive reply.
- For delayed delivery, persist `event.unified_msg_origin` as user data and call `await self.context.messages.send(...)`; inspect `PlatformSendResult.success`.
- For a multi-turn flow, call `self.context.messages.wait_for(...)`, send from the callback with `await next_event.send(...)`, handle `TimeoutError`, and stop plugin-owned work in `terminate()`.

Sources: [message sending](https://github.com/Xero-Team/AstrBot/blob/master/docs/zh/dev/star/guides/send-message.md) and [session control](https://github.com/Xero-Team/AstrBot/blob/master/docs/zh/dev/star/guides/session-control.md).

## AI and tools

Choose the smallest public capability:

| Need                                      | Public API                                          |
| ----------------------------------------- | --------------------------------------------------- |
| Continue the normal conversation pipeline | `yield event.request_llm(...)`                      |
| One direct model request                  | `await self.context.models.generate(...)`           |
| Bounded model/tool loop                   | `await self.context.models.tool_loop(...)`          |
| Register a model-callable plugin tool     | `@filter.llm_tool` or `self.context.tools.add(...)` |

Use the current session's provider selection when applicable. Bound tool steps
and timeouts, pass only the required tools, mock providers in unit tests, and
redact provider failures.

Source: [calling AI from a plugin](https://github.com/Xero-Team/AstrBot/blob/master/docs/zh/dev/star/guides/ai.md).

## Platform actions

For ordinary sending or actions, use `context.messages` and
`context.platform_actions`. For OneBot capabilities, use
`context.onebot.event(event)`, `context.onebot.for_event(event)`, and
`supports(...)`; catch the typed capability and timeout errors. Do not access
adapter clients or raw action methods.

Source: [OneBot plugin API](https://github.com/Xero-Team/AstrBot/blob/master/docs/zh/dev/star/guides/onebot.md).

## Dashboard Extension

Use this branch only when the user requests a plugin Dashboard page. Read the
full [Dashboard Extension Protocol v1 guide](https://github.com/Xero-Team/AstrBot/blob/master/docs/zh/dev/star/plugin-dashboard-extension.md).
Declare `requires.dashboard_extension: 1` and `dashboard` together; use a
content-addressed `assets.v1.json`; register typed Actions only inside
`initialize()`; keep the page in the sandboxed iframe and never proxy arbitrary
Dashboard HTTP requests or expose authentication state.

## Internationalization and plugin Skills

Use `.astrbot-plugin/i18n/zh-CN.json` and `en-US.json` only when localized
metadata or configuration text is needed. Add `skills/<skill-name>/SKILL.md`
only when the generated AstrBot plugin itself must provide a runtime Skill;
that Skill is read-only and managed by the plugin.

Source: [plugin internationalization](https://github.com/Xero-Team/AstrBot/blob/master/docs/zh/dev/star/guides/plugin-i18n.md) and [plugin Skills](https://github.com/Xero-Team/AstrBot/blob/master/docs/zh/dev/star/plugin-new.md#%E9%9A%8F%E6%8F%92%E4%BB%B6%E6%8F%90%E4%BE%9B-skills%EF%BC%88%E5%8F%AF%E9%80%89%EF%BC%89).
