"""Group-chat image captions should see animation frames, not one still."""

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from astrbot.api.provider import Provider
from astrbot.builtin_stars.astrbot import group_chat_context as gcc
from astrbot.core.utils import media_utils as media


class _CaptionProvider(Provider):
    def __init__(self) -> None:
        super().__init__({}, {})
        self.calls: list[dict] = []

    def get_current_key(self) -> str:
        return ""

    def set_key(self, key: str) -> None:
        return None

    async def get_models(self) -> list[str]:
        return []

    async def text_chat(self, **kwargs):
        path = kwargs["image_urls"][0]
        with Image.open(path) as image:
            kwargs["snapshot"] = (
                image.format,
                image.size,
                image.getpixel((image.width // 2, image.height // 2)),
            )
        self.calls.append(kwargs)
        return SimpleNamespace(completion_text="described")


def _context(provider: Provider) -> gcc.GroupChatContext:
    return gcc.GroupChatContext(
        acm=SimpleNamespace(),
        context=SimpleNamespace(
            get_using_provider_async=_await(provider),
            get_provider_by_id=lambda _provider_id: provider,
        ),
    )


def _await(provider: Provider):
    async def get_using_provider_async():
        return provider

    return get_using_provider_async


def _save_gif(path: Path, colors: list[tuple[int, int, int]]) -> None:
    frames = [Image.new("RGB", (12, 8), color) for color in colors]
    frames[0].save(
        path,
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )
    for frame in frames:
        frame.close()


@pytest.mark.asyncio
async def test_gif_caption_sends_a_frame_montage(tmp_path, monkeypatch):
    monkeypatch.setattr(gcc, "get_astrbot_temp_path", lambda: str(tmp_path))
    source = tmp_path / "sticker.jpg"
    _save_gif(source, [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)])
    provider = _CaptionProvider()

    text = await _context(provider).get_image_caption(
        str(source),
        "",
        "Describe the image.",
    )

    assert text == "described"
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert "3x3 montage" in call["prompt"]
    assert "Describe the image." in call["prompt"]
    assert call["persist"] is False
    image_format, size, _pixel = call["snapshot"]
    assert image_format == "JPEG"
    assert size[0] > 12 and size[1] > 8
    assert source.exists()
    assert not Path(call["image_urls"][0]).exists()


@pytest.mark.asyncio
async def test_still_caption_keeps_the_original_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(gcc, "get_astrbot_temp_path", lambda: str(tmp_path))
    source = tmp_path / "still.png"
    Image.new("RGB", (20, 10), "red").save(source)
    provider = _CaptionProvider()

    await _context(provider).get_image_caption(str(source), "", "Describe the image.")

    call = provider.calls[0]
    assert call["prompt"] == "Describe the image."
    assert call["image_urls"] == [str(source)]
    assert source.exists()


def _use_temp(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gcc, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(media, "get_astrbot_temp_path", lambda: str(tmp_path))


def _data_uri(path: Path, mime: str) -> str:
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "mime", "animated"),
    [("still.png", "image/png", False), ("motion.gif", "image/gif", True)],
)
async def test_caption_removes_materialized_inputs(
    tmp_path, monkeypatch, name, mime, animated
):
    _use_temp(monkeypatch, tmp_path)
    source = tmp_path / name
    if animated:
        _save_gif(source, [(255, 0, 0), (0, 255, 0), (0, 0, 255)])
    else:
        Image.new("RGB", (8, 8), "blue").save(source)
    provider = _CaptionProvider()

    await _context(provider).get_image_caption(
        _data_uri(source, mime),
        "",
        "Describe the image.",
    )

    leftovers = [
        path.name
        for path in tmp_path.iterdir()
        if path.name.startswith(("media_", "model_image_"))
    ]
    assert leftovers == []
    if animated:
        assert "3x3 montage" in provider.calls[0]["prompt"]
    else:
        assert provider.calls[0]["prompt"] == "Describe the image."


def _temp_names(tmp_path: Path) -> list[str]:
    return [
        path.name
        for path in tmp_path.iterdir()
        if path.name.startswith(("media_", "model_image_"))
    ]


@pytest.mark.asyncio
async def test_oversized_data_uri_is_removed_before_the_error_propagates(
    tmp_path, monkeypatch
):
    _use_temp(monkeypatch, tmp_path)
    monkeypatch.setattr(media, "MODEL_IMAGE_MAX_INPUT_BYTES", 1)
    source = tmp_path / "huge.png"
    Image.new("RGB", (8, 8), "blue").save(source)
    provider = _CaptionProvider()

    with pytest.raises(media.ImageInputTooLargeError):
        await _context(provider).get_image_caption(
            _data_uri(source, "image/png"),
            "",
            "Describe the image.",
        )

    assert provider.calls == []
    assert _temp_names(tmp_path) == []


@pytest.mark.asyncio
async def test_oversized_local_file_is_kept(tmp_path, monkeypatch):
    _use_temp(monkeypatch, tmp_path)
    monkeypatch.setattr(media, "MODEL_IMAGE_MAX_INPUT_BYTES", 1)
    source = tmp_path / "huge.png"
    Image.new("RGB", (8, 8), "blue").save(source)
    provider = _CaptionProvider()

    with pytest.raises(media.ImageInputTooLargeError):
        await _context(provider).get_image_caption(
            str(source),
            "",
            "Describe the image.",
        )

    assert provider.calls == []
    assert source.exists()
