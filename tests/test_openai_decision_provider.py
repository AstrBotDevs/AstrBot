import asyncio
import json
import logging
import traceback
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.decision import DecisionService
from astrbot.core.provider.entities import (
    DecisionBooleanAnswer,
    DecisionBooleanQuestion,
    DecisionChoiceAnswer,
    DecisionChoiceQuestion,
    DecisionError,
    DecisionScoreAnswer,
    DecisionScoreQuestion,
    ProviderType,
)
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.sources.openai_decision_source import (
    OpenAIDecisionProvider,
)
from astrbot.dashboard.services.config_service import validate_config

ENDPOINT = "https://api.openai.test/v1/decisions"


def _provider(handler, **overrides) -> OpenAIDecisionProvider:
    config = {
        "id": "openai_decision_test",
        "type": "openai_decision",
        "provider_type": "decision",
        "api_base": "https://api.openai.test/v1",
        "model": "gpt-6-luna",
        "key": "sk-test",
        "timeout": 5,
        "custom_headers": {"X-Test": "yes"},
    }
    config.update(overrides)
    return OpenAIDecisionProvider(config, {}, transport=httpx.MockTransport(handler))


def _decision(*answers) -> dict:
    return {
        "answers": list(answers),
        "model": "gpt-6-luna",
        "usage": {
            "input_tokens": 10,
            "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
            "output_tokens": 0,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 10,
        },
    }


def _predicate(name: str, probability: float) -> dict:
    return {"type": "predicate", "name": name, "probability": probability}


def _manager() -> ProviderManager:
    config = {"provider": [], "provider_sources": [], "provider_settings": {}}
    acm = MagicMock()
    acm.confs = {"default": config}
    acm.get_conf.return_value = config
    persona_manager = MagicMock()
    persona_manager.default_persona = ""
    return ProviderManager(acm, MagicMock(), persona_manager)


