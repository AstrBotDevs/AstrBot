"""Contracts for lightweight image history and provider text projections."""

import copy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from astrbot.core.agent.context.token_counter import EstimateTokenCounter
from astrbot.core.agent.message import (
    AssistantMessageSegment,
    ImageRefPart,
    ImageURLPart,
    Message,
    TextPart,
    ToolCallMessageSegment,
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
)
from astrbot.core.db.po import ConversationImageRef, ConversationV2, ImageAsset
from astrbot.core.provider.entities import ProviderRequest, ToolCallsResult
from astrbot.core.provider.modalities import sanitize_contexts_by_modalities
from astrbot.core.provider.provider import Provider
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


@pytest.fixture
def image_ref():
    return ImageRefPart(
        occurrence_id="image-1",
        asset_id="asset-1",
        description="A screenshot with a connection error.",
        description_status="ready",
        description_version=1,
    )


def test_history_round_trip_preserves_refs_and_drops_only_temporary_images(image_ref):
    preview = ImageURLPart(
        image_url=ImageURLPart.ImageURL(url="data:image/png;base64,AAAA")
    ).mark_as_temp()
    message = Message(role="user", content=[image_ref, preview])
    history = dump_messages_with_checkpoints([message])
    history.append({"role": "_checkpoint", "content": {"id": "cp-1"}})
    restored = bind_checkpoint_messages(json.loads(json.dumps(history)))
    assert dump_messages_with_checkpoints(restored) == history
    assert isinstance(restored[0].content[0], ImageRefPart)
    assert "base64" not in json.dumps(history)


def test_temporary_reference_keeps_existing_content_marker_contract(image_ref):
    image_ref.mark_as_temp()
    restored = Message.model_validate(
        {"role": "user", "content": [image_ref.model_dump_for_context()]}
    )
    assert restored.content[0]._no_save
    assert dump_messages_with_checkpoints([restored])[0]["content"] == []


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"asset_id": "../../private.png"},
        {"occurrence_id": ""},
        {"description": "x" * 4097},
        {"description_status": "invented"},
        {"description_version": -1},
        {"url": "data:image/png;base64,AAAA"},
    ],
)
def test_invalid_reference_is_rejected(image_ref, change):
    with pytest.raises(ValidationError):
        Message.model_validate(
            {"role": "user", "content": [{**image_ref.model_dump(), **change}]}
        )


@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize(
    "provider_cls",
    [
        ProviderOpenAIOfficial,
        ProviderOpenAIResponses,
        ProviderAnthropic,
        ProviderGoogleGenAI,
    ],
)
def test_provider_projection_preserves_legacy_blocks_without_mutating_history(
    image_ref, typed, provider_cls
):
    history = [
        {
            "role": "user",
            "content": [
                image_ref.model_dump(),
                {"type": "text", "text": "Compare it."},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/a.png"},
                },
            ],
        },
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
    ]
    messages = [Message.model_validate(m) for m in history] if typed else history
    before = copy.deepcopy(messages)
    # No provider constructor or SDK client is needed for this common boundary.
    projected = provider_cls._ensure_message_to_dicts(None, messages)
    assert messages == before
    assert len(projected) == 1
    assert projected[0]["content"][0] == {"type": "text", "text": image_ref.to_text()}
    assert projected[0]["content"][1] == history[0]["content"][1]
    assert projected[0]["content"][2]["image_url"]["url"] == "https://example.com/a.png"
    assert "asset-1" not in json.dumps(projected)
    assert "image_ref" not in json.dumps(projected)


@pytest.mark.parametrize(
    "modalities", [None, [], ["text"], ["image", "audio", "tool_use"]]
)
@pytest.mark.parametrize("typed", [False, True])
def test_modality_sanitizer_retains_reference_description(image_ref, modalities, typed):
    message = Message(role="user", content=[image_ref])
    history = [message if typed else message.model_dump()]
    before = copy.deepcopy(history)
    projected, stats = sanitize_contexts_by_modalities(history, modalities)
    assert projected == [
        {"role": "user", "content": [{"type": "text", "text": image_ref.to_text()}]}
    ]
    assert not stats.changed
    assert history == before


def test_reference_token_count_matches_provider_text(image_ref):
    counter = EstimateTokenCounter()
    reference = [Message(role="user", content=[image_ref])]
    text = [Message(role="user", content=[TextPart(text=image_ref.to_text())])]
    assert counter.count_tokens(reference) == counter.count_tokens(text) > 0
    assert counter.count_tokens(reference, trusted_token_usage=42) == 42


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_cls",
    [
        ProviderOpenAIOfficial,
        ProviderOpenAIResponses,
        ProviderAnthropic,
        ProviderGoogleGenAI,
    ],
)
async def test_extra_reference_parts_are_text_without_media_resolution(
    image_ref, provider_cls
):
    result = await provider_cls.assemble_context(
        None, "Question", extra_user_content_parts=[image_ref]
    )
    assert result["content"] == [
        {"type": "text", "text": "Question"},
        {"type": "text", "text": image_ref.to_text()},
    ]


