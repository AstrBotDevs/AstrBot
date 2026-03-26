from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from astrbot_sdk import At, Image, Plain
from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.llm.entities import ProviderType
from astrbot_sdk.message_components import component_to_payload_sync
from astrbot_sdk.testing import MockCapabilityRouter, MockPeer


class _SilentLogger:
    def bind(self, **_kwargs: Any) -> _SilentLogger:
        return self

    def opt(self, *_args: Any, **_kwargs: Any) -> _SilentLogger:
        return self

    def log(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def debug(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def info(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def warning(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def error(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def exception(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _build_context(
    *,
    plugin_id: str = "sdk-docs",
    request_id: str | None = None,
    reserved: bool = False,
    config: dict[str, Any] | None = None,
    logger: Any | None = None,
    cancel_token: CancelToken | None = None,
) -> tuple[Context, MockCapabilityRouter]:
    router = MockCapabilityRouter()
    router.upsert_plugin(
        metadata={
            "name": plugin_id,
            "display_name": plugin_id,
            "description": f"{plugin_id} plugin",
            "author": "tests",
            "version": "1.0.0",
            "reserved": reserved,
        },
        config=config or {},
    )
    peer = MockPeer(router)
    return (
        Context(
            peer=peer,
            plugin_id=plugin_id,
            request_id=request_id,
            logger=logger,
            cancel_token=cancel_token,
        ),
        router,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_core_properties_aliases_logger_and_cancel_token_behavior() -> (
    None
):
    cancel_token = CancelToken()
    ctx, _router = _build_context(
        request_id="req-core-1",
        logger=_SilentLogger(),
        cancel_token=cancel_token,
    )

    assert ctx.plugin_id == "sdk-docs"
    assert ctx.request_id == "req-core-1"
    assert ctx.persona_manager is ctx.personas
    assert ctx.conversation_manager is ctx.conversations
    assert ctx.kb_manager is ctx.kbs
    assert ctx.message_history_manager is ctx.message_history
    assert ctx.mcp_manager is ctx.mcp

    watcher = ctx.logger.watch()
    entry_task = asyncio.create_task(watcher.__anext__())
    await asyncio.sleep(0)
    ctx.logger.bind(user_id="user-42").info("hello {}", "sdk")
    entry = await asyncio.wait_for(entry_task, timeout=1)
    assert entry.plugin_id == "sdk-docs"
    assert entry.message == "hello sdk"
    assert entry.context == {"user_id": "user-42"}
    await watcher.aclose()

    wait_task = asyncio.create_task(ctx.cancel_token.wait())
    await asyncio.sleep(0)
    ctx.cancel_token.cancel()
    await asyncio.wait_for(wait_task, timeout=1)
    with pytest.raises(asyncio.CancelledError):
        ctx.cancel_token.raise_if_cancelled()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_llm_and_memory_doc_paths_behave_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    ctx, router = _build_context()

    router.enqueue_llm_response("你好，我是 AstrBot")
    assert await ctx.llm.chat("你好，介绍一下自己") == "你好，我是 AstrBot"

    router.enqueue_llm_response("记得，你叫小明")
    assert (
        await ctx.llm.chat(
            "你记得我的名字吗？",
            history=[
                {"role": "user", "content": "我叫小明"},
                {"role": "assistant", "content": "你好小明！"},
            ],
        )
        == "记得，你叫小明"
    )

    router.enqueue_llm_response("完整响应")
    raw = await ctx.llm.chat_raw("写一首诗", temperature=0.8)
    assert raw.text == "完整响应"
    assert raw.finish_reason == "stop"
    assert raw.usage is not None

    router.enqueue_llm_stream_response("流式响应")
    streamed = [chunk async for chunk in ctx.llm.stream_chat("讲一个故事")]
    assert "".join(streamed) == "流式响应"

    await ctx.memory.save(
        "user_pref",
        {"theme": "dark", "lang": "zh"},
        namespace="users/alice",
    )
    await ctx.memory.save(
        "note",
        None,
        namespace="users/alice",
        content="重要笔记",
        tags=["work"],
    )
    await ctx.memory.save_with_ttl(
        "session_temp",
        {"state": "waiting"},
        3600,
        namespace="users/alice/sessions",
    )

    pref = await ctx.memory.get("user_pref", namespace="users/alice")
    keys = await ctx.memory.list_keys(namespace="users/alice")
    exists = await ctx.memory.exists("user_pref", namespace="users/alice")
    results = await ctx.memory.search(
        "重要",
        mode="keyword",
        namespace="users/alice",
        include_descendants=True,
    )
    count = await ctx.memory.count(
        namespace="users/alice",
        include_descendants=True,
    )
    deleted = await ctx.memory.clear_namespace(
        namespace="users/alice/sessions",
        include_descendants=True,
    )
    stats = await ctx.memory.stats(
        namespace="users/alice",
        include_descendants=True,
    )

    assert pref == {"theme": "dark", "lang": "zh"}
    assert keys == ["note", "user_pref"]
    assert exists is True
    assert [item["key"] for item in results] == ["note"]
    assert count == 3
    assert deleted == 1
    assert stats["total_items"] == 2
    assert stats["namespace"] == "users/alice"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_metadata_registry_and_skill_wrappers_round_trip(
    tmp_path: Path,
) -> None:
    ctx, router = _build_context(
        request_id="req-registry-1",
        config={"api_key": "secret-key"},
    )
    router.upsert_plugin(
        metadata={
            "name": "another_plugin",
            "display_name": "Another Plugin",
            "description": "second plugin",
            "author": "tests",
            "version": "2.0.0",
        },
        config={"token": "other"},
    )
    router.set_plugin_handlers(
        "sdk-docs",
        [
            {
                "plugin_name": "sdk-docs",
                "handler_full_name": "sdk-docs:main.on_message",
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
    router.set_plugin_handlers(
        "another_plugin",
        [
            {
                "plugin_name": "another_plugin",
                "handler_full_name": "another_plugin:main.on_message",
                "trigger_type": "message",
                "description": "Other handler",
                "event_types": ["message"],
                "enabled": True,
                "group_path": [],
                "priority": 3,
                "kind": "handler",
                "require_admin": False,
            }
        ],
    )

    current = await ctx.metadata.get_current_plugin()
    other = await ctx.metadata.get_plugin("another_plugin")
    plugins = await ctx.metadata.list_plugins()
    config = await ctx.metadata.get_plugin_config()

    assert current is not None
    assert current.name == "sdk-docs"
    assert other is not None
    assert other.display_name == "Another Plugin"
    assert sorted(item.name for item in plugins) == ["another_plugin", "sdk-docs"]
    assert config == {"api_key": "secret-key"}

    handlers = await ctx.registry.get_handlers_by_event_type("message")
    handler = await ctx.registry.get_handler_by_full_name("sdk-docs:main.on_message")
    applied = await ctx.registry.set_handler_whitelist(
        ["sdk-docs", "another_plugin", "sdk-docs"]
    )
    current_whitelist = await ctx.registry.get_handler_whitelist()
    await ctx.registry.clear_handler_whitelist()
    cleared_whitelist = await ctx.registry.get_handler_whitelist()

    assert sorted(item.handler_full_name for item in handlers) == [
        "another_plugin:main.on_message",
        "sdk-docs:main.on_message",
    ]
    assert handler is not None
    assert handler.description == "Handle messages"
    assert applied == ["another_plugin", "sdk-docs"]
    assert current_whitelist == ["another_plugin", "sdk-docs"]
    assert cleared_whitelist is None

    skill_file = tmp_path / "skills" / "browser_helper" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("# skill", encoding="utf-8")
    skill_dir = tmp_path / "skills" / "writer_helper"
    skill_dir.mkdir(parents=True, exist_ok=True)

    direct_registration = await ctx.skills.register(
        name="sdk-docs.browser-helper",
        path=str(skill_file),
        description="Browser helper",
    )
    wrapped_registration = await ctx.register_skill(
        name="sdk-docs.writer-helper",
        path=skill_dir,
        description="Writer helper",
    )
    listed = await ctx.skills.list()
    removed_direct = await ctx.skills.unregister("sdk-docs.browser-helper")
    removed_wrapped = await ctx.unregister_skill("sdk-docs.writer-helper")

    assert direct_registration.skill_dir == str(skill_file.parent)
    assert wrapped_registration.skill_dir == str(skill_dir)
    assert sorted(item.name for item in listed) == [
        "sdk-docs.browser-helper",
        "sdk-docs.writer-helper",
    ]
    assert removed_direct is True
    assert removed_wrapped is True
    assert await ctx.skills.list() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_files_platform_provider_and_manager_doc_paths(
    tmp_path: Path,
) -> None:
    ctx, router = _build_context(
        plugin_id="reserved-docs",
        reserved=True,
    )
    router.set_platform_instances(
        [
            {
                "id": "mock-platform",
                "name": "Mock Platform",
                "type": "mock",
                "status": "running",
            }
        ]
    )
    router.set_provider_catalog(
        "chat",
        [
            {
                "id": "chat-provider-a",
                "model": "gpt-a",
                "type": "mock",
                "provider_type": "chat_completion",
            },
            {
                "id": "chat-provider-b",
                "model": "gpt-b",
                "type": "mock",
                "provider_type": "chat_completion",
            },
        ],
        active_id="chat-provider-a",
    )

    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")
    token = await ctx.files.register_file(str(sample), timeout=3600)
    assert await ctx.files.handle_file(token) == str(sample)

    await ctx.platform.send("mock-platform:private:user-1", "收到您的消息！")
    await ctx.platform.send_image(
        "mock-platform:private:user-1",
        "https://example.com/image.png",
    )
    await ctx.platform.send_chain(
        "mock-platform:private:user-1",
        [
            Plain("文字", convert=False),
            Image.fromURL("https://example.com/img.jpg"),
            At("user-2"),
        ],
    )
    members = await ctx.platform.get_members("mock-platform:group:123456")
    await ctx.send_message("mock-platform:private:user-2", "消息内容")
    await ctx.send_message_by_id(
        type="private",
        id="user123",
        content="Hello",
        platform="mock",
    )

    assert [item["session"] for item in router.sent_messages] == [
        "mock-platform:private:user-1",
        "mock-platform:private:user-1",
        "mock-platform:private:user-1",
        "mock-platform:private:user-2",
        "mock-platform:private:user123",
    ]
    assert router.sent_messages[0]["text"] == "收到您的消息！"
    assert router.sent_messages[1]["image_url"] == "https://example.com/image.png"
    assert router.sent_messages[2]["chain"] == [
        {"type": "text", "data": {"text": "文字"}},
        component_to_payload_sync(Image.fromURL("https://example.com/img.jpg")),
        {"type": "at", "data": {"qq": "user-2"}},
    ]
    assert len(members) == 2

    providers = await ctx.providers.list_all()
    using = await ctx.providers.get_using_chat()
    assert [item.id for item in providers] == ["chat-provider-a", "chat-provider-b"]
    assert using is not None
    assert using.id == "chat-provider-a"

    watcher = ctx.provider_manager.watch_changes()
    change_task = asyncio.create_task(anext(watcher))
    await asyncio.sleep(0)
    created = await ctx.provider_manager.create_provider(
        {
            "id": "custom_chat",
            "type": "openai",
            "provider_type": "chat_completion",
            "model": "gpt-4.1",
            "enable": True,
        }
    )
    change = await asyncio.wait_for(change_task, timeout=1)
    updated = await ctx.provider_manager.update_provider(
        "custom_chat",
        {"model": "gpt-4.1-mini"},
    )
    await ctx.provider_manager.set_provider(
        "custom_chat",
        ProviderType.CHAT_COMPLETION,
        umo="mock-platform:private:user123",
    )
    await watcher.aclose()

    assert created is not None
    assert created.id == "custom_chat"
    assert change.provider_id == "custom_chat"
    assert change.provider_type is ProviderType.CHAT_COMPLETION
    assert updated is not None
    assert updated.model == "gpt-4.1-mini"
    using_after_set = await ctx.providers.get_using_chat()
    assert using_after_set is not None
    assert using_after_set.id == "custom_chat"

    await ctx.provider_manager.delete_provider("custom_chat")
    remaining_provider_ids = [item.id for item in await ctx.providers.list_all()]
    assert "custom_chat" not in remaining_provider_ids