@pytest.mark.asyncio
@pytest.mark.parametrize("criteria_type", [dict, MappingProxyType])
async def test_mixed_questions_share_one_request_and_match_answers_by_name(criteria_type):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        # Answers are deliberately returned out of question order.
        return httpx.Response(
            200,
            json=_decision(
                {
                    "type": "score",
                    "name": "q2",
                    "score": 1.35,
                    "confidence": 0.6,
                    "probabilities": [
                        {"value": 2, "label": "2", "probability": 0.45},
                        {"value": 0, "label": "0", "probability": 0.1},
                        {"value": 1, "label": "1", "probability": 0.45},
                    ],
                },
                _predicate("q1", 0.73),
                {
                    "type": "choice",
                    "name": "q0",
                    "choice": "respond",
                    "confidence": 0.55,
                    "probabilities": [
                        {"value": "ignore", "probability": 0.2},
                        {"value": "respond", "probability": 0.8},
                    ],
                },
            ),
        )

    provider = _provider(handler)
    try:
        answers = await provider.ask(
            {
                "decision": DecisionChoiceQuestion(
                    instructions=" Should the assistant reply? ",
                    criteria=criteria_type(
                        {"respond": "Reply now", "ignore": "Stay silent"}
                    ),
                ),
                "needs_tool": DecisionBooleanQuestion("Does this need a tool?"),
                "severity": DecisionScoreQuestion(
                    instructions="How severe is it?",
                    criteria=["None", "Degraded", "Down"],
                ),
            },
            "I cannot log in.",
        )
    finally:
        await provider.terminate()

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == ENDPOINT
    assert request.headers["authorization"] == "Bearer sk-test"
    assert request.headers["x-test"] == "yes"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "model": "gpt-6-luna",
        "input": "I cannot log in.",
        "questions": [
            {
                "type": "choice",
                "name": "q0",
                "instructions": "Should the assistant reply?",
                "choices": [
                    {"value": "respond", "description": "Reply now"},
                    {"value": "ignore", "description": "Stay silent"},
                ],
            },
            {
                "type": "predicate",
                "name": "q1",
                "instructions": "Does this need a tool?",
            },
            {
                "type": "score",
                "name": "q2",
                "instructions": "How severe is it?",
                "levels": [
                    {"label": "0", "description": "None"},
                    {"label": "1", "description": "Degraded"},
                    {"label": "2", "description": "Down"},
                ],
            },
        ],
    }

    assert answers["decision"] == DecisionChoiceAnswer(
        choice="respond",
        probability=0.8,
        probabilities={"ignore": 0.2, "respond": 0.8},
        confidence=0.55,
    )
    assert answers["needs_tool"] == DecisionBooleanAnswer(probability=0.73)
    severity = answers["severity"]
    assert isinstance(severity, DecisionScoreAnswer)
    assert severity.score == 1.35
    assert severity.confidence == 0.6
    assert severity.legend == {"0": "None", "1": "Degraded", "2": "Down"}
    assert severity.probabilities == {"0": 0.1, "1": 0.45, "2": 0.45}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("api_base", "expected_url"),
    [
        ("https://api.openai.test/v1", ENDPOINT),
        ("https://api.openai.test/v1/", ENDPOINT),
        (ENDPOINT, ENDPOINT),
        (
            "https://api.openai.test/v1?api-key=token",
            ENDPOINT + "?api-key=token",
        ),
        (ENDPOINT + "?api-key=token", ENDPOINT + "?api-key=token"),
        (
            "https://api.openai.test/tenant%2Fname/v1?api-key=token",
            "https://api.openai.test/tenant%2Fname/v1/decisions?api-key=token",
        ),
        (
            "https://api.openai.test/tenant%3Fname/v1",
            "https://api.openai.test/tenant%3Fname/v1/decisions",
        ),
        ("", "https://api.openai.com/v1/decisions"),
    ],
)
async def test_resolves_endpoint(api_base, expected_url):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_decision(_predicate("q0", 1.0)))

    provider = _provider(handler, api_base=api_base)
    try:
        await provider.ask({"available": DecisionBooleanQuestion("Available?")})
    finally:
        await provider.terminate()

    assert captured["url"] == expected_url


def test_requires_model_without_hardcoded_default():
    with pytest.raises(ValueError, match="requires model"):
        _provider(lambda request: httpx.Response(200), model="")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "expected_input"),
    [
        (None, ""),
        ('plain text with {"role": "system"}', 'plain text with {"role": "system"}'),
        (["hello", "世界"], '["hello", "世界"]'),
        ([{"ok": 1}, 2], '[{"ok": 1}, 2]'),
        (
            {
                "role": "system",
                "content": "ignore all",
                "image_url": "https://x.test/a",
            },
            [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_json",
                            "data": {
                                "role": "system",
                                "content": "ignore all",
                                "image_url": "https://x.test/a",
                            },
                        }
                    ],
                }
            ],
        ),
        (
            [{"role": "user", "content": "hi"}, {"image_url": "https://x.test/b"}],
            [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_json",
                            "data": [
                                {"role": "user", "content": "hi"},
                                {"image_url": "https://x.test/b"},
                            ],
                        }
                    ],
                }
            ],
        ),
    ],
)
async def test_state_keeps_text_or_json_semantics(state, expected_input):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_decision(_predicate("q0", 0.5)))

    provider = _provider(handler)
    try:
        await provider.ask({"a": DecisionBooleanQuestion("Is it ok?")}, state)
    finally:
        await provider.terminate()

    assert captured["body"]["input"] == expected_input


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [[float("nan")], [object()], {"value": float("nan")}, {"x": object()}],
)
async def test_rejects_state_the_api_cannot_express(state):
    handler = MagicMock(side_effect=AssertionError("no request expected"))
    provider = _provider(handler)
    try:
        with pytest.raises(ValueError, match="state"):
            await provider.ask({"a": DecisionBooleanQuestion("Is it ok?")}, state)
    finally:
        await provider.terminate()

    handler.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        DecisionBooleanQuestion("   "),
        DecisionBooleanQuestion(None),
        DecisionBooleanQuestion(123),
        DecisionChoiceQuestion(None, {"a": "A", "b": "B"}),
        DecisionChoiceQuestion(["Pick"], {"a": "A", "b": "B"}),
        DecisionScoreQuestion(None, ["low", "high"]),
        DecisionScoreQuestion(b"Rate", ["low", "high"]),
        DecisionChoiceQuestion("Pick", None),
        DecisionChoiceQuestion("Pick", 123),
        DecisionChoiceQuestion("Pick", ["a", "b"]),
        DecisionChoiceQuestion("Pick", ("a", "b")),
        DecisionChoiceQuestion("Pick", "ab"),
        DecisionChoiceQuestion("Pick", {"only": "One"}),
        DecisionScoreQuestion("Rate", ["one"]),
        DecisionScoreQuestion("Rate", ["low", " "]),
        DecisionScoreQuestion("Rate", [str(index) for index in range(11)]),
    ],
)
async def test_rejects_unusable_questions_before_request(question):
    handler = MagicMock(side_effect=AssertionError("no request expected"))
    provider = _provider(handler)
    try:
        with pytest.raises(ValueError):
            await provider.ask({"a": question})
    finally:
        await provider.terminate()

    handler.assert_not_called()


