"""图片处理工具函数。
提供 MIME 类型检测与 base64 Data URL 编码等公共能力，
供 ProviderRequest 及各 Provider 适配器复用，避免重复实现。
"""

from __future__ import annotations

import asyncio
import base64
import binascii

from astrbot import logger


def detect_image_mime_type(header_bytes: bytes) -> str:
    """根据文件头magic bytes检测图片的实际 MIME 类型。

    依次匹配常见图片格式的文件头特征，均不匹配时回退到 image/jpeg
    以保持向后兼容。支持的格式：JPEG、PNG、GIF、WebP、BMP、TIFF、
    ICO、SVG、AVIF、HEIF/HEIC。

    注意：此函数为纯检测逻辑，不输出日志，日志由调用方负责。

    Args:
        header_bytes: 文件头原始字节。SVG检测需要至少 256 字节；
                      其他二进制格式最多需要 16 字节。

    Returns:
        对应的 MIME 类型字符串，例如 "image/png"。
    """
    if len(header_bytes) >= 3 and header_bytes[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if len(header_bytes) >= 8 and header_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if len(header_bytes) >= 4 and header_bytes[:4] == b'GIF8':
        return "image/gif"
    # WebP: RIFF????WEBP
    if len(header_bytes) >= 12 and header_bytes[:4] == b'RIFF' and header_bytes[8:12] == b'WEBP':
        return "image/webp"
    if len(header_bytes) >= 2 and header_bytes[:2] == b'BM':
        return "image/bmp"
    # TIFF: 小端 (II) 或大端 (MM)
    if len(header_bytes) >= 4 and header_bytes[:4] in (b'II\x2a\x00', b'MM\x00\x2a'):
        return "image/tiff"
    if len(header_bytes) >= 4 and header_bytes[:4] == b'\x00\x00\x01\x00':
        return "image/x-icon"
    # SVG 为文本格式，检测头部是否含有 《svg 标签。
    # 调用方需传入至少 256 字节以覆盖带有 XML 声明的 SVG 文件。
    if b'<svg' in header_bytes[:256].lower():
        return "image/svg+xml"
    # AVIF: ftyp box brand = avif
    if len(header_bytes) >= 12 and header_bytes[4:12] == b'ftypavif':
        return "image/avif"
    # HEIF/HEIC: ftyp box，brand 为 heic/heix/hevc/hevx/mif1
    if len(header_bytes) >= 12 and header_bytes[4:8] == b'ftyp':
        brand = header_bytes[8:12]
        if brand in (b'heic', b'heix', b'hevc', b'hevx', b'mif1'):
            return "image/heif"
    # 无法识别，回退到 image/jpeg
    return "image/jpeg"


# SVG 检测所需的最小头部字节数。
_HEADER_READ_SIZE = 256

# 对应 _HEADER_READ_SIZE 字节所需的 base64 字符数。
# ceil(256 / 3) * 4 = 344
_BASE64_SAMPLE_CHARS = 344


def detect_mime_type_from_base64_str(
    raw_b64: str,
    source_hint: str = "",
) -> str:
    """从 base64 编码字符串中采样解码头部字节并检测 MIME 类型。

    统一所有 base64 输入的 MIME 检测逻辑，避免在多处重复
    采样/解码/回退的代码。解码失败时安全回退到 image/jpeg。

    Args:
        raw_b64: 原始 base64 编码字符串（不含 "base64://" 前缀）。
        source_hint: 日志中标识调用来源的提示字符串。

    Returns:
        检测到的 MIME 类型字符串。
    """
    label = source_hint or "base64"
    try:
        sample = raw_b64[:_BASE64_SAMPLE_CHARS]
        missing_padding = len(sample) % 4
        if missing_padding:
            sample += '=' * (4 - missing_padding)
        header_bytes = base64.b64decode(sample)
    except (binascii.Error, ValueError) as exc:
        logger.debug(
            "[%s] base64 解码失败: %s，硬编码回退为 image/jpeg",
            label,
            exc,
        )
        return "image/jpeg"

    mime_type = detect_image_mime_type(header_bytes)
    logger.debug(
        "[%s] 魔术字节检测命中，识别为 %s 格式",
        label,
        mime_type,
    )
    return mime_type


def _sync_encode_from_file(path: str) -> tuple[str, str]:
    """同步读取文件并编码为 base64，同时检测 MIME 类型。

    此函数包含阻塞式文件 I/O，设计为通过 run_in_executor
    在线程池中执行，避免阻塞 asyncio 事件循环。

    Args:
        path: 本地文件路径。

    Returns:
        (mime_type, image_bs64) 元组。
    """
    with open(path, "rb") as f:
        header_bytes = f.read(_HEADER_READ_SIZE)
        mime_type = detect_image_mime_type(header_bytes)
        f.seek(0)
        image_bs64 = base64.b64encode(f.read()).decode("utf-8")
    return mime_type, image_bs64


async def encode_image_to_base64_url(image_url: str) -> str:
    """将图片转换为 base64 Data URL，自动检测实际 MIME 类型。

    对于 base64:// 输入，委托 detect_mime_type_from_base64_str
    统一处理采样/解码/回退逻辑。
    对于文件路径输入，阻塞式文件 I/O 通过 run_in_executor
    移至线程池执行，避免在高并发场景下阻塞 asyncio 事件循环。

    Args:
        image_url: 本地文件路径，或以 "base64://" 开头的 base64 字符串。

    Returns:
        形如 "data:image/png;base64,..." 的 Data URL 字符串。
    """
    if image_url.startswith("base64://"):
        raw_b64 = image_url[len("base64://"):]
        mime_type = detect_mime_type_from_base64_str(
            raw_b64, source_hint="image_utils/base64://"
        )
        return f"data:{mime_type};base64,{raw_b64}"

    # 文件 I/O 为阻塞操作，移至线程池执行以保持事件循环响应性
    loop = asyncio.get_running_loop()
    mime_type, image_bs64 = await loop.run_in_executor(
        None, _sync_encode_from_file, image_url
    )
    logger.debug(
        "[image_utils][%s] 魔术字节检测命中，识别为 %s 格式",
        image_url,
        mime_type,
    )
    return f"data:{mime_type};base64,{image_bs64}"
