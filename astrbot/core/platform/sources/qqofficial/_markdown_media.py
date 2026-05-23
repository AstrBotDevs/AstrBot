"""将 Image 组件转换为 QQ markdown 图片语法的工具。

QQ markdown 支持 `![alt #WIDTHpx #HEIGHTpx](public_url)` 语法内嵌图片，
开放平台会下载转存。这样图片就可以与 keyboard 共存于同一条 msg_type=2 消息。
"""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.message_components import Image


async def image_to_markdown_fragment(image: Image) -> str | None:
    """将 Image 组件转成 markdown 图片片段。

    Returns:
        形如 "\n![img #WIDTHpx #HEIGHTpx](url)\n" 的字符串；
        若文件服务不可用或尺寸读取失败，返回 None（调用方应回退到 msg_type=7）。
    """
    try:
        url = await image.register_to_file_service()
    except Exception as e:
        logger.warning(f"[QQOfficial] 注册图片到文件服务失败，无法转 markdown: {e}")
        return None

    width, height = await _read_image_size(image)
    if width is None or height is None:
        logger.warning(
            "[QQOfficial] 读取图片尺寸失败；不附尺寸的 markdown 图片在 QQ 客户端无法渲染，"
            "回退到 msg_type=7 富媒体路径。"
        )
        return None

    return f"\n![img #{width}px #{height}px]({url})\n"


async def _read_image_size(image: Image) -> tuple[int | None, int | None]:
    try:
        from PIL import Image as PILImage  # noqa: PLC0415
    except ImportError:
        return None, None

    try:
        path = await image.convert_to_file_path()
        with PILImage.open(path) as im:
            return im.width, im.height
    except Exception as e:
        logger.debug(f"[QQOfficial] 读取图片尺寸失败: {e}")
        return None, None