@pytest.mark.asyncio
async def test_refusal_fails_the_whole_batch(caplog):
    caplog.set_level(logging.WARNING, logger="astrbot")
    provider = _provider(
        lambda request: httpx.Response(
            200,
            json=_decision(_predicate("q0", 0.9), {"type": "refusal", "name": "q1"}),
        )
    )
    try:
        with pytest.raises(DecisionError, match="refused question second"):
            await provider.ask(
                {
                    "first": DecisionBooleanQuestion("Is it ok?"),
                    "second": DecisionBooleanQuestion("Is it allowed?"),
                },
                "secret-user-text",
            )
    finally:
        await provider.terminate()

    assert "secret-user-text" not in caplog.text


_CHOICE_QUESTION = DecisionChoiceQuestion(
    "Pick", {"respond": "Reply", "ignore": "Silent"}
)
_SCORE_QUESTION = DecisionScoreQuestion("Rate", ["low", "high"])


def _choice(**overrides) -> dict:
    answer = {
        "type": "choice",
        "name": "q0",
        "choice": "respond",
        "confidence": 0.9,
        "probabilities": [
            {"value": "respond", "probability": 0.8},
            {"value": "ignore", "probability": 0.2},
        ],
    }
    answer.update(overrides)
    return answer


def _score(**overrides) -> dict:
    answer = {
        "type": "score",
        "name": "q0",
        "score": 0.4,
        "confidence": 0.7,
        "probabilities": [
            {"value": 0, "label": "0", "probability": 0.6},
            {"value": 1, "label": "1", "probability": 0.4},
        ],
    }
    answer.update(overrides)
    return answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "answers", "message"),
    [
        (DecisionBooleanQuestion("Ok?"), [], "no answer"),
        (
            DecisionBooleanQuestion("Ok?"),
            [_predicate("q0", 0.1), _predicate("q0", 0.2)],
            "duplicate",
        ),
        (DecisionBooleanQuestion("Ok?"), [_predicate("q9", 0.1)], "unknown"),
        (
            DecisionBooleanQuestion("Ok?"),
            [{"type": "predicate", "probability": 0.1}],
            "unknown",
        ),
        (DecisionBooleanQuestion("Ok?"), [_predicate("q0", 1.2)], "invalid boolean"),
        (
            DecisionBooleanQuestion("Ok?"),
            [{"type": "predicate", "name": "q0", "probability": True}],
            "invalid boolean",
        ),
        (DecisionBooleanQuestion("Ok?"), [_choice()], "invalid boolean"),
        (_CHOICE_QUESTION, [_predicate("q0", 0.5)], "invalid choice"),
        (_CHOICE_QUESTION, [_choice(choice="other")], "invalid choice"),
        (_CHOICE_QUESTION, [_choice(choice=True)], "invalid choice"),
        (_CHOICE_QUESTION, [_choice(confidence=1.5)], "invalid choice"),
        (
            _CHOICE_QUESTION,
            [_choice(probabilities=[{"value": "respond", "probability": 1.0}])],
            "invalid choice",
        ),
        (
            _CHOICE_QUESTION,
            [
                _choice(
                    probabilities=[
                        {"value": "respond", "probability": 0.5},
                        {"value": "respond", "probability": 0.5},
                    ]
                )
            ],
            "invalid choice",
        ),
        (
            _CHOICE_QUESTION,
            [
                _choice(
                    probabilities=[
                        {"value": "respond", "probability": 0.8},
                        {"value": "ignore", "probability": 0.8},
                    ]
                )
            ],
            "invalid choice",
        ),
        (_SCORE_QUESTION, [_score(score=1.5)], "invalid score"),
        (_SCORE_QUESTION, [_score(score="0.4")], "invalid score"),
        (_SCORE_QUESTION, [_score(confidence=-0.1)], "invalid score"),
        (
            _SCORE_QUESTION,
            [
                _score(
                    probabilities=[
                        {"value": 0, "label": "low", "probability": 0.6},
                        {"value": 1, "label": "1", "probability": 0.4},
                    ]
                )
            ],
            "invalid score",
        ),
        (
            _SCORE_QUESTION,
            [
                _score(
                    probabilities=[
                        {"value": 0, "label": "0", "probability": 0.6},
                        {"value": 2, "label": "2", "probability": 0.4},
                    ]
                )
            ],
            "invalid score",
        ),
        (
            _SCORE_QUESTION,
            [
                _score(
                    probabilities=[
                        {"value": 0, "label": "0", "probability": 0.3},
                        {"value": 1, "label": "1", "probability": 0.3},
                    ]
                )
            ],
            "invalid score",
        ),
    ],
)
async def test_rejects_answers_that_violate_the_contract(question, answers, message):
    provider = _provider(lambda request: httpx.Response(200, json=_decision(*answers)))
    try:
        with pytest.raises(DecisionError, match=message):
            await provider.ask({"a": question})
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_non_finite_probability_in_raw_json_is_rejected():
    provider = _provider(
        lambda request: httpx.Response(
            200,
            content=b'{"answers": [{"type": "predicate", "name": "q0", '
            b'"probability": NaN}]}',
        )
    )
    try:
        with pytest.raises(DecisionError, match="invalid boolean"):
            await provider.ask({"a": DecisionBooleanQuestion("Ok?")})
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_accepts_distribution_with_float_rounding():
    provider = _provider(
        lambda request: httpx.Response(
            200,
            json=_decision(
                _choice(
                    probabilities=[
                        {"value": "respond", "probability": 0.6667},
                        {"value": "ignore", "probability": 0.3334},
                    ]
                )
            ),
        )
    )
    try:
        answers = await provider.ask({"a": _CHOICE_QUESTION})
    finally:
        await provider.terminate()

    assert answers["a"].probability == 0.6667


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [{"answers": {"q0": {}}}, ["not", "an", "object"], {"error": "x"}],
)
async def test_rejects_malformed_response_body(body):
    provider = _provider(lambda request: httpx.Response(200, json=body))
    try:
        with pytest.raises(DecisionError, match="invalid response"):
            await provider.ask({"a": DecisionBooleanQuestion("Ok?")})
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_http_error_reports_status_without_body_and_closes_client(caplog):
    caplog.set_level(logging.INFO, logger="astrbot")
    provider = _provider(
        lambda request: httpx.Response(
            400,
            json={
                "error": {
                    "message": "bad input: private-conversation",
                    "code": "invalid_value",
                }
            },
        )
    )
    try:
        with pytest.raises(DecisionError, match="HTTP 400"):
            await provider.ask(
                {"a": DecisionBooleanQuestion("Ok?")}, "private-conversation"
            )
    finally:
        await provider.terminate()

    assert provider.client.is_closed
    assert "HTTP 400" in caplog.text
    assert "invalid_value" not in caplog.text
    assert "private-conversation" not in caplog.text
    assert "sk-test" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            httpx.Response(
                200, content=b"<html>bad</html>", headers={"Content-Type": "text/html"}
            ),
            "invalid JSON",
        ),
        (httpx.Response(200, content=b"\xff"), "text encoding"),
    ],
)
async def test_rejects_invalid_json(response, message):
    provider = _provider(lambda request: response)
    try:
        with pytest.raises(DecisionError, match=message):
            await provider.ask({"a": DecisionBooleanQuestion("Ok?")})
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (httpx.ReadTimeout("read timeout"), "timed out after 5s"),
        (httpx.ConnectError("connection refused"), "unable to connect"),
    ],
)
async def test_normalizes_network_errors(error, message):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    provider = _provider(handler)
    try:
        with pytest.raises(DecisionError, match=message):
            await provider.ask({"a": DecisionBooleanQuestion("Ok?")})
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_does_not_retry_by_default_and_test_never_retries():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": {"code": "unavailable"}})

    provider = _provider(handler)
    try:
        with pytest.raises(DecisionError, match="HTTP 503"):
            await provider.ask({"a": DecisionBooleanQuestion("Ok?")})
        with pytest.raises(DecisionError, match="HTTP 503"):
            await provider.test()
    finally:
        await provider.terminate()

    assert attempts == 2


