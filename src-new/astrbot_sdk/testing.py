"""本地开发与插件测试辅助。

`astrbot_sdk.testing` 是面向插件作者的稳定开发入口：

- `PluginHarness` 负责复用现有 loader / dispatcher 执行链
- `MockCapabilityRouter` 提供进程内 mock core 能力
- `MockPeer` 让 `Context` 客户端继续走真实的 capability 调用路径
- `StdoutPlatformSink` / `RecordedSend` 提供可观测的发送记录

这个模块刻意不暴露 runtime 内部编排数据结构，只封装本地开发/测试真正
需要的最小稳定面。
"""

from __future__ import annotations

import asyncio
import inspect
import re
import shlex
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, TextIO, get_type_hints

from .context import CancelToken, Context as RuntimeContext
from .errors import AstrBotError
from .events import MessageEvent
from .protocol.descriptors import (
    CommandTrigger,
    EventTrigger,
    MessageTrigger,
    ScheduleTrigger,
)
from .protocol.messages import EventMessage, InvokeMessage, PeerInfo
from .runtime.capability_router import CapabilityRouter, StreamExecution
from .runtime.handler_dispatcher import CapabilityDispatcher, HandlerDispatcher
from .runtime.loader import (
    LoadedHandler,
    LoadedPlugin,
    PluginSpec,
    load_plugin,
    load_plugin_config,
    load_plugin_spec,
    validate_plugin_spec,
)
from .star import Star


class _PluginLoadError(RuntimeError):
    """本地 harness 初始化阶段的已知插件加载失败。"""


class _PluginExecutionError(RuntimeError):
    """本地 harness 执行插件代码时的已知插件异常。"""


@dataclass(slots=True)
class RecordedSend:
    """结构化发送记录，供断言和本地调试输出复用。"""

    kind: str
    message_id: str
    session_id: str
    text: str | None = None
    image_url: str | None = None
    chain: list[dict[str, Any]] | None = None
    target: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def session(self) -> str:
        return self.session_id

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RecordedSend":
        if "text" in payload:
            kind = "text"
        elif "image_url" in payload:
            kind = "image"
        elif "chain" in payload:
            kind = "chain"
        else:
            kind = "unknown"
        return cls(
            kind=kind,
            message_id=str(payload.get("message_id", "")),
            session_id=str(payload.get("session", "")),
            text=payload.get("text") if isinstance(payload.get("text"), str) else None,
            image_url=(
                payload.get("image_url")
                if isinstance(payload.get("image_url"), str)
                else None
            ),
            chain=(
                [dict(item) for item in payload.get("chain", [])]
                if isinstance(payload.get("chain"), list)
                else None
            ),
            target=(
                dict(payload.get("target"))
                if isinstance(payload.get("target"), dict)
                else None
            ),
            raw=dict(payload),
        )


class StdoutPlatformSink:
    """把 platform.* 的发送结果同时写到终端与内存记录。"""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream
        self.records: list[RecordedSend] = []

    def record(self, item: RecordedSend) -> None:
        self.records.append(item)
        if self._stream is None:
            return
        self._stream.write(self._format(item) + "\n")
        self._stream.flush()

    def clear(self) -> None:
        self.records.clear()

    def _format(self, item: RecordedSend) -> str:
        if item.kind == "text":
            return f"[text][{item.session_id}] {item.text or ''}"
        if item.kind == "image":
            return f"[image][{item.session_id}] {item.image_url or ''}"
        if item.kind == "chain":
            count = len(item.chain or [])
            return f"[chain][{item.session_id}] {count} components"
        return f"[send][{item.session_id}] {item.raw}"


class InMemoryDB:
    """测试友好的 KV 视图，直接绑定到 mock router 的内存存储。"""

    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def list(self, prefix: str | None = None) -> list[str]:
        keys = sorted(self._store.keys())
        if prefix is None:
            return keys
        return [key for key in keys if key.startswith(prefix)]

    def get_many(self, keys: list[str]) -> list[dict[str, Any]]:
        return [{"key": key, "value": self._store.get(key)} for key in keys]

    def set_many(self, items: list[dict[str, Any]]) -> None:
        for item in items:
            self.set(str(item.get("key", "")), item.get("value"))


