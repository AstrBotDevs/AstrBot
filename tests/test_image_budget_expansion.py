"""Regression tests for the expanded per-request image budget."""

import httpx
import pytest
from test_image_provider_budget import KINDS, payload, response_body, sdk_provider

from astrbot.core.image_request_budget import ImageRequestBudget


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.asyncio
async def test_actual_sdk_accepts_more_than_eight_images_without_count_cap(kind):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response_body(kind))

    budget = ImageRequestBudget()
    async with sdk_provider(kind, handler) as provider:
        for count in (8, 9, 32):
            with budget.scope(purpose="main", provider_id=kind, model="test-model"):
                result = await provider._query(
                    payload(kind, count), None, request_max_retries=1
                )
            assert result.completion_text == "ok"

    assert len(requests) == 3
    assert budget.image_submissions == 49
    assert budget.visual_request_attempts == 3


@pytest.mark.asyncio
async def test_actual_openai_sdk_accepts_payload_above_previous_byte_limit():
    requests = []
    byte_count = 32 * 1024 * 1024 + 1

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response_body("openai"))

    budget = ImageRequestBudget()
    assert budget.max_caption_attempts == 2
    assert budget.max_review_triggers is None
    assert budget.max_image_submissions is None
    async with sdk_provider("openai", handler) as provider:
        oversized = payload("openai")
        oversized["messages"][0]["content"][0]["image_url"]["url"] = (
            "data:image/png;base64," + "A" * byte_count
        )
        with budget.scope(purpose="main", provider_id="openai", model="test-model"):
            result = await provider._query(oversized, None, request_max_retries=1)
        assert result.completion_text == "ok"

    assert len(requests) == 1
    group = budget.to_dict()["groups"][0]
    assert group["image_submissions"] == budget.image_submissions == 1
    assert group["encoded_bytes"] == byte_count > 32 * 1024 * 1024