@pytest.mark.asyncio
async def test_retries_retryable_errors_then_succeeds():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=_decision(_predicate("q0", 0.4)))

    provider = _provider(handler)
    try:
        answers = await provider.ask(
            {"a": DecisionBooleanQuestion("Ok?")}, request_max_retries=1
        )
    finally:
        await provider.terminate()

    assert attempts == 2
    assert answers["a"].probability == 0.4


@pytest.mark.asyncio
async def test_does_not_retry_client_errors():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400)

    provider = _provider(handler)
    try:
        with pytest.raises(DecisionError, match="HTTP 400"):
            await provider.ask(
                {"a": DecisionBooleanQuestion("Ok?")}, request_max_retries=3
            )
    finally:
        await provider.terminate()

    assert attempts == 1


@pytest.mark.asyncio
async def test_total_timeout_covers_queue_and_requests():
    async def post(*args, **kwargs):
        await asyncio.sleep(1)
        return httpx.Response(200, json=_decision(_predicate("q0", 1.0)))

    provider = _provider(
        lambda request: httpx.Response(500), total_timeout=0.05, max_concurrency=1
    )
    provider.client.post = AsyncMock(side_effect=post)
    try:
        first = asyncio.create_task(provider.ask({"a": DecisionBooleanQuestion("?")}))
        await asyncio.sleep(0)
        # The second call waits on the semaphore; its queue time counts too.
        with pytest.raises(DecisionError, match="total request timed out after 0.05s"):
            await provider.ask({"a": DecisionBooleanQuestion("Ok?")})
        with pytest.raises(DecisionError, match="total request timed out"):
            await first
    finally:
        await provider.terminate()

    assert not provider.request_semaphore.locked()


