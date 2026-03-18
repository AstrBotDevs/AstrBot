# ruff: noqa: E402
from __future__ import annotations

import importlib.util
import sys

import pytest
from astrbot_sdk._testing_support import MockContext, MockMessageEvent
from astrbot_sdk.clients.managers import PersonaCreateParams
from astrbot_sdk.llm.entities import ProviderRequest

_PLUGIN_SPEC = importlib.util.spec_from_file_location(
    "astrbot_sdk_ai_girlfriend_test",
    "d:\\GitObjectsOwn\\AstrBot\\data\\sdk_plugins\\ai_girlfriend\\main.py",
)
assert _PLUGIN_SPEC is not None
assert _PLUGIN_SPEC.loader is not None
_PLUGIN_MODULE = importlib.util.module_from_spec(_PLUGIN_SPEC)
sys.modules.setdefault("astrbot_sdk_ai_girlfriend_test", _PLUGIN_MODULE)
_PLUGIN_SPEC.loader.exec_module(_PLUGIN_MODULE)
AiGirlfriend = _PLUGIN_MODULE.AiGirlfriend


def _configure_plugin(ctx: MockContext, config: dict[str, object]) -> None:
    ctx.router.upsert_plugin(
        metadata={
            "name": "ai_girlfriend",
            "display_name": "AI Girlfriend",
            "description": "test plugin",
        },
        config=config,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_girlfriend_on_start_creates_valid_builtin_persona() -> None:
    ctx = MockContext(plugin_id="ai_girlfriend")
    _configure_plugin(ctx, {})
    plugin = AiGirlfriend()

    await plugin.on_start(ctx)

    persona = await ctx.personas.get_persona("gf_default_gentle")
    assert persona.system_prompt
    assert len(persona.begin_dialogs) % 2 == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_girlfriend_chat_binds_current_session_persona() -> None:
    ctx = MockContext(plugin_id="ai_girlfriend")
    _configure_plugin(ctx, {})
    plugin = AiGirlfriend()
    await plugin.on_start(ctx)

    event = MockMessageEvent(
        text="gf chat",
        user_id="user-1",
        platform="mock-platform",
        session_id="mock-platform:private:user-1",
        context=ctx,
    )

    await plugin.chat(event, ctx)

    conversation = await ctx.conversations.get_current_conversation(event.session_id)
    assert conversation is not None
    assert conversation.persona_id == "gf_default_gentle"
    assert ctx.sent_messages[-1].text is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_girlfriend_global_default_mode_auto_binds_persona() -> None:
    ctx = MockContext(plugin_id="ai_girlfriend")
    _configure_plugin(
        ctx,
        {
            "chat_scope_mode": "global_default",
            "global_apply_message_types": ["private"],
        },
    )
    plugin = AiGirlfriend()
    await plugin.on_start(ctx)

    event = MockMessageEvent(
        text="你好",
        user_id="user-2",
        platform="mock-platform",
        session_id="mock-platform:private:user-2",
        context=ctx,
    )

    await plugin.ensure_global_persona(event, ctx)

    conversation = await ctx.conversations.get_current_conversation(event.session_id)
    assert conversation is not None
    assert conversation.persona_id == "gf_default_gentle"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_girlfriend_llm_request_injects_memory_into_system_prompt() -> None:
    ctx = MockContext(plugin_id="ai_girlfriend")
    _configure_plugin(ctx, {})
    plugin = AiGirlfriend()
    await plugin.on_start(ctx)

    event = MockMessageEvent(
        text="我喜欢喝什么？",
        user_id="user-3",
        platform="mock-platform",
        session_id="mock-platform:private:user-3",
        context=ctx,
    )
    await plugin.chat(event, ctx)
    await ctx.memory.save(
        "gf:memory:user-3:1",
        {
            "content": "你喜欢红茶",
            "embedding_text": "用户喜欢红茶和甜点",
        },
    )

    request = ProviderRequest(
        prompt="我喜欢喝什么？",
        system_prompt="base prompt",
        session_id=event.session_id,
    )

    await plugin.inject_relationship_context(event, ctx, request)

    assert request.system_prompt is not None
    assert "base prompt" in request.system_prompt
    assert "用户喜欢红茶和甜点" in request.system_prompt
    assert "affection" in request.system_prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_girlfriend_after_message_sent_updates_affection_and_memory() -> None:
    ctx = MockContext(plugin_id="ai_girlfriend")
    _configure_plugin(ctx, {"affection_per_chat": 2})
    plugin = AiGirlfriend()
    await plugin.on_start(ctx)

    event = MockMessageEvent(
        text="今天有点累",
        user_id="user-4",
        platform="mock-platform",
        session_id="mock-platform:private:user-4",
        raw={"extras": {"_gf_last_reply_text": "那先抱抱你，今天辛苦了。"}},
        context=ctx,
    )
    await plugin.chat(event, ctx)

    await plugin.persist_relationship_state(event, ctx)

    affection = await ctx.db.get("gf:user:user-4:affection")
    session_payload = await ctx.db.get("gf:user:user-4:last_private_session")
    memories = await ctx.memory.search("抱抱你", limit=5)

    assert affection == 2
    assert session_payload["session_id"] == "mock-platform:private:user-4"
    assert any(item["key"].startswith("gf:memory:user-4:") for item in memories)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_girlfriend_prefers_configured_persona_without_overwriting_it() -> (
    None
):
    ctx = MockContext(plugin_id="ai_girlfriend")
    await ctx.personas.create_persona(
        PersonaCreateParams(
            persona_id="custom_gf",
            system_prompt="custom persona prompt",
            begin_dialogs=["你好呀", "我就是你的自定义人格"],
        )
    )
    _configure_plugin(ctx, {"default_persona_id": "custom_gf"})
    plugin = AiGirlfriend()
    await plugin.on_start(ctx)

    event = MockMessageEvent(
        text="gf chat",
        user_id="user-5",
        platform="mock-platform",
        session_id="mock-platform:private:user-5",
        context=ctx,
    )

    await plugin.chat(event, ctx)

    conversation = await ctx.conversations.get_current_conversation(event.session_id)
    persona = await ctx.personas.get_persona("custom_gf")
    assert conversation is not None
    assert conversation.persona_id == "custom_gf"
    assert persona.system_prompt == "custom persona prompt"
