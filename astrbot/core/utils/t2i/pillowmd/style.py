# pillowmd/style.py
from __future__ import annotations
from typing import Optional, Union, TypeAlias, Literal
from pathlib import Path
from dataclasses import field, dataclass
from .decorates import MDDecorates
from .mixfont import MixFont

# ---------- 类型别名 ----------
mdPageLineStyle: TypeAlias = Literal["full_line", "dotted_line"]
mdColor: TypeAlias = Union[tuple[int, int, int], tuple[int, int, int, int]]


@dataclass
class MdStyle:
    """
    Markdown 生成风格
    字段顺序、默认值、注释与 setting.yaml 保持 1:1 对应
    """

    # 基本信息
    name: str = "Astrbot娘"  # 主题名称
    intr: str = "Astrbot的默认样式"  # 主题简介
    author: str = "Zhalslar"  # 作者
    version: str = "1.0"  # 版本号
    stylePath: str = (
        "data/t2i_styles/astrbot_style"  # 主题样式文件总路径，支持相对/绝对
    )

    # 资源目录（相对于 stylePath）
    backgrounds: str = "backgrounds"  # 背景图片目录
    images: str = "images"  # Markdown 引用图片/缓存目录
    paintPath: str = ""  # 立绘图片（autoPage=True 时生效）

    # 字体文件路径（相对于 stylePath/fonts/）
    font: str = "default.ttf"  # 正文字体
    titleFont: str = "fdefault.ttf"  # 标题字体
    expressionFont: str = "STIXTwoMath-Regular.ttf"  # 公式字体
    codeFont: str = "default.ttf"  # 代码字体

    # 字号
    fontSize: int = 25  # 正文字号
    title1FontSize: int = 70  # 一级标题
    title2FontSize: int = 55  # 二级标题
    title3FontSize: int = 40  # 三级标题
    expressionFontSizeRate: float = 0.8  # 公式字号 = 正文字号 * 该比例
    codeBlockFontSize: int = 15  # 代码块字号
    remarkFontSize: int = 14  # 备注字号

    # 页边距
    rb: int = 200  # right distance 右边距
    lb: int = 200  # left distance   左边距
    ub: int = 200  # up distance     上边距
    db: int = 200  # down distance   下边距

    # 画布最大宽度
    maxX: int = 1000  # 单行元素最大像素宽度

    # 代码块 / 表格内边距
    codeLb: int = 20  # 代码块左右留白
    codeUb: int = 20  # 代码块上下留白
    formLineb: int = 20  # 表格行间距
    lineb: int = 10  # 普通行间距
    citeb: int = 30  # 引用竖线间距

    # 页面分割线
    pageLineColor: mdColor = (253, 205, 207, 150)  # RGBA
    pageLineStyle: mdPageLineStyle = "dotted_line"  # full_line | dotted_line

    # 列表符号颜色
    unorderedListDotColor: mdColor = (234, 149, 123)  # 无序列表
    orderedListDotColor: mdColor = (241, 207, 131)  # 有序列表符号
    orderedListNumberColor: mdColor = (240, 240, 233)  # 有序列表数字

    # 引用块
    citeUnderpainting: mdColor = (196, 237, 237)  # 引用背景
    citeSplitLineColor: mdColor = (74, 72, 114, 200)  # 引用竖线

    # 代码块
    codeBlockUnderpainting: mdColor = (253, 205, 207, 180)  # 代码块背景
    codeBlockTitleColor: mdColor = (227, 95, 130)  # 代码块标题文字
    codeBlockTextColor: mdColor = (80, 89, 162)  # 代码块正文
    insertCodeUnderpainting: mdColor = (
        253,
        205,
        207,
        180,
    )  # 行内代码背景
    insertCodeTextColor: mdColor = (77, 84, 139)  # 行内代码文字

    # 正文颜色
    textColor: mdColor = (98, 79, 137)
    textGradientEndColor: mdColor = (186, 99, 133)  # 标题渐变终止色
    linkColor: mdColor = (132, 162, 240)  # 超链接

    # 公式
    expressionUnderpainting: mdColor = (74, 72, 114)  # 公式背景
    expressionTextColor: mdColor = (244, 248, 248)  # 公式文字

    # 备注 / 表单
    remarkColor: mdColor = (212, 234, 151)  # 备注文字
    formTextColor: mdColor = (105, 83, 118)  # 表格文字
    formLineColor: mdColor = (105, 83, 118)  # 表格线
    formUnderpainting: mdColor = (212, 227, 205, 255)  # 表格行背景
    formTitleUnderpainting: mdColor = (245, 213, 100, 90)  # 表头背景

    # 分割线
    idlineColor: mdColor = (186, 99, 133)  # 标题下方分割线（预留）

    # 背景（已提前处理）
    #background: dict

    # 装饰图
    decorates: Optional[MDDecorates] = None  # 由 StyleManager 实例化后注入

    # 其它杂项
    expressionTextSpace: int = 10  # 表达式边缘间距
    autoPage: bool = True  # 是否默认自动分页
    remarkCoordinate: tuple[int, int] = (30, 2)  # 标题备注坐标 (x, y)

    # 延后初始化的字体（不在 YAML 出现，由 __post_init__ 填充）
    mainFont: MixFont = field(init=False, default=None)  # type: ignore
    fontG: MixFont = field(init=False, default=None)  # type: ignore
    fontC: MixFont = field(init=False, default=None)  # type: ignore
    font1: MixFont = field(init=False, default=None)  # type: ignore
    font1G: MixFont = field(init=False, default=None)  # type: ignore
    font2: MixFont = field(init=False, default=None)  # type: ignore
    font2G: MixFont = field(init=False, default=None)  # type: ignore
    font3: MixFont = field(init=False, default=None)  # type: ignore
    font3G: MixFont = field(init=False, default=None)  # type: ignore
    fontR: MixFont = field(init=False, default=None)  # type: ignore



    def __post_init__(self) -> None:
        # 保证资源目录存在
        sp = Path(self.stylePath).resolve()
        self.paintPath = str(sp / self.paintPath)
        (sp / "fonts").mkdir(parents=True, exist_ok=True)
        (sp / "backgrounds").mkdir(parents=True, exist_ok=True)
        (sp / "images").mkdir(parents=True, exist_ok=True)

        # 加载字体
        if self.mainFont is not None:  # 已初始化
            return
        base = Path(self.stylePath).resolve() / "fonts"
        self.mainFont = MixFont.GetMixFont(base / self.font, self.fontSize)
        self.fontG = MixFont.GetMixFont(
            base / self.expressionFont,
            int(self.fontSize * self.expressionFontSizeRate),
        )
        self.fontC = MixFont.GetMixFont(base / self.codeFont, self.codeBlockFontSize)
        self.font1 = MixFont.GetMixFont(base / self.titleFont, self.title1FontSize)
        self.font1G = MixFont.GetMixFont(
            base / self.expressionFont,
            int(self.title1FontSize * self.expressionFontSizeRate),
        )
        self.font2 = MixFont.GetMixFont(base / self.titleFont, self.title2FontSize)
        self.font2G = MixFont.GetMixFont(
            base / self.expressionFont,
            int(self.title2FontSize * self.expressionFontSizeRate),
        )
        self.font3 = MixFont.GetMixFont(base / self.titleFont, self.title3FontSize)
        self.font3G = MixFont.GetMixFont(
            base / self.expressionFont,
            int(self.title3FontSize * self.expressionFontSizeRate),
        )
        self.fontR = MixFont.GetMixFont(base / self.font, self.remarkFontSize)


    # 工具：根据主字体返回对应公式字体
    def get_gfont(self, font: MixFont) -> MixFont:
        return {
            self.font1: self.font1G,
            self.font2: self.font2G,
            self.font3: self.font3G,
            self.mainFont: self.fontG,
            self.fontC: self.fontG,
            self.fontR: self.fontG,
        }.get(font, self.fontG)