class InMemoryMemory:
    """测试友好的 memory 视图，保持与 mock router 同步。"""

    def __init__(self, store: dict[str, dict[str, Any]]) -> None:
        self._store = store

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def save(self, key: str, value: dict[str, Any]) -> None:
        self._store[key] = dict(value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def search(self, query: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for key, value in self._store.items():
            if query in key or query in str(value):
                results.append({"key": key, "value": value})
        return results


class MockLLMClient:
    """在真实 LLMClient 之上补一层测试控制能力。"""

    def __init__(self, client: Any, router: "MockCapabilityRouter") -> None:
        self._client = client
        self._router = router

    def mock_response(self, text: str) -> None:
        self._router.enqueue_llm_response(text)

    def mock_stream_response(self, text: str) -> None:
        self._router.enqueue_llm_stream_response(text)

    def clear_mock_responses(self) -> None:
        self._router.clear_llm_responses()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class MockPlatformClient:
    """在真实 PlatformClient 之上补一层断言入口。"""

    def __init__(self, client: Any, sink: StdoutPlatformSink) -> None:
        self._client = client
        self._sink = sink

    @property
    def records(self) -> list[RecordedSend]:
        return list(self._sink.records)

    def assert_sent(
        self,
        expected_text: str | None = None,
        *,
        kind: str = "text",
        count: int | None = None,
    ) -> None:
        matched = [item for item in self._sink.records if item.kind == kind]
        if expected_text is not None:
            matched = [item for item in matched if item.text == expected_text]
        if count is not None:
            if len(matched) != count:
                raise AssertionError(
                    f"expected {count} sent records, got {len(matched)}: {matched}"
                )
            return
        if not matched:
            raise AssertionError(
                f"expected sent record kind={kind!r} text={expected_text!r}, got {self._sink.records}"
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class MockCapabilityRouter(CapabilityRouter):
    """本地 mock core，直接复用已有的内建 capability 实现。"""

    def __init__(self, *, platform_sink: StdoutPlatformSink | None = None) -> None:
        self.platform_sink = platform_sink or StdoutPlatformSink()
        self._llm_responses: list[str] = []
        self._llm_stream_responses: list[str] = []
        super().__init__()
        self.db = InMemoryDB(self.db_store)
        self.memory = InMemoryMemory(self.memory_store)

    def enqueue_llm_response(self, text: str) -> None:
        self._llm_responses.append(text)

    def enqueue_llm_stream_response(self, text: str) -> None:
        self._llm_stream_responses.append(text)

    def clear_llm_responses(self) -> None:
        self._llm_responses.clear()
        self._llm_stream_responses.clear()

    async def execute(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        stream: bool,
        cancel_token,
        request_id: str,
    ) -> dict[str, Any] | StreamExecution:
        if capability == "llm.chat":
            return {"text": self._take_llm_response(str(payload.get("prompt", "")))}
        if capability == "llm.chat_raw":
            text = self._take_llm_response(str(payload.get("prompt", "")))
            return {
                "text": text,
                "usage": {
                    "input_tokens": len(str(payload.get("prompt", ""))),
                    "output_tokens": len(text),
                },
                "finish_reason": "stop",
                "tool_calls": [],
            }
        if capability == "llm.stream_chat":
            text = self._take_llm_stream_response(str(payload.get("prompt", "")))

            async def iterator() -> typing.AsyncIterator[dict[str, Any]]:
                for char in text:
                    cancel_token.raise_if_cancelled()
                    await asyncio.sleep(0)
                    yield {"text": char}

            return StreamExecution(
                iterator=iterator(),
                finalize=lambda chunks: {
                    "text": "".join(item.get("text", "") for item in chunks)
                },
            )
        before = len(self.sent_messages)
        result = await super().execute(
            capability,
            payload,
            stream=stream,
            cancel_token=cancel_token,
            request_id=request_id,
        )
        self._flush_platform_records(before)
        return result

    def _flush_platform_records(self, start_index: int) -> None:
        for payload in self.sent_messages[start_index:]:
            self.platform_sink.record(RecordedSend.from_payload(payload))

    def _take_llm_response(self, prompt: str) -> str:
        if self._llm_responses:
            return self._llm_responses.pop(0)
        return f"Echo: {prompt}"

    def _take_llm_stream_response(self, prompt: str) -> str:
        if self._llm_stream_responses:
            return self._llm_stream_responses.pop(0)
        if self._llm_responses:
            return self._llm_responses.pop(0)
        return f"Echo: {prompt}"


class MockPeer:
    """满足 `Context`/`CapabilityProxy` 需要的最小 peer。"""

    def __init__(self, router: MockCapabilityRouter) -> None:
        self._router = router
        self._counter = 0
        self.remote_peer = PeerInfo(
            name="astrbot-local-core",
            role="core",
            version="local",
        )
        self.remote_capabilities = list(router.descriptors())
        self.remote_capability_map = {
            item.name: item for item in self.remote_capabilities
        }
        self.remote_handlers: list[Any] = []
        self.remote_provided_capabilities: list[Any] = []
        self.remote_metadata = {"mode": "local"}

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        stream: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if stream:
            raise ValueError("stream=True 请使用 invoke_stream()")
        return typing.cast(
            dict[str, Any],
            await self._router.execute(
                capability,
                payload,
                stream=False,
                cancel_token=CancelToken(),
                request_id=request_id or self._next_id(),
            ),
        )

    async def invoke_stream(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        include_completed: bool = False,
    ):
        request_id = request_id or self._next_id()
        execution = typing.cast(
            StreamExecution,
            await self._router.execute(
                capability,
                payload,
                stream=True,
                cancel_token=CancelToken(),
                request_id=request_id,
            ),
        )

        async def iterator():
            yield EventMessage(id=request_id, phase="started")
            chunks: list[dict[str, Any]] = []
            async for chunk in execution.iterator:
                if execution.collect_chunks:
                    chunks.append(chunk)
                yield EventMessage(id=request_id, phase="delta", data=chunk)
            output = execution.finalize(chunks)
            if include_completed:
                yield EventMessage(id=request_id, phase="completed", output=output)

        return iterator()

    def _next_id(self) -> str:
        self._counter += 1
        return f"local_{self._counter:04d}"


def _plugin_metadata_from_spec(
    plugin: PluginSpec,
    *,
    enabled: bool,
) -> dict[str, Any]:
    manifest = plugin.manifest_data
    return {
        "name": plugin.name,
        "display_name": str(manifest.get("display_name") or plugin.name),
        "description": str(manifest.get("desc") or manifest.get("description") or ""),
        "author": str(manifest.get("author") or ""),
        "version": str(manifest.get("version") or "0.0.0"),
        "enabled": enabled,
    }


def _normalize_plugin_metadata(
    plugin_id: str,
    plugin_metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if plugin_metadata is None:
        plugin_metadata = {}
    declared_name = plugin_metadata.get("name")
    if declared_name is not None and str(declared_name) != plugin_id:
        raise ValueError(
            "MockContext.plugin_metadata['name'] 必须与 plugin_id 一致，"
            f"当前收到 {declared_name!r} != {plugin_id!r}"
        )
    description = plugin_metadata.get("description")
    if description is None:
        description = plugin_metadata.get("desc", "")
    return {
        "name": plugin_id,
        "display_name": str(plugin_metadata.get("display_name") or plugin_id),
        "description": str(description or ""),
        "author": str(plugin_metadata.get("author") or ""),
        "version": str(plugin_metadata.get("version") or "0.0.0"),
        "enabled": bool(plugin_metadata.get("enabled", True)),
    }


class MockContext(RuntimeContext):
    """直接用于 handler 单元测试的轻量运行时上下文。"""

    def __init__(
        self,
        *,
        plugin_id: str = "test-plugin",
        logger: Any | None = None,
        cancel_token: CancelToken | None = None,
        platform_sink: StdoutPlatformSink | None = None,
        plugin_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.platform_sink = platform_sink or StdoutPlatformSink()
        self.router = MockCapabilityRouter(platform_sink=self.platform_sink)
        self.mock_peer = MockPeer(self.router)
        super().__init__(
            peer=self.mock_peer,
            plugin_id=plugin_id,
            cancel_token=cancel_token,
            logger=logger,
        )
        self.router.upsert_plugin(
            metadata=_normalize_plugin_metadata(plugin_id, plugin_metadata),
            config={},
        )
        self.llm = MockLLMClient(self.llm, self.router)
        self.platform = MockPlatformClient(self.platform, self.platform_sink)

    @property
    def sent_messages(self) -> list[RecordedSend]:
        return list(self.platform_sink.records)


class MockMessageEvent(MessageEvent):
    """直接用于 handler 单元测试的轻量消息事件。"""

    def __init__(
        self,
        *,
        text: str = "",
        user_id: str | None = "test-user",
        group_id: str | None = None,
        platform: str | None = "test",
        session_id: str | None = "test-session",
        raw: dict[str, Any] | None = None,
        context: MockContext | None = None,
    ) -> None:
        self.replies: list[str] = []
        super().__init__(
            text=text,
            user_id=user_id,
            group_id=group_id,
            platform=platform,
            session_id=session_id,
            raw=raw,
            context=context,
        )
        if context is not None:
            self.bind_runtime_reply(context)
        elif self._reply_handler is None:
            self.bind_reply_handler(self._capture_reply)

    @property
    def is_private(self) -> bool:
        return self.group_id is None

    def bind_runtime_reply(self, context: MockContext) -> None:
        self._context = context

        async def reply(text: str) -> None:
            self.replies.append(text)
            await context.platform.send(self.session_ref or self.session_id, text)

        self.bind_reply_handler(reply)

    async def _capture_reply(self, text: str) -> None:
        self.replies.append(text)


@dataclass(slots=True)
class LocalRuntimeConfig:
    """本地 harness 的稳定配置对象。"""

    plugin_dir: Path
    session_id: str = "local-session"
    user_id: str = "local-user"
    platform: str = "test"
    group_id: str | None = None
    event_type: str = "message"


class PluginHarness:
    """本地插件消息泵。

    这里复用真实的 loader / dispatcher 执行链，只负责：
    - 在同一个事件循环里装配单插件运行时
    - 维持本地 mock core 与发送记录
    - 把后续消息持续送入同一个 dispatcher
    """

    def __init__(
        self,
        config: LocalRuntimeConfig,
        *,
        platform_sink: StdoutPlatformSink | None = None,
    ) -> None:
        self.config = config
        self.platform_sink = platform_sink or StdoutPlatformSink()
        self.router = MockCapabilityRouter(platform_sink=self.platform_sink)
        self.peer = MockPeer(self.router)
        self.plugin: PluginSpec | None = None
        self.loaded_plugin: LoadedPlugin | None = None
        self.dispatcher: HandlerDispatcher | None = None
        self.capability_dispatcher: CapabilityDispatcher | None = None
        self.lifecycle_context: RuntimeContext | None = None
        self._request_counter = 0
        self._started = False

    @classmethod
    def from_plugin_dir(
        cls,
        plugin_dir: str | Path,
        *,
        session_id: str = "local-session",
        user_id: str = "local-user",
        platform: str = "test",
        group_id: str | None = None,
        event_type: str = "message",
        platform_sink: StdoutPlatformSink | None = None,
    ) -> "PluginHarness":
        return cls(
            LocalRuntimeConfig(
                plugin_dir=Path(plugin_dir),
                session_id=session_id,
                user_id=user_id,
                platform=platform,
                group_id=group_id,
                event_type=event_type,
            ),
            platform_sink=platform_sink,
        )

    async def __aenter__(self) -> "PluginHarness":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    @property
    def sent_messages(self) -> list[RecordedSend]:
        return list(self.platform_sink.records)

    def clear_sent_messages(self) -> None:
        self.platform_sink.clear()

    async def start(self) -> None:
        if self._started:
            return
        try:
            self.plugin = load_plugin_spec(self.config.plugin_dir)
            validate_plugin_spec(self.plugin)
            self.loaded_plugin = load_plugin(self.plugin)
        except Exception as exc:  # pragma: no cover - 由 CLI/集成测试覆盖
            raise _PluginLoadError(str(exc)) from exc
        self.dispatcher = HandlerDispatcher(
            plugin_id=self.plugin.name,
            peer=self.peer,
            handlers=self.loaded_plugin.handlers,
        )
        self.capability_dispatcher = CapabilityDispatcher(
            plugin_id=self.plugin.name,
            peer=self.peer,
            capabilities=self.loaded_plugin.capabilities,
        )
        self.lifecycle_context = RuntimeContext(
            peer=self.peer,
            plugin_id=self.plugin.name,
        )
        self.router.upsert_plugin(
            metadata=_plugin_metadata_from_spec(self.plugin, enabled=True),
            config=load_plugin_config(self.plugin),
        )
        try:
            await self._run_lifecycle("on_start")
        except AstrBotError:
            raise
        except Exception as exc:  # pragma: no cover - 由 CLI/集成测试覆盖
            raise _PluginExecutionError(str(exc)) from exc
        self._started = True

    async def stop(self) -> None:
        if (
            not self._started
            or self.loaded_plugin is None
            or self.lifecycle_context is None
        ):
            return
        try:
            await self._run_lifecycle("on_stop")
        finally:
            if self.plugin is not None:
                self.router.set_plugin_enabled(self.plugin.name, False)
                self.router.remove_http_apis_for_plugin(self.plugin.name)
            self._started = False

    async def dispatch_text(
        self,
        text: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        platform: str | None = None,
        group_id: str | None = None,
        event_type: str | None = None,
        request_id: str | None = None,
    ) -> list[RecordedSend]:
        payload = self.build_event_payload(
            text=text,
            session_id=session_id,
            user_id=user_id,
            platform=platform,
            group_id=group_id,
            event_type=event_type,
            request_id=request_id,
        )
        return await self.dispatch_event(payload, request_id=request_id)

    async def dispatch_event(
        self,
        event_payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> list[RecordedSend]:
        await self.start()
        assert self.loaded_plugin is not None
        assert self.dispatcher is not None

        start_index = len(self.platform_sink.records)
        if self._has_waiter_for_event(event_payload):
            carrier = (
                self.loaded_plugin.handlers[0] if self.loaded_plugin.handlers else None
            )
            if carrier is None:
                raise AstrBotError.invalid_input(
                    "当前没有可用于承接 session_waiter 的 handler"
                )
            await self._invoke_handler(
                carrier,
                event_payload,
                args={},
                request_id=request_id,
            )
            await self._wait_for_followup_side_effects(
                start_index=start_index,
                event_payload=event_payload,
            )
            return self.platform_sink.records[start_index:]

        matches = self._match_handlers(event_payload)
        if not matches:
            raise AstrBotError.invalid_input("未找到匹配的 handler")
        for loaded, args in matches:
            await self._invoke_handler(
                loaded,
                event_payload,
                args=args,
                request_id=request_id,
            )
        return self.platform_sink.records[start_index:]

    async def invoke_capability(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        stream: bool = False,
    ) -> dict[str, Any] | StreamExecution:
        await self.start()
        assert self.capability_dispatcher is not None
        message = InvokeMessage(
            id=request_id or self._next_request_id("cap"),
            capability=capability,
            input=dict(payload),
            stream=stream,
        )
        try:
            return await self.capability_dispatcher.invoke(message, CancelToken())
        except AstrBotError:
            raise
        except Exception as exc:  # pragma: no cover - 由 CLI/集成测试覆盖
            raise _PluginExecutionError(str(exc)) from exc

    def build_event_payload(
        self,
        *,
        text: str,
        session_id: str | None = None,
        user_id: str | None = None,
        platform: str | None = None,
        group_id: str | None = None,
        event_type: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        session_value = session_id or self.config.session_id
        group_value = group_id if group_id is not None else self.config.group_id
        event_type_value = event_type or self.config.event_type
        payload = {
            "type": event_type_value,
            "event_type": event_type_value,
            "text": text,
            "session_id": session_value,
            "user_id": user_id or self.config.user_id,
            "platform": platform or self.config.platform,
            "group_id": group_value,
            "raw": {
                "trace_id": request_id or self._next_request_id("trace"),
                "event_type": event_type_value,
            },
        }
        if group_value:
            payload["message_type"] = "group"
        elif payload["user_id"]:
            payload["message_type"] = "private"
        else:
            payload["message_type"] = "other"
        return payload

    async def _invoke_handler(
        self,
        loaded: LoadedHandler,
        event_payload: dict[str, Any],
        *,
        args: dict[str, Any],
        request_id: str | None = None,
    ) -> None:
        assert self.dispatcher is not None
        message = InvokeMessage(
            id=request_id or self._next_request_id("msg"),
            capability="handler.invoke",
            input={
                "handler_id": loaded.descriptor.id,
                "event": dict(event_payload),
                "args": dict(args),
            },
        )
        try:
            await self.dispatcher.invoke(message, CancelToken())
        except AstrBotError:
            raise
        except Exception as exc:  # pragma: no cover - 由 CLI/集成测试覆盖
            raise _PluginExecutionError(str(exc)) from exc

    async def _wait_for_followup_side_effects(
        self,
        *,
        start_index: int,
        event_payload: dict[str, Any],
    ) -> None:
        for _ in range(20):
            if len(self.platform_sink.records) > start_index:
                return
            await asyncio.sleep(0)
            if not self._has_waiter_for_event(event_payload):
                return

    async def _run_lifecycle(self, method_name: str) -> None:
        assert self.loaded_plugin is not None
        assert self.lifecycle_context is not None

        for instance in self.loaded_plugin.instances:
            hook = self._resolve_lifecycle_hook(instance, method_name)
            if hook is None:
                continue
            args: list[Any] = []
            try:
                signature = inspect.signature(hook)
            except (TypeError, ValueError):
                signature = None
            if signature is not None:
                positional_params = [
                    parameter
                    for parameter in signature.parameters.values()
                    if parameter.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                if positional_params:
                    args.append(self.lifecycle_context)
            result = hook(*args)
            if inspect.isawaitable(result):
                await result

    def _match_handlers(
        self,
        event_payload: dict[str, Any],
    ) -> list[tuple[LoadedHandler, dict[str, Any]]]:
        assert self.loaded_plugin is not None
        ranked: list[tuple[int, int, LoadedHandler, dict[str, Any]]] = []
        for index, loaded in enumerate(self.loaded_plugin.handlers):
            args = self._match_handler(loaded, event_payload)
            if args is None:
                continue
            ranked.append((loaded.descriptor.priority, index, loaded, args))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [(loaded, args) for _priority, _index, loaded, args in ranked]

    def _match_handler(
        self,
        loaded: LoadedHandler,
        event_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        trigger = loaded.descriptor.trigger
        if isinstance(trigger, CommandTrigger):
            return self._match_command_trigger(loaded, trigger, event_payload)
        if isinstance(trigger, MessageTrigger):
            return self._match_message_trigger(loaded, trigger, event_payload)
        if isinstance(trigger, EventTrigger):
            current_type = str(
                event_payload.get("event_type")
                or event_payload.get("type")
                or "message"
            )
            if current_type != trigger.event_type:
                return None
            return {}
        if isinstance(trigger, ScheduleTrigger):
            return None
        return None

    def _match_command_trigger(
        self,
        loaded: LoadedHandler,
        trigger: CommandTrigger,
        event_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self._passes_trigger_constraints(
            trigger.platforms, trigger.message_types, event_payload
        ):
            return None
        text = str(event_payload.get("text", "")).strip()
        for command_name in [trigger.command, *trigger.aliases]:
            if not command_name:
                continue
            match = self._match_command_name(text, command_name)
            if match is None:
                continue
            return self._build_command_args(loaded.callable, match)
        return None

    def _match_message_trigger(
        self,
        loaded: LoadedHandler,
        trigger: MessageTrigger,
        event_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self._passes_trigger_constraints(
            trigger.platforms, trigger.message_types, event_payload
        ):
            return None
        text = str(event_payload.get("text", ""))
        if trigger.regex:
            match = re.search(trigger.regex, text)
            if match is None:
                return None
            return self._build_regex_args(loaded.callable, match)
        if trigger.keywords and not any(
            keyword in text for keyword in trigger.keywords
        ):
            return None
        return {}

    def _passes_trigger_constraints(
        self,
        platforms: list[str],
        message_types: list[str],
        event_payload: dict[str, Any],
    ) -> bool:
        platform = str(event_payload.get("platform", ""))
        if platforms and platform not in platforms:
            return False
        if not message_types:
            return True
        current_message_type = self._message_type_name(event_payload)
        return current_message_type in message_types

    def _has_waiter_for_event(self, event_payload: dict[str, Any]) -> bool:
        assert self.dispatcher is not None
        probe_event = MessageEvent.from_payload(
            event_payload,
            context=self.lifecycle_context,
        )
        session_waiters = getattr(self.dispatcher, "_session_waiters", None)
        if session_waiters is None:
            return False
        if hasattr(session_waiters, "has_waiter"):
            return session_waiters.has_waiter(probe_event)
        if isinstance(session_waiters, dict):
            return any(
                manager.has_waiter(probe_event)
                for manager in session_waiters.values()
                if hasattr(manager, "has_waiter")
            )
        return False

    @staticmethod
    def _message_type_name(event_payload: dict[str, Any]) -> str:
        explicit = str(event_payload.get("message_type", "")).lower()
        if explicit in {"group", "private", "other"}:
            return explicit
        if event_payload.get("group_id"):
            return "group"
        if event_payload.get("user_id"):
            return "private"
        return "other"

    @staticmethod
    def _match_command_name(text: str, command_name: str) -> str | None:
        if text == command_name:
            return ""
        if text.startswith(f"{command_name} "):
            return text[len(command_name) :].strip()
        return None

    def _build_command_args(self, handler, remainder: str) -> dict[str, Any]:
        names = self._legacy_arg_parameter_names(handler)
        if not names or not remainder:
            return {}
        if len(names) == 1:
            return {names[0]: remainder}
        tokens = self._split_command_remainder(remainder)
        if not tokens:
            return {}
        values: dict[str, Any] = {}
        for index, name in enumerate(names):
            if index >= len(tokens):
                break
            if index == len(names) - 1:
                values[name] = " ".join(tokens[index:])
                break
            values[name] = tokens[index]
        return values

    def _build_regex_args(self, handler, match: re.Match[str]) -> dict[str, Any]:
        named = {
            key: value for key, value in match.groupdict().items() if value is not None
        }
        names = [
            name
            for name in self._legacy_arg_parameter_names(handler)
            if name not in named
        ]
        positional = [value for value in match.groups() if value is not None]
        for index, value in enumerate(positional):
            if index >= len(names):
                break
            named[names[index]] = value
        return named

    @staticmethod
    def _split_command_remainder(remainder: str) -> list[str]:
        try:
            return shlex.split(remainder)
        except ValueError:
            return remainder.split()

    @staticmethod
    def _resolve_lifecycle_hook(instance: Any, method_name: str):
        hook = getattr(instance, method_name, None)
        marker = getattr(instance.__class__, "__astrbot_is_new_star__", None)
        is_new_star = True
        if callable(marker):
            is_new_star = bool(marker())

        if hook is not None and callable(hook):
            bound_func = getattr(hook, "__func__", hook)
            star_default = getattr(Star, method_name, None)
            if star_default is None or bound_func is not star_default:
                return hook

        if not is_new_star:
            alias = {"on_start": "initialize", "on_stop": "terminate"}.get(method_name)
            if alias is not None:
                legacy_hook = getattr(instance, alias, None)
                if legacy_hook is not None and callable(legacy_hook):
                    return legacy_hook

        if hook is not None and callable(hook):
            return hook
        return None

    def _legacy_arg_parameter_names(self, handler) -> list[str]:
        try:
            signature = inspect.signature(handler)
        except (TypeError, ValueError):
            return []
        try:
            type_hints = get_type_hints(handler)
        except Exception:
            type_hints = {}
        names: list[str] = []
        for parameter in signature.parameters.values():
            if parameter.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                continue
            if self._is_injected_parameter(
                parameter.name, type_hints.get(parameter.name)
            ):
                continue
            names.append(parameter.name)
        return names

    def _is_injected_parameter(self, name: str, annotation: Any) -> bool:
        if name in {"event", "ctx", "context"}:
            return True
        normalized = self._unwrap_optional(annotation)
        if normalized is None:
            return False
        if normalized is RuntimeContext:
            return True
        if normalized is MessageEvent:
            return True
        if isinstance(normalized, type) and issubclass(
            normalized, (RuntimeContext, MessageEvent)
        ):
            return True
        return False

    @staticmethod
    def _unwrap_optional(annotation: Any) -> Any:
        if annotation is None:
            return None
        origin = typing.get_origin(annotation)
        if origin is typing.Union:
            options = [
                item for item in typing.get_args(annotation) if item is not type(None)
            ]
            if len(options) == 1:
                return options[0]
        return annotation

    def _next_request_id(self, prefix: str) -> str:
        self._request_counter += 1
        return f"{prefix}_{self._request_counter:04d}"


__all__ = [
    "InMemoryDB",
    "InMemoryMemory",
    "LocalRuntimeConfig",
    "MockCapabilityRouter",
    "MockContext",
    "MockLLMClient",
    "MockMessageEvent",
    "MockPeer",
    "MockPlatformClient",
    "PluginHarness",
    "RecordedSend",
    "StdoutPlatformSink",
]
