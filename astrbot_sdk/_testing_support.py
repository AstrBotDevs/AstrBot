"""Shared support primitives for local SDK testing."""

from __future__ import annotations

import asyncio
import typing
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, TextIO

from .context import CancelToken
from .context import Context as RuntimeContext
from .events import MessageEvent
from .protocol.messages import EventMessage, PeerInfo
from .runtime._streaming import StreamExecution
from .runtime.capability_router import CapabilityRouter


def _clone_payload_mapping(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


@dataclass(slots=True)
class RecordedSend:
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
    def from_payload(cls, payload: dict[str, Any]) -> RecordedSend:
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
            target=_clone_payload_mapping(payload.get("target")),
            raw=dict(payload),
        )


class StdoutPlatformSink:
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
    def __init__(self, client: Any, router: MockCapabilityRouter) -> None:
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
    def __init__(self, *, platform_sink: StdoutPlatformSink | None = None) -> None:
        self.platform_sink = platform_sink or StdoutPlatformSink()
        self._llm_responses: list[str] = []
        self._llm_stream_responses: list[str] = []
        super().__init__()
        self.db = InMemoryDB(self.db_store)
        self.memory = InMemoryMemory(self.memory_store)

    def list_dynamic_command_routes(self, plugin_id: str) -> list[dict[str, Any]]:
        return super().list_dynamic_command_routes(plugin_id)

    def remove_dynamic_command_routes_for_plugin(self, plugin_id: str) -> None:
        super().remove_dynamic_command_routes_for_plugin(plugin_id)

    def emit_provider_change(
        self,
        provider_id: str,
        provider_type: str,
        umo: str | None = None,
    ) -> None:
        super().emit_provider_change(provider_id, provider_type, umo)

    def record_platform_error(
        self,
        platform_id: str,
        message: str,
        *,
        traceback: str | None = None,
    ) -> None:
        super().record_platform_error(platform_id, message, traceback=traceback)

    def set_platform_stats(self, platform_id: str, stats: dict[str, Any]) -> None:
        super().set_platform_stats(platform_id, stats)

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
                "role": "assistant",
                "reasoning_content": None,
                "reasoning_signature": None,
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
            yield EventMessage.model_validate({"id": request_id, "phase": "started"})
            chunks: list[dict[str, Any]] = []
            async for chunk in execution.iterator:
                if execution.collect_chunks:
                    chunks.append(chunk)
                yield EventMessage.model_validate(
                    {"id": request_id, "phase": "delta", "data": chunk}
                )
            output = execution.finalize(chunks)
            if include_completed:
                yield EventMessage.model_validate(
                    {"id": request_id, "phase": "completed", "output": output}
                )

        return iterator()

    def _next_id(self) -> str:
        self._counter += 1
        return f"local_{self._counter:04d}"


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
        "reserved": bool(plugin_metadata.get("reserved", False)),
        "support_platforms": [
            str(item)
            for item in plugin_metadata.get("support_platforms", [])
            if isinstance(item, str)
        ]
        if isinstance(plugin_metadata.get("support_platforms"), list)
        else [],
        "astrbot_version": (
            str(plugin_metadata.get("astrbot_version"))
            if plugin_metadata.get("astrbot_version") is not None
            else None
        ),
    }


class MockContext(RuntimeContext):
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

    @property
    def event_actions(self) -> list[dict[str, Any]]:
        return list(self.router.event_actions)


class MockMessageEvent(MessageEvent):
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


__all__ = [
    "InMemoryDB",
    "InMemoryMemory",
    "MockCapabilityRouter",
    "MockContext",
    "MockLLMClient",
    "MockMessageEvent",
    "MockPeer",
    "MockPlatformClient",
    "RecordedSend",
    "StdoutPlatformSink",
]
