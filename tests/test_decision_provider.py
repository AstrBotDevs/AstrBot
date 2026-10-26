import json
import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from astrbot.core.provider.decision import DecisionService
from astrbot.core.provider.entities import (
    DecisionAnswer,
    DecisionBooleanQuestion,
    DecisionChoiceQuestion,
    DecisionError,
    ProviderType,
)
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import DecisionProvider, Provider
from astrbot.core.provider.sources.system_one_decision_source import (
    SystemOneDecisionProvider,
)


def _provider(handler, **overrides) -> SystemOneDecisionProvider:
    config = {
        "id": "decision_test",
        "type": "system_one_decision",
        "api_base": "https://decision.test/v1/systemone",
        "model": "jev-latest",
        "key": ["sk-test"],
        "timeout": 5,
        "custom_headers": {"X-Test": "yes"},
    }
    config.update(overrides)
    return SystemOneDecisionProvider(
        config,
        {},
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_system_one_decisions_share_one_request_and_parse_all_heads():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["custom"] = request.headers["x-test"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "jev-latest",
                "answers": {
                    "decision": {
                        "type": "choice",
                        "choice": "respond",
                        "confidence": 0.9,
                        "probabilities": {"respond": 0.8, "ignore": 0.2},
                    },
                    "available": {"type": "noul", "noul": 0.73},
                },
            },
        )

    provider = _provider(handler)
    try:
        answers = await provider.ask(
            {
                "decision": DecisionChoiceQuestion(
                    "Should the assistant reply?",
                    {"respond": "Reply now", "ignore": "Stay silent"},
                ),
                "available": DecisionBooleanQuestion("Is the endpoint available?"),
            },
            {"message": "hello"},
        )
    finally:
        await provider.terminate()

    assert captured["authorization"] == "Bearer sk-test"
    assert captured["custom"] == "yes"
    assert captured["body"] == {
        "model": "jev-latest",
        "state": {"message": "hello"},
        "questions": {
            "decision": {
                "type": "choice",
                "instructions": "Should the assistant reply?",
                "criteria": {"respond": "Reply now", "ignore": "Stay silent"},
            },
            "available": {
                "type": "noul",
                "instructions": "Is the endpoint available?",
            },
        },
    }
    assert answers["decision"].choice == "respond"
    assert answers["decision"].probability == 0.8
    assert answers["decision"].confidence == 0.9
    assert answers["decision"].probabilities == {"respond": 0.8, "ignore": 0.2}
    assert answers["available"].choice is None
    assert answers["available"].probability == 0.73


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("api_base", "expected_url"),
    [
        ("https://decision.test/v1", "https://decision.test/v1/systemone"),
        ("https://decision.test/v1/", "https://decision.test/v1"),
        (
            "https://decision.test/v1/systemone",
            "https://decision.test/v1/systemone",
        ),
    ],
)
async def test_system_one_resolves_api_base(api_base, expected_url):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"answers": {"available": {"type": "noul", "noul": 1.0}}},
        )

    provider = _provider(handler, api_base=api_base)
    try:
        await provider.ask(
            {"available": DecisionBooleanQuestion("Is the endpoint available?")}
        )
    finally:
        await provider.terminate()

    assert captured["url"] == expected_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "choice_answer",
    [
        {
            "choice": "other",
            "confidence": 0.9,
            "probabilities": {"respond": 0.8, "ignore": 0.2},
        },
        {
            "choice": "respond",
            "confidence": 0.9,
            "probabilities": {"respond": 0.8, "ignore": 0.3},
        },
        {
            "choice": "respond",
            "confidence": 0.9,
            "probabilities": {"respond": 0.2, "ignore": 0.8},
        },
    ],
)
async def test_system_one_rejects_invalid_choice_answers(choice_answer):
    provider = _provider(
        lambda request: httpx.Response(
            200,
            json={"answers": {"decision": choice_answer}},
        )
    )
    try:
        with pytest.raises(DecisionError):
            await provider.ask(
                {
                    "decision": DecisionChoiceQuestion(
                        "Choose one",
                        {"respond": "Reply", "ignore": "Ignore"},
                    )
                }
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_system_one_normalizes_http_errors_and_closes_client(caplog):
    caplog.set_level(logging.ERROR, logger="astrbot")
    provider = _provider(
        lambda request: httpx.Response(
            400,
            json={"state": "private-conversation"},
        )
    )
    try:
        with pytest.raises(DecisionError, match="HTTP 400"):
            await provider.ask(
                {"available": DecisionBooleanQuestion("Is it available?")}
            )
    finally:
        await provider.terminate()

    assert provider.client.is_closed
    assert "HTTP 400" in caplog.text
    assert "private-conversation" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (httpx.ReadTimeout("read timeout"), "timed out after 5s"),
        (httpx.ConnectError("connection refused"), "unable to connect"),
    ],
)
async def test_system_one_normalizes_network_errors(error, message):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    provider = _provider(handler)
    try:
        with pytest.raises(DecisionError, match=message):
            await provider.ask(
                {"available": DecisionBooleanQuestion("Is it available?")},
                request_max_retries=1,
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_system_one_rejects_invalid_json():
    provider = _provider(
        lambda request: httpx.Response(
            200,
            content=b"<html>bad gateway</html>",
            headers={"Content-Type": "text/html"},
        )
    )
    try:
        with pytest.raises(DecisionError, match="invalid JSON"):
            await provider.ask(
                {"available": DecisionBooleanQuestion("Is it available?")}
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_decision_provider_test_does_not_retry():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "unavailable"})

    provider = _provider(handler)
    try:
        with pytest.raises(DecisionError, match="HTTP 503"):
            await provider.test()
    finally:
        await provider.terminate()

    assert attempts == 1


