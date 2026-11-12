import asyncio
import base64
import copy
import json
import logging
import traceback
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.decision import DecisionService
from astrbot.core.provider.entities import (
    DecisionBooleanAnswer,
    DecisionBooleanQuestion,
    DecisionChoiceAnswer,
    DecisionChoiceQuestion,
    DecisionError,
    DecisionInput,
    DecisionMedia,
    DecisionScoreAnswer,
    DecisionScoreQuestion,
    ProviderType,
)
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.sources.gemini_decision_source import GeminiDecisionProvider
from astrbot.dashboard.services.config_service import validate_config

ENDPOINT = "https://gemini.test/v1beta/decisions"
BOOLEAN = DecisionBooleanQuestion("Is it urgent?")
CHOICE = DecisionChoiceQuestion(
    "What should support do?", {"reply": "Reply", "wait": ""}
)
SCORE = DecisionScoreQuestion("How severe is it?", ["None", "Degraded", "Down"])
BOOL_ANSWER = {"type": "noul", "noul": 0.05, "confidence": 0.95}
CHOICE_ANSWER = {
    "type": "choice",
    "choice": "reply",
    "confidence": 0.8,
    "probabilities": {"reply": 0.8, "wait": 0.2},
}
SCORE_ANSWER = {
    "type": "score",
    "score": 1.35,
    "confidence": 0.45,
    "probabilities": {"2": 0.45, "0": 0.1, "1": 0.45},
    "legend": {"2": "Down", "0": "None", "1": "Degraded"},
}


@pytest_asyncio.fixture
async def provider_factory():
    """Create mock providers and close their clients after each test.

    Yields:
        A factory accepting an HTTP handler and provider configuration overrides.
    """
    providers = []

    def create(handler, **overrides):
        config = {
            "id": "gemini_decision_test",
            "type": "gemini_decision",
            "provider_type": "decision",
            "api_base": "https://gemini.test/v1beta",
            "model": "gemini-decision-1",
            "key": "test-key",
            "custom_headers": {"X-Test": "yes", "X-Goog-Api-Key": "old-key"},
        }
        config.update(overrides)
        provider = GeminiDecisionProvider(
            config, {}, transport=httpx.MockTransport(handler)
        )
        providers.append(provider)
        return provider

    try:
        yield create
    finally:
        for provider in providers:
            await provider.terminate()
            assert provider.client.is_closed


def _manager():
    config = {"provider": [], "provider_sources": [], "provider_settings": {}}
    acm = MagicMock()
    acm.confs = {"default": config}
    acm.get_conf.return_value = config
    persona_manager = MagicMock()
    persona_manager.default_persona = ""
    return ProviderManager(acm, MagicMock(), persona_manager)


@pytest.mark.asyncio
async def test_mixed_questions_match_names_and_preserve_answer_semantics(
    provider_factory,
):
    sent = []
    choice_criteria = dict(CHOICE.criteria)
    score_criteria = list(SCORE.criteria)
    questions = {
        "需要回复？": BOOLEAN,
        "action": DecisionChoiceQuestion(" Pick ", MappingProxyType(choice_criteria)),
        "severity": DecisionScoreQuestion(SCORE.instructions, score_criteria),
    }

    def handler(request):
        sent.append(request)
        choice_criteria.clear()
        score_criteria.clear()
        questions.clear()
        return httpx.Response(
            200,
            json={
                "answers": {
                    "q2": SCORE_ANSWER,
                    "q0": BOOL_ANSWER,
                    "q1": CHOICE_ANSWER,
                }
            },
        )

    provider = provider_factory(handler)
    answers = await provider.ask(
        questions,
        "The service is down.",
    )
    assert len(sent) == 1
    request = sent[0]
    assert str(request.url) == ENDPOINT
    assert request.headers["x-goog-api-key"] == "test-key"
    assert "authorization" not in request.headers
    assert request.headers["x-test"] == "yes"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "model": "gemini-decision-1",
        "input": "The service is down.",
        "questions": {
            "q0": {"type": "noul", "instructions": BOOLEAN.instructions},
            "q1": {
                "type": "choice",
                "instructions": "Pick",
                "criteria": CHOICE.criteria,
            },
            "q2": {
                "type": "score",
                "instructions": SCORE.instructions,
                "criteria": SCORE.criteria,
            },
        },
    }
    assert answers["需要回复？"] == DecisionBooleanAnswer(probability=0.05)
    assert answers["action"] == DecisionChoiceAnswer(
        "reply", 0.8, {"reply": 0.8, "wait": 0.2}, 0.8
    )
    assert answers["severity"] == DecisionScoreAnswer(
        1.35, SCORE_ANSWER["legend"], SCORE_ANSWER["probabilities"], 0.45
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        None,
        "",
        "中文",
        {},
        [],
        [1, "text"],
        {"role": "system", "type": "image", "image_url": "https://private.test/a"},
        [{"type": "text", "text": "Not a content block"}],
        [
            {
                "type": "image",
                "uri": "https://example.com/a.png",
                "mime_type": "image/png",
            }
        ],
    ],
)
async def test_state_remains_plain_text_or_business_json(provider_factory, state):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"answers": {"q0": BOOL_ANSWER}})

    provider = provider_factory(handler)
    await provider.ask({"answer": BOOLEAN}, state)
    value = sent[0]["input"]
    assert isinstance(value, str)
    if isinstance(state, (dict, list)):
        assert json.loads(value) == state
    else:
        assert value == (state or "{}")


