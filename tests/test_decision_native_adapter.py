import asyncio
import copy
import json
from types import MappingProxyType

import httpx
import pytest

from astrbot.core.provider.entities import (
    DecisionBooleanQuestion,
    DecisionChoiceQuestion,
    DecisionContent,
    DecisionError,
    DecisionInput,
    DecisionRefusalAnswer,
    DecisionResult,
    DecisionScoreQuestion,
)
from astrbot.core.provider.sources.openai_decision_source import OpenAIDecisionProvider
from astrbot.core.provider.sources.system_one_decision_source import (
    SystemOneDecisionProvider,
)


def provider(handler, **overrides):
    config = {
        "id": "decisions",
        "type": "openai_decision",
        "api_base": "https://compatible.test/prefix/v1",
        "model": "vendor-arbitrary",
        "key": ["test-key"],
        "custom_headers": {"X-Tenant": "tenant"},
    }
    config.update(overrides)
    return OpenAIDecisionProvider(config, {}, transport=httpx.MockTransport(handler))


def response(request):
    body = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            "model": body["model"],
            "answers": [
                {"type": "predicate", "name": q["name"], "probability": 0.7}
                for q in body["questions"]
            ],
            "usage": {"input_tokens": 4, "output_tokens": 0, "total_tokens": 4},
        },
        headers={"x-request-id": "req-test"},
    )


@pytest.mark.asyncio
async def test_native_directory_and_manual_unknown_model_preserve_base_and_headers():
    seen = []

    def handler(request):
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "z"},
                        {"id": "a"},
                        {"id": "a"},
                        {"id": ""},
                        {"id": 3},
                    ]
                },
            )
        return response(request)

    p = provider(handler, model="")
    try:
        assert await p.get_models() == ["a", "z"]
        with pytest.raises(ValueError, match="model"):
            await p.ask({"ok": DecisionBooleanQuestion("Available?")})
        p.set_model("unlisted-model")
        result = await p.ask({"ok": DecisionBooleanQuestion("Available?")})
        assert isinstance(result, DecisionResult)
        assert result["ok"].probability == 0.7
        assert result.usage.output_tokens == 0
        assert result.usage.cached_tokens is None
        assert result.request_id == "req-test"
        with pytest.raises(TypeError):
            result.answers["other"] = result["ok"]
        with pytest.raises((AttributeError, TypeError)):
            result.model = "changed"
        assert [str(r.url) for r in seen] == [
            "https://compatible.test/prefix/v1/models",
            "https://compatible.test/prefix/v1/decisions",
        ]
        assert all(r.headers["authorization"] == "Bearer test-key" for r in seen)
        assert all(r.headers["x-tenant"] == "tenant" for r in seen)
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_typed_answers_refusal_fractional_score_and_usage():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "vendor-arbitrary",
                "answers": [
                    {"name": "flag", "type": "predicate", "probability": 0.2},
                    {
                        "name": "pick",
                        "type": "choice",
                        "choice": True,
                        "confidence": 0.8,
                        "probabilities": [
                            {"value": True, "probability": 0.4},
                            {"value": "true", "probability": 0.6},
                        ],
                    },
                    {
                        "name": "severity",
                        "type": "score",
                        "score": 0.25,
                        "confidence": 0.9,
                        "probabilities": [
                            {"value": 0, "label": "low", "probability": 0.75},
                            {"value": 1, "label": "high", "probability": 0.25},
                        ],
                    },
                    {"name": "blocked", "type": "refusal"},
                ],
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {
                        "cached_tokens": 3,
                        "cache_write_tokens": 4,
                    },
                    "output_tokens": 0,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 10,
                },
            },
        )

    p = provider(handler)
    try:
        result = await p.ask(
            {
                "flag": DecisionBooleanQuestion("Flag?"),
                "pick": DecisionChoiceQuestion(
                    "Pick", {True: "Boolean", "true": "String"}
                ),
                "severity": DecisionScoreQuestion("Severity", ["low", "high"]),
                "blocked": DecisionBooleanQuestion("Blocked?"),
            }
        )
        assert result["pick"].choice is True
        assert result["pick"].probability == 0.4
        assert result["severity"].score == 0.25
        assert isinstance(result["blocked"], DecisionRefusalAnswer)
        assert result.usage.total_tokens == 10
        assert result.usage.cache_write_tokens == 4
        assert result.attempt_usages == (result.usage,)
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_business_json_and_explicit_multimodal_tool_history_are_distinct():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return response(request)

    p = provider(
        handler, custom_extra_body={"prompt_cache_options": {"mode": "explicit"}}
    )
    business = [{"role": "user", "content": "business data"}]
    native = DecisionInput(
        [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": "rules",
                        "prompt_cache_breakpoint": {"mode": "explicit"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": "https://a.test/x.png"}
                ],
            },
            {
                "type": "function_call",
                "call_id": "f",
                "name": "tool",
                "arguments": "{}",
            },
            {"type": "function_call_output", "call_id": "f", "output": "yes"},
            {"type": "custom_tool_call", "call_id": "c", "name": "tool", "input": "a"},
            {"type": "custom_tool_call_output", "call_id": "c", "output": "yes"},
        ]
    )
    original = copy.deepcopy(native.items)
    try:
        await p.ask({"ok": DecisionBooleanQuestion("ok")}, business)
        question = DecisionContent(
            [{"type": "input_image", "image_url": "data:image/png;base64,YQ=="}]
        )
        await p.ask({"ok": DecisionBooleanQuestion(question)}, native)
        assert seen[0]["input"] == [
            {"role": "user", "content": [{"type": "input_json", "data": business}]}
        ]
        assert seen[1]["input"] == original
        assert native.items == original
        assert seen[1]["questions"][0]["instructions"] == question.parts
    finally:
        await p.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 405, 501])
