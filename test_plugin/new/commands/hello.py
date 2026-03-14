"""V4 sample plugin used by integration tests.

This fixture exercises the full public v4 API surface:

Decorators:
    - on_command: command handling with aliases and description
    - on_message: message handling with regex, keywords, platforms
    - on_event: event subscription
    - on_schedule: scheduled tasks
    - require_admin: permission control
    - provide_capability: custom capabilities (normal + stream)

Context clients:
    - ctx.llm: LLM client (chat, chat_raw, stream_chat, with images)
    - ctx.memory: Memory client (save, get, delete, search)
    - ctx.db: DB client (get, set, delete, list, get_many, set_many, watch)
    - ctx.platform: Platform client (send, send_image, send_chain, get_members)
    - ctx.http: HTTP client (register_api, unregister_api, list_apis)
    - ctx.metadata: Metadata client (get_plugin, list_plugins, get_plugin_config)

MessageEvent:
    - reply(), plain_result(), target, to_payload()
    - user_id, group_id, session_id, platform, text

Star lifecycle:
    - on_start, on_stop, on_error
"""

from __future__ import annotations

import asyncio

from astrbot_sdk import (
    Context,
    MessageEvent,
    Star,
    on_command,
    on_event,
    on_message,
    on_schedule,
    provide_capability,
    require_admin,
)
from astrbot_sdk.context import CancelToken