@pytest.mark.asyncio
@pytest.mark.parametrize("state_kwargs", [{}, {"state": None}, {"state": ""}])
@pytest.mark.parametrize("method", ["ask", "choose", "yes_no"])
async def test_service_empty_context_works_with_gemini_input_requirement(
    provider_factory, state_kwargs, method
):
    def handler(request):
        body = json.loads(request.content)
        if not body["input"]:
            return httpx.Response(
                400,
                json={"error": {"message": "Missing text in content of type text."}},
            )
        question = body["questions"]["q0"]
        if question["type"] == "choice":
            answer = {
                "type": "choice",
                "choice": "o1",
                "confidence": 0.8,
                "probabilities": {"o1": 0.8, "o2": 0.2},
            }
        else:
            answer = BOOL_ANSWER
        return httpx.Response(200, json={"answers": {"q0": answer}})

    provider = provider_factory(handler)
    manager = _manager()
    manager.get_using_provider_async = AsyncMock(return_value=provider)
    service = DecisionService(manager)
    if method == "ask":
        answers = await service.ask({"answer": BOOLEAN}, **state_kwargs)
        assert answers["answer"].probability == 0.05
    elif method == "choose":
        answer = await service.choose("Pick", ["reply", "wait"], **state_kwargs)
        assert answer.choice == "reply"
    else:
        assert await service.yes_no("Urgent?", **state_kwargs) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [42, True, ("a",), [object()], {"x": float("nan")}, [float("inf")], "\ud800"],
)
async def test_invalid_state_never_sends_a_request(provider_factory, state):
    handler = MagicMock(side_effect=AssertionError("No request expected"))
    provider = provider_factory(handler)
    with pytest.raises(ValueError):
        await provider.ask({"answer": BOOLEAN}, state)
    handler.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        object(),
        DecisionBooleanQuestion(None),
        DecisionBooleanQuestion(" "),
        DecisionChoiceQuestion("Pick", None),
        DecisionChoiceQuestion("Pick", ["a", "b"]),
        DecisionChoiceQuestion("Pick", {"a": "one"}),
        DecisionChoiceQuestion("Pick", {str(i): "" for i in range(256)}),
        DecisionChoiceQuestion("Pick", {" a": "", "b": ""}),
        DecisionChoiceQuestion("Pick", {"a\n": "", "b": ""}),
        DecisionChoiceQuestion("Pick", {"a\x7fb": "", "b": ""}),
        DecisionChoiceQuestion("Pick", {"a" * 129: "", "b": ""}),
        DecisionChoiceQuestion("Pick", {"😀" * 129: "", "b": ""}),
        *[
            DecisionChoiceQuestion("Pick", {f"a{space}b": "", "b": ""})
            for space in ("\u00a0", "\u2003", "\u2028", "\u202f", "\u3000")
        ],
        *[
            DecisionChoiceQuestion("Pick", {f"a{char}b": "", "b": ""})
            for char in (
                "\u200b",
                "\u200d",
                "\u00ad",
                "\u202e",
                "\ue000",
                "\U000f0000",
                "\u0378",
                "\ufdd0",
                "\ud800",
            )
        ],
        DecisionChoiceQuestion("Pick", {"": "", "b": ""}),
        DecisionChoiceQuestion("Pick", {1: "", "1": ""}),
        DecisionChoiceQuestion("Pick", {"a": None, "b": ""}),
        DecisionScoreQuestion("Rate", "ab"),
        DecisionScoreQuestion("Rate", ["one"]),
        DecisionScoreQuestion("Rate", ["low", " "]),
        DecisionScoreQuestion("Rate", ["low", 1]),
        DecisionScoreQuestion("Rate", []),
        DecisionScoreQuestion("Rate", [str(i) for i in range(256)]),
    ],
)
async def test_invalid_questions_never_send_a_request(provider_factory, question):
    handler = MagicMock(side_effect=AssertionError("No request expected"))
    provider = provider_factory(handler)
    with pytest.raises(ValueError):
        await provider.ask({"answer": question})
    handler.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 1000, 1001])
