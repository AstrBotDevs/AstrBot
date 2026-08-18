"""Test that _ensure_persona_and_skills handles None system_prompt.

When ProviderRequest.system_prompt is None (the default), calling
_ensure_persona_and_skills with a persona that has a prompt should
not crash with ``TypeError: unsupported operand type(s) for +=``.

The bug was that ``req.system_prompt += ...`` was called when
system_prompt was None instead of initializing it to "" first.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_ensure_persona_and_skills_handles_none_system_prompt():
    from astrbot.core.astr_main_agent import _ensure_persona_and_skills
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.db.po import ConversationV2

    # ProviderRequest.system_prompt defaults to None
    req = ProviderRequest()
    req.conversation = ConversationV2(
        conversation_id="test",
        platform_id="test",
        user_id="test",
    )

    cfg = {"computer_use_runtime": "local"}

    plugin_context = MagicMock()
    plugin_context.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(
            "persona-1",
            {"prompt": "You are a helpful assistant.", "name": "test"},
            None,
            False,
        )
    )

    event = MagicMock()
    event.unified_msg_origin = "test:test_user"

    # This should NOT raise TypeError even though req.system_prompt is None
    try:
        await _ensure_persona_and_skills(req, cfg, plugin_context, event)
    except TypeError as e:
        pytest.fail(f"_ensure_persona_and_skills crashed with TypeError: {e}")

    assert req.system_prompt is not None
    assert "# Persona Instructions" in req.system_prompt
