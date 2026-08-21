from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = PROJECT_ROOT / "astrbot-sdk" / "src"

if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

PLUGIN_ID = "capability_probe"
SESSION = "mock:group:capability-probe"
HANDLER_FULL_NAME = f"{PLUGIN_ID}.handle"


def _chain() -> list[dict[str, Any]]:
    return [{"type": "text", "data": {"text": "hello from capability probe"}}]


def _message_session() -> dict[str, str]:
    return {
        "platform_id": "mock",
        "message_type": "group",
        "session_id": "capability-probe",
    }


def _event_target() -> dict[str, Any]:
    return {
        "conversation_id": "probe-event",
        "platform": "mock",
        "raw": {"session": SESSION},
    }


def _provider_config(provider_id: str = "probe-chat-provider") -> dict[str, Any]:
    return {
        "id": provider_id,
        "model": "probe-model",
        "type": "mock",
        "provider_type": "chat_completion",
        "enable": True,
        "provider_source_id": "probe-source",
    }


def _persona_payload(persona_id: str = "probe-persona") -> dict[str, Any]:
    return {
        "persona_id": persona_id,
        "system_prompt": "You are a probe persona.",
        "begin_dialogs": ["hello"],
        "tools": [],
        "skills": [],
    }


def _kb_payload() -> dict[str, Any]:
    return {
        "kb_name": "Probe KB",
        "description": "Capability probe knowledge base",
        "embedding_provider_id": "mock-embedding-provider",
        "rerank_provider_id": "mock-rerank-provider",
        "chunk_size": 128,
    }


def _schema_sample(schema: dict[str, Any], *, field_name: str = "") -> Any:
    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        for candidate in any_of:
            if isinstance(candidate, dict) and candidate.get("type") != "null":
                return _schema_sample(candidate, field_name=field_name)
        return None

    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]

    schema_type = schema.get("type")
    if schema_type == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict):
            return {}
        return {
            str(name): _schema_sample(
                properties.get(str(name), {}),
                field_name=str(name),
            )
            for name in required
        }
    if schema_type == "array":
        return []
    if schema_type == "string":
        return _string_sample(field_name)
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 0.5
    if schema_type == "boolean":
        return True
    if schema_type == "null":
        return None
    return {}


def _string_sample(field_name: str) -> str:
    samples = {
        "after": "1",
        "audio_url": "mock://audio.wav",
        "before": "1",
        "command_name": "probe",
        "doc_id": "probe-doc",
        "emoji": "thumbs_up",
        "event_type": "message",
        "file_name": "probe.txt",
        "file_type": "txt",
        "full_name": HANDLER_FULL_NAME,
        "handler_capability": HANDLER_FULL_NAME,
        "handler_full_name": HANDLER_FULL_NAME,
        "image_url": "mock://image.png",
        "kb_id": "probe-kb",
        "key": "probe-key",
        "method": "GET",
        "name": PLUGIN_ID,
        "origin_provider_id": "mock-chat-provider",
        "persona_id": "probe-persona",
        "platform_id": "mock-platform",
        "plugin_name": PLUGIN_ID,
        "provider_id": "mock-chat-provider",
        "provider_type": "chat_completion",
        "query": "probe",
        "record_id": "1",
        "route": "/capability_probe/probe",
        "session": SESSION,
        "session_id": SESSION,
        "session_key": SESSION,
        "stream_id": "probe-stream",
        "text": "hello",
        "title": "Probe conversation",
    }
    return samples.get(field_name, f"probe-{field_name or 'value'}")