async def test_question_count_boundaries(provider_factory, count):
    def handler(request):
        payload = json.loads(request.content)
        assert len(payload["questions"]) == count
        return httpx.Response(
            200, json={"answers": dict.fromkeys(payload["questions"], BOOL_ANSWER)}
        )

    transport = MagicMock(side_effect=handler)
    provider = provider_factory(transport)
    questions = dict.fromkeys((str(i) for i in range(count)), BOOLEAN)
    if 1 <= count <= 1000:
        assert set(await provider.ask(questions)) == set(questions)
        transport.assert_called_once()
    else:
        with pytest.raises(ValueError):
            await provider.ask(questions)
        transport.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("option_id", "count"),
    [
        pytest.param("a", 2, id="single-character"),
        pytest.param("a" * 128, 2, id="max-ascii-id"),
        pytest.param("😀" * 128, 2, id="max-utf8-id"),
        pytest.param("a b", 2, id="ascii-space"),
        pytest.param("中文", 2, id="unicode"),
        pytest.param("e\u0301", 2, id="combining-mark"),
        pytest.param("❤\ufe0f", 2, id="variation-selector"),
        pytest.param("😀" * 128, 255, id="max-options-and-utf8-id"),
    ],
)
async def test_valid_choice_id_and_count_boundaries(provider_factory, option_id, count):
    criteria = {option_id: "First", **{f"other{i}": "" for i in range(count - 1)}}

    def handler(request):
        assert json.loads(request.content)["questions"]["q0"]["criteria"] == criteria
        return httpx.Response(
            200,
            json={
                "answers": {
                    "q0": {
                        "type": "choice",
                        "choice": option_id,
                        "confidence": 1.0,
                        "probabilities": {
                            key: float(key == option_id) for key in criteria
                        },
                    }
                }
            },
        )

    provider = provider_factory(handler)
    answers = await provider.ask({"answer": DecisionChoiceQuestion("Pick", criteria)})
    assert answers["answer"].choice == option_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("probabilities", "choice", "valid"),
    [
        ({"b": 0.5, "a": 0.5}, "a", True),
        ({"b": 0.5, "a": 0.5}, "b", False),
        ({"a": 0.5004, "b": 0.4996}, "a", True),
        ({"a": 0.5004, "b": 0.4996}, "b", False),
        ({"😀": 0.5, "中": 0.5}, "中", True),
        ({"😀": 0.5, "中": 0.5}, "😀", False),
        (
            {"billing": 0.99, "shipping": 0.004, "other": 0.003, "technical": 0.002},
            "billing",
            True,
        ),
    ],
)
async def test_choice_winner_matches_maximum_and_utf8_tie_order(
    provider_factory, probabilities, choice, valid
):
    provider = provider_factory(
        lambda request: httpx.Response(
            200,
            json={
                "answers": {
                    "q0": {
                        "type": "choice",
                        "choice": choice,
                        "probabilities": probabilities,
                        "confidence": max(probabilities.values()),
                    }
                }
            },
        )
    )
    questions = {
        "answer": DecisionChoiceQuestion("Pick", dict.fromkeys(probabilities, ""))
    }
    if valid:
        assert (await provider.ask(questions))["answer"].choice == choice
    else:
        with pytest.raises(DecisionError, match="invalid choice"):
            await provider.ask(questions)


