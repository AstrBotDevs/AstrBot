"""Provider commands exercise real command behavior with local boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.provider import ProviderCommands
from astrbot.core.provider.entities import ProviderType


def _provider(identifier="first", model="model-a", kind=ProviderType.CHAT_COMPLETION):
    return SimpleNamespace(
        meta=Mock(
            return_value=SimpleNamespace(id=identifier, model=model, provider_type=kind)
        ),
        test=AsyncMock(),
        get_models=AsyncMock(return_value=["model-a", "model-b"]),
        get_model=Mock(return_value=model),
        set_model=Mock(),
        provider_config={"id": identifier, "model": model},
    )


@pytest.mark.asyncio
async def test_capability_check_invokes_the_provider_once():
    provider = _provider()
    commands = ProviderCommands(SimpleNamespace())

    assert await commands._test_provider_capability(provider) == (True, None, None)
    provider.test.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_capability_failure_becomes_a_displayable_failure():
    provider = _provider()
    provider.test.side_effect = RuntimeError("offline")
    commands = ProviderCommands(SimpleNamespace())

    reachable, code, reason = await commands._test_provider_capability(provider)

    assert reachable is False
    assert code == "TEST_FAILED"
    assert "offline" in reason
    provider.test.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_capability_cancellation_propagates():
    provider = _provider()
    provider.test.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await ProviderCommands(SimpleNamespace())._test_provider_capability(provider)

    provider.test.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_listing_without_reachability_checks_does_not_contact_providers():
    providers = [_provider("first"), _provider("second", "model-b")]
    commands = ProviderCommands(SimpleNamespace())

    result = await commands._build_provider_display_data(providers, "llm", False)

    assert result == [
        {"info": "first (model-a)", "mark": "", "provider": providers[0]},
        {"info": "second (model-b)", "mark": "", "provider": providers[1]},
    ]
    for provider in providers:
        provider.test.assert_not_awaited()


@pytest.mark.asyncio
async def test_listing_preserves_order_and_reports_each_reachability_result():
    providers = [_provider("working"), _provider("broken")]
    providers[1].test.side_effect = RuntimeError("offline")
    commands = ProviderCommands(SimpleNamespace())

    result = await commands._build_provider_display_data(providers, "tts", True)

    assert [item["provider"] for item in result] == providers
    assert [item["info"] for item in result] == ["working", "broken"]
    assert [item["mark"] for item in result] == [" ✅", " ❌(errcode: TEST_FAILED)"]
    for provider in providers:
        provider.test.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_listing_propagates_a_cancelled_capability_check():
    provider = _provider()
    provider.test.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await ProviderCommands(SimpleNamespace())._build_provider_display_data(
            [provider], "llm", True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("index", "secondary", "kind"),
    [
        (1, None, ProviderType.CHAT_COMPLETION),
        ("tts", 1, ProviderType.TEXT_TO_SPEECH),
        ("stt", 1, ProviderType.SPEECH_TO_TEXT),
    ],
)
async def test_provider_selection_uses_the_callers_session(index, secondary, kind):
    provider = _provider(kind=kind)
    manager = SimpleNamespace(set_provider=AsyncMock())
    context = SimpleNamespace(
        locale=lambda umo: "en-US",
        get_config=lambda umo: {"provider_settings": {"reachability_check": False}},
        get_all_providers=lambda: [provider],
        get_all_tts_providers=lambda: [provider],
        get_all_stt_providers=lambda: [provider],
        provider_manager=manager,
    )
    event = SimpleNamespace(unified_msg_origin="adapter:group:42", set_result=Mock())

    await ProviderCommands(context).provider(event, index, secondary)

    manager.set_provider.assert_awaited_once_with(
        provider_id="first", provider_type=kind, umo="adapter:group:42"
    )
    event.set_result.assert_called_once()
    provider.test.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [0, 2, -1])
async def test_invalid_selection_does_not_change_the_active_provider(index):
    manager = SimpleNamespace(set_provider=AsyncMock())
    context = SimpleNamespace(
        locale=lambda umo: "en-US",
        get_config=lambda umo: {"provider_settings": {}},
        get_all_providers=lambda: [_provider()],
        provider_manager=manager,
    )
    event = SimpleNamespace(unified_msg_origin="session", set_result=Mock())

    await ProviderCommands(context).provider(event, index)

    manager.set_provider.assert_not_awaited()
    event.set_result.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [2, "2", "model-b"])
async def test_model_selection_updates_only_the_selected_provider_and_saves_once(
    selection,
):
    provider = _provider()

    class Config(dict):
        save_config = Mock()

    config = Config(
        provider=[
            {"id": "unrelated", "model": "keep"},
            {"id": "first", "model": "model-a"},
        ]
    )
    context = SimpleNamespace(
        get_using_provider=lambda **kwargs: provider,
        get_config=lambda umo: config,
    )
    event = SimpleNamespace(unified_msg_origin="session", set_result=Mock())

    await ProviderCommands(context).model_ls(event, selection)

    provider.get_models.assert_awaited_once_with()
    provider.set_model.assert_called_once_with("model-b")
    assert provider.provider_config["model"] == "model-b"
    assert config["provider"] == [
        {"id": "unrelated", "model": "keep"},
        {"id": "first", "model": "model-b"},
    ]
    config.save_config.assert_called_once_with()
    assert "model-b" in event.set_result.call_args.args[0].chain[0].text
