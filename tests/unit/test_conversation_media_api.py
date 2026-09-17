import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from astrbot.dashboard.services.conversation_service import (
    ConversationService,
    ConversationServiceError,
)


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_media_preview_requires_database_owner_and_reference(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "astrbot.dashboard.services.conversation_service.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    data = _image_bytes()
    from astrbot.core.utils.image_media_store import ImageMediaStore

    ref = ImageMediaStore(Path(tmp_path) / "media").put(data, "image/png")
    history = json.dumps([{"content": [ref.model_dump()]}])
    conversation = SimpleNamespace(user_id="owner", history=history)

    class Db:
        async def get_conversation_by_id(self, cid):
            return conversation if cid == "cid" else None

    service = ConversationService(Db(), SimpleNamespace(conversation_manager=None))
    result = await service.get_conversation_media("owner", "cid", ref.media_id)
    assert result.data == data

    with pytest.raises(ConversationServiceError):
        await service.get_conversation_media("other", "cid", ref.media_id)
    with pytest.raises(ConversationServiceError):
        await service.get_conversation_media("owner", "cid", "0" * 64)


@pytest.mark.asyncio
async def test_media_preview_does_not_cross_conversation_reference_boundary(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "astrbot.dashboard.services.conversation_service.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    from astrbot.core.utils.image_media_store import ImageMediaStore

    ref = ImageMediaStore(Path(tmp_path) / "media").put(_image_bytes(), "image/png")
    conversation = SimpleNamespace(user_id="owner", history=json.dumps([]))

    class Db:
        async def get_conversation_by_id(self, cid):
            return conversation if cid == "different-conversation" else None

    service = ConversationService(Db(), SimpleNamespace(conversation_manager=None))
    with pytest.raises(ConversationServiceError, match="媒体不存在"):
        await service.get_conversation_media(
            "owner", "different-conversation", ref.media_id
        )


@pytest.mark.asyncio
async def test_media_preview_missing_or_corrupt_does_not_expose_path(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "astrbot.dashboard.services.conversation_service.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    from astrbot.core.utils.image_media_store import ImageMediaStore

    store = ImageMediaStore(Path(tmp_path) / "media")
    ref = store.put(_image_bytes(), "image/png")
    conversation = SimpleNamespace(
        user_id="owner", history=json.dumps([{"content": [ref.model_dump()]}])
    )

    class Db:
        async def get_conversation_by_id(self, cid):
            return conversation

    service = ConversationService(Db(), SimpleNamespace(conversation_manager=None))
    (Path(tmp_path) / "media" / f"{ref.media_id}.bin").write_bytes(b"corrupt")
    with pytest.raises(ConversationServiceError) as exc_info:
        await service.get_conversation_media("owner", "cid", ref.media_id)
    assert str(tmp_path) not in str(exc_info.value)

    (Path(tmp_path) / "media" / f"{ref.media_id}.bin").unlink()
    with pytest.raises(ConversationServiceError) as exc_info:
        await service.get_conversation_media("owner", "cid", ref.media_id)
    assert str(tmp_path) not in str(exc_info.value)


@pytest.mark.asyncio
async def test_export_materializes_refs_with_detail_and_image_id(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "astrbot.dashboard.services.conversation_service.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    from astrbot.core.utils.image_media_store import ImageMediaStore

    store = ImageMediaStore(Path(tmp_path) / "media")
    ref = store.put(_image_bytes(), "image/png", "high")
    ref = type(ref)(
        ref.media_id,
        ref.mime_type,
        ref.width,
        ref.height,
        ref.byte_size,
        "high",
        1,
        "img-1",
    )
    conversation = SimpleNamespace(
        user_id="owner",
        history=json.dumps([{"role": "user", "content": [ref.model_dump()]}]),
        platform_id="test",
        title="title",
        persona_id=None,
        created_at=0,
        updated_at=0,
    )

    class Manager:
        async def get_conversation(self, **_kwargs):
            return conversation

    service = ConversationService(
        SimpleNamespace(), SimpleNamespace(conversation_manager=Manager())
    )
    exported = await service.export_conversations(
        {"conversations": [{"user_id": "owner", "cid": "cid"}]}
    )
    record = json.loads(exported.file_obj.read())
    image = record["content"][0]["content"][0]["image_url"]
    assert image["detail"] == "high"
    assert image["id"] == "img-1"