@pytest.mark.asyncio
@pytest.mark.parametrize("probability", [0, 0.009999, 0.01, 0.99, 0.990001, 1])
async def test_noul_probability_boundaries(provider_factory, probability):
    provider = provider_factory(
        lambda request: httpx.Response(
            200,
            json={
                "answers": {
                    "q0": {
                        "type": "noul",
                        "noul": probability,
                        "confidence": max(probability, 1 - probability),
                    }
                }
            },
        )
    )
    if 0.01 <= probability <= 0.99:
        assert (await provider.ask({"answer": BOOLEAN}))[
            "answer"
        ].probability == probability
    else:
        with pytest.raises(DecisionError, match="invalid boolean"):
            await provider.ask({"answer": BOOLEAN})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "safety",
        "prohibited_content",
        "blocklist",
        "image_safety",
        "content_blocked",
    ],
)
async def test_http_safety_blocks_whole_batch_without_leaking_input(
    provider_factory, code, caplog
):
    private_state = "private-context"
    handler = MagicMock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "code": code,
                    "message": "test-key private-context",
                }
            },
        )
    )
    provider = provider_factory(handler)
    caplog.set_level(logging.WARNING, logger="astrbot")
    with pytest.raises(DecisionError, match="blocked") as exc:
        await provider.ask(
            {"a": BOOLEAN, "b": CHOICE}, private_state, request_max_retries=2
        )
    handler.assert_called_once()
    output = caplog.text + "".join(traceback.format_exception(exc.value))
    assert "private-context" not in output and "test-key" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},
        [],
        {"error": None},
        {"error": []},
        {"error": {"code": []}},
        {"error": {"code": "unknown"}},
    ],
)
async def test_other_bad_requests_remain_http_errors(provider_factory, body):
    provider = provider_factory(lambda request: httpx.Response(400, json=body))
    with pytest.raises(DecisionError, match="HTTP 400"):
        await provider.ask({"answer": BOOLEAN})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "answer", "changes"),
    [
        (BOOLEAN, BOOL_ANSWER, {"type": "predicate"}),
        (BOOLEAN, BOOL_ANSWER, {"noul": True}),
        (BOOLEAN, BOOL_ANSWER, {"noul": -0.1}),
        (BOOLEAN, BOOL_ANSWER, {"noul": None}),
        (BOOLEAN, BOOL_ANSWER, {"confidence": 0.05}),
        (BOOLEAN, BOOL_ANSWER, {"confidence": float("nan")}),
        (BOOLEAN, BOOL_ANSWER, {"noul": 10**400}),
        (CHOICE, CHOICE_ANSWER, {"choice": "wait"}),
        (CHOICE, CHOICE_ANSWER, {"choice": ["reply"]}),
        (CHOICE, CHOICE_ANSWER, {"confidence": 0.7}),
        (CHOICE, CHOICE_ANSWER, {"probabilities": {"reply": 1.0}}),
        (CHOICE, CHOICE_ANSWER, {"probabilities": {"reply": 0.8, "other": 0.2}}),
        (CHOICE, CHOICE_ANSWER, {"probabilities": {"reply": 0.8, "wait": 0.3}}),
        (CHOICE, CHOICE_ANSWER, {"probabilities": {"reply": True, "wait": 0}}),
        (CHOICE, CHOICE_ANSWER, {"probabilities": [0.8, 0.2]}),
        (
            CHOICE,
            CHOICE_ANSWER,
            {"probabilities": {"reply": float("inf"), "wait": 0.2}},
        ),
        (SCORE, SCORE_ANSWER, {"score": 1.0}),
        (SCORE, SCORE_ANSWER, {"score": True}),
        (SCORE, SCORE_ANSWER, {"score": 2.1}),
        (SCORE, SCORE_ANSWER, {"score": float("nan")}),
        (SCORE, SCORE_ANSWER, {"score": 10**400}),
        (SCORE, SCORE_ANSWER, {"legend": {"0": "Wrong", "1": "Degraded", "2": "Down"}}),
        (SCORE, SCORE_ANSWER, {"legend": None}),
        (SCORE, SCORE_ANSWER, {"probabilities": {"1": 0.5, "2": 0.5}}),
        (SCORE, SCORE_ANSWER, {"confidence": 0.8}),
    ],
)
async def test_rejects_invalid_answer_contract(
    provider_factory, question, answer, changes
):
    # Raw JSON exercises non-finite numbers from non-conforming gateways.
    provider = provider_factory(
        lambda request: httpx.Response(
            200,
            content=json.dumps({"answers": {"q0": {**answer, **changes}}}),
        )
    )
    with pytest.raises(DecisionError, match="invalid"):
        await provider.ask({"answer": question})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        [],
        {},
        {"answers": []},
        {"answers": {}},
        {"answers": {"q0": BOOL_ANSWER, "extra": BOOL_ANSWER}},
        {"answers": {"q0": None}},
        {"answers": {"q0": {"type": "UNKNOWN"}}},
        {"answers": {"q0": BOOL_ANSWER}, "prompt_feedback": "invalid"},
    ],
)
async def test_rejects_incomplete_or_malformed_batches(provider_factory, body):
    provider = provider_factory(lambda request: httpx.Response(200, json=body))
    with pytest.raises(DecisionError):
        await provider.ask({"answer": BOOLEAN})