async def test_failed_directory_does_not_prevent_manual_ask_or_fallback(status):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return (
            httpx.Response(status, json={"error": "secret prompt"})
            if request.method == "GET"
            else response(request)
        )

    p = provider(handler)
    try:
        with pytest.raises(DecisionError, match=f"HTTP {status}"):
            await p.get_models()
        assert (await p.ask({"ok": DecisionBooleanQuestion("ok")}))[
            "ok"
        ].probability == 0.7
        assert seen == ["/prefix/v1/models", "/prefix/v1/decisions"]
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_question_boundaries_and_invalid_input_do_not_send():
    seen = []

    def handler(request):
        seen.append(request)
        return response(request)

    p = provider(handler)
    try:
        await p.ask({str(i): DecisionBooleanQuestion("ok") for i in range(400)})
        for questions, state in [
            ({}, None),
            ({str(i): DecisionBooleanQuestion("ok") for i in range(401)}, None),
            (
                {"ok": DecisionBooleanQuestion("ok")},
                DecisionInput(
                    [
                        {
                            "type": "function_call_output",
                            "call_id": "missing",
                            "output": "x",
                        }
                    ]
                ),
            ),
            (
                {
                    "ok": DecisionBooleanQuestion(
                        DecisionContent(
                            [
                                {
                                    "type": "input_text",
                                    "text": "x",
                                    "prompt_cache_breakpoint": {"mode": "explicit"},
                                }
                            ]
                        )
                    )
                },
                None,
            ),
        ]:
            with pytest.raises(ValueError):
                await p.ask(questions, state)
        assert len(seen) == 1
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_queue_timeout_cancellation_and_close_release_semaphore():
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(request):
        started.set()
        await release.wait()
        return response(request)

    p = provider(handler, max_concurrency=1, total_timeout=0.05)
    try:
        first = asyncio.create_task(p.ask({"ok": DecisionBooleanQuestion("ok")}))
        await started.wait()
        with pytest.raises(DecisionError, match="timed out"):
            await p.ask({"ok": DecisionBooleanQuestion("ok")})
        with pytest.raises(DecisionError, match="timed out"):
            await first
        p.total_timeout = 2
        task = asyncio.create_task(
            p.ask({"ok": DecisionBooleanQuestion("ok")}, request_max_retries=3)
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        assert (await p.ask({"ok": DecisionBooleanQuestion("ok")}))[
            "ok"
        ].probability == 0.7
    finally:
        await p.terminate()
        await p.terminate()
    with pytest.raises(DecisionError, match="closed"):
        await p.ask({"ok": DecisionBooleanQuestion("ok")})


@pytest.mark.asyncio
async def test_retry_metadata_is_request_local_and_errors_are_safe(monkeypatch):
    logs = []
    monkeypatch.setattr(
        "astrbot.core.provider.sources.request_retry.logger.warning", logs.append
    )
    hits = 0

    def handler(request):
        nonlocal hits
        hits += 1
        if hits == 1:
            return httpx.Response(
                429,
                json={"error": "test-key private prompt", "usage": {"input_tokens": 2}},
            )
        if hits == 3:
            raise httpx.ConnectError(
                "test-key https://secret.test/?private=prompt", request=request
            )
        return response(request)

    p = provider(handler)
    try:
        result = await p.ask(
            {"ok": DecisionBooleanQuestion("ok")}, request_max_retries=1
        )
        assert len(result.attempt_usages) == 2
        assert result.attempt_usages[0].input_tokens == 2
        assert result.usage.input_tokens == 4
        with pytest.raises(DecisionError) as caught:
            await p.ask({"ok": DecisionBooleanQuestion("ok")})
        assert caught.value.usage is None
        assert caught.value.attempt_usages == (None,)
        assert "test-key" not in str(caught.value)
        assert "private" not in str(caught.value)
        assert all("test-key" not in line and "private" not in line for line in logs)
        assert hits == 3
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_concurrent_results_do_not_share_usage_or_authorization(monkeypatch):
    keys = iter(["first", "second"])
    monkeypatch.setattr(
        "astrbot.core.provider.sources.openai_decision_source.random.choice",
        lambda _: next(keys),
    )
    started = asyncio.Event()

    async def handler(request):
        key = request.headers["authorization"]
        if key == "Bearer first":
            started.set()
            await asyncio.sleep(0.02)
        count = 1 if key == "Bearer first" else 2
        return httpx.Response(
            200,
            json={
                "model": "m",
                "answers": [{"name": "ok", "type": "predicate", "probability": 1}],
                "usage": {"input_tokens": count},
            },
        )

    p = provider(handler, key=["first", "second"])
    try:
        first = asyncio.create_task(p.ask({"ok": DecisionBooleanQuestion("ok")}))
        await started.wait()
        second = asyncio.create_task(p.ask({"ok": DecisionBooleanQuestion("ok")}))
        a, b = await asyncio.gather(first, second)
        assert a.usage.input_tokens == 1
        assert b.usage.input_tokens == 2
        assert "authorization" not in p.client.headers
    finally:
        await p.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {"name": "ok", "type": "predicate", "probability": float("inf")},
        {"name": "ok", "type": "predicate", "probability": True},
        {"name": "wrong", "type": "predicate", "probability": 0.5},
        {"name": "ok", "type": "choice", "choice": "a"},
    ],
)
async def test_invalid_answer_does_not_erase_observed_usage(bad):
    # Infinity is deliberately rendered by the custom transport to test decoding.
    def handler(request):
        return httpx.Response(
            200,
            content=json.dumps(
                {"model": "m", "answers": [bad], "usage": {"input_tokens": 3}}
            ),
        )

    p = provider(handler)
    try:
        with pytest.raises(DecisionError) as caught:
            await p.ask({"ok": DecisionBooleanQuestion("ok")})
        assert caught.value.usage.input_tokens == 3
        assert caught.value.attempt_usages == (caught.value.usage,)
    finally:
        await p.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage,expected",
    [
        (None, None),
        ({}, None),
        ({"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, 0),
    ],
)
async def test_missing_and_zero_usage_are_distinct(usage, expected):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "m",
                "answers": [{"name": "ok", "type": "predicate", "probability": 0}],
                "usage": usage,
            },
        )

    p = provider(handler)
    try:
        result = await p.ask({"ok": DecisionBooleanQuestion("ok")})
        assert (result.usage.total_tokens if result.usage else None) is expected
        if usage == {}:
            assert result.usage is not None
    finally:
        await p.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": -1},
        {"input_tokens": True},
        {"input_tokens_details": "bad"},
        "bad",
    ],
)
async def test_malformed_usage_is_not_reported_as_zero(usage):
    p = provider(
        lambda _: httpx.Response(
            200, json={"model": "m", "answers": [], "usage": usage}
        )
    )
    try:
        with pytest.raises(DecisionError, match="invalid usage") as caught:
            await p.ask({"ok": DecisionBooleanQuestion("ok")})
        assert caught.value.usage is None
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_system_one_rejects_new_native_wrappers_without_network():
    p = SystemOneDecisionProvider(
        {
            "id": "one",
            "type": "system_one_decision",
            "api_base": "https://one.test",
            "model": "m",
        },
        {},
        transport=httpx.MockTransport(
            lambda _: pytest.fail("Unexpected network request")
        ),
    )
    try:
        assert await p.get_models() == ["m"]
        for question, state in [
            (DecisionBooleanQuestion("ok"), DecisionInput("input")),
            (DecisionBooleanQuestion(DecisionContent([])), None),
            (DecisionChoiceQuestion("ok", {True: "yes", False: "no"}), None),
        ]:
            with pytest.raises(ValueError):
                await p.ask({"ok": question}, state)
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_native_failure_statuses_never_use_chat_endpoints():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(404, json={"error": "missing"})

    p = provider(handler)
    try:
        with pytest.raises(DecisionError, match="HTTP 404"):
            await p.ask({"ok": DecisionBooleanQuestion("ok")}, request_max_retries=3)
        assert paths == ["/prefix/v1/decisions"]
    finally:
        await p.terminate()


