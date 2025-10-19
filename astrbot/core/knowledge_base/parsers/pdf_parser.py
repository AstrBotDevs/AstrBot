"""PDF 文件解析器

支持解析 PDF 文件中的文本和图片资源。
"""

import io

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
                # 安全检查 Resources
                if "/Resources" not in page:
                    continue

                resources = page["/Resources"]
                if not resources or "/XObject" not in resources:
                    continue

                xobjects = resources["/XObject"].get_object()
                if not xobjects:
                    continue

                for obj_name in xobjects:
                    try:
                        obj = xobjects[obj_name]

                        if obj.get("/Subtype") != "/Image":
                            continue

                        # 提取图片数据
                        image_data = obj.get_data()

                        # 确定格式
                        filter_type = obj.get("/Filter", "")
                        if filter_type == "/DCTDecode":
                            ext = "jpg"
                            mime_type = "image/jpeg"
                        elif filter_type == "/FlateDecode":
                            ext = "png"
                            mime_type = "image/png"
                        else:
                            ext = "png"
                            mime_type = "image/png"

                        image_counter += 1
                        media_items.append(
                            MediaItem(
                                media_type="image",
                                file_name=f"page_{page_num}_img_{image_counter}.{ext}",
                                content=image_data,
                                mime_type=mime_type,
                            )
                        )
                    except Exception:
                        # 单个图片提取失败不影响整体
                        continue
            except Exception:
                # 页面处理失败不影响其他页面
                continue

        full_text = "\n\n".join(text_parts)
        return ParseResult(text=full_text, media=media_items)
