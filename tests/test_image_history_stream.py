"""Tests for the bounded legacy image history JSON rewriter."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import sqlite3
from pathlib import Path

import pytest

from astrbot.core.image_history_migration import ImageHistoryMigrationError
from astrbot.core.image_history_stream import (
    StagedImage,
    StreamHistoryError,
    _decode_json_string_chunks,
    rewrite_legacy_history_stream,
)


def _reference(number: int) -> dict:
    return {
        "type": "image_ref",
        "schema_version": 1,
        "occurrence_id": f"occurrence-{number}",
        "asset_id": f"asset-{number}",
        "description": "",
        "description_status": "pending",
        "description_version": 0,
    }


class _ReadGuard(io.BytesIO):
    def __init__(self, content: bytes, maximum_read: int) -> None:
        super().__init__(content)
        self.maximum_read = maximum_read
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        assert 0 <= size <= self.maximum_read
        self.read_sizes.append(size)
        return super().read(size)


async def _rewrite(
    raw: bytes,
    staging_dir: Path,
    *,
    chunk_bytes: int = 31,
    max_output_bytes: int = 16 * 1024 * 1024,
    callback=None,
):
    calls: list[StagedImage] = []

    async def import_image(image: StagedImage) -> dict:
        calls.append(image)
        if callback is not None:
            return await callback(image)
        return _reference(len(calls))

    source = _ReadGuard(raw, chunk_bytes)
    output = io.BytesIO()
    stats = await rewrite_legacy_history_stream(
        source,
        output,
        staging_dir=staging_dir,
        import_image=import_image,
        max_output_bytes=max_output_bytes,
        chunk_bytes=chunk_bytes,
    )
    return stats, output, calls, source


def test_rewrites_data_uri_after_type_and_preserves_other_json(tmp_path: Path) -> None:
    source_bytes = b"a small image payload"
    uri = "data:image/png;base64," + base64.b64encode(source_bytes).decode()
    history = [
        {
            "role": "user",
            "provider_extension": {"nested": [1, True, None, "kept"]},
            "content": [
                {"type": "text", "text": "hello", "custom": {"x": 4}},
                {
                    "image_url": {"id": "old", "url": uri},
                    "custom_image_field": "discarded with old image block",
                    "type": "image_url",
                },
            ],
        }
    ]
    raw = json.dumps(history, ensure_ascii=False, separators=(",", ":")).encode()
    seen: list[tuple[int, int, bytes, Path]] = []

    async def import_image(image: StagedImage) -> dict:
        seen.append(
            (
                image.message_index,
                image.part_index,
                image.payload_path.read_bytes(),
                image.payload_path,
            )
        )
        return _reference(1)

    stats, output, calls, source = asyncio.run(
        _rewrite(raw, tmp_path, callback=import_image)
    )

    rewritten = json.loads(output.getvalue())
    assert stats.images_rewritten == 1
    assert stats.input_bytes == len(raw)
    assert stats.output_bytes == len(output.getvalue())
    assert calls[0].message_index == 0
    assert calls[0].part_index == 1
    assert seen[0][:3] == (0, 1, source_bytes)
    assert not seen[0][3].exists()
    assert rewritten[0]["provider_extension"] == history[0]["provider_extension"]
    assert rewritten[0]["content"][0] == history[0]["content"][0]
    assert rewritten[0]["content"][1] == _reference(1)
    assert b" " not in output.getvalue()
    assert max(source.read_sizes) <= 31


def test_supports_string_image_url_and_escaped_keys_and_values(tmp_path: Path) -> None:
    payload = b"payload"
    encoded = base64.b64encode(payload).decode()
    raw = (
        '[{"content":[{"image\\u005furl":"data:image/png;base64,'
        + encoded
        + '","type":"image\\u005furl"}],"role":"user"}]'
    ).encode()

    stats, output, calls, _ = asyncio.run(_rewrite(raw, tmp_path, chunk_bytes=5))

    assert stats.images_rewritten == 1
    assert len(calls) == 1
    assert json.loads(output.getvalue())[0]["content"][0] == _reference(1)


def test_single_large_base64_string_uses_bounded_reads(tmp_path: Path) -> None:
    payload = b"p" * (2 * 1024 * 1024 + 7)
    uri = "data:image/png;base64," + base64.b64encode(payload).decode()
    raw = (
        '[{"role":"user","content":[{"type":"image_url",'
        '"image_url":{"url":"' + uri + '"}}]}]'
    ).encode()
    observed: list[int] = []

    async def import_image(image: StagedImage) -> dict:
        observed.append(image.payload_path.stat().st_size)
        assert image.payload_path.read_bytes() == payload
        return _reference(1)

    stats, output, _, source = asyncio.run(
        _rewrite(raw, tmp_path, chunk_bytes=4093, callback=import_image)
    )

    assert stats.images_rewritten == 1
    assert observed == [len(payload)]
    assert len(output.getvalue()) < 1024
    assert max(source.read_sizes) <= 4093
    assert list(tmp_path.glob("m7-image-*.img")) == []


def test_accepts_sqlite_blob_without_seekable_method(tmp_path: Path) -> None:
    payload = b"sqlite blob payload"
    uri = "data:image/png;base64," + base64.b64encode(payload).decode()
    raw = json.dumps(
        [
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": uri}],
            }
        ],
        separators=(",", ":"),
    ).encode()
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE snapshots (payload BLOB)")
    connection.execute("INSERT INTO snapshots VALUES (?)", (raw,))
    output = io.BytesIO()
    observed: list[bytes] = []

    async def import_image(image: StagedImage) -> dict:
        observed.append(image.payload_path.read_bytes())
        return _reference(1)

    try:
        with connection.blobopen("snapshots", "payload", 1) as source:
            assert not hasattr(source, "seekable")
            stats = asyncio.run(
                rewrite_legacy_history_stream(
                    source,
                    output,
                    staging_dir=tmp_path,
                    import_image=import_image,
                    chunk_bytes=13,
                )
            )
    finally:
        connection.close()

    assert stats.images_rewritten == 1
    assert observed == [payload]
    assert json.loads(output.getvalue())[0]["content"][0] == _reference(1)


def test_duplicate_content_uses_last_value_without_importing_hidden_image(
    tmp_path: Path,
) -> None:
    hidden = base64.b64encode(b"unused").decode()
    raw = (
        '[{"content":[{"type":"image_url","image_url":"data:image/png;base64,'
        + hidden
        + '"}],"content":[{"type":"text","text":"visible"}]}]'
    ).encode()

    stats, output, calls, _ = asyncio.run(_rewrite(raw, tmp_path))

    assert stats.images_rewritten == 0
    assert calls == []
    assert json.loads(output.getvalue()) == [
        {"content": [{"type": "text", "text": "visible"}]}
    ]


def test_local_temp_path_fallback_is_used_but_not_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import astrbot.core.image_history_stream as stream_module

    temp_root = tmp_path / "astrbot-temp"
    temp_root.mkdir()
    local_image = temp_root / "cached.png"
    local_image.write_bytes(b"cached image")
    monkeypatch.setattr(stream_module, "get_astrbot_temp_path", lambda: str(temp_root))
    raw = json.dumps(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": None,
                        "url": local_image.as_posix(),
                    }
                ],
            }
        ],
        separators=(",", ":"),
    ).encode()
    observed: list[Path] = []

    async def import_image(image: StagedImage) -> dict:
        observed.append(image.payload_path)
        assert image.payload_path.read_bytes() == b"cached image"
        return _reference(1)

    stats, output, _, _ = asyncio.run(
        _rewrite(raw, tmp_path / "staging", callback=import_image)
    )

    assert stats.images_rewritten == 1
    assert json.loads(output.getvalue())[0]["content"][0] == _reference(1)
    assert observed == [local_image]
    assert local_image.exists()


def test_remote_image_url_is_rejected_without_network_or_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import astrbot.core.image_history_stream as stream_module

    monkeypatch.setattr(stream_module, "get_astrbot_temp_path", lambda: str(tmp_path))
    raw = json.dumps(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.invalid/image.png"},
                    }
                ],
            }
        ],
        separators=(",", ":"),
    ).encode()
    calls = []

    async def import_image(image: StagedImage) -> dict:
        calls.append(image)
        return _reference(1)

    with pytest.raises(ImageHistoryMigrationError):
        asyncio.run(
            rewrite_legacy_history_stream(
                io.BytesIO(raw),
                io.BytesIO(),
                staging_dir=tmp_path / "staging",
                import_image=import_image,
            )
        )
    assert calls == []


def test_output_limit_fails_and_clears_partial_result(tmp_path: Path) -> None:
    raw = json.dumps(
        [{"role": "user", "content": [{"type": "text", "text": "x" * 2048}]}],
        separators=(",", ":"),
    ).encode()
    output = io.BytesIO(b"previous content")
    calls = []

    async def import_image(image: StagedImage) -> dict:
        calls.append(image)
        return _reference(1)

    with pytest.raises(StreamHistoryError, match="16 MiB"):
        asyncio.run(
            rewrite_legacy_history_stream(
                io.BytesIO(raw),
                output,
                staging_dir=tmp_path,
                import_image=import_image,
                max_output_bytes=128,
                chunk_bytes=11,
            )
        )
    assert output.getvalue() == b""
    assert calls == []


def test_image_payload_limit_is_enforced_before_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import astrbot.core.image_history_stream as stream_module

    monkeypatch.setattr(stream_module, "DEFAULT_MAX_IMAGE_BYTES", 3)
    payload = base64.b64encode(b"four").decode()
    raw = json.dumps(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": f"data:image/png;base64,{payload}",
                    }
                ],
            }
        ],
        separators=(",", ":"),
    ).encode()
    calls = []

    async def import_image(image: StagedImage) -> dict:
        calls.append(image)
        return _reference(1)

    with pytest.raises(ImageHistoryMigrationError) as error:
        asyncio.run(
            rewrite_legacy_history_stream(
                io.BytesIO(raw),
                io.BytesIO(),
                staging_dir=tmp_path,
                import_image=import_image,
                chunk_bytes=7,
            )
        )
    assert error.value.reason == "invalid_image"
    assert calls == []
    assert list(tmp_path.glob("m7-image-*.img")) == []


def test_invalid_json_and_invalid_image_shape_fail_closed(tmp_path: Path) -> None:
    async def import_image(image: StagedImage) -> dict:
        return _reference(1)

    for raw in (b'[{"role":"user",]', b'[{"content":[{"type":"image_url"}]}]'):
        with pytest.raises((StreamHistoryError, ImageHistoryMigrationError)):
            asyncio.run(
                rewrite_legacy_history_stream(
                    io.BytesIO(raw),
                    io.BytesIO(),
                    staging_dir=tmp_path,
                    import_image=import_image,
                    chunk_bytes=5,
                )
            )


def test_data_uri_json_escapes_are_decoded_incrementally(tmp_path: Path) -> None:
    payload = b"\xff\xff"
    encoded = base64.b64encode(payload).decode().replace("/", "\\/")
    raw = (
        '[{"role":"user","content":[{"type":"image_url",'
        '"image_url":{"url":"data:image/png;base64,' + encoded + '"}}]}]'
    ).encode()
    read = io.BytesIO(raw)
    output = io.BytesIO()
    observed: list[bytes] = []

    async def import_image(image: StagedImage) -> dict:
        observed.append(image.payload_path.read_bytes())
        return _reference(1)

    stats = asyncio.run(
        rewrite_legacy_history_stream(
            read,
            output,
            staging_dir=tmp_path,
            import_image=import_image,
            chunk_bytes=4,
        )
    )
    assert stats.images_rewritten == 1
    assert observed == [payload]


def test_string_span_decoder_handles_unicode_and_surrogate_pair() -> None:
    raw = io.BytesIO(b'"\\u0061\\ud83d\\ude00"')
    assert "".join(_decode_json_string_chunks(raw, 0, len(raw.getvalue()), 4)) == "a😀"


@pytest.mark.parametrize(
    "number",
    ["0", "-0", "10", "10009", "-2030", "1.23", "-0.0030", "10e12", "1.20E-03"],
)
def test_preserves_valid_json_number_tokens(tmp_path, number):
    raw = ('[{"role":"user","content":"kept","extra":' + number + "}]").encode()
    _, output, calls, _ = asyncio.run(_rewrite(raw, tmp_path, chunk_bytes=4))
    assert output.getvalue() == raw
    assert json.loads(output.getvalue()) == json.loads(raw)
    assert calls == []


@pytest.mark.parametrize("number", ["01", "-01", "1.", "1e", "1e+", "--1", "+1", ".2"])
def test_rejects_invalid_json_number_tokens(tmp_path, number):
    raw = ('[{"extra":' + number + "}]").encode()
    with pytest.raises(StreamHistoryError):
        asyncio.run(_rewrite(raw, tmp_path, chunk_bytes=4))


def test_preserves_uncaptured_long_unicode_object_key(tmp_path):
    original = [{"role": "user", "content": "kept", "图" * 3000: "unknown field"}]
    raw = json.dumps(original, ensure_ascii=False, separators=(",", ":")).encode()
    _, output, calls, _ = asyncio.run(_rewrite(raw, tmp_path, chunk_bytes=31))
    assert json.loads(output.getvalue()) == original
    assert calls == []
