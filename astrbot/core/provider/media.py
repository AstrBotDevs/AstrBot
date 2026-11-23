"""Small media operations shared by provider adapters."""

import base64

import aiofiles
import anyio


async def image_data_url(image_url: str) -> str:
    """Encode a local image or expand an existing base64 image reference."""
    if image_url.startswith("base64://"):
        return image_url.replace("base64://", "data:image/jpeg;base64,")
    async with aiofiles.open(image_url, "rb") as image_file:
        encoded = base64.b64encode(await image_file.read()).decode("utf-8")
    return "data:image/jpeg;base64," + encoded


async def is_silk_file(file_path: str) -> bool:
    """Recognize the SILK marker in the first eight bytes."""
    async with await anyio.open_file(file_path, "rb") as audio_file:
        return b"SILK" in await audio_file.read(8)


def initial_text_content(
    text: str, *, has_images: bool, has_audio: bool, has_extra_parts: bool
) -> list[dict[str, str]]:
    """Start user content with text or the matching media placeholder."""
    if not text:
        if has_images:
            text = "[Image]"
        elif has_audio:
            text = "[Audio]"
        elif has_extra_parts:
            text = " "
    return [{"type": "text", "text": text}] if text else []
