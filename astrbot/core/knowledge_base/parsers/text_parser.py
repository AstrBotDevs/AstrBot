"""文本文件解析器

支持解析 TXT 和 Markdown 文件。
"""

import codecs

from astrbot.core.knowledge_base.parsers.base import BaseParser, ParseResult

_BOM_UTF16_PAIR = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)


class TextParser(BaseParser):
    """TXT/MD 文本解析器

    支持多种字符编码的自动检测。
    """

    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        """解析文本文件

        尝试使用多种编码解析文件内容。带 BOM 的文件（如 Windows 记事本
        「UTF-8 with BOM」/「Unicode」保存的 txt）按 BOM 直接解码，避免被
        无 BOM 序列误判。

        Args:
            file_content: 文件内容
            file_name: 文件名

        Returns:
            ParseResult: 解析结果,不包含多媒体资源

        Raises:
            ValueError: 如果无法解码文件

        """
        if file_content.startswith(codecs.BOM_UTF8):
            text = file_content.decode("utf-8-sig")
        elif file_content.startswith(_BOM_UTF16_PAIR):
            text = file_content.decode("utf-16")
        else:
            # 尝试多种编码（无 BOM 文件，utf-8 优先，GBK 系兜底）
            for encoding in ["utf-8", "gbk", "gb2312", "gb18030"]:
                try:
                    text = file_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError(f"无法解码文件: {file_name}")

        # 文本文件无多媒体资源
        return ParseResult(text=text, media=[])
