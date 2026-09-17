import base64
import io

import pytest
from PIL import Image

from astrbot.core.agent.message import ImageURLPart
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.image_media_store import (
    ImageMediaStore,
    persist_inline_image_refs,
)
from astrbot.core.utils.media_utils import (
    ImagePayloadTooLargeError,
    ImagePreparationInput,
    ImagePreparationOptions,
    prepare_image_source,
)


def _image(size=(40, 20), image_format="PNG"):
    output = io.BytesIO()
    with Image.new("RGB", size, (30, 60, 90)) as image:
        image.save(output, image_format)
    return output.getvalue()


@pytest.mark.asyncio
async def test_current_plugin_image_part_is_prepared_without_mutating_caller(tmp_path):
    source = tmp_path / "quoted.png"
    original = _image()
    source.write_bytes(original)
    part = ImageURLPart(
        image_url=ImageURLPart.ImageURL(
            url=str(source), id="plugin-image", detail="high"
        )
    ).mark_as_temp()

    context = await ProviderRequest(extra_user_content_parts=[part]).assemble_context()
    payload = context["content"][0]

    assert payload["image_url"]["id"] == "plugin-image"
    assert payload["image_url"]["detail"] == "high"
    assert payload["_no_save"] is True
    assert payload["image_url"]["url"].startswith("data:image/png;base64,")
    assert part.image_url.url == str(source)


@pytest.mark.asyncio
async def test_quoted_user_path_uses_configured_encoded_limit(tmp_path):
    source = tmp_path / "quoted.png"
    source.write_bytes(_image())
    options = ImagePreparationOptions(max_encoded_bytes=1)

    with pytest.raises(ImagePayloadTooLargeError):
        await prepare_image_source(str(source), options=options)


@pytest.mark.asyncio
async def test_cua_dimensions_are_explicit_and_normal_tool_can_resize(tmp_path):
    source = tmp_path / "tool.png"
    source.write_bytes(_image((80, 40)))
    normal = await prepare_image_source(
        str(source), options=ImagePreparationOptions(max_size=20)
    )
    cua = await prepare_image_source(
        str(source),
        options=ImagePreparationOptions(max_size=20, preserve_dimensions=True),
    )

    with Image.open(io.BytesIO(normal.to_bytes())) as image:
        assert max(image.size) <= 20
    with Image.open(io.BytesIO(cua.to_bytes())) as image:
        assert image.size == (80, 40)


def test_temporary_image_part_is_not_persisted(tmp_path):
    image_bytes = _image()
    image_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                    "_no_save": True,
                }
            ],
        }
    ]

    stored = persist_inline_image_refs(history, ImageMediaStore(tmp_path / "media"))

    assert stored == history
    assert not (tmp_path / "media").exists()


@pytest.mark.asyncio
async def test_shared_preparation_input_releases_owned_source(tmp_path):
    source = tmp_path / "plugin-source.png"
    owned = tmp_path / "resolver-owned.tmp"
    data = _image((32, 24))
    source.write_bytes(data)
    owned.write_bytes(b"temporary source")

    prepared = await prepare_image_source(
        ImagePreparationInput(
            str(source),
            source_kind="plugin_mcp",
            cleanup_paths=(owned,),
        )
    )

    assert prepared.to_bytes() == data
    assert not owned.exists()
