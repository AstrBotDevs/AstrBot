from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Importing core_lifecycle first resolves astrbot.core.persona_mgr's own circular
# import with astrbot.core.provider.manager (also exercised by test_core_lifecycle.py).
import astrbot.core.core_lifecycle  # noqa: F401
from astrbot.core.persona_mgr import DEFAULT_PERSONALITY, PersonaManager


def _build_manager(personas_v3: list[dict]) -> PersonaManager:
    acm = MagicMock()
    acm.default_conf = {"agent_runner": {"runner_type": "local", "config": {}}}
    acm.get_conf.return_value = {"agent_runner": {"runner_type": "local", "config": {}}}
    mgr = PersonaManager(db_helper=MagicMock(), acm=acm)
    mgr.personas_v3 = personas_v3
    return mgr


@pytest.mark.asyncio
async def test_resolve_selected_persona_agrees_with_get_persona_v3_by_id_for_default():
    """A user persona literally named "default" must not shadow the built-in one on
    only one of the two lookup paths: get_persona_v3_by_id and resolve_selected_persona
    have to agree on what persona_id "default" means.
    """
    user_default = {
        "prompt": "This is a user-authored default persona, NOT the built-in one",
        "name": "default",
        "begin_dialogs": [],
        "mood_imitation_dialogs": [],
        "tools": None,
        "skills": None,
        "custom_error_message": None,
        "_begin_dialogs_processed": [],
        "_mood_imitation_dialogs_processed": "",
    }
    mgr = _build_manager([user_default])

    by_id = mgr.get_persona_v3_by_id("default")
    assert by_id is DEFAULT_PERSONALITY

    with patch("astrbot.core.persona_mgr.sp.get_async", new=AsyncMock(return_value={})):
        _, resolved, _, _ = await mgr.resolve_selected_persona(
            umo="platform:group:1",
            conversation_persona_id="default",
            platform_name="not_webchat",
        )

    assert resolved is by_id
    assert resolved is not user_default


@pytest.mark.asyncio
async def test_resolve_selected_persona_still_finds_a_non_default_persona():
    other = {
        "prompt": "irrelevant",
        "name": "helper",
        "begin_dialogs": [],
        "mood_imitation_dialogs": [],
        "tools": None,
        "skills": None,
        "custom_error_message": None,
        "_begin_dialogs_processed": [],
        "_mood_imitation_dialogs_processed": "",
    }
    mgr = _build_manager([other])

    with patch("astrbot.core.persona_mgr.sp.get_async", new=AsyncMock(return_value={})):
        _, resolved, _, _ = await mgr.resolve_selected_persona(
            umo="platform:group:1",
            conversation_persona_id="helper",
            platform_name="not_webchat",
        )

    assert resolved is other
