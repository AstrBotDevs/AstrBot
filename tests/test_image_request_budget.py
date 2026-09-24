"""Deterministic accounting tests without provider or network access."""

import asyncio
import json

import pytest

from astrbot.core.image_request_budget import (
    ImageBudgetExceeded,
    ImageRequestBudget,
    charge_image_attempt,
    current_image_request,
    image_payload_size,
)
from astrbot.core.provider.entities import TokenUsage


@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            {
                "messages": [
                    {
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/png;base64,YWJj"},
                            }
                        ]
                    }
                ]
            },
            (1, 4),
        ),
        (
            {
                "input": [
                    {"type": "input_image", "image_url": "data:image/png;base64,YWJj"}
                ]
            },
            (1, 4),
        ),
        ({"type": "image", "source": {"type": "base64", "data": "YWJj"}}, (1, 4)),
        (
            {
                "contents": [
                    {
                        "parts": [
                            {"inline_data": {"mime_type": "image/png", "data": b"abc"}}
                        ]
                    }
                ]
            },
            (1, 4),
        ),
        ({"inlineData": {"mimeType": "audio/mp3", "data": b"abc"}}, (0, 0)),
        ({"messages": [{"content": "data:image/png;base64,YWJj"}]}, (0, 0)),
    ],
)
def test_final_payload_accounting(payload, expected):
    assert image_payload_size(payload) == expected


def test_limits_retry_and_unknown_usage():
    budget = ImageRequestBudget()
    with budget.scope(
        purpose="caption", provider_id="p", model="m", image_count=4, encoded_bytes=100
    ):
        charge_image_attempt()
        charge_image_attempt()
        with pytest.raises(ImageBudgetExceeded):
            charge_image_attempt()
    budget.record_usage(
        TokenUsage(input_other=10, output=5),
        purpose="caption",
        provider_id="p",
        model="m",
    )
    result = budget.to_dict()
    assert result["image_submissions"] == 8
    assert budget.visual_request_attempts == 2
    assert result["groups"][0]["unknown_calls"] == 1
    assert result["groups"][0]["token_usage"]["input_other"] == 10
    json.dumps(result)
    assert current_image_request.get() is None


def test_scope_does_not_charge_and_text_fallback_is_not_visual():
    budget = ImageRequestBudget()
    with budget.scope(purpose="main", provider_id="p", model="m", image_count=4):
        assert budget.image_submissions == 0
        charge_image_attempt({"messages": [{"content": "text fallback"}]})
    assert budget.image_submissions == 0
    assert budget.to_dict()["groups"][0]["attempts"] == 1
    charge_image_attempt({"type": "input_image"})
    assert budget.image_submissions == 0


def test_default_request_limits_and_unlimited_turn_accounting():
    budget = ImageRequestBudget()
    assert budget.max_images is None
    budget.preflight(100, 32 * 1024 * 1024)
    for _ in range(20):
        budget.consume_review()
        with budget.scope(purpose="main", provider_id="p", model="m", image_count=8):
            charge_image_attempt()
    assert budget.review_triggers == 20
    assert budget.image_submissions == 160
    assert budget.visual_request_attempts == 20
    budget.preflight(1000, 0)
    with pytest.raises(ImageBudgetExceeded):
        budget.preflight(1, 32 * 1024 * 1024 + 1)


def test_explicit_turn_limits_remain_supported():
    budget = ImageRequestBudget(max_image_submissions=1, max_review_triggers=1)
    with budget.scope(purpose="main", provider_id="p", model="m", image_count=1):
        charge_image_attempt()
    with pytest.raises(ImageBudgetExceeded):
        budget.preflight(1, 0)
    budget.consume_review()
    with pytest.raises(ImageBudgetExceeded):
        budget.consume_review()


@pytest.mark.asyncio
async def test_context_isolation_and_atomic_shared_limit():
    budget = ImageRequestBudget(max_image_submissions=4)

    async def run(provider):
        try:
            with budget.scope(
                purpose="main", provider_id=provider, model="m", image_count=4
            ):
                await asyncio.sleep(0)
                assert current_image_request.get().provider_id == provider
                charge_image_attempt()
            return True
        except ImageBudgetExceeded:
            return False

    assert sum(await asyncio.gather(run("one"), run("two"))) == 1
    assert budget.image_submissions == 4
    assert current_image_request.get() is None


@pytest.mark.parametrize("schema_type", [{"type": "string"}, ["string", "null"]])
def test_tool_schema_type_and_examples_are_not_images(schema_type):
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}}
    payload = {
        "messages": [{"role": "user", "content": [image]}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "send_message",
                    "parameters": {
                        "type": "object",
                        "properties": {"type": schema_type},
                        "examples": [image],
                    },
                },
            }
        ],
        "metadata": {"content": [image]},
    }
    assert image_payload_size(payload) == (1, 4)
    assert image_payload_size({"type": schema_type}) == (0, 0)


def test_nested_anthropic_tool_result_images_are_counted():
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "data": "YWJj"},
                            }
                        ],
                    }
                ],
            }
        ]
    }
    assert image_payload_size(payload) == (1, 4)


def test_visual_request_attempts_exclude_text_and_rejected_requests():
    budget = ImageRequestBudget(max_image_submissions=1)
    with budget.scope(purpose="main", provider_id="p", model="m"):
        charge_image_attempt({"messages": [{"content": "hello"}]})
        assert budget.visual_request_attempts == 0
        image = {"type": "image_url", "image_url": "data:image/png;base64,YWJj"}
        charge_image_attempt(image)
        with pytest.raises(ImageBudgetExceeded):
            charge_image_attempt(image)
    assert budget.visual_request_attempts == 1
