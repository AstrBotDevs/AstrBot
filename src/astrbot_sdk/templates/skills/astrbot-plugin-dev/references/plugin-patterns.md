# Plugin Patterns

Complete, working plugin examples. Each pattern includes `main.py`, `plugin.yaml`, and a test snippet.

---

## Pattern 1: Simple Command Plugin

A basic command with aliases and typed parameters.

**main.py:**
```python
from astrbot_sdk import Context, MessageEvent, Star
from astrbot_sdk.decorators import on_command


class GreetPlugin(Star):
    @on_command("greet", aliases=["hi", "hello"], description="Greet the user")
    async def greet(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply(f"Hello, {event.sender_name}!")
```

**plugin.yaml:**
```yaml
name: astrbot_plugin_greet
display_name: Greet
desc: Simple greeting plugin
author: dev
version: 1.0.0
runtime:
  python: "3.12"
components:
  - class: main:GreetPlugin
```

**test:**
```python
@pytest.mark.asyncio
async def test_greet():
    async with PluginHarness.from_plugin_dir(plugin_dir) as h:
        records = await h.dispatch_text("greet")
    assert any("Hello" in r.text for r in records)
```

---

## Pattern 2: CRUD KV Store Plugin

Full create/read/update/delete with `ctx.db`.

**main.py:**
```python
from astrbot_sdk import Context, GreedyStr, MessageEvent, Star
from astrbot_sdk.decorators import on_command


class NotesPlugin(Star):
    @on_command("note-save", description="Save a note: note-save <key> <content>")
    async def save(self, event: MessageEvent, ctx: Context, key: str, content: GreedyStr) -> None:
        await ctx.db.set(f"notes:{key}", {"content": str(content).strip()})
        await event.reply(f"Saved note '{key}'.")

    @on_command("note-get", description="Read a note: note-get <key>")
    async def get(self, event: MessageEvent, ctx: Context, key: str) -> None:
        note = await ctx.db.get(f"notes:{key}")
        if not isinstance(note, dict) or not note.get("content"):
            await event.reply(f"No note found for '{key}'.")
            return
        await event.reply(f"{key}: {note['content']}")

    @on_command("note-delete", description="Delete a note: note-delete <key>")
    async def delete(self, event: MessageEvent, ctx: Context, key: str) -> None:
        # IMPORTANT: ctx.db.delete() returns None, not bool.
        # Check existence first if you need to inform the user.
        existing = await ctx.db.get(f"notes:{key}")
        if not existing:
            await event.reply(f"No note found for '{key}'.")
            return
        await ctx.db.delete(f"notes:{key}")
        await event.reply(f"Deleted note '{key}'.")

    @on_command("note-list", description="List all notes")
    async def list_notes(self, event: MessageEvent, ctx: Context) -> None:
        keys = await ctx.db.list("notes:")
        if not keys:
            await event.reply("No notes saved.")
            return
        names = [k.removeprefix("notes:") for k in keys]
        await event.reply("Notes: " + ", ".join(names))
```

**test:**
```python
@pytest.mark.asyncio
async def test_note_crud():
    async with PluginHarness.from_plugin_dir(plugin_dir) as h:
        await h.dispatch_text("note-save todo buy milk")
        records = await h.dispatch_text("note-get todo")
    assert any(r.text == "todo: buy milk" for r in records)
```

---

## Pattern 3: Keyword and Regex Message Handler

React to keywords and regex patterns with platform/group filters.

**main.py:**
```python
from astrbot_sdk import Context, MessageEvent, Star
from astrbot_sdk.decorators import on_message, group_only, platforms


class KeywordPlugin(Star):
    @on_message(keywords=["help", "帮助"])
    async def help_handler(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply("Available commands: /greet, /note-save, /note-get")

    @on_message(regex=r"^\d{4}-\d{2}-\d{2}$")
    async def date_handler(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply(f"Detected date: {event.text}")

    @on_message(keywords=["notify"])
    @group_only()
    @platforms("qq")
    async def qq_group_only(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply("QQ group notification received!")
```

---

## Pattern 4: Scheduled Task Plugin

Periodic tasks using cron and interval.

**main.py:**
```python
import asyncio
from astrbot_sdk import Context, Star
from astrbot_sdk.decorators import on_schedule
from astrbot_sdk.schedule import ScheduleContext


class ScheduledPlugin(Star):
    @on_schedule(cron="0 8 * * *", description="Daily morning greeting")
    async def morning(self, ctx: Context) -> None:
        # No event available — use ctx.platform.send() for proactive messages
        await ctx.platform.send("target-session-id", "Good morning!")

    @on_schedule(interval_seconds=3600, description="Hourly health check")
    async def health_check(self, ctx: Context, schedule: ScheduleContext) -> None:
        ctx.logger.info(f"Health check #{schedule.schedule_id}, trigger: {schedule.trigger_kind}")
```

**Note:** Scheduled handlers have no `event` parameter. You cannot call `event.reply()`.

---

## Pattern 5: Multi-Turn Conversation Plugin

Interactive dialogue with `ConversationSession`.

