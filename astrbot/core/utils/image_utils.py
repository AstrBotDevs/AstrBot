"""图片处理工具函数。
提供 MIME 类型检测与 base64 Data URL 编码等公共能力，
供 ProviderRequest 及各 Provider 适配器复用，避免重复实现。
"""

from __future__ import annotations

import base64


def detect_image_mime_type(header_bytes: bytes) -> str:
    """根据文件头magic bytes检测图片的实际 MIME 类型。

    依次匹配常见图片格式的文件头特征，均不匹配时回退到 image/jpeg
    以保持向后兼容。支持的格式：JPEG、PNG、GIF、WebP、BMP、TIFF、
    ICO、SVG、AVIF、HEIF/HEIC。

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
    # SVG 为文本格式，检测头部是否含有 <svg 标签。
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
# 其他二进制格式的魔术字节最多 16 字节，SVG 需要更多以跳过可能的 XML 声明。
_HEADER_READ_SIZE = 256

# 对应 _HEADER_READ_SIZE 字节所需的 base64 字符数。
# base64 每 3 字节编码为 4 字符，向上取整后再补充少量余量保证填充对齐。
# ceil(256 / 3) * 4 = 344
_BASE64_SAMPLE_CHARS = 344


async def encode_image_to_base64_url(image_url: str) -> str:
    """将图片转换为 base64 Data URL，自动检测实际 MIME 类型。

    原实现硬编码 image/jpeg，会导致 PNG 等格式在严格校验的接口上报错。
    现通过读取文件头魔术字节来推断正确的 MIME 类型。

    对于 SVG 文件，需要读取至少 256 字节的头部才能可靠检测，
    因此统一将读取/解码量提升到 256 字节，消除之前字节数不足的问题。

    Args:
        image_url: 本地文件路径，或以 "base64://" 开头的 base64 字符串。

    Returns:
        形如 "data:image/png;base64,..." 的 Data URL 字符串。
    """
    if image_url.startswith("base64://"):
        raw_b64 = image_url[len("base64://"):]
        # 从 base64 数据中解码足量字节以检测实际格式。
        # 取前 344 个 base64 字符可解码出约 258 字节，足以覆盖 SVG 检测所需的 256 字节。
        try:
            sample = raw_b64[:_BASE64_SAMPLE_CHARS]
            # 确保 base64 填充正确，避免解码报错
            missing_padding = len(sample) % 4
            if missing_padding:
                sample += '=' * (4 - missing_padding)
            header_bytes = base64.b64decode(sample)
            mime_type = detect_image_mime_type(header_bytes)
        except Exception:
            # 解码失败时安全回退
            mime_type = "image/jpeg"
        return f"data:{mime_type};base64,{raw_b64}"

    with open(image_url, "rb") as f:
        # 读取 256 字节用于格式检测，以支持需要较多头部数据的 SVG 等格式，
        # 再 seek 回起点读取完整内容进行 base64 编码。
        header_bytes = f.read(_HEADER_READ_SIZE)
        mime_type = detect_image_mime_type(header_bytes)
        f.seek(0)
        image_bs64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime_type};base64,{image_bs64}"