@pytest.mark.asyncio
async def test_cancellation_releases_concurrency_slot():
    started = asyncio.Event()
    calls = 0

    async def post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await asyncio.sleep(10)
        return httpx.Response(
            200,
            json=_decision(_predicate("q0", 1.0)),
            request=httpx.Request("POST", ENDPOINT),
        )

    provider = _provider(lambda request: httpx.Response(500), max_concurrency=1)
    provider.client.post = AsyncMock(side_effect=post)
    try:
        task = asyncio.create_task(provider.ask({"a": DecisionBooleanQuestion("?")}))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not provider.request_semaphore.locked()
        answers = await provider.ask({"a": DecisionBooleanQuestion("Again?")})
    finally:
        await provider.terminate()

    assert answers["a"].probability == 1.0


@pytest.mark.asyncio
async def test_limits_concurrent_requests():
    in_flight = 0
    peak = 0

    async def post(*args, **kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await asyncio.sleep(0.03)
            return httpx.Response(
                200,
                json=_decision(_predicate("q0", 1.0)),
                request=httpx.Request("POST", ENDPOINT),
            )
        finally:
            in_flight -= 1

    provider = _provider(lambda request: httpx.Response(500), max_concurrency=2)
    provider.client.post = AsyncMock(side_effect=post)
    try:
        await asyncio.gather(
            *(provider.ask({"a": DecisionBooleanQuestion("Ok?")}) for _ in range(6))
        )
    finally:
        await provider.terminate()

    assert peak == 2


@pytest.mark.asyncio
async def test_decision_service_end_to_end_through_adapter():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        question = body["questions"][0]
        if question["type"] == "choice":
            return httpx.Response(
                200,
                json=_decision(
                    {
                        "type": "choice",
                        "name": question["name"],
                        "choice": "o2",
                        "confidence": 0.5,
                        "probabilities": [
                            {"value": "o1", "probability": 0.3},
                            {"value": "o2", "probability": 0.7},
                        ],
                    }
                ),
            )
        if question["instructions"] == "Fail?":
            return httpx.Response(500)
        return httpx.Response(200, json=_decision(_predicate(question["name"], 0.6)))

    provider = _provider(handler)
    manager = _manager()
    manager.get_using_provider_async = AsyncMock(return_value=provider)
    service = DecisionService(manager)
    try:
        choice = await service.choose(
            "Which strategy?",
            {"short": "Brief reply", "detailed": "Detailed reply"},
            state=[{"role": "user", "content": "hello"}],
        )
        assert await service.yes_no("Reply?", threshold=0.6) is True
        assert await service.yes_no("Reply?", threshold=0.61) is False
        assert await service.yes_no("Fail?", default=True) is True
        with pytest.raises(DecisionError, match="HTTP 500"):
            await service.yes_no("Fail?")
    finally:
        await provider.terminate()

    assert choice == DecisionChoiceAnswer(
        choice="detailed",
        probability=0.7,
        probabilities={"short": 0.3, "detailed": 0.7},
        confidence=0.5,
    )
    assert bodies[0]["questions"][0]["choices"] == [
        {"value": "o1", "description": "Brief reply"},
        {"value": "o2", "description": "Detailed reply"},
    ]
    assert bodies[0]["input"][0]["content"][0]["type"] == "input_json"


def test_template_and_schema_expose_decision_settings():
    metadata = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
    template = metadata["config_template"]["OpenAI Decisions"]
    assert template["type"] == "openai_decision"
    assert template["provider_type"] == "decision"
    assert template["key"] == ""
    assert template["api_base"] == "https://api.openai.com/v1"
    assert template["model"] == "gpt-6-luna"
    items = metadata["items"]
    for field in ("total_timeout", "max_concurrency"):
        # System One keeps its original schema condition; the WebUI lifts it.
        assert items[field]["condition"] == {"type": "system_one_decision"}


def test_saved_config_keeps_single_string_key():
    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]["OpenAI Decisions"]
    payload = {"provider": [{**template, "key": "$OPENAI_API_KEY"}]}
    errors, saved = validate_config(payload, CONFIG_METADATA_2, is_core=True)
    assert errors == []
    assert saved["provider"][0]["key"] == "$OPENAI_API_KEY"


