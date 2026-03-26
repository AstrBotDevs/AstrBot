from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from astrbot_sdk import At, Image, MessageHistorySender, MessageSession, Plain
from astrbot_sdk.clients.registry import HandlerMetadata
from astrbot_sdk.llm.entities import ProviderType

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clients_doc_llm_memory_and_metadata_round_trip_through_core_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    runtime.plugin_bridge.upsert_plugin(
        metadata={
            "name": "client-docs",
            "display_name": "Client Docs",
            "description": "doc coverage plugin",
            "author": "tests",
            "version": "1.0.0",
        },
        config={"api_key": "old-key"},
    )
    runtime.plugin_bridge.upsert_plugin(
        metadata={
            "name": "another-plugin",
            "display_name": "Another Plugin",
            "description": "secondary plugin",
            "author": "tests",
            "version": "2.0.0",
        },
        config={"token": "other"},
    )
    ctx = runtime.make_context("client-docs")

    runtime.enqueue_llm_response("你好，我是 AstrBot")
    runtime.enqueue_llm_response("完整响应")
    runtime.enqueue_llm_stream("流式响应")

    assert await ctx.llm.chat("你好，介绍一下自己") == "你好，我是 AstrBot"
    raw = await ctx.llm.chat_raw("写一首诗", temperature=0.8)
    assert raw.text == "完整响应"
    assert raw.finish_reason == "stop"
    assert raw.usage is not None
    assert raw.usage["total_tokens"] > 0

    chunks = [chunk async for chunk in ctx.llm.stream_chat("讲一个故事")]
    assert "".join(chunks) == "流式响应"

    await ctx.memory.save("user_pref", {"theme": "dark"}, namespace="users/alice")
    await ctx.memory.save(
        "note",
        {"content": "Alice likes blue oceans"},
        namespace="users/alice",
    )
    await ctx.memory.save_with_ttl(
        "session_temp",
        {"state": "waiting"},
        3600,
        namespace="users/alice/sessions",
    )

    assert await ctx.memory.get("user_pref", namespace="users/alice") == {
        "theme": "dark"
    }
    assert await ctx.memory.list_keys(namespace="users/alice") == [
        "note",
        "user_pref",
    ]
    assert await ctx.memory.exists("user_pref", namespace="users/alice") is True

    results = await ctx.memory.search(
        "blue",
        mode="keyword",
        namespace="users/alice",
        include_descendants=True,
    )
    assert any(item["key"] == "note" for item in results)

    deleted_many = await ctx.memory.delete_many(
        ["missing", "session_temp"],
        namespace="users/alice/sessions",
    )
    assert deleted_many == 1
    await ctx.memory.delete("note", namespace="users/alice")
    assert (
        await ctx.memory.count(
            namespace="users/alice",
            include_descendants=True,
        )
        == 1
    )

    stats = await ctx.memory.stats(
        namespace="users/alice",
        include_descendants=True,
    )
    assert stats["total_items"] == 1
    assert stats["plugin_id"] == "client-docs"

    current = await ctx.metadata.get_current_plugin()
    other = await ctx.metadata.get_plugin("another-plugin")
    plugins = await ctx.metadata.list_plugins()
    assert current is not None
    assert current.name == "client-docs"
    assert other is not None
    assert other.display_name == "Another Plugin"
    assert sorted(item.name for item in plugins) == ["another-plugin", "client-docs"]
    assert await ctx.metadata.get_plugin_config() == {"api_key": "old-key"}
    assert await ctx.metadata.save_plugin_config({"api_key": "new-key"}) == {
        "api_key": "new-key"
    }
    assert runtime.plugin_bridge.get_plugin_config("client-docs") == {
        "api_key": "new-key"
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clients_doc_platform_file_and_http_round_trip_through_core_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    runtime.plugin_bridge.upsert_plugin(
        metadata={
            "name": "client-docs",
            "display_name": "Client Docs",
            "description": "doc coverage plugin",
            "author": "tests",
            "version": "1.0.0",
        }
    )
    request_id = "client-docs:event-1"
    session = "mock-platform:group:room-7"
    runtime.register_group_request(
        request_id=request_id, session=session, is_admin=True
    )
    ctx = runtime.make_context("client-docs", request_id=request_id)

    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")
    token = await ctx.files.register_file(str(sample), timeout=120)
    assert token.startswith("file-token-")
    assert await ctx.files.handle_file(token) == str(sample)

    await ctx.platform.send(session, "大家好！")
    await ctx.platform.send_image(session, "https://example.com/image.png")
    await ctx.platform.send_chain(
        session,
        [
            Plain("文字", convert=False),
            Image.fromURL("https://example.com/img.jpg"),
            At("member-1"),
        ],
    )
    await ctx.platform.send_by_session(session, "主动消息")
    await ctx.platform.send_by_id(
        platform_id="mock-platform",
        session_id="user-42",
        content="Hello",
        message_type="private",
    )
    members = await ctx.platform.get_members(session)

    assert [item["session"] for item in runtime.star_context.sent_messages] == [
        session,
        session,
        session,
        session,
        "mock-platform:private:user-42",
    ]
    assert runtime.star_context.sent_messages[0]["text"] == "大家好！"
    image_chain = runtime.star_context.sent_messages[1]["chain"]
    assert image_chain[0]["type"] == "image"
    assert image_chain[0]["data"]["file"] == "https://example.com/image.png"
    rich_chain = runtime.star_context.sent_messages[2]["chain"]
    assert rich_chain[0] == {"type": "text", "data": {"text": "文字"}}
    assert rich_chain[1]["type"] == "image"
    assert rich_chain[1]["data"]["file"] == "https://example.com/img.jpg"
    assert rich_chain[2] == {"type": "at", "data": {"qq": "member-1"}}
    assert [member["user_id"] for member in members] == ["owner-1", "member-1"]

    await ctx.http.register_api(
        route="/status",
        handler_capability="client-docs.http_handler",
        methods=["GET", "post"],
        description="Status API",
    )
    assert await ctx.http.list_apis() == [
        {
            "route": "/status",
            "methods": ["GET", "POST"],
            "handler_capability": "client-docs.http_handler",
            "description": "Status API",
        }
    ]
    await ctx.http.unregister_api("/status", methods=["POST"])
    assert await ctx.http.list_apis() == [
        {
            "route": "/status",
            "methods": ["GET"],
            "handler_capability": "client-docs.http_handler",
            "description": "Status API",
        }
    ]
    await ctx.http.unregister_api("/status")
    assert await ctx.http.list_apis() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clients_doc_other_managers_round_trip_through_core_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_sync(self) -> None:
        return None

    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.skill.SkillCapabilityMixin._sync_registered_skills_to_sandboxes",
        _noop_sync,
    )

    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    runtime.plugin_bridge.upsert_plugin(
        metadata={
            "name": "reserved-plugin",
            "display_name": "Reserved Plugin",
            "description": "reserved plugin",
            "author": "tests",
            "version": "1.0.0",
            "reserved": True,
        }
    )
    runtime.plugin_bridge.upsert_plugin(
        metadata={
            "name": "disabled-plugin",
            "display_name": "Disabled Plugin",
            "description": "disabled plugin",
            "author": "tests",
            "version": "1.0.0",
        }
    )
    runtime.plugin_bridge.set_plugin_handlers(
        "reserved-plugin",
        [
            {
                "plugin_name": "reserved-plugin",
                "handler_full_name": "reserved-plugin:main.on_message",
                "trigger_type": "message",
                "description": "Handle messages",
                "event_types": ["message"],
                "enabled": True,
                "group_path": [],
                "priority": 5,
                "kind": "handler",
                "require_admin": False,
            }
        ],
    )
    runtime.plugin_bridge.set_plugin_handlers(
        "disabled-plugin",
        [
            {
                "plugin_name": "disabled-plugin",
                "handler_full_name": "disabled-plugin:main.on_message",
                "trigger_type": "message",
                "description": "Disabled handler",
                "event_types": ["message"],
                "enabled": True,
                "group_path": [],
                "priority": 1,
                "kind": "handler",
                "require_admin": False,
            }
        ],
    )

    request_id = "reserved-plugin:event-1"
    session = "mock-platform:group:room-7"
    runtime.register_group_request(
        request_id=request_id, session=session, is_admin=True
    )
    runtime.set_session_plugin_config(session, disabled_plugins=["disabled-plugin"])
    runtime.set_session_service_config(session, llm_enabled=False, tts_enabled=False)
    ctx = runtime.make_context(
        "reserved-plugin",
        request_id=request_id,
        source_event_payload={"is_admin": True},
    )

    providers = await ctx.providers.list_all()
    using_before = await ctx.providers.get_using_chat()
    assert [item.id for item in providers] == ["chat-provider-a"]
    assert using_before is not None
    assert using_before.id == "chat-provider-a"

    watcher = ctx.provider_manager.watch_changes()
    waiter = asyncio.create_task(anext(watcher))
    await asyncio.sleep(0)
    created = await ctx.provider_manager.create_provider(
        {
            "id": "custom-chat",
            "type": "openai",
            "provider_type": "chat_completion",
            "model": "gpt-4.1",
            "enable": True,
        }
    )
    change = await asyncio.wait_for(waiter, timeout=1)
    updated = await ctx.provider_manager.update_provider(
        "custom-chat",
        {"model": "gpt-4.1-mini"},
    )
    await ctx.provider_manager.set_provider(
        "custom-chat",
        ProviderType.CHAT_COMPLETION,
        umo=session,
    )
    await watcher.aclose()
    assert created is not None
    assert created.id == "custom-chat"
    assert change.provider_id == "custom-chat"
    assert change.provider_type is ProviderType.CHAT_COMPLETION
    assert updated is not None
    assert updated.model == "gpt-4.1-mini"
    using_after = await ctx.providers.get_using_chat(session)
    assert using_after is not None
    assert using_after.id == "custom-chat"
    await ctx.provider_manager.delete_provider("custom-chat")
    assert [item.id for item in await ctx.providers.list_all()] == ["chat-provider-a"]

    assert (
        await ctx.session_plugins.is_plugin_enabled_for_session(
            session,
            "disabled-plugin",
        )
        is False
    )
    filtered = await ctx.session_plugins.filter_handlers_by_session(
        session,
        [
            HandlerMetadata.from_dict(
                runtime.plugin_bridge.get_handler_by_full_name(
                    "reserved-plugin:main.on_message"
                )
            ),
            HandlerMetadata.from_dict(
                runtime.plugin_bridge.get_handler_by_full_name(
                    "disabled-plugin:main.on_message"
                )
            ),
        ],
    )
    assert [item.plugin_name for item in filtered] == ["reserved-plugin"]

    assert await ctx.session_services.is_llm_enabled_for_session(session) is False
    assert await ctx.session_services.is_tts_enabled_for_session(session) is False
    await ctx.session_services.set_llm_status_for_session(session, True)
    await ctx.session_services.set_tts_status_for_session(session, True)
    assert await ctx.session_services.should_process_llm_request(session) is True
    assert await ctx.session_services.should_process_tts_request(session) is True

    handlers = await ctx.registry.get_handlers_by_event_type("message")
    handler = await ctx.registry.get_handler_by_full_name(
        "reserved-plugin:main.on_message"
    )
    assert [item.plugin_name for item in handlers] == [
        "disabled-plugin",
        "reserved-plugin",
    ]
    assert handler is not None
    assert handler.description == "Handle messages"
    assert await ctx.registry.set_handler_whitelist(
        ["reserved-plugin", "disabled-plugin", "reserved-plugin"]
    ) == ["disabled-plugin", "reserved-plugin"]
    assert await ctx.registry.get_handler_whitelist() == [
        "disabled-plugin",
        "reserved-plugin",
    ]
    await ctx.registry.clear_handler_whitelist()
    assert await ctx.registry.get_handler_whitelist() is None

    assert (await ctx.permission.check("owner-1")).is_admin is True
    assert await ctx.permission.get_admins() == ["owner-1"]
    assert await ctx.permission_manager.add_admin("alice") is True
    assert (await ctx.permission.check("alice")).role == "admin"
    assert await ctx.permission_manager.remove_admin("alice") is True
    assert (await ctx.permission.check("alice")).role == "member"

    skill_file = tmp_path / "skills" / "browser-helper" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("# skill", encoding="utf-8")
    registered = await ctx.skills.register(
        name="reserved-plugin.browser-helper",
        path=str(skill_file),
        description="Browser helper",
    )
    assert registered.skill_dir == str(skill_file.parent)
    assert [item.name for item in await ctx.skills.list()] == [
        "reserved-plugin.browser-helper"
    ]
    assert await ctx.skills.unregister("reserved-plugin.browser-helper") is True
    assert await ctx.skills.list() == []

    history_session = MessageSession(
        platform_id="mock-platform",
        message_type="group",
        session_id="room-7",
    )
    first = await ctx.message_history.append(
        history_session,
        parts=[Plain("hello history", convert=False)],
        sender=MessageHistorySender(sender_id="owner-1", sender_name="Owner"),
        metadata={"trace_id": "trace-1"},
        idempotency_key="idem-1",
    )
    second = await ctx.message_history.append(
        history_session,
        parts=[Plain("follow up", convert=False)],
        sender=MessageHistorySender(sender_id="member-1", sender_name="Member"),
    )
    page = await ctx.message_history.list(history_session, limit=10)
    fetched = await ctx.message_history.get(history_session, second.id)
    assert [record.id for record in page.records] == [first.id, second.id]
    assert fetched is not None
    assert fetched.sender.sender_id == "member-1"

    before_cutoff = first.created_at + timedelta(microseconds=1)
    deleted_before = await ctx.message_history.delete_before(
        history_session,
        before=before_cutoff,
    )
    assert deleted_before == 1
    after_cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)
    deleted_after = await ctx.message_history.delete_after(
        history_session,
        after=after_cutoff,
    )
    assert deleted_after == 1
    assert await ctx.message_history.delete_all(history_session) == 0
