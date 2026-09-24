"""Strict caption mapping and stale-update protection without real models."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from astrbot.core.db.po import ConversationImageRef
from astrbot.core.image_context import ImageTurnContext
from astrbot.core.image_description import describe_images
from astrbot.core.image_request_budget import (
    ImageBudgetExceeded,
    ImageRequestBudget,
    charge_image_attempt,
)
from astrbot.core.provider.entities import LLMResponse, TokenUsage


@pytest.fixture
def setup_caption(tmp_path):
    path = tmp_path / "preview.png"
    Image.new("RGB", (4, 4)).save(path)
    refs = {
        key: ConversationImageRef(
            conversation_id="cid",
            occurrence_id=key,
            asset_id="asset",
            checkpoint_id="cp",
        )
        for key in ("a", "b")
    }
    turn = ImageTurnContext(
        SimpleNamespace(update_image_description=AsyncMock(return_value=True)),
        "cid",
        "cp",
    )
    turn.references = refs
    turn.pending_visuals = {key: str(path) for key in refs}
    turn.budget = ImageRequestBudget()
    turn.get_reference = AsyncMock(side_effect=lambda key: refs.get(key))
    turn.open_preview = AsyncMock(return_value=str(path))
    turn.user_id, turn.platform_id = "u", "p"

    class FakeProvider:
        image_request_budget_supported = True
        provider_config = {"id": "caption"}
        calls = 0
        response = None
        callback = None

        def get_model(self):
            return "vision"

        async def text_chat(self, **kwargs):
            self.calls += 1
            assert "contexts" not in kwargs and "func_tool" not in kwargs
            assert kwargs["request_max_retries"] == 1
            charge_image_attempt({"parts": kwargs["extra_user_content_parts"]})
            if self.callback:
                await self.callback()
            if isinstance(self.response, Exception):
                raise self.response
            return self.response or LLMResponse(
                role="assistant",
                completion_text=json.dumps(
                    {
                        "images": [
                            {"image_id": key, "description": "visible shape"}
                            for key in refs
                        ]
                    }
                ),
                usage=TokenUsage(input_other=10),
            )

    return turn, FakeProvider()


@pytest.mark.asyncio
@pytest.mark.parametrize("ids", [["a"], ["a", "b"]])
async def test_correct_id_mapping(setup_caption, ids):
    turn, provider = setup_caption
    provider.response = LLMResponse(
        role="assistant",
        completion_text=json.dumps(
            {"images": [{"image_id": key, "description": key} for key in reversed(ids)]}
        ),
        usage=TokenUsage(input_other=3),
    )
    await describe_images(turn, provider, occurrence_ids=ids)
    for key in ids:
        assert turn.references[key].description == key
        assert turn.references[key].description_version == 1
    assert turn.budget.image_submissions == len(ids)
    assert not turn.budget.usage_unknown


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"images":[]}',
        '{"images":[{"image_id":"wrong","description":"x"}]}',
        '{"images":[{"image_id":"a","description":"x"},{"image_id":"a","description":"y"}]}',
        '{"images":[{"image_id":"a","description":123},{"image_id":"b","description":"y"}]}',
        '{"images":[{"image_id":"a","description":""},{"image_id":"b","description":"y"}]}',
    ],
)
async def test_invalid_batch_preserves_ready_and_counts_usage(setup_caption, content):
    turn, provider = setup_caption
    ref = turn.references["a"]
    ref.description, ref.description_status = "previous", "ready"
    provider.response = LLMResponse(
        role="assistant", completion_text=content, usage=TokenUsage(input_other=7)
    )
    await describe_images(turn, provider, refresh=True)
    assert ref.description == "previous" and ref.description_version == 0
    assert turn.references["b"].description_status == "pending"
    assert provider.calls == 1
    assert turn.budget.to_dict()["groups"][0]["token_usage"]["input_other"] == 7


@pytest.mark.asyncio
async def test_unknown_and_failure_attempts(setup_caption):
    turn, provider = setup_caption
    provider.response = LLMResponse(
        role="assistant", completion_text='{"images":[]}', usage=None
    )
    await describe_images(turn, provider)
    provider.response = RuntimeError("offline failure")
    await describe_images(turn, provider)
    assert turn.budget.to_dict()["groups"][0]["unknown_calls"] == 2
    with pytest.raises(ImageBudgetExceeded):
        await describe_images(turn, provider)
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_stale_current_and_persisted_cas(setup_caption):
    turn, provider = setup_caption

    async def update():
        turn.references["a"].description_version += 1
        turn.references["a"].description = "concurrent"

    provider.callback = update
    await describe_images(turn, provider)
    assert turn.references["a"].description == "concurrent"
    provider.callback = None
    refs = dict(turn.references)
    turn.references = {}
    turn.get_reference = AsyncMock(side_effect=lambda key: refs[key])
    turn.db.update_image_description.return_value = False
    await describe_images(turn, provider, occurrence_ids=["a", "b"], refresh=True)
    assert refs["a"].description == "concurrent"
    assert turn.db.update_image_description.await_count == 2


@pytest.mark.asyncio
async def test_unsupported_provider_and_cancellation(setup_caption):
    turn, provider = setup_caption
    provider.image_request_budget_supported = False
    await describe_images(turn, provider)
    assert provider.calls == 0
    provider.image_request_budget_supported = True

    async def cancel():
        raise asyncio.CancelledError

    provider.callback = cancel
    with pytest.raises(asyncio.CancelledError):
        await describe_images(turn, provider)
    assert all(ref.description_status == "pending" for ref in turn.references.values())


@pytest.mark.asyncio
async def test_directed_answer(setup_caption):
    turn, provider = setup_caption
    provider.response = LLMResponse(
        role="assistant",
        completion_text=json.dumps(
            {"images": [{"image_id": "a", "description": "shape"}], "answer": "red"}
        ),
    )
    assert (
        await describe_images(
            turn, provider, occurrence_ids=["a"], question="What color?"
        )
        == "red"
    )


@pytest.mark.asyncio
async def test_explicit_batch_bound_and_pending_remainder(setup_caption):
    turn, provider = setup_caption
    turn.budget.max_images = 8
    preview = turn.pending_visuals["a"]
    for key in ("c", "d", "e", "f", "g", "h", "i"):
        turn.references[key] = ConversationImageRef(
            conversation_id="cid",
            occurrence_id=key,
            asset_id="asset",
            checkpoint_id="cp",
        )
        turn.pending_visuals[key] = preview
    provider.response = LLMResponse(
        role="assistant",
        completion_text=json.dumps(
            {
                "images": [
                    {"image_id": key, "description": "shape"}
                    for key in ("a", "b", "c", "d", "e", "f", "g", "h")
                ]
            }
        ),
    )
    await describe_images(turn, provider)
    assert provider.calls == 1 and turn.budget.image_submissions == 8
    assert turn.references["i"].description_status == "pending"


@pytest.mark.asyncio
async def test_persisted_update_is_authorized_and_cas_failure_preserves(setup_caption):
    from sqlalchemy.exc import SQLAlchemyError

    turn, provider = setup_caption
    refs = dict(turn.references)
    turn.references = {}
    turn.get_reference = AsyncMock(side_effect=lambda key: refs[key])
    await describe_images(turn, provider, occurrence_ids=["a", "b"])
    assert refs["a"].description_version == 1
    assert turn.open_preview.await_count == 2
    kwargs = turn.db.update_image_description.await_args.kwargs
    assert kwargs["user_id"] == "u" and kwargs["expected_checkpoint_id"] == "cp"
    turn.db.update_image_description.side_effect = SQLAlchemyError(
        "storage unavailable"
    )
    await describe_images(turn, provider, occurrence_ids=["a", "b"], refresh=True)
    assert refs["a"].description_version == 1


@pytest.mark.asyncio
async def test_deleted_preview_skips_call(setup_caption):
    turn, provider = setup_caption
    turn.references = {}
    turn.open_preview.side_effect = PermissionError("deleted")
    await describe_images(turn, provider, occurrence_ids=["a", "b"])
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_resource_exhaustion_is_not_hidden(setup_caption):
    import errno

    turn, provider = setup_caption
    provider.response = OSError(errno.ENOMEM, "out of memory")
    with pytest.raises(OSError):
        await describe_images(turn, provider)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_description_byte_boundary_stops_before_later_smaller_image(
    setup_caption, tmp_path
):
    turn, provider = setup_caption
    preview = turn.pending_visuals["a"]
    encoded_size = 4 * ((Path(preview).stat().st_size + 2) // 3)
    large = tmp_path / "large.png"
    large.write_bytes(b"x" * (encoded_size * 3))
    turn.pending_visuals["b"] = str(large)
    turn.references["c"] = ConversationImageRef(
        conversation_id="cid", occurrence_id="c", asset_id="asset", checkpoint_id="cp"
    )
    turn.pending_visuals["c"] = preview
    turn.budget = ImageRequestBudget(max_encoded_bytes=encoded_size * 2)
    provider.response = LLMResponse(
        role="assistant",
        completion_text=json.dumps(
            {"images": [{"image_id": "a", "description": "shape"}]}
        ),
    )
    await describe_images(turn, provider)
    assert provider.calls == 1
    assert turn.budget.image_submissions == 1
    assert turn.references["a"].description_status == "ready"
    assert turn.references["b"].description_status == "pending"
    assert turn.references["c"].description_status == "pending"
