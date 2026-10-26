"""PDF 文件解析器

支持解析 PDF 文件中的文本和图片资源。
"""

import io
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from astrbot.core.knowledge_base.parsers.base import (
    BaseParser,
    MediaItem,
    ParseResult,
)


class PDFParser(BaseParser):
    """PDF 文档解析器

    提取 PDF 中的文本内容和嵌入的图片资源。
    """

    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        """解析 PDF 文件

        Args:
            file_content: 文件内容
            file_name: 文件名

        Returns:
            ParseResult: 包含文本和图片的解析结果

        """
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file)

        text_parts = []
        media_items = []

        # 提取文本
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        # 提取图片
        image_counter = 0
        for page_num, page in enumerate(reader.pages):
            try:
                images = page.images
                for image_name in images.keys():
                    try:
                        # pypdf encodes pixel streams and applies color spaces
                        # and soft masks; raw get_data() bytes are not PNG files.
                        image = images[image_name]
                        if image.image is None:
                            continue
                        ext = Path(image.name).suffix
                        mime_type = Image.MIME[image.image.format]

                        image_counter += 1
                        media_items.append(
                            MediaItem(
                                media_type="image",
                                file_name=f"page_{page_num}_img_{image_counter}{ext}",
                                content=image.data,
                                mime_type=mime_type,
                            ),
                        )
                    except Exception:
                        # A broken image must not hide other images on the page.
                        continue
            except Exception:
                # A page-level image error must not discard other pages or text.
                continue

        full_text = "\n\n".join(text_parts)
        return ParseResult(text=full_text, media=media_items)