**main.py:**
```python
from astrbot_sdk import Context, ConversationSession, MessageEvent, Star
from astrbot_sdk.decorators import conversation_command


class SurveyPlugin(Star):
    @conversation_command(
        "survey",
        description="Interactive survey",
        timeout=120,
        mode="reject",
        busy_message="A survey is already in progress. Please complete it first.",
    )
    async def survey(self, event: MessageEvent, ctx: Context, session: ConversationSession) -> None:
        await session.reply("Welcome to the survey! What is your name?")

        name_event = await session.ask("Please enter your name:")
        name = name_event.text.strip()

        rating_event = await session.ask(f"Hi {name}! Rate us 1-5:")
        rating = rating_event.text.strip()

        await ctx.db.set(f"survey:{event.user_id}", {"name": name, "rating": rating})
        await session.reply(f"Thanks {name}! Your rating of {rating} has been saved.")
        session.end()
```

**Key points:**
- `session.ask()` sends a prompt and waits for the user's next message.
- `session.reply()` sends a message without waiting.
- `session.end()` marks the session complete.
- Handle `TimeoutError` if the user doesn't respond within `timeout`.

---

## Pattern 6: LLM-Powered Plugin

Use AI for intelligent responses.

**main.py:**
```python
from astrbot_sdk import Context, GreedyStr, MessageEvent, Star
from astrbot_sdk.decorators import on_command
from astrbot_sdk.clients import ChatMessage


class AIPlugin(Star):
    @on_command("ask", description="Ask the AI a question")
    async def ask_ai(self, event: MessageEvent, ctx: Context, question: GreedyStr) -> None:
        answer = await ctx.llm.chat(
            str(question),
            system="You are a helpful assistant. Be concise.",
        )
        await event.reply(answer)

    @on_command("chat", description="Chat with history")
    async def chat_with_history(self, event: MessageEvent, ctx: Context, message: GreedyStr) -> None:
        # Load history from DB
        history_data = await ctx.db.get(f"chat_history:{event.user_id}") or {"messages": []}
        history = [ChatMessage(**m) for m in history_data["messages"][-10:]]

        response = await ctx.llm.chat(str(message), history=history)

        # Save updated history
        history_data["messages"].append({"role": "user", "content": str(message)})
        history_data["messages"].append({"role": "assistant", "content": response})
        await ctx.db.set(f"chat_history:{event.user_id}", history_data)

        await event.reply(response)

    @on_command("stream-ask", description="Stream AI response")
    async def stream_ask(self, event: MessageEvent, ctx: Context, question: GreedyStr) -> None:
        chunks = []
        async for chunk in ctx.llm.stream_chat(str(question)):
            chunks.append(chunk)
        await event.reply("".join(chunks))
```

---

## Pattern 7: Capability Provider Plugin

Expose capabilities for other plugins to call.

**main.py:**
```python
from pydantic import BaseModel
from astrbot_sdk import Context, Star
from astrbot_sdk.decorators import provide_capability


class CalcInput(BaseModel):
    x: float
    y: float
    op: str = "add"


class CalcOutput(BaseModel):
    result: float


class CalcPlugin(Star):
    @provide_capability(
        "calc.compute",
        description="Perform arithmetic",
        input_model=CalcInput,
        output_model=CalcOutput,
    )
    async def compute(self, payload: dict, ctx: Context) -> dict:
        data = CalcInput.model_validate(payload)
        ops = {"add": data.x + data.y, "sub": data.x - data.y, "mul": data.x * data.y}
        result = ops.get(data.op, data.x + data.y)
        return {"result": result}
```

**test:**
```python
@pytest.mark.asyncio
async def test_capability():
    async with PluginHarness.from_plugin_dir(plugin_dir) as h:
        result = await h.invoke_capability("calc.compute", {"x": 3, "y": 4, "op": "mul"})
    assert result["result"] == 12.0
```

---

## Pattern 8: HTTP API Plugin

Expose REST endpoints.

**main.py:**
```python
from astrbot_sdk import Context, Star
from astrbot_sdk.decorators import http_api


class WebhookPlugin(Star):
    @http_api("/api/status", methods=["GET"], description="Health check")
    async def status(self, payload: dict, ctx: Context) -> dict:
        return {"status": "ok", "plugin": ctx.plugin_id}

    @http_api("/api/notify", methods=["POST"], description="Send notification")
    async def notify(self, payload: dict, ctx: Context) -> dict:
        target = payload.get("session_id", "")
        message = payload.get("message", "")
        if not target or not message:
            return {"error": "session_id and message required"}
        await ctx.platform.send(target, message)
        return {"sent": True}
```

---

## Pattern 9: Rich Messages Plugin

Build rich messages with components.