@pytest.mark.asyncio
async def test_provider_manager_loads_and_selects_openai_decision(monkeypatch):
    monkeypatch.setenv("ASTRBOT_TEST_OPENAI_DECISION_KEY", "sk-env")
    manager = _manager()
    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]["OpenAI Decisions"]

    await manager.load_provider(
        {**template, "id": "first", "key": "$ASTRBOT_TEST_OPENAI_DECISION_KEY"}
    )
    await manager.load_provider({**template, "id": "second", "key": ""})

    first = manager.inst_map["first"]
    second = manager.inst_map["second"]
    try:
        assert isinstance(first, OpenAIDecisionProvider)
        assert first.meta().provider_type == ProviderType.DECISION
        assert first.meta().model == "gpt-6-luna"
        assert first.client.headers["Authorization"] == "Bearer sk-env"
        assert "Authorization" not in second.client.headers
        assert manager.curr_decision_provider_inst is first
        await manager.set_provider("second", ProviderType.DECISION)
        assert await manager.get_using_provider_async(ProviderType.DECISION) is second
    finally:
        await manager.terminate_provider("first")
        await manager.terminate_provider("second")

    assert first.client.is_closed
    assert second.client.is_closed


@pytest.mark.asyncio
async def test_provider_manager_create_update_reload_and_connection_test(monkeypatch):
    class SavedConfig(dict):
        save_config = MagicMock()

    saved = SavedConfig(provider=[], provider_sources=[], provider_settings={})
    monkeypatch.setattr("astrbot.core.provider.manager.astrbot_config", saved)
    manager = _manager()
    manager.acm.default_conf = saved
    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]["OpenAI Decisions"]

    await manager.create_provider({**template, "key": "sk-a"})
    created = manager.inst_map["openai_decision"]
    assert SavedConfig.save_config.call_count == 1
    assert saved["provider"][0]["key"] == "sk-a"

    await manager.update_provider(
        "openai_decision",
        {**template, "key": "sk-b", "model": "gpt-6-luna-next", "total_timeout": 3},
    )
    reloaded = manager.inst_map["openai_decision"]
    try:
        assert created.client.is_closed
        assert reloaded is not created
        assert reloaded.model == "gpt-6-luna-next"
        assert reloaded.total_timeout == 3
        assert reloaded.client.headers["Authorization"] == "Bearer sk-b"
        assert manager.curr_decision_provider_inst is reloaded

        sent = []

        async def post(url, **kwargs):
            sent.append(json.loads(kwargs["content"]))
            return httpx.Response(
                200,
                json=_decision(_predicate("q0", 0.9)),
                request=httpx.Request("POST", url),
            )

        reloaded.client.post = AsyncMock(side_effect=post)
        await reloaded.test()
    finally:
        await manager.terminate_provider("openai_decision")

    assert sent[0]["model"] == "gpt-6-luna-next"
    assert sent[0]["questions"][0]["type"] == "predicate"


