"""Protect omitted fields, partial batch outcomes, and legacy error responses."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.dashboard.routes import conversation as conversation_route
from astrbot.dashboard.routes import persona as persona_route
from astrbot.dashboard.routes import skills as skills_route
from astrbot.dashboard.services import skills_service
from astrbot.dashboard.services.persona_service import PersonaService


class _FilesRequest:
    @property
    def files(self):
        async def get_files():
            return SimpleNamespace(getlist=lambda _: [object(), object()])

        return get_files()


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "succeeded,failed,skipped,ok,message",
    [
        (["a", "b"], [], [], True, "All 2 skill(s) uploaded successfully."),
        ([], [], ["a", "b"], True, "All 2 file(s) were skipped."),
        ([], ["a", "b"], [], False, "Upload failed for all 2 file(s)."),
        (["a"], ["b"], [], True, "Partial success: 1/2 skill(s) uploaded."),
    ],
)
async def test_skill_batch_preserves_partial_results_and_status(
    monkeypatch, legacy, succeeded, failed, skipped, ok, message
):
    module = skills_route if legacy else skills_service
    monkeypatch.setattr(module, "DEMO_MODE", False)
    monkeypatch.setattr(module, "SkillManager", Mock())
    monkeypatch.setattr(module, "get_astrbot_temp_path", lambda: "/unused")
    install = AsyncMock(return_value=(succeeded, failed, skipped))
    monkeypatch.setattr(module, "install_skill_archives", install)
    expected = {
        "total": 2,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
    }
    if legacy:
        monkeypatch.setattr(module, "request", _FilesRequest())
        instance = object.__new__(skills_route.SkillsRoute)
        result = await instance.batch_upload_skills()
        assert result == {
            "status": "ok" if ok else "error",
            "message": message,
            "data": expected,
        }
    else:
        instance = object.__new__(skills_service.SkillsService)
        result = await instance.batch_upload_skills([object(), object()])
        assert result.ok is ok
        assert result.message == message
        assert result.data == expected
    install.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"tools": None, "skills": None},
        {"tools": [], "skills": [], "custom_error_message": "  "},
    ],
)
async def test_persona_update_preserves_omitted_explicit_null_and_empty_fields(
    monkeypatch, legacy, extra
):
    payload = {"persona_id": "persona", **extra}
    manager = SimpleNamespace(update_persona=AsyncMock())
    if legacy:
        monkeypatch.setattr(
            persona_route,
            "request",
            SimpleNamespace(get_json=AsyncMock(return_value=payload)),
        )
        instance = object.__new__(persona_route.PersonaRoute)
        instance.persona_mgr = manager
        result = await instance.update_persona()
        assert result["status"] == "ok"
    else:
        instance = PersonaService(SimpleNamespace(persona_mgr=manager))
        await instance.update_persona(payload)
    expected = {
        "persona_id": "persona",
        "system_prompt": None,
        "begin_dialogs": None,
        **extra,
    }
    if "custom_error_message" in extra:
        expected["custom_error_message"] = None
    manager.update_persona.assert_awaited_once_with(**expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get_conv_detail", "upd_conv"])
@pytest.mark.parametrize(
    "case,message",
    [
        ("missing_id", "缺少必要参数: user_id 和 cid"),
        ("missing_manager", "Conversation manager not available"),
        ("missing_conversation", "对话不存在"),
    ],
)
async def test_conversation_errors_remain_unprefixed_before_read_or_update(
    monkeypatch, operation, case, message
):
    payload = (
        {"user_id": "user", "cid": "cid"}
        if case != "missing_id"
        else {"user_id": "user"}
    )
    manager = SimpleNamespace(
        get_conversation=AsyncMock(return_value=None), update_conversation=AsyncMock()
    )
    monkeypatch.setattr(
        conversation_route,
        "request",
        SimpleNamespace(get_json=AsyncMock(return_value=payload)),
    )
    route = object.__new__(conversation_route.ConversationRoute)
    route.conv_mgr = None if case == "missing_manager" else manager
    result = await getattr(route, operation)()
    assert result == {"status": "error", "message": message, "data": {}}
    manager.update_conversation.assert_not_awaited()
    if case == "missing_conversation":
        manager.get_conversation.assert_awaited_once_with(
            unified_msg_origin="user", conversation_id="cid"
        )
    else:
        manager.get_conversation.assert_not_awaited()