@pytest.mark.asyncio
async def test_content_filter_blocks_whole_batch_without_leaking_input(
    provider_factory, caplog
):
    provider = provider_factory(
        lambda request: httpx.Response(
            200,
            json={
                "answers": {"q0": BOOL_ANSWER},
                "prompt_feedback": {
                    "block_reason": "safety",
                    "block_reason_message": "private-context",
                },
            },
        )
    )
    caplog.set_level(logging.WARNING, logger="astrbot")
    with pytest.raises(DecisionError, match="blocked") as exc:
        await provider.ask({"a": BOOLEAN, "b": CHOICE}, "private-context")
    assert "private-context" not in str(exc.value) + caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("", "https://generativelanguage.googleapis.com/v1beta/decisions"),
        ("https://gemini.test/v1beta/", ENDPOINT),
        (ENDPOINT + "/", ENDPOINT),
        ("https://gemini.test/v1beta?route=x", ENDPOINT + "?route=x"),
    ],
)
async def test_endpoint_preserves_custom_route(provider_factory, base, expected):
    def handler(request):
        assert str(request.url) == expected
        return httpx.Response(200, json={"answers": {"q0": BOOL_ANSWER}})

    provider = provider_factory(handler, api_base=base)
    await provider.ask({"q": BOOLEAN})


@pytest.mark.parametrize(
    "overrides",
    [
        {"model": ""},
        {"key": ["a"]},
        {"timeout": 0},
        {"timeout": float("inf")},
        {"total_timeout": float("nan")},
        {"total_timeout": -1},
        {"max_concurrency": 0},
    ],
)
@pytest.mark.asyncio
async def test_rejects_invalid_configuration(provider_factory, overrides):
    with pytest.raises(ValueError):
        provider_factory(lambda request: httpx.Response(500), **overrides)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
async def test_http_errors_and_connection_test_do_not_retry_by_default(
    provider_factory, status, caplog
):
    private_state = "private-context"
    handler = MagicMock(
        return_value=httpx.Response(status, text="test-key private-context")
    )
    provider = provider_factory(handler)
    caplog.set_level(logging.WARNING, logger="astrbot")
    with pytest.raises(DecisionError, match=f"HTTP {status}") as exc:
        await provider.ask({"answer": BOOLEAN}, private_state)
    with pytest.raises(DecisionError):
        await provider.test()
    assert handler.call_count == 2
    output = caplog.text + "".join(traceback.format_exception(exc.value))
    assert "test-key" not in output
    assert "private-context" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("private-context"), httpx.ConnectError("test-key")]
)
async def test_normalizes_network_errors_without_leaking_details(
    provider_factory, error
):
    provider = provider_factory(MagicMock(side_effect=error))
    with pytest.raises(DecisionError) as exc:
        await provider.ask({"answer": BOOLEAN})
    output = "".join(traceback.format_exception(exc.value))
    assert "test-key" not in output and "private-context" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"not json", b"\xff"])
async def test_invalid_json_is_a_decision_error(provider_factory, body):
    provider = provider_factory(lambda request: httpx.Response(200, content=body))
    with pytest.raises(DecisionError, match="invalid JSON"):
        await provider.ask({"answer": BOOLEAN})


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "attempts"), [(503, 2), (400, 1)])
async def test_explicit_retries_only_retry_transient_errors(
    provider_factory, status, attempts
):
    handler = MagicMock(
        side_effect=[
            httpx.Response(status),
            httpx.Response(200, json={"answers": {"q0": BOOL_ANSWER}}),
        ]
    )
    provider = provider_factory(handler)
    if status == 503:
        assert (await provider.ask({"answer": BOOLEAN}, request_max_retries=1))[
            "answer"
        ].probability == 0.05
    else:
        with pytest.raises(DecisionError):
            await provider.ask({"answer": BOOLEAN}, request_max_retries=1)
    assert handler.call_count == attempts


@pytest.mark.asyncio
async def test_queue_timeout_and_cancellation_release_slots(provider_factory):
    started = asyncio.Event()
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await asyncio.Event().wait()
        return httpx.Response(200, json={"answers": {"q0": BOOL_ANSWER}})

    provider = provider_factory(handler, max_concurrency=1, total_timeout=1)
    running = asyncio.create_task(provider.ask({"answer": BOOLEAN}))
    try:
        await asyncio.wait_for(started.wait(), 1)
        provider.total_timeout = 0.02
        with pytest.raises(DecisionError, match="total request timed out"):
            await provider.ask({"answer": BOOLEAN})
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert not provider.request_semaphore.locked()
        assert (await provider.ask({"answer": BOOLEAN}))["answer"].probability == 0.05
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)