@pytest.mark.asyncio
async def test_request_assembly_keeps_internal_history_ref_until_provider_boundary(
    image_ref,
):
    req = ProviderRequest(prompt="Question", extra_user_content_parts=[image_ref])
    history = await req.assemble_context()
    assert history["content"][1]["type"] == "image_ref"
    projected = Provider._ensure_message_to_dicts(None, [history])
    assert projected[0]["content"][1]["type"] == "text"
    assert history["content"][1]["type"] == "image_ref"


def test_conversation_associations_keep_branch_descriptions_independent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'images.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all(
                [
                    ConversationV2(
                        conversation_id="parent", platform_id="test", user_id="one"
                    ),
                    ConversationV2(
                        conversation_id="child", platform_id="test", user_id="one"
                    ),
                    ImageAsset(
                        asset_id="asset",
                        storage_key="a.png",
                        mime_type="image/png",
                        byte_size=12,
                        width=1,
                        height=1,
                        sha256="a" * 64,
                    ),
                ]
            )
            session.commit()
            session.add_all(
                [
                    ConversationImageRef(
                        conversation_id="parent",
                        occurrence_id="image",
                        asset_id="asset",
                        description="original",
                    ),
                    ConversationImageRef(
                        conversation_id="child",
                        occurrence_id="image",
                        asset_id="asset",
                        description="original",
                    ),
                ]
            )
            session.commit()
            child = session.get(ConversationImageRef, ("child", "image"))
            child.description = "corrected in child"
            session.add(child)
            session.commit()
            assert (
                session.get(ConversationImageRef, ("parent", "image")).description
                == "original"
            )
            assert session.get(ConversationImageRef, ("other", "image")) is None
            session.delete(child)
            session.commit()
            assert session.get(ImageAsset, "asset") is not None
            assert len(session.exec(select(ConversationImageRef)).all()) == 1
            session.add(
                ConversationImageRef(
                    conversation_id="child", occurrence_id="bad", asset_id="missing"
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("as_list", [False, True])
@pytest.mark.parametrize(
    "provider_cls", [ProviderOpenAIOfficial, ProviderOpenAIResponses]
)
async def test_openai_tool_result_refs_are_projected_before_payload(
    image_ref, as_list, provider_cls
):
    result = ToolCallsResult(
        tool_calls_info=AssistantMessageSegment(content="Inspection result"),
        tool_calls_result=[
            ToolCallMessageSegment(content=[image_ref], tool_call_id="call-1")
        ],
    )
    provider = object.__new__(provider_cls)
    provider.client = SimpleNamespace(base_url=SimpleNamespace(host="api.openai.com"))
    provider.provider_config = {}
    payload, _ = await provider._prepare_chat_payload(
        None,
        contexts=[],
        tool_calls_result=[result] if as_list else result,
        model="test",
    )
    serialized = json.dumps(payload)
    assert "asset-1" not in serialized
    assert '"image_ref"' not in serialized
    assert image_ref.description in serialized
    assert isinstance(result.tool_calls_result[0].content[0], ImageRefPart)


@pytest.mark.asyncio
@pytest.mark.parametrize("as_list", [False, True])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("provider_cls", [ProviderAnthropic, ProviderGoogleGenAI])
async def test_tool_result_refs_are_projected_in_stream_and_nonstream_paths(
    image_ref, as_list, stream, provider_cls
):
    result = ToolCallsResult(
        tool_calls_info=AssistantMessageSegment(content="Inspection result"),
        tool_calls_result=[
            ToolCallMessageSegment(content=[image_ref], tool_call_id="call-1")
        ],
    )
    provider = object.__new__(provider_cls)
    provider.api_keys = []

    async def capture(payload, *args, **kwargs):
        return payload

    async def capture_stream(payload, *args, **kwargs):
        yield payload

    provider._query = capture
    provider._query_stream = capture_stream
    arguments = {
        "contexts": [],
        "tool_calls_result": [result] if as_list else result,
        "model": "test",
    }
    if stream:
        outputs = [part async for part in provider.text_chat_stream(**arguments)]
        payload = outputs[0]
    else:
        payload = await provider.text_chat(**arguments)
    serialized = json.dumps(payload)
    assert "asset-1" not in serialized
    assert '"image_ref"' not in serialized
    assert image_ref.description in serialized
    assert isinstance(result.tool_calls_result[0].content[0], ImageRefPart)
