from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api  # noqa: F401  # import first to avoid a circular import
from astrbot.core import persona_mgr as pm
from astrbot.core.db.po import Persona


def make_acm(persona_id: str = "default") -> MagicMock:
    """Build a mocked AstrBotConfigManager with the given default persona."""
    conf = {
        "agent_runner": {
            "runner_type": "local",
            "config": {"persona": {"persona_id": persona_id}},
        },
        "provider_settings": {},
    }
    acm = MagicMock()
    acm.default_conf = conf
    acm.get_conf.return_value = conf
    return acm


def make_persona(persona_id: str, prompt: str) -> Persona:
    return Persona(
        persona_id=persona_id,
        system_prompt=prompt,
        begin_dialogs=[],
        tools=None,
        skills=None,
        custom_error_message=None,
        folder_id=None,
        sort_order=0,
    )


def make_manager(
    personas: list[Persona], persona_id: str = "default"
) -> pm.PersonaManager:
    manager = pm.PersonaManager(db_helper=MagicMock(), acm=make_acm(persona_id))
    manager.personas = personas
    manager.get_v3_persona_data()
    return manager


def make_seeding_db(personas: list[Persona]) -> MagicMock:
    db = MagicMock()
    db.get_personas = AsyncMock(return_value=personas)
    db.insert_persona = AsyncMock(
        side_effect=lambda **kwargs: make_persona(
            kwargs["persona_id"], kwargs["system_prompt"]
        )
    )
    return db


@pytest.mark.asyncio
async def test_initialize_seeds_default_when_absent():
    db = make_seeding_db([make_persona("alice", "ALICE")])
    manager = pm.PersonaManager(db_helper=db, acm=make_acm())

    await manager.initialize()

    db.insert_persona.assert_awaited_once()
    assert {persona.persona_id for persona in manager.personas} == {
        "alice",
        "default",
    }
    seeded = manager.get_persona_v3_by_id("default")
    assert seeded is not None
    assert seeded["prompt"] == pm.DEFAULT_PERSONALITY["prompt"]


@pytest.mark.asyncio
async def test_initialize_adopts_existing_default():
    db = make_seeding_db([make_persona("default", "USER DEFAULT")])
    manager = pm.PersonaManager(db_helper=db, acm=make_acm())

    await manager.initialize()

    db.insert_persona.assert_not_awaited()
    adopted = manager.get_persona_v3_by_id("default")
    assert adopted is not None
    assert adopted["prompt"] == "USER DEFAULT"


@pytest.mark.asyncio
async def test_delete_default_persona_is_rejected():
    db = make_seeding_db([make_persona("default", "USER DEFAULT")])
    manager = pm.PersonaManager(db_helper=db, acm=make_acm())
    await manager.initialize()

    with pytest.raises(ValueError):
        await manager.delete_persona("default")


@pytest.mark.asyncio
async def test_create_default_persona_is_rejected():
    manager = pm.PersonaManager(db_helper=MagicMock(), acm=make_acm())

    with pytest.raises(ValueError):
        await manager.create_persona("default", "PROMPT")


def test_get_persona_v3_by_id_prefers_persona_named_default():
    manager = make_manager([make_persona("default", "USER DEFAULT")])

    resolved = manager.get_persona_v3_by_id("default")

    assert resolved is not None
    assert resolved["prompt"] == "USER DEFAULT"


def test_get_persona_v3_by_id_falls_back_to_builtin_default():
    manager = make_manager([make_persona("alice", "ALICE")])

    assert manager.get_persona_v3_by_id("default") == pm.DEFAULT_PERSONALITY


@pytest.mark.asyncio
async def test_get_default_persona_v3_uses_db_default():
    manager = make_manager([make_persona("default", "USER DEFAULT")])

    resolved = await manager.get_default_persona_v3(umo="test:umo")

    assert resolved["prompt"] == "USER DEFAULT"


@pytest.mark.asyncio
async def test_resolve_selected_persona_matches_db_default():
    manager = make_manager([make_persona("default", "USER DEFAULT")])

    with patch.object(pm.sp, "get_async", new=AsyncMock(return_value={})):
        persona_id, persona, _, _ = await manager.resolve_selected_persona(
            umo="test:umo",
            conversation_persona_id="default",
            platform_name="webchat",
            provider_settings={},
        )

    assert persona_id == "default"
    assert persona is not None
    assert persona["prompt"] == "USER DEFAULT"


@pytest.mark.asyncio
async def test_resolve_selected_persona_webchat_implicit_uses_chatui_default():
    manager = make_manager([make_persona("default", "USER DEFAULT")])

    with patch.object(pm.sp, "get_async", new=AsyncMock(return_value={})):
        (
            persona_id,
            persona,
            _,
            use_webchat_special_default,
        ) = await manager.resolve_selected_persona(
            umo="test:umo",
            conversation_persona_id=None,
            platform_name="webchat",
            provider_settings={},
        )

    assert persona_id == "_chatui_default_"
    assert persona is None
    assert use_webchat_special_default is True


@pytest.mark.asyncio
async def test_resolve_selected_persona_non_webchat_implicit_uses_db_default():
    manager = make_manager([make_persona("default", "USER DEFAULT")])

    with patch.object(pm.sp, "get_async", new=AsyncMock(return_value={})):
        (
            persona_id,
            persona,
            _,
            use_webchat_special_default,
        ) = await manager.resolve_selected_persona(
            umo="test:umo",
            conversation_persona_id=None,
            platform_name="telegram",
            provider_settings={},
        )

    assert persona_id == "default"
    assert persona is not None
    assert persona["prompt"] == "USER DEFAULT"
    assert use_webchat_special_default is False


@pytest.mark.asyncio
async def test_resolve_selected_persona_explicit_default_ignores_chatui_default():
    manager = make_manager([make_persona("default", "USER DEFAULT")])

    with patch.object(pm.sp, "get_async", new=AsyncMock(return_value={})):
        (
            persona_id,
            persona,
            _,
            use_webchat_special_default,
        ) = await manager.resolve_selected_persona(
            umo="test:umo",
            conversation_persona_id="default",
            platform_name="webchat",
            provider_settings={},
        )

    assert persona_id == "default"
    assert persona is not None
    assert persona["prompt"] == "USER DEFAULT"
    assert use_webchat_special_default is False


@pytest.mark.asyncio
async def test_resolve_selected_persona_session_rule_default_uses_db_default():
    manager = make_manager([make_persona("default", "USER DEFAULT")])

    with patch.object(
        pm.sp, "get_async", new=AsyncMock(return_value={"persona_id": "default"})
    ):
        (
            persona_id,
            persona,
            force_applied_persona_id,
            use_webchat_special_default,
        ) = await manager.resolve_selected_persona(
            umo="test:umo",
            conversation_persona_id=None,
            platform_name="webchat",
            provider_settings={},
        )

    assert persona_id == "default"
    assert persona is not None
    assert persona["prompt"] == "USER DEFAULT"
    assert force_applied_persona_id == "default"
    assert use_webchat_special_default is False
