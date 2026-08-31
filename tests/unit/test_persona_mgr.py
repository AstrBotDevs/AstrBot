from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.persona_mgr import PersonaManager


@pytest.mark.asyncio
async def test_resolve_selected_persona_uses_agent_runner_default_persona():
    agent_runner = {
        "runner_type": "local",
        "config": {"persona": {"persona_id": "from-agent-runner"}},
    }
    acm = SimpleNamespace(
        default_conf={"agent_runner": agent_runner},
        get_conf=lambda _umo: {"agent_runner": agent_runner},
    )
    preferences = SimpleNamespace(get_async=AsyncMock(return_value={}))
    manager = PersonaManager(db_helper=MagicMock(), acm=acm, preferences=preferences)
    manager.runtime_personas = [{"name": "from-agent-runner"}]

    persona_id, persona, force_id, use_webchat = await manager.resolve_selected_persona(
        umo="webchat:FriendMessage:user",
        conversation_persona_id=None,
        platform_name="webchat",
    )

    assert persona_id == "from-agent-runner"
    assert persona == {"name": "from-agent-runner"}
    assert force_id is None
    assert use_webchat is False