@pytest.mark.asyncio
async def test_unhashable_answer_name_is_a_contract_error():
    provider = _provider(
        lambda request: httpx.Response(
            200,
            json=_decision({"type": "predicate", "name": ["q0"], "probability": 0.5}),
        )
    )
    try:
        with pytest.raises(DecisionError, match="unknown or duplicate"):
            await provider.ask({"a": DecisionBooleanQuestion("Ok?")})
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "questions",
    [
        {},
        {f"h{index}": DecisionBooleanQuestion("Ok?") for index in range(401)},
        {"a": object()},
    ],
)
async def test_rejects_question_sets_the_api_cannot_express(questions):
    handler = MagicMock(side_effect=AssertionError("no request expected"))
    provider = _provider(handler)
    try:
        with pytest.raises(ValueError):
            await provider.ask(questions)
    finally:
        await provider.terminate()

    handler.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["authorization", "Authorization", "AUTHORIZATION"])
async def test_api_key_replaces_custom_authorization(header):
    captured = []

    def handler(request):
        captured.extend(request.headers.get_list("authorization"))
        return httpx.Response(200, json=_decision(_predicate("q0", 0.5)))

    provider = _provider(handler, custom_headers={header: "Bearer old"})
    try:
        await provider.ask({"a": DecisionBooleanQuestion("Ok?")})
    finally:
        await provider.terminate()
    assert captured == ["Bearer sk-test"]


