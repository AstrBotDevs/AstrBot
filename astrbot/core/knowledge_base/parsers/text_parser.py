"""文本文件解析器

支持解析 TXT 和 Markdown 文件。
"""

from astrbot.core.knowledge_base.parsers.base import BaseParser, ParseResult


class TextParser(BaseParser):
    """TXT/MD 文本解析器

    支持多种字符编码的自动检测。
    """

    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        """解析文本文件

        尝试使用多种编码解析文件内容。

        Args:
            file_content: 文件内容
            file_name: 文件名

        Returns:
            ParseResult: 解析结果,不包含多媒体资源

        Raises:
            ValueError: 如果无法解码文件

        """
        # 尝试多种编码
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
