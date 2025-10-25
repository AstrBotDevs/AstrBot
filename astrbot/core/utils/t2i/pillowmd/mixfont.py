import os
from typing import Dict
from PIL import ImageFont
from PIL.ImageFont import FreeTypeFont
from fontTools.ttLib import TTFont
import pillowlatex
from pathlib import Path


class MixFont:
    """混合字体类"""

    _size_cache: Dict["MixFont", Dict[str, tuple[int, int]]] = {}
    _font_cache: Dict[str, "MixFont"] = {}
    _latex_font_cache: Dict[str, pillowlatex.MixFont] = {}

    def __init__(self, path: str, size: int = 10) -> None:
        # 字体路径
        self.path = os.path.abspath(path)
        # 字体名称
        self.name = os.path.basename(self.path)
        # 字体大小
        self.size = size
        # 字体的 FreeTypeFont 对象
        self.ft_font: FreeTypeFont = ImageFont.truetype(self.path, size)
        # 字体字符集
        self.font_dict = self._load_cmap(self.path)

    @staticmethod
    def _load_cmap(font_path: str) -> set[int]:
        """返回字体支持的字形 Unicode 码位集合"""
        try:
            with TTFont(font_path) as tt:
                return set(tt.getBestCmap().keys())
        except Exception:
            return set()

    # -------------- 公有接口 --------------
    def ChoiceFont(self, char: str) -> FreeTypeFont | None:
        """返回能渲染该字符的字体"""
        if ord(char) in self.font_dict:
            return self.ft_font

    def CheckChar(self, char: str) -> bool:
        """判断主字体是否支持该字符"""
        return ord(char) in self.font_dict

    def GetSize(self, text: str) -> tuple[int, int]:
        """计算文本在字体下的宽高"""
        if not text:
            return 0, 0

        # 优先使用缓存
        cache = self._size_cache.setdefault(self, {})
        if text in cache:
            return cache[text]

        # 确定可用字体
        use_font = self.ft_font
        for ch in text:
            if not self.CheckChar(ch):
                alt = self.ChoiceFont(ch)
                if alt:
                    use_font = alt
                break

        bbox = use_font.getbbox(text)
        size = int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])
        cache[text] = size
        return size

    @classmethod
    def GetMixFont(cls, font_path: str | Path, font_size: int) -> "MixFont":
        """工厂方法"""
        font_path = str(font_path)
        if not os.path.isfile(font_path):
            raise FileNotFoundError(f"配置的字体未找到：{font_path}")

        # 缓存 key
        key = str(hash((os.path.abspath(font_path), font_size)))
        if key in cls._font_cache:
            return cls._font_cache[key]

        cls._font_cache[key] = cls(font_path, font_size)
        return cls._font_cache[key]

    @classmethod
    def MixFontToLatexFont(cls, mix_font: "MixFont") -> pillowlatex.MixFont:
        """将 MixFont 转换为 pillowlatex.MixFont"""
        key = str(hash((mix_font.path, mix_font.size)))

        if key not in cls._latex_font_cache:
            cls._latex_font_cache[key] = pillowlatex.MixFont(
                font=mix_font.path,
                size=mix_font.size,
            )
        return cls._latex_font_cache[key]
