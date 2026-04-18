# ruff: noqa: E402
from __future__ import annotations

import asyncio
import json
import sys
import types
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})


_install_optional_dependency_stubs()

from astrbot_sdk._internal.invocation_context import current_caller_plugin_id
from astrbot_sdk._internal.plugin_ids import (
    capability_belongs_to_plugin,
    http_route_belongs_to_plugin,
    plugin_capability_prefix,
    plugin_http_route_root,
)
from astrbot_sdk.context import Context
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.message.components import component_to_payload_sync
from astrbot_sdk.runtime._streaming import StreamExecution

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession as CoreMessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform_message_history_mgr import (
    MessageHistoryPage,
    MessageHistoryRecord,
    MessageHistorySender,
)
from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge


class FakeCancelToken:
    def raise_if_cancelled(self) -> None:
        return None


class FakeRuntimeSP:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str], object] = {}

    async def get_async(self, scope, scope_id, key, default=None):
        return self.store.get((scope, scope_id, key), default)

    async def put_async(self, scope, scope_id, key, value):
        self.store[(scope, scope_id, key)] = value

    async def remove_async(self, scope, scope_id, key):
        self.store.pop((scope, scope_id, key), None)

    async def range_get_async(self, scope, scope_id, prefix=None):
        keys = sorted(
            key
            for current_scope, current_scope_id, key in self.store
            if current_scope == scope
            and current_scope_id == scope_id
            and (prefix is None or key.startswith(prefix))
        )
        return [SimpleNamespace(key=key) for key in keys]


class FakeFileTokenService:
    def __init__(self) -> None:
        self._registered: dict[str, str] = {}
        self._counter = 0

    async def register_file(self, path: str, timeout: float | None = None) -> str:
        del timeout
        self._counter += 1
        token = f"file-token-{self._counter}"
        self._registered[token] = str(Path(path))
        return token

    async def handle_file(self, token: str) -> str:
        return self._registered[str(token)]


class FakeConfig(dict[str, Any]):
    def __init__(self) -> None:
        super().__init__(
            callback_api_base="https://callback.example",
            admins_id=["owner-1"],
        )
        self.save_calls = 0

    def save_config(self) -> None:
        self.save_calls += 1


class FakeHTMLRenderer:
    async def render_t2i(
        self,
        text: str,
        *,
        return_url: bool,
        template_name: str | None,
    ) -> str:
        del return_url, template_name
        return f"mock://text-to-image/{text}"

    async def render_custom_template(
        self,
        tmpl: str,
        data: dict[str, Any],
        *,
        return_url: bool,
        options: dict[str, Any] | None,
    ) -> str:
        del return_url, options
        title = data.get("title", "")
        return f"mock://html/{tmpl}/{title}"


@dataclass(slots=True)
class FakeHTTPRoute:
    plugin_id: str
    route: str
    methods: tuple[str, ...]
    handler_capability: str
    description: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "methods": list(self.methods),
            "handler_capability": self.handler_capability,
            "description": self.description,
        }


@dataclass(slots=True)
class _RoundTripOverlay:
    request_id: str
    requested_llm: bool = False
    result_payload: dict[str, Any] | None = None
    handler_whitelist: set[str] | None = None


@dataclass(slots=True)
class FakeRequestContext:
    event: Any
    dispatch_token: str
    cancelled: bool = False
    has_event: bool = True


class FakeGroupEvent:
    def __init__(
        self,
        *,
        session: str,
        is_admin: bool = False,
        members: list[dict[str, str]] | None = None,
    ) -> None:
        self.unified_msg_origin = str(session)
        self._is_admin = bool(is_admin)
        self._members = list(
            members
            or [
                {"user_id": "owner-1", "nickname": "Owner", "role": "owner"},
                {"user_id": "member-1", "nickname": "Member", "role": "member"},
            ]
        )

    def is_admin(self) -> bool:
        return self._is_admin

    async def get_group(self):
        parts = self.unified_msg_origin.split(":")
        if len(parts) < 3 or parts[1] != "group":
            return None
        group_id = parts[-1]
        admins = [
            item["user_id"]
            for item in self._members
            if item.get("role") in {"owner", "admin"}
        ]
        members = [SimpleNamespace(**item) for item in self._members]
        return SimpleNamespace(
            group_id=group_id,
            group_name=f"Group {group_id}",
            group_avatar="",
            group_owner=admins[0] if admins else "",
            group_admins=admins,
            members=members,
        )