@pytest.mark.asyncio
async def test_inflight_timeout_releases_slot(provider_factory):
    async def handler(request):
        await asyncio.Event().wait()

    provider = provider_factory(handler, total_timeout=0.02, max_concurrency=1)
    with pytest.raises(DecisionError, match="total request timed out"):
        await provider.ask({"answer": BOOLEAN})
    assert not provider.request_semaphore.locked()


@pytest.mark.asyncio
async def test_concurrency_limit(provider_factory):
    in_flight = 0
    peak = 0

    async def handler(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await asyncio.sleep(0.01)
            return httpx.Response(200, json={"answers": {"q0": BOOL_ANSWER}})
        finally:
            in_flight -= 1

    provider = provider_factory(handler, max_concurrency=2)
    await asyncio.gather(*(provider.ask({"answer": BOOLEAN}) for _ in range(6)))
    assert peak == 2


@pytest.mark.asyncio
async def test_service_choose_thresholds_and_fallback(provider_factory):
    def handler(request):
        question = json.loads(request.content)["questions"]["q0"]
        if question["instructions"] == "Fail?":
            return httpx.Response(503)
        if question["type"] == "choice":
            answer = {
                "type": "choice",
                "choice": "o2",
                "confidence": 0.7,
                "probabilities": {"o1": 0.3, "o2": 0.7},
            }
        else:
            answer = BOOL_ANSWER
        return httpx.Response(200, json={"answers": {"q0": answer}})

    provider = provider_factory(handler)
    manager = _manager()
    manager.get_using_provider_async = AsyncMock(return_value=provider)
    service = DecisionService(manager)
    choice = await service.choose("Pick", {"short": "Brief", "long": "Detailed"})
    assert choice.choice == "long"
    assert choice.probabilities == {"short": 0.3, "long": 0.7}
    assert await service.yes_no("Urgent?") is False
    assert await service.yes_no("Urgent?", threshold=0.05) is True
    assert await service.yes_no("Fail?", default=True) is True
    with pytest.raises(DecisionError):
        await service.yes_no("Fail?")


@pytest.mark.asyncio
async def test_template_config_save_manager_reload_and_test(monkeypatch):
    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]["Gemini Decisions"]
    assert template["model"] == "gemini-decision-1"
    assert template["api_base"] == "https://generativelanguage.googleapis.com/v1beta"
    assert template["provider"] == "google"
    monkeypatch.setenv("ASTRBOT_TEST_GEMINI_DECISION_KEY", "env-key")
    errors, validated = validate_config(
        {"provider": [{**template, "key": "$ASTRBOT_TEST_GEMINI_DECISION_KEY"}]},
        CONFIG_METADATA_2,
        is_core=True,
    )
    assert errors == []
    assert validated["provider"][0]["key"] == "$ASTRBOT_TEST_GEMINI_DECISION_KEY"

    class SavedConfig(dict):
        save_config = MagicMock()

    saved = SavedConfig(provider=[], provider_sources=[], provider_settings={})
    monkeypatch.setattr("astrbot.core.provider.manager.astrbot_config", saved)
    manager = _manager()
    manager.acm.default_conf = saved
    await manager.create_provider(copy.deepcopy(validated["provider"][0]))
    first = manager.inst_map["gemini_decision"]
    try:
        assert isinstance(first, GeminiDecisionProvider)
        assert first.client.headers["x-goog-api-key"] == "env-key"
        assert first.meta().provider_type == ProviderType.DECISION
        assert manager.curr_decision_provider_inst is first
        await manager.update_provider("gemini_decision", {**template, "key": "new-key"})
        current = manager.inst_map["gemini_decision"]
        assert first.client.is_closed
        assert current.client.headers["x-goog-api-key"] == "new-key"
        assert await manager.get_using_provider_async(ProviderType.DECISION) is current
        current.client.post = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"answers": {"q0": BOOL_ANSWER}},
                request=httpx.Request("POST", ENDPOINT),
            )
        )
        await current.test()
        sent = json.loads(current.client.post.call_args.kwargs["content"])
        assert sent["questions"]["q0"]["type"] == "noul"
        assert sent["input"] == "{}"
    finally:
        await manager.terminate_provider("gemini_decision")
    assert current.client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "mime"),
    [
        ("image", "image/png"),
        ("audio", "audio/wav"),
        ("video", "video/mp4"),
        ("document", "application/pdf"),
    ],
)
@pytest.mark.parametrize("source", ["data", "uri"])
async def test_explicit_media_preserves_wire_blocks_and_order(
    provider_factory, kind, mime, source
):
    media_value = "AA==" if source == "data" else "https://example.com/media"
    media = DecisionMedia(type=kind, mime_type=mime, **{source: media_value})
    state = DecisionInput(content=["Context:\n", media, "\nEnd."])
    original = copy.deepcopy(state)

    def handler(request):
        assert json.loads(request.content)["input"] == [
            {"type": "text", "text": "Context:\n"},
            {"type": kind, "mime_type": mime, source: media_value},
            {"type": "text", "text": "\nEnd."},
        ]
        return httpx.Response(200, json={"answers": {"q0": BOOL_ANSWER}})

    provider = provider_factory(handler)
    await provider.ask({"answer": BOOLEAN}, state)
    assert state == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "resolution"),
    [
        ("image", "low"),
        ("image", "medium"),
        ("image", "high"),
        ("image", "ultra_high"),
        ("video", "low"),
        ("video", "medium"),
        ("video", "high"),
    ],
)
async def test_media_resolution_is_forwarded(provider_factory, kind, resolution):
    mime = "image/jpeg" if kind == "image" else "video/mp4"

    def handler(request):
        assert json.loads(request.content)["input"][0]["resolution"] == resolution
        return httpx.Response(200, json={"answers": {"q0": BOOL_ANSWER}})

    provider = provider_factory(handler)
    await provider.ask(
        {"q": BOOLEAN},
        DecisionInput([DecisionMedia(kind, mime, data="AA==", resolution=resolution)]),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "message"),
    [
        (DecisionInput([]), "non-empty content list"),
        (DecisionInput("text"), "non-empty content list"),
        (DecisionInput(None), "non-empty content list"),
        (DecisionInput([""]), "text must not be empty"),
        (DecisionInput([{}]), "text or DecisionMedia"),
        (
            DecisionInput([{"type": "image", "uri": "https://example.com/a"}]),
            "text or DecisionMedia",
        ),
        (DecisionInput([42]), "text or DecisionMedia"),
        (DecisionInput(["\ud800"]), "request is not JSON serializable"),
        (
            DecisionInput([DecisionMedia("image", "image/png")]),
            "exactly one of data or uri",
        ),
        (
            DecisionInput(
                [
                    DecisionMedia(
                        "image",
                        "image/png",
                        data="AA==",
                        uri="https://example.com/private-context",
                    )
                ]
            ),
            "exactly one of data or uri",
        ),
        (
            DecisionInput([DecisionMedia("image", "image/png", data="")]),
            "non-empty base64",
        ),
        (
            DecisionInput(
                [DecisionMedia("image", "image/png", data="private-context!")]
            ),
            "valid base64",
        ),
        (
            DecisionInput([DecisionMedia("image", "image/png", data=b"AA==")]),
            "non-empty base64",
        ),
        (
            DecisionInput([DecisionMedia("image", "image/png", uri="")]),
            "non-empty HTTPS URI",
        ),
        (
            DecisionInput(
                [DecisionMedia("image", "image/png", uri="file:///private-context")]
            ),
            "requires an HTTPS URI",
        ),
        (
            DecisionInput(
                [DecisionMedia("image", "image/png", uri="gs://bucket/a.png")]
            ),
            "requires an HTTPS URI",
        ),
        (
            DecisionInput(
                [DecisionMedia("image", "image/png", uri="http://example.com/a.png")]
            ),
            "requires an HTTPS URI",
        ),
        (
            DecisionInput(
                [
                    DecisionMedia(
                        "image",
                        "image/png",
                        uri="https://example.com:bad/private-context",
                    )
                ]
            ),
            "valid HTTPS URI",
        ),
        (
            DecisionInput([DecisionMedia("image", "audio/wav", data="AA==")]),
            "media MIME type",
        ),
        (
            DecisionInput(
                [DecisionMedia("document", "application/octet-stream", data="AA==")]
            ),
            "media MIME type",
        ),
        (
            DecisionInput([DecisionMedia("thought", "image/png", data="AA==")]),
            "media MIME type",
        ),
        (
            DecisionInput(
                [DecisionMedia("audio", "audio/wav", data="AA==", resolution="low")]
            ),
            "media resolution",
        ),
        (
            DecisionInput(
                [
                    DecisionMedia(
                        "document", "application/pdf", data="AA==", resolution="low"
                    )
                ]
            ),
            "media resolution",
        ),
        (
            DecisionInput(
                [
                    DecisionMedia(
                        "video", "video/mp4", data="AA==", resolution="ultra_high"
                    )
                ]
            ),
            "media resolution",
        ),
        (
            DecisionInput(
                [DecisionMedia("image", "image/png", data="AA==", resolution="unknown")]
            ),
            "media resolution",
        ),
        (
            [DecisionMedia("image", "image/png", data="AA==")],
            "state is not JSON serializable",
        ),
        (
            {"content": [DecisionMedia("image", "image/png", data="AA==")]},
            "state is not JSON serializable",
        ),
        (
            DecisionInput([DecisionMedia([], "image/png", data="AA==")]),
            "media MIME type",
        ),
        (DecisionInput([DecisionMedia("image", [], data="AA==")]), "media MIME type"),
        ({"private-context": object()}, "state is not JSON serializable"),
    ],
)
async def test_invalid_input_is_rejected_without_exposing_data(
    provider_factory, state, message, caplog
):
    handler = MagicMock(side_effect=AssertionError("No request expected"))
    provider = provider_factory(handler)
    with pytest.raises(ValueError, match=message) as error:
        await provider.ask({"q": BOOLEAN}, state)
    handler.assert_not_called()
    assert "private-context" not in str(error.value) + caplog.text
    assert error.value.__suppress_context__ or error.value.__context__ is None


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["ask", "choose", "yes_no"])
async def test_service_forwards_explicit_input(provider_factory, method):
    from astrbot.api.provider import (
        DecisionInput as PublicInput,
    )
    from astrbot.api.provider import (
        DecisionMedia as PublicMedia,
    )

    state = PublicInput(
        ["Photo:", PublicMedia("image", "image/png", uri="https://example.com/a.png")]
    )

    def handler(request):
        payload = json.loads(request.content)
        assert payload["input"][1]["type"] == "image"
        question = payload["questions"]["q0"]
        answer = (
            BOOL_ANSWER
            if question["type"] == "noul"
            else {
                "type": "choice",
                "choice": "o1",
                "confidence": 0.8,
                "probabilities": {"o1": 0.8, "o2": 0.2},
            }
        )
        return httpx.Response(200, json={"answers": {"q0": answer}})

    provider = provider_factory(handler)
    manager = _manager()
    manager.get_using_provider_async = AsyncMock(return_value=provider)
    service = DecisionService(manager)
    if method == "ask":
        assert (await service.ask({"q": BOOLEAN}, state))["q"].probability == 0.05
    elif method == "choose":
        assert (await service.choose("Pick", ["A", "B"], state=state)).choice == "A"
    else:
        assert await service.yes_no("Is it true?", state=state) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "document"])
