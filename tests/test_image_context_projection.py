"""Request-only image accounting and dimension-based visual estimates."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from PIL import Image

from astrbot.core import image_asset_store, image_context
from astrbot.core.agent.context.compressor import LLMSummaryCompressor
from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.context.token_counter import (
    EstimateTokenCounter,
    count_projected_tokens,
    estimate_preview_tokens,
)
from astrbot.core.agent.message import ImageRefPart, ImageURLPart, Message, TextPart
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.image_request_budget import (
    ImageAuthorizationRevoked,
    ImageRequestBudget,
    current_image_request,
)
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


@pytest_asyncio.fixture
async def managed_image(tmp_path, monkeypatch):
    """Create a real stored image reference and a configured visual turn."""
    monkeypatch.setattr(
        image_asset_store, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    monkeypatch.setattr(
        image_context, "get_astrbot_temp_path", lambda: str(tmp_path / "temp")
    )
    db = SQLiteDatabase(str(tmp_path / "gallery.db"))
    await db.initialize()
    db.inited = True
    await db.create_conversation("owner", "test", cid="conversation")
    source = tmp_path / "original.png"
    Image.new("RGB", (640, 320), "orange").save(source)
    tracked_files = []
    event = SimpleNamespace(track_temporary_local_file=tracked_files.append)
    turn = image_context.ImageTurnContext(db, "conversation", "checkpoint")
    reference = await turn.capture(str(source), max_size=128, event=event)
    provider = SimpleNamespace(
        provider_config={"id": "visual", "modalities": ["text", "image"]},
        image_request_budget_supported=ProviderOpenAIOfficial.image_request_budget_supported,
        get_model=lambda: "vision-model",
    )
    turn.configure(
        user_id="owner",
        platform_id="test",
        event=event,
        max_size=128,
        provider=provider,
        budget=ImageRequestBudget(),
    )
    try:
        yield SimpleNamespace(
            db=db,
            event=event,
            turn=turn,
            reference=reference,
            provider=provider,
            tracked_files=tracked_files,
        )
    finally:
        await db.engine.dispose()


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
    turn = SimpleNamespace(
        projected_visuals={},
        pending_visuals={},
        budget=ImageRequestBudget(),
        authorize_visuals=AsyncMock(return_value=set()),
        revoked=False,
    )

    async def project(messages, *, provider=None):
        return copy.deepcopy(messages)

    async def prepare_step(provider, model=None):
        turn.provider = provider

    turn.prepare_step = AsyncMock(side_effect=prepare_step)
    turn.project_messages = AsyncMock(side_effect=project)
    return turn


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
    submitted = provider.text_chat.call_args.kwargs["contexts"]
    assert any("old question" in str(message) for message in submitted)
    assert any("Generate a summary" in str(message) for message in submitted)


@pytest.mark.asyncio
async def test_manager_projects_real_image_without_swallowing_errors(
    managed_image, caplog
):
    ref = managed_image.reference
    messages = [Message(role="user", content=[ref])]
    manager = ContextManager(
        ContextConfig(image_context=managed_image.turn, max_context_tokens=10000)
    )

    result = await manager.process(messages, trusted_token_usage=99999)

    assert result is messages
    assert managed_image.turn.projected_visuals
    assert "Error during context processing" not in caplog.text


@pytest.mark.asyncio
async def test_repeated_image_positions_are_each_included_in_token_estimate(
    managed_image,
):
    reference = managed_image.reference
    message = Message(
        role="user",
        content=[
            TextPart(text="before"),
            reference,
            TextPart(text="between"),
            reference,
        ],
    )
    projected = await managed_image.turn.project_messages([message])
    estimate = await count_projected_tokens(
        projected,
        managed_image.turn,
        EstimateTokenCounter(),
        provider=managed_image.provider,
    )
    text_only = copy.deepcopy(projected)
    positions = 0
    preview = managed_image.turn.projected_visuals[reference.occurrence_id]
    for projected_message in text_only:
        if isinstance(projected_message.content, list):
            positions += sum(
                isinstance(part, ImageURLPart) for part in projected_message.content
            )
            projected_message.content = [
                part
                for part in projected_message.content
                if not isinstance(part, ImageURLPart)
            ]
    single_image = await estimate_preview_tokens([preview])
    assert positions == 2
    assert (
        estimate
        == EstimateTokenCounter().count_tokens(text_only) + 2 * (single_image["tokens"])
    )


@pytest.mark.asyncio
async def test_nonvisual_summary_provider_uses_reference_marker_only(
    managed_image, monkeypatch
):
    turn = managed_image.turn
    reference = managed_image.reference
    provider = SimpleNamespace(
        provider_config={"id": "text-summary", "modalities": ["text"]},
        image_request_budget_supported=False,
        get_model=lambda: "text-summary-model",
        text_chat=AsyncMock(
            return_value=LLMResponse(role="assistant", completion_text="summary")
        ),
    )
    open_preview = AsyncMock(wraps=turn.open_preview)
    monkeypatch.setattr(turn, "open_preview", open_preview)
    compressor = LLMSummaryCompressor(provider, image_context=turn, keep_recent_ratio=0)
    messages = [
        Message(role="user", content=[reference]),
        Message(role="assistant", content="I saw it."),
        Message(role="user", content="Continue."),
        Message(role="assistant", content="Done."),
    ]

    await compressor(messages)

    provider.text_chat.assert_awaited_once()
    open_preview.assert_not_awaited()
    assert not turn.projected_visuals
    submitted = provider.text_chat.call_args.kwargs["contexts"]
    assert "cannot view images" in str(submitted)
    assert '"type": "image_url"' not in str(submitted)


@pytest.mark.asyncio
@pytest.mark.parametrize("reuse_gallery_id", [False, True])
async def test_visual_summary_sends_reference_in_place_and_rechecks_revocation(
    managed_image, reuse_gallery_id
):
    turn = managed_image.turn
    reference = managed_image.reference
    sent_at_factory = []
    revoke_at_factory = False

    async def submit_summary(**kwargs):
        payload = kwargs["contexts"]
        scope = current_image_request.get()
        assert scope is not None
        if revoke_at_factory:
            turn.revoked_occurrences.add(reference.occurrence_id)
        scope.budget.on_attempt(scope, {"contexts": payload})
        sent_at_factory.append(copy.deepcopy(payload))
        return LLMResponse(role="assistant", completion_text="summary")

    provider = SimpleNamespace(
        provider_config={
            "id": "visual-summary",
            "modalities": ["text", "image", "audio", "tool_use"],
        },
        image_request_budget_supported=managed_image.provider.image_request_budget_supported,
        get_model=lambda: "vision-summary-model",
        text_chat=AsyncMock(side_effect=submit_summary),
    )
    compressor = LLMSummaryCompressor(provider, image_context=turn, keep_recent_ratio=0)
    inline_id = reference.occurrence_id if reuse_gallery_id else None
    messages = [
        Message(
            role="user",
            content=[
                TextPart(text="before"),
                reference,
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(
                        url="data:image/png;base64,QUJD", id=inline_id
                    )
                ),
                TextPart(text="after"),
            ],
        ),
        Message(role="assistant", content="I inspected it."),
        Message(role="user", content="More context."),
        Message(role="assistant", content="Finished."),
    ]

    await compressor(messages)

    provider.text_chat.assert_awaited_once()
    assert turn.budget.image_submissions == 1
    assert len(sent_at_factory) == 1
    image_message = next(
        message
        for message in sent_at_factory[0]
        if isinstance(message.get("content"), list)
        and any(
            isinstance(part, dict) and part.get("type") == "image_url"
            for part in message["content"]
        )
    )
    parts = image_message["content"]
    assert [part.get("type") for part in parts] == [
        "text",
        "text",
        "image_url",
        "text",
        "text",
    ]
    assert parts[0]["text"] == "before"
    assert parts[1]["text"] == reference.to_text()
    assert parts[2]["image_url"]["id"] == reference.occurrence_id
    assert parts[3]["text"] == "[Image unavailable]"
    assert parts[4]["text"] == "after"
    assert "QUJD" not in str(sent_at_factory[0])

    sent_at_factory.clear()
    revoke_at_factory = True
    provider.text_chat.reset_mock()
    with pytest.raises(ImageAuthorizationRevoked):
        await compressor(messages)

    provider.text_chat.assert_awaited_once()
    assert sent_at_factory == []