class FakePluginBridge:
    def __init__(self) -> None:
        self.http_routes: dict[str, list[FakeHTTPRoute]] = {}
        self._plugin_metadata: dict[str, dict[str, Any]] = {}
        self._plugin_configs: dict[str, dict[str, Any]] = {}
        self._skill_records: dict[str, list[dict[str, str]]] = {}
        self._handlers_by_plugin: dict[str, list[dict[str, Any]]] = {}
        self._request_contexts: dict[str, FakeRequestContext] = {}
        self._latest_request_context_by_plugin: dict[str, FakeRequestContext] = {}
        self._request_contexts_by_token: dict[str, FakeRequestContext] = {}
        self._request_overlays: dict[str, _RoundTripOverlay] = {}
        self._platform_message_counter = 0

    def upsert_plugin(
        self,
        *,
        metadata: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> None:
        plugin_id = str(metadata.get("name", "")).strip()
        if not plugin_id:
            raise ValueError("plugin metadata requires name")
        self._plugin_metadata[plugin_id] = {
            "name": plugin_id,
            "display_name": str(metadata.get("display_name", plugin_id)),
            "description": str(metadata.get("description", "")),
            "author": str(metadata.get("author", "")),
            "version": str(metadata.get("version", "1.0.0")),
            "enabled": bool(metadata.get("enabled", True)),
            "reserved": bool(metadata.get("reserved", False)),
            "acknowledge_global_mcp_risk": bool(
                metadata.get("acknowledge_global_mcp_risk", False)
            ),
            "support_platforms": list(metadata.get("support_platforms", [])),
        }
        self._plugin_configs.setdefault(plugin_id, dict(config or {}))

    def get_plugin_metadata(self, plugin_id: str) -> dict[str, Any] | None:
        payload = self._plugin_metadata.get(str(plugin_id))
        return dict(payload) if isinstance(payload, dict) else None

    def list_plugin_metadata(self) -> list[dict[str, Any]]:
        return [
            dict(self._plugin_metadata[key]) for key in sorted(self._plugin_metadata)
        ]

    def get_plugin_config(self, plugin_id: str) -> dict[str, Any] | None:
        config = self._plugin_configs.get(str(plugin_id))
        return dict(config) if isinstance(config, dict) else None

    def save_plugin_config(
        self,
        plugin_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(config)
        self._plugin_configs[str(plugin_id)] = normalized
        return dict(normalized)

    def set_plugin_handlers(
        self,
        plugin_id: str,
        handlers: list[dict[str, Any]],
    ) -> None:
        self._handlers_by_plugin[str(plugin_id)] = [dict(item) for item in handlers]

    def get_handlers_by_event_type(self, event_type: str) -> list[dict[str, Any]]:
        matched: list[dict[str, Any]] = []
        for handlers in self._handlers_by_plugin.values():
            for handler in handlers:
                if event_type in handler.get("event_types", []):
                    matched.append(dict(handler))
        matched.sort(key=lambda item: item.get("handler_full_name", ""))
        return matched

    def get_handler_by_full_name(self, full_name: str) -> dict[str, Any] | None:
        for handlers in self._handlers_by_plugin.values():
            for handler in handlers:
                if handler.get("handler_full_name") == full_name:
                    return dict(handler)
        return None

    def register_request_context(
        self,
        request_id: str,
        request_context: FakeRequestContext,
    ) -> None:
        normalized_request_id = str(request_id)
        self._request_contexts[normalized_request_id] = request_context
        plugin_id = self.resolve_request_plugin_id(normalized_request_id)
        self._latest_request_context_by_plugin[plugin_id] = request_context
        self._request_contexts_by_token[request_context.dispatch_token] = (
            request_context
        )
        self._request_overlays.setdefault(
            normalized_request_id,
            _RoundTripOverlay(request_id=normalized_request_id),
        )

    def resolve_request_plugin_id(self, request_id: str) -> str:
        plugin_id, _, _ = str(request_id).partition(":")
        return plugin_id or "unknown-plugin"

    def resolve_request_session(self, request_id: str) -> FakeRequestContext | None:
        normalized_request_id = str(request_id)
        request_context = self._request_contexts.get(normalized_request_id)
        if request_context is not None:
            return request_context
        plugin_id = self.resolve_request_plugin_id(normalized_request_id)
        return self._latest_request_context_by_plugin.get(plugin_id)

    def get_request_context_by_token(
        self,
        dispatch_token: str,
    ) -> FakeRequestContext | None:
        return self._request_contexts_by_token.get(str(dispatch_token))

    def before_platform_send(self, dispatch_token: str) -> None:
        del dispatch_token
        return None

    def mark_platform_send(self, dispatch_token: str) -> str:
        self._platform_message_counter += 1
        return f"{dispatch_token or 'dispatchless'}:{self._platform_message_counter}"

    def plugin_supports_platform(self, plugin_id: str, platform_name: str) -> bool:
        metadata = self._plugin_metadata.get(str(plugin_id), {})
        support_platforms = metadata.get("support_platforms")
        if not isinstance(support_platforms, list) or not support_platforms:
            return True
        return str(platform_name) in {
            str(item).strip().lower() for item in support_platforms
        }

    def _overlay(self, request_id: str) -> _RoundTripOverlay:
        return self._request_overlays.setdefault(
            str(request_id),
            _RoundTripOverlay(request_id=str(request_id)),
        )

    def get_request_overlay_by_request_id(
        self,
        request_id: str,
    ) -> _RoundTripOverlay | None:
        return self._request_overlays.get(str(request_id))

    def request_llm_for_request(self, request_id: str) -> bool:
        self._overlay(request_id).requested_llm = True
        return True

    def get_should_call_llm_for_request(self, request_id: str) -> bool | None:
        overlay = self._request_overlays.get(str(request_id))
        return overlay.requested_llm if overlay is not None else None

    def set_result_for_request(
        self,
        request_id: str,
        result_payload: dict[str, Any],
    ) -> bool:
        self._overlay(request_id).result_payload = dict(result_payload)
        return True

    def clear_result_for_request(self, request_id: str) -> bool:
        self._overlay(request_id).result_payload = None
        return True

    def get_result_payload_for_request(
        self,
        request_id: str,
    ) -> dict[str, Any] | None:
        payload = self._overlay(request_id).result_payload
        return dict(payload) if isinstance(payload, dict) else None

    def set_handler_whitelist_for_request(
        self,
        request_id: str,
        plugin_names: set[str] | None,
    ) -> bool:
        overlay = self._overlay(request_id)
        overlay.handler_whitelist = None if plugin_names is None else set(plugin_names)
        return True

    def get_handler_whitelist_for_request(
        self,
        request_id: str,
    ) -> set[str] | None:
        whitelist = self._overlay(request_id).handler_whitelist
        return None if whitelist is None else set(whitelist)

    @staticmethod
    def _normalize_route(route: str) -> str:
        route_text = str(route).strip()
        if not route_text:
            raise ValueError("http route must not be empty")
        if not route_text.startswith("/"):
            route_text = f"/{route_text}"
        return route_text

    @staticmethod
    def _normalize_methods(methods: list[str]) -> tuple[str, ...]:
        normalized = sorted({str(method).upper() for method in methods if method})
        if not normalized:
            raise ValueError("http methods must not be empty")
        return tuple(normalized)

    def register_http_api(
        self,
        *,
        plugin_id: str,
        route: str,
        methods: list[str],
        handler_capability: str,
        description: str,
    ) -> None:
        normalized_route = self._normalize_route(route)
        normalized_methods = self._normalize_methods(methods)
        if not http_route_belongs_to_plugin(normalized_route, plugin_id):
            route_root = plugin_http_route_root(plugin_id)
            raise AstrBotError.invalid_input(
                "http.register_api requires route to use the current plugin "
                f"namespace: route={normalized_route!r}, plugin_id={plugin_id!r}, "
                f"expected={route_root!r} or {route_root + '/...'}"
            )
        if not capability_belongs_to_plugin(str(handler_capability), plugin_id):
            expected_prefix = plugin_capability_prefix(plugin_id)
            raise AstrBotError.invalid_input(
                "http.register_api requires handler_capability to belong to the "
                "current plugin: "
                f"capability={handler_capability!r}, plugin_id={plugin_id!r}, "
                f"expected_prefix={expected_prefix!r}"
            )
        existing = [
            item
            for item in self.http_routes.get(plugin_id, [])
            if item.route != normalized_route or item.methods != normalized_methods
        ]
        existing.append(
            FakeHTTPRoute(
                plugin_id=plugin_id,
                route=normalized_route,
                methods=normalized_methods,
                handler_capability=str(handler_capability),
                description=str(description),
            )
        )
        self.http_routes[plugin_id] = existing

    def unregister_http_api(
        self,
        *,
        plugin_id: str,
        route: str,
        methods: list[str],
    ) -> None:
        normalized_route = self._normalize_route(route)
        existing = list(self.http_routes.get(plugin_id, []))
        if not methods:
            retained = [item for item in existing if item.route != normalized_route]
        else:
            target_methods = set(self._normalize_methods(methods))
            retained = []
            for item in existing:
                if item.route != normalized_route:
                    retained.append(item)
                    continue
                remaining_methods = tuple(
                    method for method in item.methods if method not in target_methods
                )
                if remaining_methods:
                    retained.append(
                        FakeHTTPRoute(
                            plugin_id=item.plugin_id,
                            route=item.route,
                            methods=remaining_methods,
                            handler_capability=item.handler_capability,
                            description=item.description,
                        )
                    )
        if retained:
            self.http_routes[plugin_id] = retained
        else:
            self.http_routes.pop(plugin_id, None)

    def list_http_apis(self, plugin_id: str) -> list[dict[str, Any]]:
        return [
            item.to_payload()
            for item in sorted(
                self.http_routes.get(plugin_id, []),
                key=lambda route: (route.route, route.methods),
            )
        ]

    def register_skill(
        self,
        *,
        plugin_id: str,
        name: str,
        path: str,
        description: str,
    ) -> dict[str, str]:
        raw_path = Path(path)
        if raw_path.is_dir():
            skill_dir = raw_path
            skill_path = raw_path / "SKILL.md"
        else:
            skill_path = raw_path
            skill_dir = raw_path.parent
        record = {
            "name": str(name),
            "description": str(description),
            "path": str(skill_path),
            "skill_dir": str(skill_dir),
        }
        retained = [
            item
            for item in self._skill_records.get(plugin_id, [])
            if item.get("name") != str(name)
        ]
        retained.append(record)
        self._skill_records[plugin_id] = retained
        return dict(record)

    def unregister_skill(self, *, plugin_id: str, name: str) -> bool:
        existing = self._skill_records.get(plugin_id, [])
        retained = [item for item in existing if item.get("name") != str(name)]
        removed = len(retained) != len(existing)
        if retained:
            self._skill_records[plugin_id] = retained
        else:
            self._skill_records.pop(plugin_id, None)
        return removed

    def list_registered_skills(self, plugin_id: str) -> list[dict[str, str]]:
        return [dict(item) for item in self._skill_records.get(plugin_id, [])]

    def acknowledges_global_mcp_risk(self, plugin_id: str) -> bool:
        metadata = self._plugin_metadata.get(str(plugin_id), {})
        return bool(metadata.get("acknowledge_global_mcp_risk", False))

    def remove_plugin(self, plugin_id: str) -> None:
        normalized_plugin_id = str(plugin_id)
        self._plugin_metadata.pop(normalized_plugin_id, None)
        self._plugin_configs.pop(normalized_plugin_id, None)
        self._skill_records.pop(normalized_plugin_id, None)
        self._handlers_by_plugin.pop(normalized_plugin_id, None)
        self.http_routes.pop(normalized_plugin_id, None)
        self._latest_request_context_by_plugin.pop(normalized_plugin_id, None)
        request_ids = [
            request_id
            for request_id in self._request_contexts
            if self.resolve_request_plugin_id(request_id) == normalized_plugin_id
        ]
        for request_id in request_ids:
            request_context = self._request_contexts.pop(request_id, None)
            self._request_overlays.pop(request_id, None)
            if request_context is None:
                continue
            self._request_contexts_by_token.pop(request_context.dispatch_token, None)


class FakeFunctionToolManager:
    def __init__(self) -> None:
        self.func_list: list[object] = []
        self._config: dict[str, Any] = {"mcpServers": {}}
        self.mcp_server_runtime_view: dict[str, Any] = {}

    def load_mcp_config(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._config))

    def save_mcp_config(self, config: dict[str, Any]) -> bool:
        self._config = json.loads(json.dumps(config))
        return True

    async def enable_mcp_server(
        self,
        name: str,
        config: dict[str, Any],
        *_args,
        **_kwargs,
    ) -> None:
        tools = [
            SimpleNamespace(name=str(tool_name))
            for tool_name in config.get("mock_tools", [f"{name}_tool"])
            if str(tool_name).strip()
        ]
        self.mcp_server_runtime_view[str(name)] = SimpleNamespace(
            client=SimpleNamespace(tools=tools, server_errlogs=[]),
        )

    async def disable_mcp_server(
        self,
        name: str | None = None,
        **_kwargs,
    ) -> None:
        if name is None:
            self.mcp_server_runtime_view.clear()
            return
        self.mcp_server_runtime_view.pop(str(name), None)


@dataclass(slots=True)
class FakeProviderMeta:
    id: str
    model: str | None
    type: str
    provider_type: str


@dataclass(slots=True)
class FakeUsage:
    input: int
    output: int
    total: int


@dataclass(slots=True)
class FakeLLMResponse:
    completion_text: str
    usage: FakeUsage | None
    tools_call_ids: list[str] = field(default_factory=list)
    role: str = "assistant"
    reasoning_content: str = ""
    reasoning_signature: str | None = None
    is_chunk: bool = False

    def to_openai_tool_calls(self) -> list[dict[str, Any]]:
        return []


class FakeChatProvider:
    def __init__(
        self,
        provider_id: str,
        *,
        model: str = "mock-model",
        provider_type: str = "chat_completion",
    ) -> None:
        self.provider_config = {
            "id": provider_id,
            "type": "mock",
            "provider_type": provider_type,
            "enable": True,
            "model": model,
        }
        self._meta = FakeProviderMeta(
            id=provider_id,
            model=model,
            type="mock",
            provider_type=provider_type,
        )
        self._chat_queue: list[str] = []
        self._stream_queue: list[str] = []
        self.last_chat_requests: list[dict[str, Any]] = []
        self.last_stream_requests: list[dict[str, Any]] = []

    def meta(self) -> FakeProviderMeta:
        return self._meta

    def enqueue_chat(self, text: str) -> None:
        self._chat_queue.append(str(text))

    def enqueue_stream(self, text: str) -> None:
        self._stream_queue.append(str(text))

    async def text_chat(self, **kwargs: Any) -> FakeLLMResponse:
        self.last_chat_requests.append(dict(kwargs))
        text = self._chat_queue.pop(0) if self._chat_queue else str(kwargs["prompt"])
        usage = FakeUsage(input=3, output=len(text), total=3 + len(text))
        return FakeLLMResponse(completion_text=text, usage=usage)

    async def text_chat_stream(self, **kwargs: Any):
        self.last_stream_requests.append(dict(kwargs))
        text = (
            self._stream_queue.pop(0) if self._stream_queue else str(kwargs["prompt"])
        )
        for char in text:
            await asyncio.sleep(0)
            yield FakeLLMResponse(
                completion_text=char,
                usage=None,
                is_chunk=True,
            )
        yield FakeLLMResponse(completion_text=text, usage=None, is_chunk=False)


class FakeProviderManager:
    def __init__(self, chat_provider: FakeChatProvider) -> None:
        self.providers_config: list[dict[str, Any]] = [
            dict(chat_provider.provider_config)
        ]
        self.inst_map: dict[str, FakeChatProvider] = {
            chat_provider.meta().id: chat_provider
        }
        self.provider_insts: list[FakeChatProvider] = [chat_provider]
        self.active_chat_provider_id = chat_provider.meta().id
        self.active_chat_provider_by_umo: dict[str, str] = {}
        self._hooks: list[Any] = []

    def _provider_payload(self, provider_id: str) -> dict[str, Any]:
        provider = self.inst_map[provider_id]
        payload = dict(provider.provider_config)
        payload.setdefault("enable", True)
        return payload

    @staticmethod
    def _provider_type(config: dict[str, Any]) -> str:
        return str(config.get("provider_type", "chat_completion"))

    def _notify(self, provider_id: str, provider_type: str, umo: str | None) -> None:
        for hook in list(self._hooks):
            hook(provider_id, provider_type, umo)

    def get_insts(self) -> list[FakeChatProvider]:
        return list(self.provider_insts)

    def register_provider_change_hook(self, hook) -> None:
        self._hooks.append(hook)

    def unregister_provider_change_hook(self, hook) -> None:
        if hook in self._hooks:
            self._hooks.remove(hook)

    def get_merged_provider_config(
        self,
        provider_config: dict[str, Any],
    ) -> dict[str, Any]:
        return dict(provider_config)

    async def set_provider(
        self,
        *,
        provider_id: str,
        provider_type,
        umo: str | None = None,
    ) -> None:
        provider_type_value = getattr(provider_type, "value", provider_type)
        if umo:
            self.active_chat_provider_by_umo[str(umo)] = str(provider_id)
        else:
            self.active_chat_provider_id = str(provider_id)
        self._notify(str(provider_id), str(provider_type_value), umo)

    async def create_provider(self, provider_config: dict[str, Any]) -> None:
        normalized = dict(provider_config)
        provider = FakeChatProvider(
            str(normalized["id"]),
            model=str(normalized.get("model", "mock-model")),
            provider_type=self._provider_type(normalized),
        )
        provider.provider_config.update(normalized)
        self.providers_config.append(dict(provider.provider_config))
        self.inst_map[provider.meta().id] = provider
        self.provider_insts = list(self.inst_map.values())
        self._notify(provider.meta().id, self._provider_type(normalized), None)

    async def update_provider(
        self,
        origin_provider_id: str,
        new_config: dict[str, Any],
    ) -> None:
        target_id = str(new_config.get("id") or origin_provider_id)
        updated = dict(self._provider_payload(str(origin_provider_id)))
        updated.update(dict(new_config))
        self.providers_config = [
            updated if item.get("id") == str(origin_provider_id) else dict(item)
            for item in self.providers_config
        ]
        provider = self.inst_map.pop(str(origin_provider_id), None)
        if provider is None:
            provider = FakeChatProvider(
                target_id,
                model=str(updated.get("model", "mock-model")),
                provider_type=self._provider_type(updated),
            )
        provider.provider_config = dict(updated)
        provider._meta = FakeProviderMeta(  # noqa: SLF001
            id=target_id,
            model=str(updated.get("model"))
            if updated.get("model") is not None
            else None,
            type=str(updated.get("type", "mock")),
            provider_type=self._provider_type(updated),
        )
        self.inst_map[target_id] = provider
        self.provider_insts = list(self.inst_map.values())
        if self.active_chat_provider_id == str(origin_provider_id):
            self.active_chat_provider_id = target_id
        self.active_chat_provider_by_umo = {
            key: (target_id if value == str(origin_provider_id) else value)
            for key, value in self.active_chat_provider_by_umo.items()
        }
        self._notify(target_id, self._provider_type(updated), None)

    async def delete_provider(
        self,
        *,
        provider_id: str | None = None,
        provider_source_id: str | None = None,
    ) -> None:
        del provider_source_id
        normalized_provider_id = str(provider_id or "")
        if not normalized_provider_id:
            return
        self.providers_config = [
            item
            for item in self.providers_config
            if str(item.get("id", "")) != normalized_provider_id
        ]
        self.inst_map.pop(normalized_provider_id, None)
        self.provider_insts = list(self.inst_map.values())
        if self.active_chat_provider_id == normalized_provider_id:
            self.active_chat_provider_id = (
                self.provider_insts[0].meta().id if self.provider_insts else ""
            )
        self.active_chat_provider_by_umo = {
            key: value
            for key, value in self.active_chat_provider_by_umo.items()
            if value != normalized_provider_id
        }

    async def load_provider(self, provider_config: dict[str, Any]) -> None:
        await self.create_provider(provider_config)

    async def terminate_provider(self, provider_id: str) -> None:
        await self.delete_provider(provider_id=provider_id)


@dataclass(slots=True)
class FakePlatformMeta:
    id: str
    name: str
    adapter_display_name: str


class FakePlatform:
    def __init__(
        self,
        *,
        platform_id: str = "mock-platform",
        name: str = "mock",
        display_name: str = "Mock Platform",
        status: str = "running",
    ) -> None:
        self._meta = FakePlatformMeta(
            id=platform_id,
            name=name,
            adapter_display_name=display_name,
        )
        self.status = SimpleNamespace(value=status)

    def meta(self) -> FakePlatformMeta:
        return self._meta


class FakeMessageHistoryManager:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], list[MessageHistoryRecord]] = {}
        self._next_id = 1
        self._last_created_at: datetime | None = None

    @staticmethod
    def _session_key(session: CoreMessageSession) -> tuple[str, str, str]:
        if session.message_type == MessageType.GROUP_MESSAGE:
            message_type = "group"
        elif session.message_type == MessageType.FRIEND_MESSAGE:
            message_type = "private"
        else:
            message_type = "other"
        return (str(session.platform_id), message_type, str(session.session_id))

    def _records_for(self, session: CoreMessageSession) -> list[MessageHistoryRecord]:
        return self._records.setdefault(self._session_key(session), [])

    async def append(
        self,
        session: CoreMessageSession,
        *,
        parts: list[Any],
        sender: MessageHistorySender,
        metadata: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> MessageHistoryRecord:
        now = datetime.now(timezone.utc)
        # Windows test environments can return identical wall-clock timestamps
        # for consecutive inserts. Keep fake history timestamps monotonic so
        # delete_before/delete_after boundary tests reflect the manager contract
        # instead of host clock resolution.
        if self._last_created_at is not None and now <= self._last_created_at:
            now = self._last_created_at + timedelta(microseconds=1)
        self._last_created_at = now
        record = MessageHistoryRecord(
            id=self._next_id,
            session=session,
            sender=sender,
            parts=list(parts),
            metadata=dict(metadata),
            created_at=now,
            updated_at=now,
            idempotency_key=idempotency_key,
        )
        self._next_id += 1
        self._records_for(session).append(record)
        return record

    async def list(
        self,
        session: CoreMessageSession,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> MessageHistoryPage:
        records = list(self._records_for(session))
        start = int(cursor) if cursor is not None else 0
        page_records = records[start : start + limit]
        next_cursor = str(start + limit) if start + limit < len(records) else None
        return MessageHistoryPage(
            records=page_records,
            next_cursor=next_cursor,
            total=len(records),
        )

    async def get_by_id(
        self,
        session: CoreMessageSession,
        record_id: int,
    ) -> MessageHistoryRecord | None:
        for record in self._records_for(session):
            if record.id == record_id:
                return record
        return None

    async def delete_before(
        self,
        session: CoreMessageSession,
        *,
        before: datetime,
    ) -> int:
        records = self._records_for(session)
        retained = [record for record in records if record.created_at >= before]
        deleted = len(records) - len(retained)
        self._records[self._session_key(session)] = retained
        return deleted

    async def delete_after(
        self,
        session: CoreMessageSession,
        *,
        after: datetime,
    ) -> int:
        records = self._records_for(session)
        retained = [record for record in records if record.created_at <= after]
        deleted = len(records) - len(retained)
        self._records[self._session_key(session)] = retained
        return deleted

    async def delete_all(self, session: CoreMessageSession) -> int:
        records = self._records_for(session)
        deleted = len(records)
        self._records[self._session_key(session)] = []
        return deleted


class FakeStarContext:
    def __init__(
        self,
        *,
        plugin_bridge: FakePluginBridge,
        func_tool_manager: FakeFunctionToolManager,
        provider_manager: FakeProviderManager,
        platforms: list[FakePlatform],
        config: FakeConfig,
        message_history_manager: FakeMessageHistoryManager,
    ) -> None:
        self._plugin_bridge = plugin_bridge
        self._func_tool_manager = func_tool_manager
        self.provider_manager = provider_manager
        self.platform_manager = SimpleNamespace(get_insts=lambda: list(platforms))
        self._config = config
        self.message_history_manager = message_history_manager
        self.persona_manager = object()
        self.conversation_manager = object()
        self.kb_manager = object()
        self.sent_messages: list[dict[str, Any]] = []

    async def send_message(self, session: str, message_chain: MessageChain) -> None:
        self.sent_messages.append(
            {
                "session": str(session),
                "text": message_chain.get_plain_text(with_other_comps_mark=True),
                "chain": [
                    component_to_payload_sync(component)
                    for component in message_chain.chain
                ],
            }
        )

    def get_config(self) -> FakeConfig:
        return self._config

    def get_llm_tool_manager(self) -> FakeFunctionToolManager:
        return self._func_tool_manager

    def get_all_stars(self) -> list[Any]:
        return [
            SimpleNamespace(
                name=payload["name"],
                reserved=bool(payload.get("reserved", False)),
            )
            for payload in self._plugin_bridge.list_plugin_metadata()
        ]

    def get_provider_by_id(self, provider_id: str) -> FakeChatProvider | None:
        return self.provider_manager.inst_map.get(str(provider_id))

    def get_using_provider(self, umo: str | None = None) -> FakeChatProvider | None:
        provider_id = (
            self.provider_manager.active_chat_provider_by_umo.get(str(umo))
            if umo is not None
            else self.provider_manager.active_chat_provider_id
        )
        if not provider_id:
            provider_id = self.provider_manager.active_chat_provider_id
        return self.provider_manager.inst_map.get(provider_id)

    def get_all_providers(self) -> list[FakeChatProvider]:
        return list(self.provider_manager.provider_insts)

    def get_all_tts_providers(self) -> list[Any]:
        return []

    def get_all_stt_providers(self) -> list[Any]:
        return []

    def get_all_embedding_providers(self) -> list[Any]:
        return []

    def get_all_rerank_providers(self) -> list[Any]:
        return []

    def get_using_tts_provider(self, umo: str | None = None) -> Any | None:
        del umo
        return None

    def get_using_stt_provider(self, umo: str | None = None) -> Any | None:
        del umo
        return None


class BridgeBackedPeer:
    def __init__(self, bridge: CoreCapabilityBridge) -> None:
        self._bridge = bridge
        self._request_counter = 0
        self.remote_peer = object()
        self.remote_capability_map = {
            descriptor.name: descriptor for descriptor in bridge.all_descriptors()
        }

    def _next_request_id(self) -> str:
        self._request_counter += 1
        plugin_id = current_caller_plugin_id() or "unknown-plugin"
        return f"{plugin_id}:ctx-{self._request_counter}"

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        stream: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        result = await self._bridge.execute(
            capability,
            dict(payload),
            stream=stream,
            cancel_token=FakeCancelToken(),
            request_id=request_id or self._next_request_id(),
        )
        assert isinstance(result, dict)
        return result

    async def invoke_stream(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ):
        result = await self._bridge.execute(
            capability,
            dict(payload),
            stream=True,
            cancel_token=FakeCancelToken(),
            request_id=request_id or self._next_request_id(),
        )
        assert isinstance(result, StreamExecution)

        async def _iterator():
            async for chunk in result.iterator:
                yield SimpleNamespace(phase="delta", data=chunk)

        return _iterator()


@dataclass(slots=True)
class RoundTripRuntime:
    bridge: CoreCapabilityBridge
    peer: BridgeBackedPeer
    plugin_bridge: FakePluginBridge
    func_tool_manager: FakeFunctionToolManager
    runtime_sp: FakeRuntimeSP
    star_context: FakeStarContext
    provider_manager: FakeProviderManager
    chat_provider: FakeChatProvider
    file_token_service: FakeFileTokenService
    config: FakeConfig
    message_history_manager: FakeMessageHistoryManager

    def make_context(
        self,
        plugin_id: str,
        *,
        request_id: str | None = None,
        source_event_payload: dict[str, Any] | None = None,
    ) -> Context:
        return Context(
            peer=self.peer,
            plugin_id=plugin_id,
            request_id=request_id,
            source_event_payload=source_event_payload,
        )

    def enqueue_llm_response(self, text: str) -> None:
        self.chat_provider.enqueue_chat(text)

    def enqueue_llm_stream(self, text: str) -> None:
        self.chat_provider.enqueue_stream(text)

    def register_group_request(
        self,
        *,
        request_id: str,
        session: str,
        is_admin: bool = False,
        members: list[dict[str, str]] | None = None,
    ) -> str:
        dispatch_token = f"dispatch-{uuid.uuid4().hex}"
        self.plugin_bridge.register_request_context(
            request_id,
            FakeRequestContext(
                event=FakeGroupEvent(
                    session=session,
                    is_admin=is_admin,
                    members=members,
                ),
                dispatch_token=dispatch_token,
            ),
        )
        return dispatch_token

    def set_session_plugin_config(
        self,
        session: str,
        *,
        enabled_plugins: list[str] | None = None,
        disabled_plugins: list[str] | None = None,
    ) -> None:
        self.runtime_sp.store[("umo", str(session), "session_plugin_config")] = {
            str(session): {
                "enabled_plugins": list(enabled_plugins or []),
                "disabled_plugins": list(disabled_plugins or []),
            }
        }

    def set_session_service_config(
        self,
        session: str,
        *,
        llm_enabled: bool = True,
        tts_enabled: bool = True,
    ) -> None:
        self.runtime_sp.store[("umo", str(session), "session_service_config")] = {
            "llm_enabled": bool(llm_enabled),
            "tts_enabled": bool(tts_enabled),
        }


def build_roundtrip_runtime(
    monkeypatch,
    *,
    tmp_path,
) -> RoundTripRuntime:
    runtime_sp = FakeRuntimeSP()
    file_token_service = FakeFileTokenService()
    config = FakeConfig()
    plugin_bridge = FakePluginBridge()
    func_tool_manager = FakeFunctionToolManager()
    chat_provider = FakeChatProvider("chat-provider-a", model="gpt-roundtrip")
    provider_manager = FakeProviderManager(chat_provider)
    message_history_manager = FakeMessageHistoryManager()
    star_context = FakeStarContext(
        plugin_bridge=plugin_bridge,
        func_tool_manager=func_tool_manager,
        provider_manager=provider_manager,
        platforms=[FakePlatform()],
        config=config,
        message_history_manager=message_history_manager,
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic._get_runtime_sp",
        lambda: runtime_sp,
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.session._get_runtime_sp",
        lambda: runtime_sp,
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.system._get_runtime_html_renderer",
        lambda: FakeHTMLRenderer(),
    )

    bridge = CoreCapabilityBridge(
        star_context=star_context,
        plugin_bridge=plugin_bridge,
    )
    peer = BridgeBackedPeer(bridge)
    return RoundTripRuntime(
        bridge=bridge,
        peer=peer,
        plugin_bridge=plugin_bridge,
        func_tool_manager=func_tool_manager,
        runtime_sp=runtime_sp,
        star_context=star_context,
        provider_manager=provider_manager,
        chat_provider=chat_provider,
        file_token_service=file_token_service,
        config=config,
        message_history_manager=message_history_manager,
    )