def test_configuration_rejects_core_overrides_and_copies_nested_data():
    for key in ("model", "input", "questions", "stream"):
        with pytest.raises(ValueError, match="override"):
            provider(response, custom_extra_body={key: "bad"})


@pytest.mark.asyncio
async def test_readonly_criteria_and_arbitrary_business_json_are_supported():
    captured = []

    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "model": "m",
                "answers": [
                    {
                        "name": "pick",
                        "type": "choice",
                        "choice": "a",
                        "confidence": 1,
                        "probabilities": [
                            {"value": "a", "probability": 1},
                            {"value": "b", "probability": 0},
                        ],
                    }
                ],
            },
        )

    p = provider(handler)
    try:
        result = await p.ask(
            {
                "pick": DecisionChoiceQuestion(
                    "pick", MappingProxyType({"a": "a", "b": "b"})
                )
            },
            [1, "x"],
        )
        assert result["pick"].choice == "a"
        assert captured[0]["input"][0]["content"] == [
            {"type": "input_json", "data": {"state": [1, "x"]}}
        ]
    finally:
        await p.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entries,choice",
    [
        ([{"value": "a", "probability": 0.2}, {"value": "b", "probability": 0.2}], "a"),
        ([{"value": "a", "probability": 1}, {"value": "a", "probability": 0}], "a"),
        ([{"value": "a", "probability": 1}], "a"),
        (
            [{"value": "a", "probability": 1}, {"value": "b", "probability": 0}],
            "unknown",
        ),
    ],
)
async def test_choice_requires_complete_typed_distribution(entries, choice):
    p = provider(
        lambda _: httpx.Response(
            200,
            json={
                "model": "m",
                "answers": [
                    {
                        "name": "pick",
                        "type": "choice",
                        "choice": choice,
                        "confidence": 1,
                        "probabilities": entries,
                    }
                ],
            },
        )
    )
    try:
        with pytest.raises(DecisionError):
            await p.ask({"pick": DecisionChoiceQuestion("pick", {"a": "a", "b": "b"})})
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_queued_cancellation_does_not_send_or_consume_capacity():
    entered, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def handler(request):
        nonlocal count
        count += 1
        entered.set()
        await release.wait()
        return response(request)

    p = provider(handler, total_timeout=2, max_concurrency=1)
    try:
        first = asyncio.create_task(p.ask({"ok": DecisionBooleanQuestion("ok")}))
        await entered.wait()
        queued = asyncio.create_task(p.ask({"ok": DecisionBooleanQuestion("ok")}))
        await asyncio.sleep(0)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        release.set()
        await first
        await p.ask({"ok": DecisionBooleanQuestion("ok")})
        assert count == 2
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_retry_backoff_is_included_in_total_deadline():
    hits = 0

    def handler(request):
        nonlocal hits
        hits += 1
        return httpx.Response(
            503, json={"error": "not ready", "usage": {"input_tokens": 7}}
        )

    p = provider(handler, total_timeout=0.05)
    try:
        with pytest.raises(DecisionError, match="total request timed out") as caught:
            await p.ask({"ok": DecisionBooleanQuestion("ok")}, request_max_retries=3)
        assert hits == 1
        assert caught.value.attempt_usages[0].input_tokens == 7
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_configuration_and_question_snapshot_are_not_mutated():
    extra = {
        "prompt_cache_options": {"mode": "explicit"},
        "safety_identifier": "tester",
    }
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return response(request)

    p = provider(handler, custom_extra_body=extra)
    extra["prompt_cache_options"]["mode"] = "implicit"
    question = DecisionBooleanQuestion(
        DecisionContent([{"type": "input_text", "text": "ok"}])
    )
    before = copy.deepcopy(question.instructions.parts)
    try:
        await p.ask({"ok": question})
        assert captured[0]["prompt_cache_options"]["mode"] == "explicit"
        assert question.instructions.parts == before
    finally:
        await p.terminate()


@pytest.mark.asyncio
async def test_failure_metadata_uses_requested_model_snapshot():
    def handler(request):
        p.set_model("next-model")
        return httpx.Response(400, json={"error": "invalid"})

    p = provider(handler, model="requested-model")
    try:
        with pytest.raises(DecisionError) as caught:
            await p.ask({"ok": DecisionBooleanQuestion("ok")})
        assert caught.value.model == "requested-model"
    finally:
        await p.terminate()