**main.py:**
```python
from astrbot_sdk import (
    Context, MessageBuilder, MessageEvent, Plain, At, Image, Star,
)
from astrbot_sdk.decorators import on_command


class RichPlugin(Star):
    @on_command("welcome", description="Welcome with rich message")
    async def welcome(self, event: MessageEvent, ctx: Context) -> None:
        chain = (
            MessageBuilder()
            .text("Welcome ")
            .at(event.user_id)
            .text("!\nHere's a guide image:")
            .image("https://example.com/guide.png")
            .build()
        )
        await event.reply_chain(chain.components)

    @on_command("card", description="Send info card")
    async def card(self, event: MessageEvent, ctx: Context) -> None:
        # Manual component list
        components = [
            Plain("📋 User Info\n"),
            Plain(f"Name: {event.sender_name}\n"),
            Plain(f"ID: {event.user_id}\n"),
            Plain(f"Platform: {event.platform}"),
        ]
        await event.reply_chain(components)
```

---

## Pattern 10: Lifecycle Hooks with Config Validation

Initialize resources on start, clean up on stop.

**main.py:**
```python
from pydantic import BaseModel
from astrbot_sdk import Context, MessageEvent, Star
from astrbot_sdk.decorators import on_command, validate_config


class PluginConfig(BaseModel):
    api_key: str
    max_retries: int = 3
    timeout: float = 30.0


class ConfigPlugin(Star):
    def __init__(self) -> None:
        super().__init__()
        self._api_key: str = ""
        self._max_retries: int = 3

    async def on_start(self, ctx) -> None:
        await super().on_start(ctx)
        config = await ctx.metadata.get_plugin_config()
        if config:
            validated = PluginConfig.model_validate(config)
            self._api_key = validated.api_key
            self._max_retries = validated.max_retries

    async def on_stop(self, ctx) -> None:
        # Clean up resources here
        await super().on_stop(ctx)

    @on_command("status", description="Show config status")
    async def status(self, event: MessageEvent, ctx: Context) -> None:
        masked = self._api_key[:4] + "****" if self._api_key else "not set"
        await event.reply(f"API key: {masked}, retries: {self._max_retries}")
```

**Key rules:**
- Always call `await super().on_start(ctx)` and `await super().on_stop(ctx)`.
- Do not store `ctx` on `self` — use it only within the call.
- Store extracted config values on `self`, not the ctx object.

---

## Pattern 11: Command Groups

Hierarchical command organization.

**main.py:**
```python
from astrbot_sdk import Context, GreedyStr, MessageEvent, Star
from astrbot_sdk.commands import command_group
from astrbot_sdk.decorators import require_admin

admin = command_group("admin", description="Admin commands")
user_grp = admin.group("user", description="User management")


class AdminPlugin(Star):
    @user_grp.command("add", description="Add a user")
    @require_admin
    async def user_add(self, event: MessageEvent, ctx: Context, username: str) -> None:
        await ctx.db.set(f"users:{username}", {"added_by": event.user_id})
        await event.reply(f"User '{username}' added.")

    @user_grp.command("remove", description="Remove a user")
    @require_admin
    async def user_remove(self, event: MessageEvent, ctx: Context, username: str) -> None:
        existing = await ctx.db.get(f"users:{username}")
        if not existing:
            await event.reply(f"User '{username}' not found.")
            return
        await ctx.db.delete(f"users:{username}")
        await event.reply(f"User '{username}' removed.")

    @admin.command("help", description="Show admin help")
    async def admin_help(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply("Admin commands: admin user add <name>, admin user remove <name>")
```

---

## Pattern 12: Background Task

Long-running background loop.

**main.py:**
```python
import asyncio
from astrbot_sdk import Context, Star
from astrbot_sdk.decorators import background_task, on_command


class MonitorPlugin(Star):
    def __init__(self) -> None:
        super().__init__()
        self._check_count: int = 0

    @background_task(description="Periodic monitor", auto_start=True, on_error="restart")
    async def monitor(self, ctx: Context) -> None:
        while True:
            self._check_count += 1
            ctx.logger.info(f"Monitor check #{self._check_count}")
            # Perform monitoring logic here
            await asyncio.sleep(60)

    @on_command("monitor-status", description="Show monitor status")
    async def status(self, event, ctx: Context) -> None:
        await event.reply(f"Monitor has run {self._check_count} checks.")
```

---

## Pattern 13: Rate-Limited Admin Command

Stack multiple decorators for access control and throttling.

**main.py:**
```python
from astrbot_sdk import Context, GreedyStr, MessageEvent, Star
from astrbot_sdk.decorators import on_command, require_admin, rate_limit, group_only


class ModerationPlugin(Star):
    @on_command("announce", description="Send group announcement")
    @require_admin
    @group_only()
    @rate_limit(3, 300.0, scope="group", behavior="hint", message="Max 3 announcements per 5 minutes.")
    async def announce(self, event: MessageEvent, ctx: Context, text: GreedyStr) -> None:
        announcement = f"📢 Announcement from {event.sender_name}:\n{text}"
        await event.reply(announcement)
```

**Decorator stacking order:** trigger first (topmost), then guards, then throttle.

---

## Source basis

Derived from:
- `src/astrbot_sdk/decorators.py`
- `src/astrbot_sdk/clients/*.py`
- `src/astrbot_sdk/conversation.py`
- `src/astrbot_sdk/commands.py`
- `src/astrbot_sdk/message/result.py`
- `forward-tests/astrbot-plugin-dev/`