@pytest.mark.parametrize("size", [3, 4])
async def test_inline_media_size_limits(provider_factory, monkeypatch, kind, size):
    from astrbot.core.provider.sources import gemini_decision_source

    monkeypatch.setattr(gemini_decision_source, "_MAX_INLINE_MEDIA_BYTES", 6)
    monkeypatch.setattr(gemini_decision_source, "_MAX_INLINE_PDF_BYTES", 3)
    media = DecisionMedia(
        kind,
        "image/png" if kind == "image" else "application/pdf",
        data=base64.b64encode(b"x" * size).decode("ascii"),
    )
    state = DecisionInput([media, media] if kind == "image" else [media])
    handler = MagicMock(
        return_value=httpx.Response(200, json={"answers": {"q0": BOOL_ANSWER}})
    )
    provider = provider_factory(handler)
    if size == 4:
        with pytest.raises(ValueError, match="exceeds"):
            await provider.ask({"q": BOOLEAN}, state)
        handler.assert_not_called()
    else:
        assert (await provider.ask({"q": BOOLEAN}, state))["q"].probability == 0.05


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [2, 10, 11, 255])
@pytest.mark.parametrize("score_error", [0, 0.0005, 0.002])
async def test_score_levels_and_expectation_at_extended_boundaries(
    provider_factory, count, score_error
):
    criteria = [f"Level {i}" for i in range(count)]

    def handler(request):
        assert json.loads(request.content)["questions"]["q0"]["criteria"] == criteria
        return httpx.Response(
            200,
            json={
                "answers": {
                    "q0": {
                        "type": "score",
                        "score": (0.25 + score_error) * (count - 1),
                        "confidence": 0.75,
                        "legend": {str(i): s for i, s in enumerate(criteria)},
                        "probabilities": {
                            str(i): (0.75 if i == 0 else 0.25 if i == count - 1 else 0)
                            for i in range(count)
                        },
                    }
                }
            },
        )

    provider = provider_factory(handler)
    if score_error > 0.001:
        with pytest.raises(DecisionError):
            await provider.ask({"q": DecisionScoreQuestion("Rate", criteria)})
    else:
        answer = (await provider.ask({"q": DecisionScoreQuestion("Rate", criteria)}))[
            "q"
        ]
        assert answer.score == (0.25 + score_error) * (count - 1)
        assert len(answer.legend) == count
        assert len(answer.probabilities) == count
