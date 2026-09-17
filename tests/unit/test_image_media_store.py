"""Tests for durable image object ownership and authorization."""

import base64
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from astrbot.core.utils import media_utils
from astrbot.core.utils.image_media_store import ImageMediaStore


def _png() -> bytes:
    output = io.BytesIO()
    with Image.new("RGBA", (9, 7), (20, 40, 60, 100)) as image:
        image.save(output, "PNG")
    return output.getvalue()


def test_store_deduplicates_and_round_trips_exact_bytes(tmp_path):
    store = ImageMediaStore(tmp_path / "media")
    data = _png()
    first = store.put(data, detail="high")
    second = store.put(data, detail="low")

    assert first.media_id == second.media_id
    assert first.width == 9 and first.height == 7
    assert store.read(first, {first.media_id}) == data
    assert len(list((tmp_path / "media").glob("*.bin"))) == 1


def test_shared_blob_keeps_each_reference_metadata(tmp_path):
    store = ImageMediaStore(tmp_path / "media")
    data = _png()
    first = store.put(data, detail="low", image_id="first")
    second = store.put(data, detail="high", image_id="second")
    assert first.detail == "low" and first.image_id == "first"
    assert second.detail == "high" and second.image_id == "second"


def test_shared_blob_keeps_declared_mime_per_reference(tmp_path):
    store = ImageMediaStore(tmp_path / "media")
    data = _png()
    first = store.put(data, mime_type="image/png")
    second = store.put(data, mime_type="image/custom", image_id="custom")
    assert first.mime_type == "image/png"
    assert second.mime_type == "image/custom"
    assert store.read(second, {second.media_id}) == data


def test_store_rejects_unauthorized_reference_and_missing_object(tmp_path):
    store = ImageMediaStore(tmp_path / "media")
    ref = store.put(_png())
    with pytest.raises(PermissionError):
        store.read(ref, set())
    (tmp_path / "media" / f"{ref.media_id}.bin").unlink()
    with pytest.raises(FileNotFoundError):
        store.read(ref, {ref.media_id})


def test_store_never_commits_invalid_or_partial_media(tmp_path):
    store = ImageMediaStore(tmp_path / "media")
    with pytest.raises(ValueError):
        store.put(b"not an image")
    assert not list((tmp_path / "media").glob("*.bin"))
    assert not list((tmp_path / "media").glob("*.json"))


