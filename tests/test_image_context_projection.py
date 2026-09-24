"""Request-only description projection and dimension-based visual estimates."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from astrbot.core.agent.context.compressor import LLMSummaryCompressor
from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.context.token_counter import estimate_preview_tokens
from astrbot.core.agent.message import ImageRefPart, ImageURLPart, Message, TextPart
from astrbot.core.image_request_budget import ImageRequestBudget, charge_image_attempt
from astrbot.core.provider.entities import LLMResponse, TokenUsage


@pytest.mark.asyncio
async def test_preview_dimensions_not_file_or_base64_size(tmp_path):
    small = tmp_path / "small.bmp"
    large = tmp_path / "large.png"
    Image.new("RGB", (512, 512)).save(small)
    Image.new("RGB", (1024, 1024)).save(large)
    with small.open("ab") as stream:
        stream.write(b"x" * 1024)
    estimates = await estimate_preview_tokens(
        [small, large, "data:image/png;base64,AAAA"]
    )
    assert estimates["images"][0]["tokens"] == 512
    assert estimates["images"][1]["tokens"] == 1280
    assert estimates["unknown_images"] == 1
    assert estimates["status"] == "unknown"


@pytest.fixture
def projection_turn():
    async def project(messages):
        result = copy.deepcopy(messages)
        for message in result:
            if isinstance(message.content, list):
                message.content = [
                    TextPart(text="latest authorized observation")
                    if isinstance(part, ImageRefPart)
                    else part
                    for part in message.content
                ]
        return result

    return SimpleNamespace(
        project_messages=AsyncMock(side_effect=project),
        pending_visuals={},
        budget=ImageRequestBudget(),
    )


@pytest.mark.asyncio
async def test_manager_counts_projection_preserves_persistent_ref(projection_turn):
    ref = ImageRefPart(occurrence_id="occ", asset_id="asset", description="old")
    messages = [Message(role="user", content=[ref])]
    manager = ContextManager(
        ContextConfig(image_context=projection_turn, max_context_tokens=10000)
    )
    result = await manager.process(messages, trusted_token_usage=99999)
    assert result[0] is messages[0]
    assert isinstance(result[0].content[0], ImageRefPart)
    assert result[0].content[0].description == "old"
    assert projection_turn.project_messages.await_count == 1


@pytest.mark.asyncio
async def test_summary_latest_description_no_bytes_and_separate_usage(projection_turn):
    class Provider:
        image_request_budget_supported = True
        provider_config = {"id": "summary-provider", "modalities": ["text", "image"]}

        def get_model(self):
            return "summary-model"

        async def text_chat(self, **kwargs):
            payload = [
                message.model_dump() if hasattr(message, "model_dump") else message
                for message in kwargs["contexts"]
            ]
            assert "latest authorized observation" in str(payload)
            assert "data:image" not in str(payload)
            charge_image_attempt(payload)
            return LLMResponse(
                role="assistant",
                completion_text="summary",
                usage=TokenUsage(input_other=12),
            )

    image = ImageURLPart(
        image_url=ImageURLPart.ImageURL(url="data:image/png;base64,AAAA")
    )
    ref = ImageRefPart(occurrence_id="occ", asset_id="asset", description="old")
    messages = [
        Message(role="user", content=[ref, image]),
        Message(role="assistant", content="old response"),
        Message(role="user", content=[ref]),
    ]
    compressor = LLMSummaryCompressor(
        Provider(), image_context=projection_turn, keep_recent_ratio=0
    )
    result = await compressor(messages)
    assert result[-1] is messages[-1]
    assert isinstance(result[-1].content[0], ImageRefPart)
    assert isinstance(messages[0].content[1], ImageURLPart)
    group = projection_turn.budget.to_dict()["groups"][0]
    assert group["purpose"] == "summary" and group["image_submissions"] == 0
    assert group["token_usage"]["input_other"] == 12


@pytest.mark.asyncio
async def test_default_off_does_not_project(projection_turn):
    messages = [Message(role="user", content="old")]
    result = await ContextManager(ContextConfig()).process(messages)
    assert result is messages
    projection_turn.project_messages.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["known", "unknown", "error"])
async def test_opaque_summary_records_logical_usage(projection_turn, outcome):
    async def respond(**kwargs):
        if outcome == "error":
            raise RuntimeError("offline failure")
        return LLMResponse(
            role="assistant",
            completion_text="summary",
            usage=TokenUsage(input_other=12, output=3) if outcome == "known" else None,
        )

    provider = SimpleNamespace(
        provider_config={"id": "opaque", "modalities": ["text"]},
        image_request_budget_supported=False,
        get_model=lambda: "summary-model",
        text_chat=AsyncMock(side_effect=respond),
    )
    messages = [
        Message(role="user", content="old question"),
        Message(role="assistant", content="old answer"),
        Message(role="user", content="recent question"),
    ]
    compressor = LLMSummaryCompressor(
        provider, image_context=projection_turn, keep_recent_ratio=0
    )
    await compressor(messages)
    provider.text_chat.assert_awaited_once()
    assert projection_turn.budget.to_dict()["groups"] == []
    assert len(projection_turn.unmetered_stats) == 1
    group = projection_turn.unmetered_stats[0]
    assert group["purpose"] == "summary"
    assert group["attempts"] == 1 and group["attempts_kind"] == "logical"
    assert group["unknown_calls"] == (0 if outcome == "known" else 1)
    assert group["token_usage"]["input_other"] == (12 if outcome == "known" else 0)
    assert group["token_usage"]["output"] == (3 if outcome == "known" else 0)
