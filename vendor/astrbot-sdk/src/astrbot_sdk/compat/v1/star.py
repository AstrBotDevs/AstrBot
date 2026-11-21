"""Legacy Star base class and Context facade."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from .components import MessageChain
from .errors import IsolationUnsupportedError
from .event import AstrMessageEvent  # noqa: F401  (re-exported for plugins)
from .provider import LLMResponse, Provider  # noqa: F401
from .provider import ProviderType as _CompatProviderType
from .tools import FunctionTool, LegacyFunctionToolAdapter


class MessageSesion:
    """Legacy message session; the historical typo is part of the API."""

    def __init__(
        self,
        platform_name: str,
        message_type: Any,
        session_id: str,
    ) -> None:
        self.platform_name = platform_name
        self.platform_id = platform_name
        self.message_type = message_type
        self.session_id = session_id

    def __str__(self) -> str:
        from ...events import MessageType

        core_type = self.message_type
        if isinstance(core_type, MessageType):
            core_type = {
                MessageType.PRIVATE: "FriendMessage",
                MessageType.GROUP: "GroupMessage",
                MessageType.OTHER: "OtherMessage",
            }[core_type]
        return f"{self.platform_name}:{core_type}:{self.session_id}"

    @staticmethod
    def from_str(session_str: str) -> MessageSesion:
        platform_id, message_type, session_id = session_str.split(":", 2)
        return MessageSesion(platform_id, message_type, session_id)


class Context:
    """Facade over the plugin's new SDK context with the old Context API."""

    def __init__(self, ctx: Any, config: Any = None, snapshot: Any = None) -> None:
        self._ctx = ctx
        self._config = config or {}
        self._snapshot = snapshot if isinstance(snapshot, dict) else {}
        self._pending: list[asyncio.Task] = []
        self._tasks: list[asyncio.Task] = []
        self._stars_cache: list | None = None
        self._web_routes: list = []
        self.logger = ctx.logger
        from .conversation import ConversationManager
        from .cron import CronManagerFacade
        from .host_snapshot import (
            AstrbotConfigMgrFacade,
            PersonaManagerFacade,
            PlatformManagerFacade,
            ProviderManagerFacade,
        )
        from .kb import KbManagerFacade
        from .message_history import MessageHistoryManagerFacade

        self.conversation_manager = ConversationManager(ctx)
        self._persona_manager = PersonaManagerFacade(ctx, self._snapshot)
        self._provider_manager = ProviderManagerFacade(
            ctx,
            self._snapshot,
            self._persona_manager,
        )
        self.platform_manager = PlatformManagerFacade(self, self._snapshot)
        self.astrbot_config_mgr = AstrbotConfigMgrFacade(self, self._snapshot)
        self.kb_manager = KbManagerFacade(self)
        self.cron_manager = CronManagerFacade(self)
        self.message_history_manager = MessageHistoryManagerFacade(self)

    @property
    def persona_manager(self) -> Any:
        """Sync persona getters served from the handshake snapshot."""
        return self._persona_manager

    @property
    def provider_manager(self) -> Any:
        """Legacy provider registry served from the handshake snapshot."""
        return self._provider_manager

    @property
    def html_renderer(self) -> Any:
        """Legacy HtmlRenderer facade backed by the render capability."""
        from .html import HtmlRendererFacade

        return HtmlRendererFacade()

    def get_config(self, umo: str | None = None) -> Any:
        """Return the redacted global AstrBot config, routed by umo.

        Served from the handshake snapshot with secrets blanked by the
        host; runtime host edits only arrive after a plugin reload.
        """
        if not self._snapshot.get("config"):
            raise IsolationUnsupportedError(
                "Context.get_config() has no host config snapshot; the plugin "
                "must run in-process"
            )
        from .host_snapshot import copy_global_config

        return copy_global_config(self._snapshot, str(umo) if umo is not None else None)

    # ---- providers ---------------------------------------------------------

    def get_using_provider(self, umo: str | None = None) -> Provider | None:
        """Return the session's chat provider, or None when unavailable.

        Resolved synchronously from the handshake snapshot, mirroring the
        in-process semantics (a concrete provider bound at call time).
        """
        return self._provider_manager.get_using_provider(
            _CompatProviderType.CHAT_COMPLETION,
            str(umo) if umo is not None else None,
        )

    async def get_using_provider_async(self, umo: str | None = None) -> Provider:
        """Async variant of get_using_provider (provider metadata resolved)."""
        provider = Provider(self._ctx, umo=umo)
        await provider._resolve()
        return provider

    def get_provider_by_id(self, provider_id: str) -> Provider | None:
        """Return a facade bound to one explicit provider instance.

        Returns None when the id is unknown, mirroring the in-process
        behavior (which also logs a warning).
        """
        from ...llm import ProviderKind
        from .host_snapshot import find_provider_entry, provider_info

        entry = find_provider_entry(self._snapshot, ProviderKind.CHAT, provider_id)
        if entry is None:
            if provider_id:
                self.logger.warning(
                    "Provider %s was not found. Its provider or model ID may "
                    "have been changed.",
                    provider_id,
                )
            return None
        return Provider(
            self._ctx,
            provider_id=provider_id,
            info=provider_info(entry, ProviderKind.CHAT),
        )

    async def get_current_chat_provider_id(self, umo: str) -> str | None:
        """Return the chat provider id currently selected for the session."""
        from ...llm import ProviderKind

        info = await self._ctx.llm.current_provider(ProviderKind.CHAT, umo=umo)
        return info.id if info is not None else None

    def get_all_providers(self) -> list[Provider]:
        """Return facades for every configured chat provider (sync)."""
        return list(self._provider_manager.provider_insts)

    async def llm_generate(
        self,
        *,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        tools: Any = None,
        system_prompt: str | None = None,
        contexts: list | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """One-shot completion on an explicit provider (legacy signature)."""
        provider = Provider(self._ctx, provider_id=chat_provider_id)
        return await provider.text_chat(
            prompt=prompt,
            image_urls=image_urls,
            audio_urls=audio_urls,
            contexts=contexts,
            system_prompt=system_prompt or "",
            func_tool=tools,
            **kwargs,
        )

    async def tool_loop_agent(
        self,
        *,
        event: AstrMessageEvent,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        tools: Any = None,
        system_prompt: str | None = None,
        contexts: list | None = None,
        max_steps: int = 128,
        **kwargs: Any,
    ) -> LLMResponse:
        """Run the built-in tool-loop agent (legacy signature)."""
        from ...llm import AgentRequest
        from .provider import build_input_message, contexts_to_messages

        messages = contexts_to_messages(contexts)
        input_message = build_input_message(prompt, image_urls, audio_urls)
        if input_message is not None:
            messages.append(input_message)
        tool_names: tuple[str, ...] | None = None
        if tools is not None:
            tool_names = tuple(
                tool.name for tool in getattr(tools, "tools", []) if tool.name
            )
        request = AgentRequest(
            input=tuple(messages),
            system_prompt=system_prompt or None,
            provider_id=chat_provider_id,
            max_steps=max_steps,
            tools=tool_names,
            event=getattr(event, "_event", None),
        )
        response = await self._ctx.llm.run_agent(request)
        return LLMResponse(
            role="assistant",
            completion_text=response.text,
            reasoning_content=response.reasoning_content,
        )

    # ---- plugin registry ----------------------------------------------------

    async def _prime_stars(self) -> None:
        """Fetch the plugin registry snapshot used by the sync getters."""
        try:
            infos = await self._ctx.plugins.list()
        except Exception:  # noqa: BLE001 - inspection is best-effort
            infos = []
        self._stars_cache = [_star_metadata_shell(info) for info in infos]

    def get_all_stars(self) -> list:
        """Return metadata of installed plugins (startup snapshot)."""
        return list(self._stars_cache or [])

    async def get_all_stars_async(self) -> list:
        """Async variant returning a fresh registry snapshot."""
        await self._prime_stars()
        return self.get_all_stars()

    def get_registered_star(self, star_name: str) -> Any:
        """Return one plugin's metadata by name from the snapshot."""
        for metadata in self.get_all_stars():
            if metadata.name == star_name:
                return metadata
        return None

    # ---- speech and embedding providers -------------------------------------

    def get_using_tts_provider(self, umo: str | None = None) -> Any:
        """Return the session's TTS provider, or None when disabled."""
        return self._provider_manager.get_using_provider(
            _CompatProviderType.TEXT_TO_SPEECH,
            str(umo) if umo is not None else None,
        )

    async def get_using_tts_provider_async(self, umo: str | None = None) -> Any:
        return self.get_using_tts_provider(umo)

    def get_using_stt_provider(self, umo: str | None = None) -> Any:
        """Return the session's STT provider, or None when disabled."""
        return self._provider_manager.get_using_provider(
            _CompatProviderType.SPEECH_TO_TEXT,
            str(umo) if umo is not None else None,
        )

    async def get_using_stt_provider_async(self, umo: str | None = None) -> Any:
        return self.get_using_stt_provider(umo)

    def get_all_tts_providers(self) -> list:
        """Return facades for every configured TTS provider (sync)."""
        return list(self._provider_manager.tts_provider_insts)

    def get_all_stt_providers(self) -> list:
        """Return facades for every configured STT provider (sync)."""
        return list(self._provider_manager.stt_provider_insts)

    def get_all_embedding_providers(self) -> list:
        """Return facades for every configured embedding provider (sync)."""
        return list(self._provider_manager.embedding_provider_insts)

    # ---- background tasks ---------------------------------------------------

    def register_task(self, task: Any, desc: str = "") -> None:
        """Run a background coroutine for the plugin's lifetime."""
        handle = asyncio.get_running_loop().create_task(task, name=desc or None)
        self._tasks.append(handle)

    # ---- host-internal APIs (fail loudly) ------------------------------------

    def register_commands(self, *args: Any, **kwargs: Any) -> None:
        """Manage host command registrations (unsupported when isolated)."""
        raise IsolationUnsupportedError(
            "register_commands is unavailable in isolated legacy mode"
        )

    def get_llm_tool_manager(self) -> Any:
        """The global tool manager is host-internal (unsupported)."""
        raise IsolationUnsupportedError(
            "get_llm_tool_manager is unavailable in isolated legacy mode"
        )

    def get_event_queue(self) -> Any:
        """The host event queue is host-internal (unsupported)."""
        raise IsolationUnsupportedError(
            "get_event_queue is unavailable in isolated legacy mode"
        )

    def get_platform(self, platform_type: Any) -> Any:
        """Return the first platform adapter matching the given type name.

        Mirrors the deprecated in-process getter: string names match the
        adapter metadata name. Enum-based PlatformAdapterType matching is
        unavailable in isolated mode.

        Raises:
            IsolationUnsupportedError: A non-string platform type is passed.
        """
        if not isinstance(platform_type, str):
            raise IsolationUnsupportedError(
                "get_platform with a PlatformAdapterType is unavailable in "
                "isolated legacy mode; pass the adapter name string instead."
            )
        for platform in self.platform_manager.platform_insts:
            if platform.meta().name == platform_type:
                return platform
        return None

    def get_platform_inst(self, platform_id: str) -> Any:
        """Return the platform adapter facade with the given instance ID."""
        for platform in self.platform_manager.platform_insts:
            if platform.meta().id == platform_id:
                return platform
        return None

    def get_db(self) -> Any:
        """The host database is host-internal (unsupported)."""
        raise IsolationUnsupportedError("get_db is unavailable in isolated legacy mode")

    def register_provider(self, *args: Any, **kwargs: Any) -> None:
        """Custom providers are host-internal (unsupported)."""
        raise IsolationUnsupportedError(
            "register_provider is unavailable in isolated legacy mode"
        )

    # ---- dynamic tools -----------------------------------------------------

    def register_llm_tool(self, tool_class: type[FunctionTool]) -> None:
        """Register one legacy FunctionTool class (instantiated internally).

        The old API is synchronous, while isolated registration is an RPC;
        the task is tracked and awaited before plugin startup completes.
        """
        instance = tool_class()
        adapter = LegacyFunctionToolAdapter(instance, self)
        self._pending.append(
            asyncio.get_running_loop().create_task(self._ctx.tools.register(adapter)),
        )

    def add_llm_tools(self, *tools: FunctionTool) -> None:
        """Register already-instantiated legacy tools."""
        for tool in tools:
            adapter = LegacyFunctionToolAdapter(tool, self)
            self._pending.append(
                asyncio.get_running_loop().create_task(
                    self._ctx.tools.register(adapter),
                ),
            )

    def unregister_llm_tool(self, name: str) -> None:
        """Remove one dynamically registered tool by name."""
        self._pending.append(
            asyncio.get_running_loop().create_task(
                self._unregister_llm_tool(name),
            ),
        )

    async def _unregister_llm_tool(self, name: str) -> None:
        from ...tools import ToolRef

        for handler_id, handler in list(self._ctx.dynamic_tools.items()):
            tool_name = getattr(handler, "__self__", handler)
            tool_name = getattr(tool_name, "name", None)
            if tool_name == name:
                await self._ctx.tools.unregister(
                    ToolRef(name=name, handler_id=handler_id),
                )

    def activate_llm_tool(self, name: str) -> bool:
        """Toggle a global tool's active flag (unsupported when isolated)."""
        raise IsolationUnsupportedError(
            "activate_llm_tool is unavailable in isolated legacy mode"
        )

    async def activate_llm_tool_async(self, name: str) -> bool:
        """Activate a registered function-calling tool via the Host."""
        result = await self._ctx._invoke_capability(
            "llm.tool.register",
            "activate",
            {"name": name},
        )
        return bool(result.get("activated")) if isinstance(result, dict) else False

    def deactivate_llm_tool(self, name: str) -> bool:
        """Toggle a global tool's active flag (unsupported when isolated)."""
        raise IsolationUnsupportedError(
            "deactivate_llm_tool is unavailable in isolated legacy mode"
        )

    async def deactivate_llm_tool_async(self, name: str) -> bool:
        """Deactivate a registered function-calling tool via the Host."""
        result = await self._ctx._invoke_capability(
            "llm.tool.register",
            "deactivate",
            {"name": name},
        )
        return bool(result.get("deactivated")) if isinstance(result, dict) else False

    @property
    def registered_web_apis(self) -> list[tuple[str, Any, list[str], str]]:
        """Read-only view of this plugin's routes, in the core tuple shape."""
        return [
            (entry.route, entry.handler, entry.methods, entry.desc)
            for entry in self._web_routes
        ]

    def register_web_api(
        self,
        route: str,
        view_handler: Any,
        methods: list[str],
        desc: str,
    ) -> None:
        """Register one dashboard web route (legacy signature).

        Registration is an RPC under the hood; the task is tracked and
        awaited before plugin startup completes, same as tool registration.
        """
        from .web import WebRouteEntry

        entry = WebRouteEntry(route, methods, desc, view_handler)
        self._web_routes = [
            item
            for item in self._web_routes
            if not (item.route == route and item.methods == entry.methods)
        ]
        self._web_routes.append(entry)
        self._pending.append(
            asyncio.get_running_loop().create_task(
                self._ctx._invoke_capability(
                    "web.route",
                    "register",
                    {
                        "route": route,
                        "methods": [method.upper() for method in methods],
                        "description": desc,
                    },
                ),
            ),
        )

    async def _drain_pending(self) -> None:
        """Await all scheduled tool registrations (called at startup)."""
        while self._pending:
            task = self._pending.pop()
            await task

    async def put_kv_data(self, key: str, value: Any) -> None:
        await self._ctx.storage.set(key, value)

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        return await self._ctx.storage.get(key, default)

    async def delete_kv_data(self, key: str) -> None:
        await self._ctx.storage.delete(key)

    async def send_message(
        self,
        session: str | MessageSesion,
        message_chain: MessageChain,
    ) -> bool:
        """Proactively send a message chain to a session."""
        from ...events import UMO, MessageType

        if isinstance(session, str):
            session = MessageSesion.from_str(session)
        core_type = session.message_type
        sdk_type = {
            "FriendMessage": MessageType.PRIVATE,
            "private": MessageType.PRIVATE,
            "GroupMessage": MessageType.GROUP,
            "group": MessageType.GROUP,
        }.get(core_type, MessageType.OTHER)
        umo = UMO(session.platform_name, sdk_type, session.session_id)
        chain = (
            message_chain.to_sdk()
            if isinstance(message_chain, MessageChain)
            else message_chain
        )
        await self._ctx.messages.send(umo, chain)
        return True

    @property
    def _inner(self) -> Any:
        """Access the underlying new SDK context (compat escape hatch)."""
        return self._ctx


def _star_metadata_shell(info: Any) -> Any:
    """Convert one PluginInfo into a legacy StarMetadata-shaped object."""
    from types import SimpleNamespace

    return SimpleNamespace(
        name=info.name,
        author=getattr(info, "author", None),
        desc=getattr(info, "desc", None),
        version=info.version,
        repo=None,
        activated=getattr(info, "activated", True),
        module_path=None,
        root_dir_name=None,
    )


class CompatConfig(dict):
    """Plugin config facade: a dict whose save_config persists via the Host.

    The isolated Runner holds a snapshot of the plugin config; writes back
    to data/config are forwarded to the Host through the ``config.write``
    capability, which owns the real AstrBotConfig (and its file).

    Mirrors AstrBotConfig's attribute access: ``config.key`` reads a
    top-level item (missing keys yield None), and attribute assignment
    writes into the in-memory dict without persisting.
    """

    def __init__(self, *args: Any, ctx: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Bypass __setattr__: the context reference must not become a
        # config item inside the dict snapshot.
        object.__setattr__(self, "_ctx", ctx)

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError:
            return None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def __delattr__(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key) from None

    def save_config(
        self, replace_config: dict | None = None, *, indent: int = 2
    ) -> None:
        """Persist the config through the Host, fire-and-forget.

        The legacy signature is synchronous, but the Host round-trip is
        async; plugins call this from async handlers, so the write is
        scheduled on the running loop and failures are logged. Use
        save_config_async to await the write.

        Args:
            replace_config: Values merged into the config before saving.
            indent: JSON indent hint forwarded to the Host.
        """
        ctx = object.__getattribute__(self, "_ctx")
        if ctx is None:
            raise IsolationUnsupportedError(
                "config.save_config() has no Host channel in this context"
            )
        if replace_config:
            self.update(replace_config)
        task = asyncio.get_running_loop().create_task(
            ctx._invoke_capability(
                "config.write",
                "save",
                {"config": dict(self), "indent": indent},
            ),
        )
        task.add_done_callback(self._log_save_failure)

    async def save_config_async(
        self, replace_config: dict | None = None, *, indent: int = 2
    ) -> bool:
        """Persist the config through the Host and await the result.

        Args:
            replace_config: Values merged into the config before saving.
            indent: JSON indent hint forwarded to the Host.

        Returns:
            Whether the snapshot was committed by the Host.
        """
        ctx = object.__getattribute__(self, "_ctx")
        if ctx is None:
            raise IsolationUnsupportedError(
                "config.save_config_async() has no Host channel in this context"
            )
        if replace_config:
            self.update(replace_config)
        result = await ctx._invoke_capability(
            "config.write",
            "save",
            {"config": dict(self), "indent": indent},
        )
        if isinstance(result, Mapping):
            return bool(result.get("committed", True))
        return True

    @staticmethod
    def _log_save_failure(task: asyncio.Task) -> None:
        """Surface fire-and-forget save failures to the plugin log."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logging.getLogger("astrbot.compat").error(
                "config.save_config() failed: %s",
                exc,
            )


class StarTools:
    """Legacy StarTools utility class bound to the plugin's Context."""

    _context: Context | None = None

    @classmethod
    def initialize(cls, context: Context) -> None:
        cls._context = context

    @classmethod
    def _bound(cls) -> Context:
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        return cls._context

    @classmethod
    def get_data_dir(cls, plugin_name: str | None = None) -> Any:
        """Return data/plugin_data/{name}, creating it when missing."""
        from pathlib import Path

        data_dir = Path(cls._bound()._ctx.data_dir)
        if plugin_name:
            data_dir = data_dir.parent / plugin_name
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    @classmethod
    async def send_message(cls, session: Any, message_chain: MessageChain) -> bool:
        """Send a message chain to a session by unified message origin."""
        return await cls._bound().send_message(session, message_chain)

    @classmethod
    def register_llm_tool(cls, tool_class: type[FunctionTool]) -> None:
        cls._bound().register_llm_tool(tool_class)

    @classmethod
    def unregister_llm_tool(cls, name: str) -> None:
        cls._bound().unregister_llm_tool(name)

    @classmethod
    def activate_llm_tool(cls, name: str) -> bool:
        return cls._bound().activate_llm_tool(name)

    @classmethod
    def deactivate_llm_tool(cls, name: str) -> bool:
        return cls._bound().deactivate_llm_tool(name)


class Star:
    """Legacy plugin base class."""

    name: str

    def __init__(self, context: Context, config: Any = None) -> None:
        self.context = context
        self.logger = context._ctx.logger

    async def initialize(self) -> None:
        """Called once when the plugin is loaded."""

    async def terminate(self) -> None:
        """Called once when the plugin is unloaded."""

    async def text_to_image(
        self,
        text: str,
        return_url: bool = True,
        template_name: str | None = None,
        umo: str | None = None,
    ) -> Any:
        """Convert text to an image via the render capability.

        Returns an AssetRef rather than a URL or path; legacy media
        components accept it directly as their file source.
        """
        return await self.context.html_renderer.render_t2i(
            text,
            return_url=return_url,
            template_name=template_name,
        )

    async def html_render(
        self,
        tmpl: str,
        data: dict,
        return_url: bool = True,
        options: dict | None = None,
        umo: str | None = None,
    ) -> Any:
        """Render a custom Jinja2 HTML template into an image.

        Returns an AssetRef rather than a URL or path; legacy media
        components accept it directly as their file source.
        """
        return await self.context.html_renderer.render_custom_template(
            tmpl,
            data,
            return_url=return_url,
            **(options or {}),
        )

    async def put_kv_data(self, key: str, value: Any) -> None:
        await self.context.put_kv_data(key, value)

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        return await self.context.get_kv_data(key, default)

    async def delete_kv_data(self, key: str) -> None:
        await self.context.delete_kv_data(key)


def register(
    name: str,
    author: str,
    desc: str,
    version: str,
    repo: str = "",
) -> Any:
    """Legacy register decorator declaring plugin metadata on the class."""

    def decorator(cls: type[Star]) -> type[Star]:
        cls.__astrbot_register__ = {
            "name": name,
            "author": author,
            "desc": desc,
            "version": version,
            "repo": repo,
        }
        return cls

    return decorator