def test_persist_inline_image_refs_rejects_oversized_payload_before_decode(
    tmp_path, monkeypatch
):
    store = ImageMediaStore(tmp_path / "media")
    monkeypatch.setattr(media_utils, "MODEL_IMAGE_MAX_INPUT_BYTES", 4)
    encoded = base64.b64encode(b"12345").decode("ascii")

    with pytest.raises(media_utils.ImagePayloadTooLargeError, match="input exceeds"):
        from astrbot.core.utils.image_media_store import persist_inline_image_refs

        persist_inline_image_refs(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        }
                    ],
                }
            ],
            store,
        )

    assert not list((tmp_path / "media").glob("*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_message", [False, True])
async def test_reference_materialization_preserves_history_and_bytes(
    tmp_path, runtime_message
):
    import base64

    from astrbot.core.agent.message import Message
    from astrbot.core.utils.image_media_store import materialize_image_media_refs

    store = ImageMediaStore(tmp_path / "media")
    data = _png()
    ref = store.put(data, detail="high")
    history = [{"role": "user", "content": [ref.model_dump()]}]
    messages = (
        [Message.model_validate(item) for item in history]
        if runtime_message
        else history
    )
    result = await materialize_image_media_refs(messages, store)
    dumped = result[0].model_dump() if runtime_message else result[0]
    image = dumped["content"][0]["image_url"]
    assert base64.b64decode(image["url"].split(",", 1)[1]) == data
    assert image["detail"] == "high"
    assert history[0]["content"][0]["type"] == "image_media_ref"
    if runtime_message:
        assert messages[0].content[0].type == "image_media_ref"


@pytest.mark.asyncio
async def test_unselected_reference_is_not_read(tmp_path, monkeypatch):
    from astrbot.core.utils.image_media_store import materialize_image_media_refs

    store = ImageMediaStore(tmp_path / "media")
    store.put(_png())

    def fail_read(*args, **kwargs):
        raise AssertionError("An unselected image must not be opened")

    monkeypatch.setattr(store, "read", fail_read)
    selected = [{"role": "user", "content": "Only this text is in the active window"}]
    assert await materialize_image_media_refs(selected, store) == selected


@pytest.mark.asyncio
async def test_missing_reference_has_bounded_placeholder(tmp_path):
    from astrbot.core.utils.image_media_store import materialize_image_media_refs

    store = ImageMediaStore(tmp_path / "media")
    ref = store.put(_png())
    (store.root / f"{ref.media_id}.bin").unlink()
    result = await materialize_image_media_refs(
        [{"role": "user", "content": [ref.model_dump()]}], store
    )
    assert result[0]["content"] == [{"type": "text", "text": "[Image unavailable]"}]


def test_reference_rejects_path_traversal():
    from astrbot.core.utils.image_media_store import ImageMediaRef

    with pytest.raises(ValueError):
        ImageMediaRef("../outside", "image/png", 1, 1, 10)


def test_deduplicated_corrupt_object_is_rejected(tmp_path):
    store = ImageMediaStore(tmp_path / "media")
    ref = store.put(_png())
    (store.root / f"{ref.media_id}.bin").write_bytes(b"corrupt")
    with pytest.raises(OSError):
        store.put(_png())


@pytest.mark.parametrize("failure_point", ["link", "fsync"])
def test_write_failure_leaves_no_usable_reference(tmp_path, monkeypatch, failure_point):
    import astrbot.core.utils.image_media_store as media_store

    store = ImageMediaStore(tmp_path / "media")
    original_link = os.link
    original_fsync = os.fsync

    if failure_point == "link":

        def fail_link(source, target):
            raise OSError("injected link failure")

        monkeypatch.setattr(media_store.os, "link", fail_link)
    else:

        def fail_fsync(fd):
            raise OSError("injected fsync failure")

        monkeypatch.setattr(media_store.os, "fsync", fail_fsync)

    with pytest.raises(OSError):
        store.put(_png())
    assert not list(store.root.glob("*.json"))
    if failure_point == "fsync":
        assert not list(store.root.iterdir())
    assert original_link and original_fsync


def test_metadata_replace_failure_is_repaired_by_next_put(tmp_path, monkeypatch):
    import astrbot.core.utils.image_media_store as media_store

    store = ImageMediaStore(tmp_path / "media")
    original_link = os.link
    failed = False

    def fail_metadata_link(source, target):
        nonlocal failed
        if target.suffix == ".json" and not failed:
            failed = True
            raise OSError("injected metadata link failure")
        return original_link(source, target)

    monkeypatch.setattr(media_store.os, "link", fail_metadata_link)
    with pytest.raises(OSError):
        store.put(_png())
    assert not list(store.root.glob("*.json"))
    ref = store.put(_png(), detail="next")
    assert store.read(ref, {ref.media_id}) == _png()


def test_concurrent_same_bytes_puts_return_independent_references(tmp_path):
    data = _png()

    def put(detail):
        return ImageMediaStore(tmp_path / "media").put(
            data, detail=detail, image_id=detail
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        refs = list(executor.map(put, ["first", "second"]))
    assert {ref.detail for ref in refs} == {"first", "second"}
    assert {ref.image_id for ref in refs} == {"first", "second"}
    for ref in refs:
        assert ImageMediaStore(tmp_path / "media").read(ref, {ref.media_id}) == data


def test_partial_reference_metadata_missing_is_not_usable(tmp_path):
    store = ImageMediaStore(tmp_path / "media")
    data = _png()
    ref = store.put(data)
    (store.root / f"{ref.media_id}.json").unlink()
    with pytest.raises(OSError, match="incomplete"):
        store.read(ref, {ref.media_id})


@pytest.mark.parametrize("suffix", [".bin", ".json"])
def test_symlinked_media_entries_are_rejected(tmp_path, suffix):
    store = ImageMediaStore(tmp_path / "media")
    ref = store.put(_png())
    target = store.root / f"{ref.media_id}{suffix}"
    target.unlink()
    target.symlink_to(tmp_path / "outside")
    with pytest.raises(OSError):
        store.read(ref, {ref.media_id})


def test_metadata_tampering_and_byte_size_tampering_are_rejected(tmp_path):
    store = ImageMediaStore(tmp_path / "media")
    ref = store.put(_png(), detail="high", image_id="original-id")
    metadata_path = store.root / f"{ref.media_id}.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["detail"] = "low"
    metadata_path.write_text(json.dumps(metadata))
    assert store.read(ref, {ref.media_id}) == _png()
    metadata["detail"] = ref.detail
    metadata["byte_size"] = ref.byte_size + 1
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(OSError):
        store.read(ref, {ref.media_id})


@pytest.mark.asyncio
async def test_materialized_provider_prefix_preserves_mime_detail_id_and_bytes(
    tmp_path,
):
    import base64

    from astrbot.core.utils.image_media_store import materialize_image_media_refs

    store = ImageMediaStore(tmp_path / "media")
    data = _png()
    ref = store.put(data, mime_type="image/png", detail="high", image_id="img-7")
    result = await materialize_image_media_refs(
        [{"role": "user", "content": [ref.model_dump()]}], store
    )
    image_url = result[0]["content"][0]["image_url"]
    assert image_url == {
        "url": "data:image/png;base64," + base64.b64encode(data).decode(),
        "detail": "high",
        "id": "img-7",
    }


def test_shared_reference_survives_restart_and_temp_cleanup(tmp_path):
    data = _png()
    first = ImageMediaStore(tmp_path / "media")
    ref = first.put(data)
    (first.root / "orphan.tmp").write_bytes(b"orphan")
    restarted = ImageMediaStore(tmp_path / "media")
    assert restarted.read(ref, {ref.media_id}) == data
    assert (restarted.root / "orphan.tmp").exists()


def test_symlinked_store_root_is_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    root = tmp_path / "media"
    root.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError, match="root"):
        ImageMediaStore(root).put(_png())


def test_memory_error_is_not_swallowed(tmp_path, monkeypatch):
    store = ImageMediaStore(tmp_path / "media")
    ref = store.put(_png())

    def fail_read(*args, **kwargs):
        raise MemoryError("injected")

    monkeypatch.setattr(store, "read", fail_read)

    async def run():
        from astrbot.core.utils.image_media_store import materialize_image_media_refs

        return await materialize_image_media_refs(
            [{"role": "user", "content": [ref.model_dump()]}], store
        )

    with pytest.raises(MemoryError, match="injected"):
        import asyncio

        asyncio.run(run())