@pytest.mark.asyncio
async def test_decision_service_maps_choice_ids_and_applies_threshold():
    provider = MagicMock(spec=DecisionProvider)
    provider.ask = AsyncMock(
        side_effect=[
            {
                "answer": DecisionAnswer(
                    choice="o2",
                    probability=0.75,
                    probabilities={"o1": 0.25, "o2": 0.75},
                    confidence=0.8,
                )
            },
            {
                "answer": DecisionAnswer(
                    choice=None,
                    probability=0.6,
                    probabilities={},
                    confidence=None,
                )
            },
        ]
    )
    manager = MagicMock()
    manager.get_using_provider_async = AsyncMock(return_value=provider)
    service = DecisionService(manager)

    choice = await service.choose("Pick one", ["wait", "reply"])
    result = await service.yes_no("Continue?", threshold=0.5)

    assert choice.choice == "reply"
    assert choice.probability == 0.75
    assert choice.probabilities == {"wait": 0.25, "reply": 0.75}
    assert result is True
    assert manager.get_using_provider_async.await_args.args == (ProviderType.DECISION,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        DecisionAnswer(
            choice="o3",
            probability=0.6,
            probabilities={"o1": 0.4, "o2": 0.6},
            confidence=0.8,
        ),
        DecisionAnswer(
            choice="o2",
            probability=0.6,
            probabilities={"o1": 0.4, "o3": 0.6},
            confidence=0.8,
        ),
    ],
)
async def test_decision_service_rejects_unknown_provider_option_keys(answer):
    provider = MagicMock(spec=DecisionProvider)
    provider.ask = AsyncMock(return_value={"answer": answer})
    manager = MagicMock()
    manager.get_using_provider_async = AsyncMock(return_value=provider)

    with pytest.raises(DecisionError, match="invalid choice"):
        await DecisionService(manager).choose("Pick one", ["wait", "reply"])


@pytest.mark.asyncio
async def test_decision_service_rejects_non_decision_provider():
    manager = MagicMock()
    manager.get_using_provider_async = AsyncMock(return_value=MagicMock(spec=Provider))

    with pytest.raises(DecisionError):
        await DecisionService(manager).yes_no("Continue?")


@pytest.mark.asyncio
async def test_provider_manager_loads_decision_provider():
    config = {
        "provider": [],
        "provider_sources": [],
        "provider_settings": {},
    }
    acm = MagicMock()
    acm.confs = {"default": config}
    acm.get_conf.return_value = config
    persona_manager = MagicMock()
    persona_manager.default_persona = ""
    manager = ProviderManager(acm, MagicMock(), persona_manager)

    await manager.load_provider(
        {
            "id": "decision_test",
            "type": "system_one_decision",
            "provider_type": "decision",
            "api_base": "https://decision.test/v1/systemone",
            "model": "jev-latest",
            "key": [],
            "enable": True,
        }
    )

    loaded = manager.inst_map["decision_test"]
    assert isinstance(loaded, SystemOneDecisionProvider)
    assert manager.decision_provider_insts == [loaded]
    assert manager.curr_decision_provider_inst is loaded
    await loaded.terminate()


@pytest.mark.asyncio
async def test_provider_manager_uses_selected_decision_provider():
    config = {
        "provider": [],
        "provider_sources": [],
        "provider_settings": {},
    }
    acm = MagicMock()
    acm.confs = {"default": config}
    acm.get_conf.return_value = config
    persona_manager = MagicMock()
    persona_manager.default_persona = ""
    manager = ProviderManager(acm, MagicMock(), persona_manager)

    provider_configs = [
        {
            "id": f"decision_{index}",
            "type": "system_one_decision",
            "provider_type": "decision",
            "api_base": f"https://decision{index}.test/v1/systemone",
            "model": "jev-latest",
            "key": [],
            "enable": True,
        }
        for index in range(2)
    ]
    for provider_config in provider_configs:
        await manager.load_provider(provider_config)

    second = manager.inst_map["decision_1"]
    await manager.set_provider("decision_1", ProviderType.DECISION)

    assert await manager.get_using_provider_async(ProviderType.DECISION) is second

    await manager.terminate_provider("decision_0")
    await manager.terminate_provider("decision_1")


@pytest.mark.asyncio
async def test_create_provider_rolls_back_when_loading_fails():
    config = MagicMock()
    providers = []
    config.__getitem__.side_effect = lambda key: {
        "provider": providers,
        "provider_settings": {},
    }[key]
    acm = MagicMock()
    acm.default_conf = config
    acm.confs = {
        "default": {
            "provider": [],
            "provider_sources": [],
            "provider_settings": {},
        }
    }
    persona_manager = MagicMock()
    persona_manager.default_persona = ""
    manager = ProviderManager(acm, MagicMock(), persona_manager)
    manager.load_provider = AsyncMock(side_effect=ValueError("api_base is required"))

    with pytest.raises(ValueError, match="api_base is required"):
        await manager.create_provider(
            {
                "id": "invalid_decision",
                "type": "system_one_decision",
                "provider_type": "decision",
                "api_base": "",
                "enable": True,
            }
        )

    assert providers == []
    config.save_config.assert_not_called()