def _base_payload(name: str, input_schema: dict[str, Any]) -> dict[str, Any]:
    payload = _schema_sample(input_schema)
    if not isinstance(payload, dict):
        payload = {}

    payload.update(
        {
            "chain": _chain(),
            "config": {"enabled": True},
            "conversation": {"title": "Probe conversation"},
            "data": {"value": "probe"},
            "document": {
                "file_name": "probe.txt",
                "file_type": "txt",
                "text": "probe document content",
            },
            "documents": ["probe document"],
            "handlers": [{"handler_full_name": HANDLER_FULL_NAME}],
            "items": [{"key": "probe-key", "value": {"ok": True}}],
            "kb": _kb_payload(),
            "kb_ids": ["probe-kb"],
            "keys": ["probe-key"],
            "methods": ["GET"],
            "new_config": _provider_config("probe-updated-provider"),
            "options": {"viewport": {"width": 800, "height": 600}},
            "parts": _chain(),
            "persona": _persona_payload(),
            "plugin_names": [PLUGIN_ID],
            "provider_config": _provider_config(),
            "sender": {"user_id": "probe-user", "nickname": "Probe"},
            "source_event_type": "astrbot_loaded",
            "target": _event_target(),
            "texts": ["hello", "world"],
            "tools": [
                {
                    "name": "probe_tool",
                    "description": "Probe tool",
                    "parameters_schema": {"type": "object", "properties": {}},
                    "active": True,
                }
            ],
            "value": {"ok": True},
        }
    )

    if name.startswith("provider.tts."):
        payload["provider_id"] = "mock-tts-provider"
    elif name.startswith("provider.stt."):
        payload["provider_id"] = "mock-stt-provider"
    elif name.startswith("provider.embedding."):
        payload["provider_id"] = "mock-embedding-provider"
    elif name.startswith("provider.rerank."):
        payload["provider_id"] = "mock-rerank-provider"
    elif name == "provider.get_by_id":
        payload["provider_id"] = "mock-chat-provider"
    elif name.startswith("provider.manager."):
        payload.setdefault("provider_id", "mock-chat-provider")

    if name in {"llm_tool.manager.activate", "llm_tool.manager.deactivate"}:
        payload["name"] = "probe_tool"
    elif name == "llm_tool.manager.remove":
        payload["name"] = "removable_tool"
    elif name == "agent.registry.get":
        payload["name"] = "probe_agent"
    elif name.startswith("persona."):
        payload["persona_id"] = "probe-persona"
    elif name.startswith("kb."):
        payload["kb_id"] = "probe-kb"
        payload["doc_id"] = "probe-doc"
    elif name.startswith("message_history."):
        payload["session"] = _message_session()
        payload["record_id"] = 1
        payload["before"] = "2099-01-01T00:00:00+00:00"
        payload["after"] = "1970-01-01T00:00:00+00:00"

    if name.startswith("permission.manager."):
        payload["_caller_is_admin"] = True
    if name == "provider.tts.get_audio_stream":
        payload["text"] = "hello"

    return payload


async def _execute(router, name: str, payload: dict[str, Any], *, stream: bool):
    from astrbot_sdk.context import CancelToken

    return await router.execute(
        name,
        payload,
        stream=stream,
        cancel_token=CancelToken(),
        request_id=f"probe-{name}",
    )


