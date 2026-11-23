"""Persona application accepts an absent prompt and keeps request state isolated."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime.main_agent import persona as persona_module
from astrbot.core.db.po import ConversationV2
from astrbot.core.provider.entities import ProviderRequest


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_prompt", [None, "", "Existing instructions."])
async def test_apply_persona_handles_absent_or_existing_prompt(
    monkeypatch, initial_prompt
):
    begin_dialogs = [{"role": "user", "content": "Hello"}]
    selected = {
        "name": "test",
        "prompt": "You are a helpful assistant.",
        "_begin_dialogs_processed": begin_dialogs,
        "tools": [],
        "skills": [],
    }
    resolver = AsyncMock(return_value=("persona-1", selected, False))
    context = SimpleNamespace(
        persona_manager=SimpleNamespace(resolve_selected_persona=resolver),
        get_llm_tool_manager=lambda: SimpleNamespace(get_full_tool_set=ToolSet),
    )
    extras = {}
    event = SimpleNamespace(
        unified_msg_origin="test:FriendMessage:alice",
        get_platform_name=lambda: "test",
        set_extra=extras.__setitem__,
        get_extra=lambda key, default=None: extras.get(key, default),
    )
    monkeypatch.setattr(
        persona_module,
        "SkillManager",
        lambda: SimpleNamespace(list_skills=lambda **kwargs: []),
    )
    request = ProviderRequest(system_prompt=initial_prompt)
    request.conversation = ConversationV2(
        conversation_id="test", platform_id="test", user_id="alice"
    )
    await persona_module.apply_persona(
        request,
        {"computer_use_runtime": "none"},
        context,
        event,
        plugin_tools=ToolSet(),
        plugin_skills=[],
    )
    assert (
        request.system_prompt
        == (initial_prompt or "")
        + "\n<persona_instructions>\nYou are a helpful assistant.\n</persona_instructions>\n"
    )
    assert extras["_trace_persona_id"] == "persona-1"
    resolver.assert_awaited_once_with(
        umo=event.unified_msg_origin, platform_name="test"
    )
    assert request.contexts == begin_dialogs
    assert request.contexts[0] is not begin_dialogs[0]
    request.contexts[0]["content"] = "Changed"
    assert begin_dialogs[0]["content"] == "Hello"