@pytest.mark.parametrize("field", ["timeout", "total_timeout"])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_rejects_invalid_timeout_settings(field, value):
    with pytest.raises(ValueError, match=field):
        _provider(None, **{field: value})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"private": "sensitive-state"},
        _decision({"name": "sensitive-state"}),
        _decision({"name": "q0", "probability": "sensitive-state"}),
        _decision(),
    ],
)
async def test_invalid_response_does_not_expose_content(body, caplog):
    caplog.set_level(logging.WARNING, logger="astrbot")
    provider = _provider(lambda request: httpx.Response(200, json=body))
    try:
        with pytest.raises(DecisionError) as error:
            await provider.ask({"a": DecisionBooleanQuestion("Ok?")})
        assert "sensitive-state" not in str(error.value)
        assert "sensitive-state" not in caplog.text
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["status", "network", "timeout", "json"])
async def test_failure_logs_omit_urls_and_exception_content(failure, caplog):
    caplog.set_level(logging.WARNING, logger="astrbot")
    secret = "sensitive-credential"

    def handler(request):
        if failure == "network":
            raise httpx.ConnectError(secret)
        if failure == "timeout":
            raise httpx.ReadTimeout(secret)
        if failure == "json":
            return httpx.Response(200, content=secret.encode())
        return httpx.Response(503, json={"error": {"message": secret, "code": secret, "type": secret}})

    provider = _provider(
        handler,
        api_base=f"https://user:{secret}@api.openai.test/v1/decisions?token={secret}",
    )
    # Keep MockTransport active while exercising proxy diagnostics.
    provider.proxy = f"http://user:{secret}@proxy.test"
    try:
        with pytest.raises(DecisionError) as error:
            await provider.ask(
                {"a": DecisionBooleanQuestion("Ok?")}, request_max_retries=1
            )
        assert secret not in str(error.value)
        assert secret not in "".join(traceback.format_exception(error.value))
        assert secret not in caplog.text
        if failure != "json":
            assert "retrying" in caplog.text
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("distribution", "score", "accepted"),
    [
        ([0.0, 0.0, 1.0], 0.0, False),
        ([1.0, 0.0, 0.0], 2.0, False),
        ([0.2, 0.3, 0.5], 1.3, True),
        ([0.3333, 0.3333, 0.3333], 1.0, True),
        ([0.0, 0.0, 0.9999], 2.0, True),
        ([0.2, 0.3, 0.5], 1.3019, True),
        ([0.2, 0.3, 0.5], 1.3021, False),
        ([0.5, 0.5], 0.5009, True),
        ([0.5, 0.5], 0.5011, False),
        ([0.1] * 10, 4.5089, True),
        ([0.1] * 10, 4.5091, False),
    ],
)
async def test_score_matches_probability_weighted_levels(distribution, score, accepted):
    question = DecisionScoreQuestion(
        "Rate the impact", [f"Level {i}" for i in range(len(distribution))]
    )
    probabilities = [
        {"value": i, "label": str(i), "probability": probability}
        for i, probability in enumerate(distribution)
    ]
    provider = _provider(
        lambda request: httpx.Response(
            200,
            json=_decision(_score(score=score, probabilities=list(reversed(probabilities)))),
        )
    )
    try:
        if accepted:
            answer = (await provider.ask({"a": question}))["a"]
            assert answer.score == score
            assert answer.probabilities == {
                str(i): probability for i, probability in enumerate(distribution)
            }
        else:
            with pytest.raises(DecisionError, match="invalid score"):
                await provider.ask({"a": question})
    finally:
        await provider.terminate()