class HelloPlugin(Star):
    """Representative v4 plugin fixture covering all SDK capabilities."""

    # ============================================================
    # Lifecycle hooks
    # ============================================================

    async def on_start(self, ctx: Context) -> None:
        """Called when the plugin starts."""
        ctx.logger.info("HelloPlugin starting up")
        # Store startup timestamp
        await ctx.db.set("demo:started", {"status": "ok"})

    async def on_stop(self, ctx: Context) -> None:
        """Called when the plugin stops."""
        ctx.logger.info("HelloPlugin shutting down")
        # Cleanup
        await ctx.db.delete("demo:started")

    # ============================================================
    # Command handlers
    # ============================================================

    @on_command("hello", aliases=["hi"], description="发送问候消息")
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        """Basic command with LLM response."""
        reply = await ctx.llm.chat(event.text)
        await event.reply(reply)

    @on_command("raw", description="调用 llm.chat_raw 并返回结构化信息")
    async def raw(self, event: MessageEvent, ctx: Context):
        """LLM chat with full response metadata."""
        response = await ctx.llm.chat_raw(
            event.text,
            system="be concise",
            history=[{"role": "user", "content": "history"}],
        )
        return event.plain_result(
            f"raw={response.text}|finish={response.finish_reason}|"
            f"usage={response.usage}"
        )

    @on_command("stream", description="流式 LLM 调用")
    async def stream(self, event: MessageEvent, ctx: Context) -> None:
        """Streaming LLM response."""
        chunks: list[str] = []
        async for chunk in ctx.llm.stream_chat(event.text or "stream"):
            chunks.append(chunk)
            # Real-time feedback
            await event.reply(f"[streaming...] {chunk}")
        await event.reply(f"[完成] {''.join(chunks)}")

    @on_command("vision", description="带图片的 LLM 调用")
    async def vision(self, event: MessageEvent, ctx: Context) -> None:
        """LLM with image input."""
        # Extract image URL from message or use default
        image_url = "https://example.com/demo.png"
        response = await ctx.llm.chat(
            event.text or "描述这张图片",
            image_urls=[image_url],
        )
        await event.reply(response)

    # ============================================================
    # Memory operations
    # ============================================================

    @on_command("remember", description="记忆操作演示")
    async def remember(self, event: MessageEvent, ctx: Context):
        """Memory client full API demo."""
        # Save with metadata
        await ctx.memory.save(
            "demo:last_message",
            {"user_id": event.user_id or "", "text": event.text},
            source="fixture",
            tags=["demo"],
        )

        # Get exact match
        remembered = await ctx.memory.get("demo:last_message") or {}

        # Semantic search
        searched = await ctx.memory.search("demo")

        # Delete
        await ctx.memory.delete("demo:last_message")

        return event.plain_result(
            f"remembered={remembered.get('user_id', 'unknown')}|"
            f"searched={len(searched)}"
        )

    # ============================================================
    # Database operations
    # ============================================================

    @on_command("db", description="数据库操作演示")
    async def db_ops(self, event: MessageEvent, ctx: Context):
        """DB client full API demo."""
        # Basic operations
        await ctx.db.set("demo:key1", {"value": "data1"})
        await ctx.db.set("demo:key2", {"value": "data2"})
        await ctx.db.set("demo:key3", {"value": "data3"})

        value1 = await ctx.db.get("demo:key1")

        # List keys with prefix
        keys = await ctx.db.list("demo:")

        # Batch operations
        values = await ctx.db.get_many(["demo:key1", "demo:key2"])
        await ctx.db.set_many(
            {
                "demo:batch1": {"batch": True},
                "demo:batch2": {"batch": True},
            }
        )

        # Cleanup
        for key in [
            "demo:key1",
            "demo:key2",
            "demo:key3",
            "demo:batch1",
            "demo:batch2",
        ]:
            await ctx.db.delete(key)

        return event.plain_result(
            f"value1={value1}|keys={len(keys)}|batch_get={len(values)}"
        )

    @on_command("watch", description="监听数据库变更")
    async def watch_db(self, event: MessageEvent, ctx: Context) -> None:
        """Watch for DB changes (demonstration)."""
        await event.reply("开始监听 demo: 前缀的变更 (5秒)...")

        async def watcher():
            count = 0
            async for change in ctx.db.watch("demo:"):
                count += 1
                await event.reply(f"变更: {change['op']} {change['key']}")
                if count >= 3:
                    break

        # Run watcher with timeout
        try:
            await asyncio.wait_for(watcher(), timeout=5.0)
        except asyncio.TimeoutError:
            await event.reply("监听超时结束")

    # ============================================================
    # Platform operations
    # ============================================================

    @on_command("platforms", description="平台操作演示")
    async def platforms(self, event: MessageEvent, ctx: Context) -> None:
        """Platform client full API demo."""
        target = event.target or event.session_id

        # Get group members
        members = await ctx.platform.get_members(target)

        # Send text
        await ctx.platform.send(target, f"成员数: {len(members)}")

        # Send image
        await ctx.platform.send_image(target, "https://example.com/demo.png")

        # Send message chain
        await ctx.platform.send_chain(
            target,
            [
                {"type": "Plain", "text": "消息链 "},
                {"type": "Image", "file": "https://example.com/demo.png"},
            ],
        )

    @on_command("announce", description="发送富消息链")
    async def announce(self, event: MessageEvent, ctx: Context) -> None:
        """Send rich message chain."""
        await ctx.platform.send_chain(
            event.target or event.session_id,
            [
                {"type": "Plain", "text": "公告: "},
                {"type": "Plain", "text": event.text or "无内容"},
            ],
        )

    # ============================================================
    # HTTP API operations
    # ============================================================

    @on_command("register_api", description="注册 HTTP API")
    async def register_http_api(self, event: MessageEvent, ctx: Context) -> None:
        """Register a custom HTTP API endpoint."""
        await ctx.http.register_api(
            route="/demo/api",
            handler_capability="demo.http_handler",
            methods=["GET", "POST"],
            description="Demo HTTP API",
        )
        apis = await ctx.http.list_apis()
        return event.plain_result(f"已注册 API，当前共 {len(apis)} 个")

    @on_command("unregister_api", description="注销 HTTP API")
    async def unregister_http_api(self, event: MessageEvent, ctx: Context) -> None:
        """Unregister the HTTP API endpoint."""
        await ctx.http.unregister_api("/demo/api")
        return event.plain_result("已注销 API")

    # ============================================================
    # Metadata operations
    # ============================================================

    @on_command("plugins", description="列出所有插件")
    async def list_plugins(self, event: MessageEvent, ctx: Context):
        """List all loaded plugins."""
        plugins = await ctx.metadata.list_plugins()
        names = [p.name for p in plugins]
        return event.plain_result(f"插件: {', '.join(names)}")

    @on_command("plugin_info", description="获取插件信息")
    async def plugin_info(self, event: MessageEvent, ctx: Context):
        """Get current plugin metadata."""
        me = await ctx.metadata.get_current_plugin()
        if me:
            return event.plain_result(
                f"name={me.name}|version={me.version}|author={me.author}"
            )
        return event.plain_result("无法获取插件信息")

    @on_command("config", description="获取插件配置")
    async def get_config(self, event: MessageEvent, ctx: Context):
        """Get plugin configuration."""
        config = await ctx.metadata.get_plugin_config()
        if config:
            return event.plain_result(f"config={config}")
        return event.plain_result("无配置")

    # ============================================================
    # Permission control
    # ============================================================

    @require_admin
    @on_command("secure", description="管理员专用命令")
    async def secure(self, event: MessageEvent):
        """Admin-only command."""
        return event.plain_result(f"secure:{event.user_id or 'unknown'}")

    # ============================================================
    # Message handlers
    # ============================================================

    @on_message(regex=r"^ping$", keywords=["ping"], platforms=["test"])
    async def ping(self, event: MessageEvent):
        """Regex and keyword matching."""
        return event.plain_result("pong")

    @on_message(keywords=["hello"])
    async def on_hello(self, event: MessageEvent, ctx: Context) -> None:
        """Keyword-based message handler."""
        await event.reply("检测到 hello 关键词!")

    # ============================================================
    # Event handlers
    # ============================================================

    @on_event("group_join")
    async def on_group_join(self, event: MessageEvent, ctx: Context) -> None:
        """Handle group join events."""
        ctx.logger.info("用户加入群组: {}", event.user_id)
        await ctx.platform.send(event.session_id, f"欢迎 {event.user_id} 加入群组!")

    @on_event("group_leave")
    async def on_group_leave(self, event: MessageEvent, ctx: Context) -> None:
        """Handle group leave events."""
        ctx.logger.info("用户离开群组: {}", event.user_id)

    # ============================================================
    # Scheduled tasks
    # ============================================================

    @on_schedule(interval_seconds=3600)
    async def hourly_heartbeat(self, ctx: Context) -> None:
        """Hourly scheduled task."""
        await ctx.db.set("demo:last_heartbeat", {"time": "hourly"})
        ctx.logger.info("执行每小时心跳")

    @on_schedule(cron="0 9 * * *")
    async def morning_greeting(self, ctx: Context) -> None:
        """Cron-based scheduled task (9 AM daily)."""
        ctx.logger.info("早安问候任务触发")

    # ============================================================
    # Custom capabilities
    # ============================================================

    @provide_capability(
        "demo.echo",
        description="回显输入文本",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "echo": {"type": "string"},
                "plugin_id": {"type": "string"},
            },
            "required": ["echo", "plugin_id"],
        },
    )
    async def echo_capability(
        self,
        payload: dict[str, object],
        ctx: Context,
        cancel_token: CancelToken,
    ) -> dict[str, str]:
        """Simple echo capability."""
        cancel_token.raise_if_cancelled()
        text = str(payload.get("text", ""))
        await ctx.db.set("demo:capability_echo", {"text": text})
        return {
            "echo": text,
            "plugin_id": ctx.plugin_id,
        }

    @provide_capability(
        "demo.stream",
        description="流式回显输入文本",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "object"},
                }
            },
            "required": ["items"],
        },
        supports_stream=True,
        cancelable=True,
    )
    async def stream_capability(
        self,
        payload: dict[str, object],
        ctx: Context,
        cancel_token: CancelToken,
    ):
        """Streaming echo capability."""
        text = str(payload.get("text", ""))
        await ctx.db.set("demo:last_stream", {"text": text})
        for char in text:
            cancel_token.raise_if_cancelled()
            await asyncio.sleep(0)
            yield {"text": char}

    @provide_capability(
        "demo.http_handler",
        description="处理 /demo/api HTTP 请求",
        input_schema={
            "type": "object",
            "properties": {
                "method": {"type": "string"},
                "body": {"type": "object"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "integer"},
                "body": {"type": "object"},
            },
        },
    )
    async def http_handler_capability(
        self,
        payload: dict[str, object],
        ctx: Context,
        cancel_token: CancelToken,
    ) -> dict[str, object]:
        """Handle HTTP API requests."""
        method = payload.get("method", "GET")
        body = payload.get("body", {})
        ctx.logger.info(f"HTTP {method} request: {body}")
        return {
            "status": 200,
            "body": {
                "message": "Hello from plugin!",
                "method": method,
                "plugin_id": ctx.plugin_id,
            },
        }