async def _seed_router_for_capability(router, name: str) -> dict[str, Any]:
    from astrbot_sdk.context import CancelToken
    from astrbot_sdk.protocol import BUILTIN_CAPABILITY_SCHEMAS

    router._system_data_root = Path.cwd() / ".astrbot_sdk_testing" / "capability_probe"
    router.upsert_plugin(
        metadata={
            "name": PLUGIN_ID,
            "display_name": "Capability Probe",
            "reserved": True,
            "enabled": True,
        },
        config={"probe": True},
    )
    router.set_plugin_handlers(
        PLUGIN_ID,
        [
            {
                "plugin_name": PLUGIN_ID,
                "handler_full_name": HANDLER_FULL_NAME,
                "event_types": ["message"],
                "enabled": True,
                "trigger_type": "command",
                "kind": "handler",
            }
        ],
    )
    router.set_platform_instances(
        [
            {
                "id": "mock-platform",
                "name": "Mock Platform",
                "type": "mock",
                "status": "running",
                "errors": [],
                "last_error": None,
                "unified_webhook": False,
                "stats": {
                    "id": "mock-platform",
                    "type": "mock",
                    "display_name": "Mock Platform",
                    "status": "running",
                    "error_count": 0,
                    "last_error": None,
                    "unified_webhook": False,
                    "meta": {},
                },
            }
        ]
    )
    router.set_plugin_llm_tools(
        PLUGIN_ID,
        [
            {
                "name": "probe_tool",
                "description": "Probe tool",
                "parameters_schema": {"type": "object", "properties": {}},
                "active": True,
            },
            {
                "name": "removable_tool",
                "description": "Removable probe tool",
                "parameters_schema": {"type": "object", "properties": {}},
                "active": True,
            },
        ],
    )
    router.set_plugin_agents(
        PLUGIN_ID,
        [
            {
                "name": "probe_agent",
                "description": "Probe agent",
                "tool_names": ["probe_tool"],
                "runner_class": "ProbeAgentRunner",
                "active": True,
            }
        ],
    )

    token = CancelToken()
    if name.startswith("persona.") and name != "persona.create":
        await router.execute(
            "persona.create",
            {"persona": _persona_payload()},
            stream=False,
            cancel_token=token,
            request_id=f"seed-{name}-persona",
        )

    if name.startswith("conversation.") and name != "conversation.new":
        created = await router.execute(
            "conversation.new",
            {"session": SESSION, "conversation": {"title": "Seed conversation"}},
            stream=False,
            cancel_token=token,
            request_id=f"seed-{name}-conversation",
        )
        conversation_id = str(created["conversation_id"])
    else:
        conversation_id = "probe-conversation"

    if name.startswith("message_history.") and name != "message_history.append":
        record = await router.execute(
            "message_history.append",
            {
                "session": _message_session(),
                "sender": {"user_id": "probe-user"},
                "parts": _chain(),
            },
            stream=False,
            cancel_token=token,
            request_id=f"seed-{name}-message-history",
        )
        record_id = int(record["record"]["id"])
    else:
        record_id = 1

    kb_id = "probe-kb"
    doc_id = "probe-doc"
    if name.startswith("kb.") and name != "kb.create":
        kb = await router.execute(
            "kb.create",
            {"kb": _kb_payload()},
            stream=False,
            cancel_token=token,
            request_id=f"seed-{name}-kb",
        )
        kb_id = str(kb["kb"]["kb_id"])
        if name.startswith("kb.document.") or name == "kb.retrieve":
            doc = await router.execute(
                "kb.document.upload",
                {
                    "kb_id": kb_id,
                    "document": {
                        "file_name": "probe.txt",
                        "file_type": "txt",
                        "text": "probe document content",
                    },
                },
                stream=False,
                cancel_token=token,
                request_id=f"seed-{name}-doc",
            )
            doc_id = str(doc["document"]["doc_id"])

    payload = _base_payload(name, BUILTIN_CAPABILITY_SCHEMAS[name]["input"])
    payload.update(
        {
            "conversation_id": conversation_id,
            "record_id": record_id,
            "before": "2099-01-01T00:00:00+00:00",
            "after": "1970-01-01T00:00:00+00:00",
            "kb_id": kb_id,
            "kb_ids": [kb_id],
            "doc_id": doc_id,
        }
    )

    if name in {
        "system.event.send_streaming_chunk",
        "system.event.send_streaming_close",
    }:
        created_stream = await router.execute(
            "system.event.send_streaming",
            {"target": _event_target()},
            stream=False,
            cancel_token=token,
            request_id=f"seed-{name}-streaming",
        )
        payload["stream_id"] = str(created_stream["stream_id"])

    return payload


async def _exercise_stream(router, name: str, payload: dict[str, Any]) -> None:
    execution = await _execute(router, name, payload, stream=True)

    async def _next_chunk(iterator: AsyncIterator[dict[str, Any]]) -> dict[str, Any]:
        return await asyncio.wait_for(anext(iterator), timeout=1)

    chunk_task = asyncio.create_task(_next_chunk(execution.iterator))
    if name == "db.watch":
        await _execute(
            router,
            "db.set",
            {"key": "probe-key", "value": {"ok": True}},
            stream=False,
        )
    elif name == "provider.manager.watch_changes":
        router.emit_provider_change("mock-chat-provider", "chat_completion", SESSION)

    chunk = await chunk_task
    chunks = [chunk] if execution.collect_chunks else []
    if hasattr(execution.iterator, "aclose"):
        await execution.iterator.aclose()
    execution.finalize(chunks)


@pytest.mark.asyncio
async def test_probe_plugin_can_execute_every_builtin_sdk_capability(tmp_path: Path) -> None:
    from astrbot_sdk._internal.invocation_context import caller_plugin_scope
    from astrbot_sdk.runtime import CapabilityRouter

    failures: list[str] = []
    with caller_plugin_scope(PLUGIN_ID):
        router = CapabilityRouter()
        capability_names = sorted(getattr(router, "_registrations"))

        for name in capability_names:
            router = CapabilityRouter()
            router._system_data_root = tmp_path / name.replace(".", "_")
            registration = getattr(router, "_registrations")[name]
            payload = await _seed_router_for_capability(router, name)
            try:
                if registration.stream_handler is not None:
                    await _exercise_stream(router, name, payload)
                else:
                    await _execute(router, name, payload, stream=False)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: {type(exc).__name__}: {exc}")

    assert not failures, "\n".join(failures)
