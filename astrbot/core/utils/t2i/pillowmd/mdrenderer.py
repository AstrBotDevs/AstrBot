from PIL import Image
from typing import Optional, Union, Any, List, Tuple
from pathlib import Path
import os
import math
import copy
import pillowlatex
import hashlib
from astrbot.core.utils.io import download_image_by_url
from dataclasses import dataclass, field
from .drawer import DefaultMdBackGroundDraw
from .mixfont import MixFont
from .drawer import ImageDrawPro, extendFuncs
from .style import MdStyle



@dataclass(slots=True)
class MdRenderState:
    # --------------- 样式入口（只读） -------------
    style: MdStyle

    # ---------------- 字体 ----------------
    nowf: MixFont  # 当前生效字体
    fontK: MixFont  # 字体备份（代码块/公式等场景切换后恢复）

    # ---------------- 排版 ----------------
    nmaxX: int = 0  # 当前行最大宽度（像素）
    xidx: int = 0  # 当前行内字符序号（从 1 开始）
    yidx: int = 1  # 当前行号（从 1 开始）
    nx: int = 0  # 当前行已占宽度（像素）
    ny: int = 0  # 当前行已占高度（像素）
    ys: int = 0  # 当前行总高度（像素）
    nmaxh: int = 0  # 当前行最大字符高度（像素）

    hs: List[int] = field(default_factory=list)  # 每行高度记录
    maxxs: List[int] = field(default_factory=list)  # 每行最大宽度记录

    # ---------------- 文本 ----------------
    text: str = ""
    textS: int = 0  # 文本总长度
    idx: int = -1  # 当前解析到的字符索引

    # ---------------- 模式开关 ----------------
    bMode: bool = False  # 行间公式模式 ($$)
    bMode2: bool = False  # 行内代码模式 (`)
    lMode: bool = False  # 删除线模式 (~~)
    codeMode: bool = False  # 代码块模式 (```)
    linkMode: bool = False  # 链接模式
    yMode: bool = False  # 引用块模式 (>)
    textMode: bool = False  # 纯文本模式（避免重复进入 Markdown 标记判断）
    citeNum: int = 0  # 引用层级深度

    # ---------------- 表格 ----------------
    forms: List[dict] = field(default_factory=list)  # 预解析的表格数据
    formIdx: int = -1  # 当前表格索引

    # ---------------- 图片 ----------------
    images: List[dict[str, Any]] = field(default_factory=list)  # 待绘制图片列表
    isImage: bool = False  # 当前字符是否为图片占位
    nowImage: Optional[Image.Image] = None  # 当前待绘制图片对象

    # ---------------- 链接/跳过/颜色 ------
    skips: List[int] = field(default_factory=list)  # 需跳过的字符索引（链接、公式等）
    linkbegins: List[int] = field(default_factory=list)  # 链接开始索引
    linkends: List[int] = field(default_factory=list)  # 链接结束索引
    lockColor: Optional[Tuple[int, int, int]] = None  # 锁定文字颜色
    colors: List[dict] = field(default_factory=list)  # 颜色区间记录

    # ---------------- 公式 ----------------
    latexs: List[dict] = field(default_factory=list)  # 预解析的公式数据
    latexIdx: int = -1  # 当前公式索引
    nowlatexImageIdx: int = -1  # 当前公式图片子索引（多行公式）

    # ---------------- 其他 ----------------
    dr: int = 0  # 列表符号占用高度（用于垂直对齐）

    # --------------- 工厂方法 ---------------------
    @classmethod
    def create(cls, text: str, style: MdStyle) -> "MdRenderState":
        return cls(
            text=text,
            textS=len(text),
            nowf=style.mainFont,
            fontK=style.mainFont,
            style=style,
        )


class PillowMdRenderer:
    """
    Markdown → 长图渲染器
    1. 预解析：扫描文本，记录表格、公式、图片、链接、颜色等区间
    2. 排版：计算每行宽高、分页
    3. 绘制：分层绘制背景、特效、文字、图片
    """

    def __init__(self) -> None:
        pass

    @staticmethod
    def safe_open_image(path: str):
        """
        如果文件存在且能正常打开，返回 RGBA 的 Image 对象；
        """
        try:
            if path and os.path.isfile(path):
                return Image.open(path).convert("RGBA")
        except Exception:
            pass


    @staticmethod
    async def open_image_with_cache(imageSrc: str, cache_dir: Path) -> Image.Image:
        """
        根据链接返回 PIL.Image：
        1. 用 md5 做文件名，保留原后缀
        2. 缓存目录：cache_dir / .cache
        3. 无缓存则下载，下载失败返回 1×1 透明图
        """
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        suffix = Path(imageSrc).suffix or ".jpg"
        safe_name = hashlib.md5(imageSrc.encode()).hexdigest() + suffix
        cache_path = cache_dir / safe_name

        try:
            if cache_path.exists():  # 命中缓存
                return Image.open(cache_path).convert("RGBA")
            # 下载
            tmp_path = await download_image_by_url(imageSrc)
            # 移动到缓存
            cache_path.write_bytes(Path(tmp_path).read_bytes())
            return Image.open(cache_path).convert("RGBA")
        except Exception:
            # 任意异常都降级
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    @staticmethod
    def get_args(args: str) -> tuple[list[Any], dict[str, Any]]:
        args += ","
        args1 = []
        args2 = {}
        pmt = ""

        def _get_one_arg(arg: str):
            if arg[0] == "[" and arg[-1] == "]":
                args = []
                pmt = ""
                deep = 0
                string = False
                pre = ""
                for i in arg[1:-1] + ",":
                    if i == "]" and not string:
                        deep -= 1
                    if i == '"' and pre != "\\":
                        string = not string

                    if i == "," and deep == 0 and not string:
                        args.append(pmt.strip())
                        pmt = ""
                        pre = ""
                        continue
                    elif i == "[" and not string:
                        deep += 1

                    pmt += i
                    pre = i
                return [_get_one_arg(i) for i in args]
            if arg[0] == '"' and arg[-1] == '"':
                return arg[1:-1]
            if arg in ["True", "true"]:
                return True
            if "." in arg:
                return float(arg)
            return int(arg)

        deep = 0
        pre = ""
        string = False
        for i in args:
            if i == "]" and not string:
                deep -= 1

            if i == '"' and pre != "\\":
                string = not string

            if i == "," and deep == 0 and not string:
                pmt = pmt.strip()
                if (
                    pmt[0]
                    not in [
                        '"',
                        "[",
                    ]
                    and pmt not in ["True", "true", "False", "false"]
                    and not pmt[0].isdigit()
                ):
                    args2[pmt.split("=")[0].strip()] = "=".join(pmt.split("=")[1:]).strip()
                else:
                    args1.append(pmt)
                pmt = ""
                pre = ""
                continue
            elif i == "[" and not string:
                deep += 1

            pmt += i
            pre = i

        args1 = [_get_one_arg(i) for i in args1]
        for key in args2:
            args2[key] = _get_one_arg(args2[key])

        return (args1, args2)

    # 老接口，新接口开发中
    async def md_to_image(
        self,
        text: str,
        style: MdStyle,
        imagePath: Optional[Union[str, Path]] = None,
        autoPage: bool | None = None,
    ):
        """
        将Markdown转化为图片
        text - 要转化的文本
        style - 风格
        imagePath - 图片相对路径所使用的基路径
        autoPage - 是否自动分页（尽可能接近黄金分割比）
        """
        s = style
        t = MdRenderState.create(text, style)
        imagePath = Path(imagePath) if imagePath else Path(s.images)
        autoPage = autoPage if autoPage is not None else s.autoPage

        # ========== 1. 预解析：扫描特殊区间 ==========
        while t.idx < t.textS - 1:
            t.isImage = False
            nowObjH = t.nowf.size
            t.idx += 1
            i = text[t.idx]
            t.xidx += 1

            size = t.nowf.GetSize(i)
            xs, ys = size[0], size[1]

            # ---- 公式图片占位高度 ----
            if (
                t.latexIdx != -1
                and t.latexs[t.latexIdx]["begin"] < t.idx < t.latexs[t.latexIdx]["end"]
            ):
                t.nowlatexImageIdx += 1

                if t.nowlatexImageIdx >= len(t.latexs[t.latexIdx]["images"]):
                    t.idx = t.latexs[t.latexIdx]["end"] - 1
                    t.nowlatexImageIdx = -1

                    continue
                else:
                    space = t.latexs[t.latexIdx]["space"]
                    i = t.latexs[t.latexIdx]["images"][t.nowlatexImageIdx]
                    sz = t.latexs[t.latexIdx]["images"][t.nowlatexImageIdx].size
                    xs, ys = [sz[0], sz[1] + space * 2]
                    nowObjH = ys

            # ---- 跳过已处理区间 ----
            if t.idx in t.skips:
                continue
            if t.idx in t.linkends:
                continue

            # ---- 行首空格压缩 ----
            if t.xidx == 1 and not t.codeMode and i == " ":
                while t.idx < t.textS and text[t.idx] == " ":
                    t.idx += 1
                t.idx -= 1
                t.xidx = 0
                continue

            # ---- 标题 ----
            if not t.textMode and i == "#" and not t.codeMode:
                if t.idx + 1 < t.textS and text[t.idx + 1] == "#":
                    if t.idx + 2 <= t.textS and text[t.idx + 2] == "#":
                        t.idx += 2
                        t.nowf = s.font1
                    else:
                        t.idx += 1
                        t.nowf = s.font2
                else:
                    t.nowf = s.font3
                while t.idx + 1 < t.textS and text[t.idx + 1] == " ":
                    t.idx += 1
                continue

            # ---- 无序列表 ----
            elif (
                not t.textMode
                and i in ["*", "-", "+"]
                and t.idx + 1 < t.textS
                and text[t.idx + 1] == " "
                and not t.codeMode
            ):
                t.idx += 1
                t.dr = t.nmaxh
                t.nx += t.nmaxh
                while t.idx + 1 < t.textS and text[t.idx + 1] == " ":
                    t.idx += 1
                continue

            # ---- 有序列表 ----
            elif not t.textMode and i.isdigit() and not t.codeMode:
                tempIdx = t.idx - 1
                flag = False
                number = ""
                while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                    tempIdx += 1
                    if text[tempIdx].isdigit():
                        number += text[tempIdx]
                    elif text[tempIdx] == ".":
                        flag = True
                        break
                    else:
                        break
                if flag:
                    t.idx = tempIdx
                    t.nx += 30
                    while t.idx + 1 < t.textS and text[t.idx + 1] == " ":
                        t.idx += 1
                    continue
                t.textMode = True

            # ---- 引用 ----
            elif not t.textMode and i == ">" and not t.codeMode:
                t.citeNum = 1
                while t.idx + 1 < t.textS and text[t.idx + 1] == ">":
                    t.citeNum += 1
                    t.idx += 1
                while t.idx + 1 < t.textS and text[t.idx + 1] == " ":
                    t.idx += 1
                t.nx += 30 * (t.citeNum) + 5
                continue

            # ---- 代码块 ----
            elif (
                not t.textMode
                and t.idx + 2 <= t.textS
                and text[t.idx : t.idx + 3] in ["```", "~~~"]
            ):
                t.ny += s.codeUb
                t.nx += s.codeLb
                while t.idx < t.textS - 1 and text[t.idx + 1] != "\n":
                    t.idx += 1
                if not t.codeMode:
                    t.fontK = t.nowf
                    t.nowf = s.fontC
                else:
                    t.nowf = t.fontK
                t.codeMode = not t.codeMode
                continue

            # ---- 表格 ----
            elif not t.textMode and i == "|" and not t.codeMode:
                tempIdx = t.idx - 1
                lText = ""
                while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                    tempIdx += 1
                    lText += text[tempIdx]

                tempIdx += 1
                lText2 = ""
                while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                    tempIdx += 1
                    lText2 += text[tempIdx]

                lText = lText.strip()
                lText2 = lText.strip()

                temp1 = lText.count("|")
                temp2 = lText2.count("|")
                exterX = temp1 * s.formLineb
                if (
                    len(lText)
                    and len(lText2)
                    and lText[0] == lText[-1] == lText2[0] == lText2[-1] == "|"
                    and temp1 == temp2
                    and temp1 >= 2
                    and exterX < s.maxX
                ):
                    form = [lText.split("|")[1:-1]]

                    while True:
                        preIdx = tempIdx
                        tempIdx += 1
                        tempText = ""

                        if tempIdx + 1 >= t.textS or text[tempIdx + 1] != "|":
                            break

                        while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                            tempIdx += 1
                            tempText += text[tempIdx]

                        temp = tempText.count("|")
                        if not (tempText[0] == tempText[-1] == "|" and temp >= 2):
                            tempIdx = preIdx
                            break

                        form.append(tempText.split("|")[1:-1])

                    formHeadNum = len(form[0])
                    formSize = []
                    for ii in range(len(form)):
                        formNowLNum = len(form[ii])

                        if formNowLNum < formHeadNum:
                            form[ii] = form[ii] + [""] * (formHeadNum - formNowLNum)
                        if formNowLNum > formHeadNum:
                            form = form[0:formHeadNum]

                        formSize.append(
                            [
                                sum([s.mainFont.GetSize(j)[0] for j in i])
                                for i in form[ii]
                            ]
                        )

                    formRow = len(form)
                    colunmSizes = [[0, 99999]] + sorted(
                        [
                            [max([formSize[deep][i] for deep in range(formRow)]), i]
                            for i in range(formHeadNum)
                        ],
                        key=lambda x: x[0],
                    )
                    maxIdx = len(colunmSizes) - 1

                    if not (s.mainFont.size * len(colunmSizes) + exterX > s.maxX):
                        while sum([i[0] for i in colunmSizes]) + exterX > s.maxX:
                            exceed = sum([i[0] for i in colunmSizes]) + exterX - s.maxX
                            sizeIdx = len(colunmSizes) - 1

                            while (
                                colunmSizes[sizeIdx - 1][0] == colunmSizes[sizeIdx][0]
                            ):
                                sizeIdx -= 1

                            temp = math.ceil(
                                min(
                                    exceed / (maxIdx - sizeIdx + 1),
                                    colunmSizes[sizeIdx][0]
                                    - colunmSizes[sizeIdx - 1][0],
                                )
                            )
                            for ii in range(sizeIdx, maxIdx + 1):
                                colunmSizes[ii][0] = colunmSizes[ii][0] - temp

                        colunmSizes = [
                            i[0] for i in sorted(colunmSizes[1:], key=lambda x: x[1])
                        ]
                        rowSizes = []

                        for ii in range(formRow):
                            nMaxRowSize = 0

                            for j in range(formHeadNum):
                                tempRowSize = s.mainFont.size
                                formNx = 0
                                formTextIdx = -1
                                formText = form[ii][j]
                                formTextSize = len(formText)

                                while formTextIdx + 1 < formTextSize:
                                    formTextIdx += 1
                                    char = formText[formTextIdx]
                                    formCharX = s.mainFont.GetSize(char)[0]

                                    if formNx + formCharX > colunmSizes[j]:
                                        tempRowSize += s.mainFont.size + s.lineb
                                        formNx = 0

                                    formNx += formCharX

                                nMaxRowSize = max(nMaxRowSize, tempRowSize)

                            rowSizes.append(nMaxRowSize)

                        t.forms.append(
                            {
                                "height": (formRow) * s.formLineb
                                + sum(rowSizes)
                                + s.formLineb,
                                "width": sum(colunmSizes) + exterX,
                                "rowSizes": copy.deepcopy(rowSizes),
                                "colunmSizes": copy.deepcopy(colunmSizes),
                                "form": copy.deepcopy(form),
                                "endIdx": tempIdx,
                                "beginIdx": t.idx,
                            }
                        )
                        t.ny += s.lineb * (tempIdx < t.textS) + t.forms[-1]["height"]
                        t.ys = 0
                        t.idx = tempIdx
                        t.nmaxX = max(t.nmaxX, sum(colunmSizes) + exterX)
                        continue

            # ---- 普通文字 ----
            else:
                t.textMode = True

            # ---- 行内公式/代码/图片/链接/颜色等 ----
            if (
                i == "*"
                and t.idx + 1 < t.textS
                and text[t.idx + 1] == "*"
                and not t.codeMode
            ):
                t.idx += 1
                continue
            if (
                i == "~"
                and t.idx + 1 < t.textS
                and text[t.idx + 1] == "~"
                and not t.codeMode
            ):
                t.idx += 1
                continue

            if (
                i == "$"
                and (text[t.idx - 1] != "\\" if t.idx >= 1 else True)
                and (t.idx + 1 < t.textS and text[t.idx + 1] == "$")
                and not t.codeMode
                and not t.bMode2
            ):
                tempIdx = t.idx
                flag = False
                while tempIdx < t.textS - 1:
                    tempIdx += 1
                    if (
                        text[tempIdx] == "$"
                        and tempIdx + 1 < t.textS
                        and text[tempIdx + 1] == "$"
                    ):
                        flag = True
                        break
                if flag or t.bMode:
                    t.nx += 2
                    if not t.bMode:
                        if t.xidx != 1:
                            t.nmaxX = max(t.nx, t.nmaxX)
                            t.maxxs.append(t.nx)
                            t.nx = t.codeMode * s.codeLb
                            t.ny += t.nmaxh + s.lineb
                            t.xidx = 0
                            t.yidx += 1
                            t.hs.append(t.nmaxh)
                            t.nmaxh = int(s.fontC.size / 3)
                            t.citeNum = 0
                            t.dr = 0

                        t.fontK = t.nowf
                        t.nowf = s.get_gfont(t.nowf)
                        lateximgs = pillowlatex.RenderLaTeXObjs(
                            pillowlatex.GetLaTeXObjs(text[t.idx + 2 : tempIdx]),
                            font=MixFont.MixFontToLatexFont(t.nowf),
                            color=s.expressionTextColor,
                        )
                        t.latexs.append(
                            {
                                "begin": t.idx + 1,
                                "end": tempIdx,
                                "images": lateximgs,
                                "maxheight": max([i.height for i in lateximgs])
                                if lateximgs
                                else t.nowf.size,
                                "space": pillowlatex.settings.SPACE,
                                "super": True,
                            }
                        )
                        t.latexIdx += 1
                        t.nowlatexImageIdx = -1
                    else:
                        t.nmaxX = max(t.nx, t.nmaxX)
                        t.maxxs.append(t.nx)
                        t.nx = t.codeMode * s.codeLb
                        t.ny += t.nmaxh + s.lineb
                        t.xidx = 0
                        t.yidx += 1
                        t.hs.append(t.nmaxh)
                        t.nmaxh = int(s.fontC.size / 3)
                        t.citeNum = 0
                        t.dr = 0

                        t.nowf = t.fontK
                    t.bMode = not t.bMode
                    t.idx += 1
                    continue

            if (
                i == "$"
                and (text[t.idx - 1] != "\\" if t.idx >= 1 else True)
                and not t.codeMode
                and not t.bMode2
            ):
                tempIdx = t.idx
                flag = False
                while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                    tempIdx += 1
                    if text[tempIdx] == "$":
                        flag = True
                        break
                if flag or t.bMode:
                    t.nx += 2
                    if not t.bMode:
                        t.fontK = t.nowf
                        t.nowf = s.get_gfont(t.nowf)
                        lateximgs = pillowlatex.RenderLaTeXObjs(
                            pillowlatex.GetLaTeXObjs(text[t.idx + 1 : tempIdx]),
                            font=MixFont.MixFontToLatexFont(t.nowf),
                            color=s.expressionTextColor,
                        )
                        t.latexs.append(
                            {
                                "begin": t.idx,
                                "end": tempIdx,
                                "images": lateximgs,
                                "maxheight": max([i.height for i in lateximgs])
                                if lateximgs
                                else t.nowf.size,
                                "space": pillowlatex.settings.SPACE,
                                "super": False,
                            }
                        )
                        t.latexIdx += 1
                        t.nowlatexImageIdx = -1
                    else:
                        t.nowf = t.fontK
                    t.bMode = not t.bMode
                    continue

            if (
                i == "`"
                and (text[t.idx - 1] != "\\" if t.idx >= 1 else True)
                and not t.codeMode
                and not t.bMode
            ):
                if not (
                    t.xidx == 1
                    and t.idx + 2 <= t.textS
                    and text[t.idx : t.idx + 3] == "```"
                ):
                    tempIdx = t.idx
                    flag = False
                    while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                        tempIdx += 1
                        if text[tempIdx] == "`":
                            flag = True
                            break
                    if flag or t.bMode2:
                        t.nx += 2
                        if not t.bMode2:
                            t.fontK = t.nowf
                            t.nowf = s.get_gfont(t.nowf)
                        else:
                            t.nowf = t.fontK
                        t.bMode2 = not t.bMode2
                        continue

            if (
                i == "!"
                and t.idx + 9 < t.textS
                and text[t.idx : t.idx + 9] == "!sgexter["
                and not t.codeMode
                and not t.bMode
            ):
                tempIdx = t.idx + 8
                flag = False
                data = ""

                deep = 0
                string = False
                while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                    tempIdx += 1

                    if text[tempIdx] == '"' and text[tempIdx - 1] == "\\":
                        string = not string

                    if text[tempIdx] == "[" and not string:
                        deep += 1

                    if text[tempIdx] == "]" and not string:
                        if deep == 0:
                            flag = True
                            break

                        deep -= 1

                    data += text[tempIdx]

                if flag:
                    flag = False

                    try:
                        args = data.split(",")
                        funcName = args[0]
                        args = ",".join(args[1:])
                        flag = True
                    except Exception:
                        pass

                    if flag and funcName in extendFuncs:
                        flag = False

                        try:
                            args1, args2 = self.get_args(args)  # type: ignore
                            flag = True
                        except Exception:
                            pass

                        if flag:
                            idata = {
                                "image": extendFuncs[funcName](
                                    *args1,
                                    **args2,
                                    nowf=t.nowf,
                                    style=s,
                                    lockColor=t.lockColor,
                                ),
                                "begin": t.idx,
                                "end": tempIdx,
                            }
                            t.images.append(idata)
                            t.isImage = True
                            xs, ys = idata["image"].size
                            nowObjH = ys
                            t.idx = tempIdx


            if (
                i == "!"
                and t.idx + 1 < t.textS
                and text[t.idx : t.idx + 2] == "!["
                and not t.codeMode
                and not t.bMode
            ):
                imageName = ""
                imageSrc = ""
                tempIdx = t.idx + 1
                try:
                    flag = False
                    while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                        tempIdx += 1
                        if text[tempIdx] == "]":
                            flag = True
                            break
                        imageName += text[tempIdx]
                    if not flag:
                        raise ValueError("错误: 图片解析失败")
                    tempIdx += 1
                    flag = False
                    while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                        tempIdx += 1
                        if text[tempIdx] == ")":
                            flag = True
                            break
                        imageSrc += text[tempIdx]
                    if not flag:
                        raise ValueError("错误: 图片解析失败")
                    imageSrc = imageSrc.split(" ")[0]
                    image = await self.open_image_with_cache(imageSrc, imagePath)
                    idata = {"image": image, "begin": t.idx, "end": tempIdx}
                    t.images.append(idata)
                    if idata["image"].size[0] > s.maxX:
                        idata["image"] = idata["image"].resize(
                            (
                                int(s.maxX),
                                int(
                                    idata["image"].size[1]
                                    * (s.maxX / idata["image"].size[0])
                                ),
                            )
                        )
                    t.isImage = True
                    xs, ys = idata["image"].size
                    nowObjH = ys
                    t.idx = tempIdx
                except Exception as e:
                    print(e)
                    t.skips += list(range(t.idx + len(imageName) + 2, tempIdx))
                    t.linkbegins.append(t.idx)
                    t.linkends.append(tempIdx)
                    continue

            if i == "[" and not t.codeMode and not t.bMode:
                tempIdx = t.idx
                linkName = ""
                link = ""
                flag = False
                while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                    tempIdx += 1
                    if text[tempIdx] == "]":
                        flag = True
                        break
                    linkName += text[tempIdx]
                flag = False
                tempIdx += 1
                if tempIdx + 1 <= t.textS and text[tempIdx] == "(":
                    while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                        tempIdx += 1
                        if text[tempIdx] == ")":
                            flag = True
                            break
                        link += text[tempIdx]
                if flag:
                    t.skips.append(t.idx + len(linkName) + 2)
                    t.linkbegins.append(t.idx)
                    t.linkends.append(t.idx + len(linkName) + 2)
                    for k in range(t.idx + len(linkName) + 3, tempIdx):
                        t.skips.append(k)
                    t.skips.append(tempIdx)

            if (
                i == "<"
                and t.idx + 6 < t.textS
                and text[t.idx + 1 : t.idx + 7] == "color="
            ):
                color = ""
                flag = False
                tempIdx = t.idx + 6
                k = 0
                while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                    k += 1
                    if k >= 10:
                        break
                    tempIdx += 1
                    if text[tempIdx] == ">":
                        flag = True
                        break
                    color += text[tempIdx]

                if flag:
                    if (len(color) == 7 and color[0] == "#") or color == "None":
                        t.lockColor = None if color == "None" else color # type ignored
                        t.colors.append(
                            {"beginIdx": t.idx, "endIdx": tempIdx, "color": t.lockColor}
                        )
                        t.idx = tempIdx
                        continue

            ex = 0
            preNmaxh = max(t.nmaxh, nowObjH)
            if t.dr and min(preNmaxh, s.font3.size) > t.dr:
                ex += min(preNmaxh, s.font3.size) - t.dr
                t.dr = min(preNmaxh, s.font3.size)

            if i == "\n":
                t.nmaxX = max(t.nx, t.nmaxX)
                t.maxxs.append(t.nx)
                t.nx = t.codeMode * s.codeLb
                t.ny += t.nmaxh + s.lineb
                t.xidx = 0
                t.yidx += 1
                t.hs.append(t.nmaxh)
                t.nmaxh = int(s.fontC.size / 3)
                t.textMode = False
                t.citeNum = 0
                if not t.codeMode:
                    t.nowf = s.mainFont
                t.dr = 0
                continue
            if t.nx + xs + ex > s.maxX:
                t.nmaxX = max(t.nx, t.nmaxX)
                t.maxxs.append(t.nx)
                t.yidx += 1
                t.nx = t.codeMode * s.codeLb
                t.ny += t.nmaxh + s.lineb
                if t.citeNum:
                    t.nx += 30 * (t.citeNum - 1) + 5
                t.hs.append(t.nmaxh)
                t.nmaxh = int(s.fontC.size)
                t.dr = 0

            t.nx += int(xs + ex)
            t.nmaxh = int(max(t.nmaxh, nowObjH))

        # ========== 2. 计算分页 & 画布尺寸 ==========

        t.nmaxX = max(t.nx, t.nmaxX)
        t.nmaxh = max(t.nmaxh, t.ys)
        t.ny += t.nmaxh
        t.maxxs.append(t.nx)
        t.hs.append(t.nmaxh)

        paintImage = self.safe_open_image(s.paintPath)

        page = 1
        if autoPage:
            while True:
                bX = (t.nmaxX + s.rb + s.lb) * page
                bY = int(t.ny / page) + s.ub + s.db
                if bY > 300 and paintImage:
                    txs, tys = bX, bY

                    if tys < txs * 2.5:
                        bX += int(
                            paintImage.size[0] / paintImage.size[1] * (bY - s.ub - s.db)
                        )
                eX = (t.nmaxX + s.rb + s.lb) * (page + 1)
                eY = int(t.ny / (page + 1)) + s.ub + s.db
                if eY > 300 and paintImage:
                    txs, tys = eX, eY

                    if tys < txs * 2.5:
                        eX += int(
                            paintImage.size[0] / paintImage.size[1] * (eY - s.ub - s.db)
                        )
                if abs(min(bX, bY) / max(bX, bY) - 0.618) < abs(
                    min(eX, eY) / max(eX, eY) - 0.618
                ):
                    break
                page += 1

        if page > len(t.hs):
            page = len(t.hs)

        txs, tys = (t.nmaxX + s.rb + s.lb) * page, int(t.ny / page)

        yTys = tys

        temp = 0
        temp2 = tys
        temp3 = tys
        for ys in t.hs:
            temp += ys

            if temp > yTys:
                temp2 = max(temp2, temp + 1)
                temp = 0
                continue

            temp += s.lineb

        temp = 0
        for ys in t.hs[-1::-1]:
            temp += ys

            if temp > yTys:
                temp3 = max(temp3, temp + 1)
                temp = 0
                continue

            temp += s.lineb

        tys = min(temp2, temp3)

        tys = int(tys)

        PYL = tys + 1
        tys += s.ub + s.db
        tlb = s.lb

        bt = False

        if tys > 300 and tys < txs * 2.5 and paintImage:
            bt = True
            temp = int(tys - s.ub - s.db)
            paintImage = paintImage.resize(
                (int(paintImage.size[0] / paintImage.size[1] * temp), temp)
            ).convert("RGBA")
            txs += paintImage.size[0]

        t.lockColor = None

        # ========== 3. 创建画布 & 分层绘制 ==========

        if s.decorates:
            outImage = s.decorates.Draw(int(txs), tys)
        else:
            outImage = DefaultMdBackGroundDraw(int(txs), tys)

        imgEffect = Image.new("RGBA", (int(txs), tys), color=(0, 0, 0, 0))
        imgText = Image.new("RGBA", (int(txs), tys), color=(0, 0, 0, 0))
        imgImages = Image.new("RGBA", (int(txs), tys), color=(0, 0, 0, 0))

        drawEffect = ImageDrawPro(imgEffect)
        draw = ImageDrawPro(imgText)

        # 分页线
        for i in range(1, page):
            lx = (t.nmaxX + s.rb + s.lb) * i
            lby = s.ub
            ley = tys - s.db
            lwidth = int(min(s.lb, s.rb) / 6) * 2
            match s.pageLineStyle:
                case "full_line":
                    drawEffect.line((lx, lby, lx, ley), s.pageLineColor, lwidth)
                case "dotted_line":
                    for nly in range(lby, ley, lwidth * 8):
                        drawEffect.line(
                            (lx, nly, lx, nly + lwidth * 5), s.pageLineColor, lwidth
                        )

        # 重置状态，准备绘制
        t.xidx = 0
        t.yidx = 1
        t.nx = 0
        t.ny = 0
        t.nmaxh = 0
        t.nowf = s.mainFont
        hMode = False
        t.bMode = False
        t.bMode2 = False
        lMode = False
        t.yMode = False
        t.codeMode = False
        t.citeNum = 0
        t.textMode = False

        # 绘制函数闭包
        def ChangeLockColor(color) -> None:
            nonlocal t
            t.lockColor = color
            draw.text_lock_color = color

        def ChangeLinkMode(mode: bool) -> None:
            nonlocal t
            t.linkMode = mode
            draw.under_line_mode = mode

        def ChangeDeleteLineMode(mode: bool) -> None:
            nonlocal lMode, t
            lMode = mode
            draw.delete_line_mode = mode

        def ChangeBlodMode(mode: bool) -> None:
            nonlocal hMode, t
            hMode = mode
            draw.text_blod_mode = mode

        # ========== 4. 逐字绘制 ==========

        t.nowlatexImageIdx = -1
        imageIdx = -1
        islatex = False

        t.idx: int = -1
        while t.idx < t.textS - 1:
            t.isImage = False
            nowObjH = t.nowf.size
            t.idx += 1
            i = text[t.idx]
            t.xidx += 1
            size = t.nowf.GetSize(i)
            xs, ys = size[0], size[1]

            islatex = False

            # 公式
            if t.latexs and t.latexs[0]["begin"] < t.idx < t.latexs[0]["end"]:
                t.nowlatexImageIdx += 1
                if t.nowlatexImageIdx >= len(t.latexs[0]["images"]):
                    t.idx = t.latexs[0]["end"] - 1
                    t.nowlatexImageIdx = -1
                    del t.latexs[0]
                    continue
                else:
                    islatex = True
                    space = t.latexs[0]["space"]
                    i = t.latexs[0]["images"][t.nowlatexImageIdx]
                    sz = t.latexs[0]["images"][t.nowlatexImageIdx].size
                    xs, ys = [sz[0], sz[1] + space * 2]
                    nowObjH = ys

            # 跳过
            if t.idx in t.skips:
                if t.idx in t.linkends:
                    ChangeLinkMode(False)
                continue
            if t.idx in t.linkbegins:
                ChangeLinkMode(True)
            if t.idx in t.linkends:
                ChangeLinkMode(False)
                continue

            # 行首空格
            if t.xidx == 1 and not t.codeMode and i == " ":
                while t.idx < t.textS and text[t.idx] == " ":
                    t.idx += 1
                t.idx -= 1
                t.xidx = 0
                continue

            # 标题
            if not t.textMode and i == "#" and not t.codeMode:
                if t.idx + 1 < t.textS and text[t.idx + 1] == "#":
                    if t.idx + 2 <= t.textS and text[t.idx + 2] == "#":
                        t.idx += 2
                        t.nowf = s.font1
                    else:
                        t.idx += 1
                        t.nowf = s.font2
                else:
                    t.nowf = s.font3
                while t.idx + 1 < t.textS and text[t.idx + 1] == " ":
                    t.idx += 1
                continue

            # 无序列表
            elif (
                not t.textMode
                and i in ["*", "-", "+"]
                and t.idx + 1 < t.textS
                and text[t.idx + 1] == " "
                and not t.codeMode
            ):
                t.idx += 1
                h = min(t.hs[t.yidx - 1], s.font3.size)
                sh = int(h / 6)
                zx, zy = s.lb + t.nx + int(h / 2), s.ub + t.ny + int(h / 2) + 1
                draw.polygon(
                    [(zx - sh, zy), (zx, zy - sh), (zx + sh, zy), (zx, zy + sh)],
                    s.unorderedListDotColor,
                )
                t.nx += int(h)
                while t.idx + 1 < t.textS and text[t.idx + 1] == " ":
                    t.idx += 1
                continue

            # 有序列表
            elif not t.textMode and i.isdigit() and not t.codeMode:
                tempIdx = t.idx - 1
                flag = False
                number = ""
                while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                    tempIdx += 1
                    if text[tempIdx].isdigit():
                        number += text[tempIdx]
                    elif text[tempIdx] == ".":
                        flag = True
                        break
                    else:
                        break
                if flag:
                    t.idx = tempIdx
                    h = t.hs[t.yidx - 1]
                    sh = int(s.codeBlockFontSize * 0.67)
                    zx, zy = (
                        s.lb + t.nx + int(h / 2),
                        s.ub + t.ny + int(t.hs[t.yidx - 1] / 2) + 1,
                    )
                    draw.polygon(
                        [(zx - sh, zy), (zx, zy - sh), (zx + sh, zy), (zx, zy + sh)],
                        s.orderedListDotColor,
                    )
                    sz = s.fontC.GetSize(number)
                    draw.text(
                        (zx - int((sz[0] - 1) / 2), zy - int(s.fontC.size / 2) - 1),
                        number,
                        s.orderedListNumberColor,
                        s.fontC,
                    )
                    t.nx += h
                    while t.idx + 1 < t.textS and text[t.idx + 1] == " ":
                        t.idx += 1
                    continue
                else:
                    t.textMode = True

            # 引用
            elif not t.textMode and i == ">" and not t.codeMode:
                t.citeNum = 1
                while t.idx + 1 < t.textS and text[t.idx + 1] == ">":
                    t.citeNum += 1
                    t.idx += 1
                if not t.yMode:
                    drawEffect.rectangle(
                        (
                            s.lb + t.nx,
                            s.ub + t.ny - s.lineb // 2,
                            s.lb + t.nx + t.nmaxX,
                            s.ub + t.ny + t.hs[t.yidx - 1] + s.lineb // 2,
                        ),
                        s.citeUnderpainting,
                    )
                for k in range(t.citeNum):
                    drawEffect.line(
                        (
                            s.lb + t.nx + s.citeb * (k),
                            s.ub + t.ny - s.lineb // 2,
                            s.lb + t.nx + s.citeb * (k),
                            s.ub + t.ny + t.hs[t.yidx - 1] + s.lineb // 2,
                        ),
                        s.citeSplitLineColor,
                        5,
                    )
                t.nx += s.citeb * (t.citeNum) + 5
                t.yMode = True
                t.xidx -= 1
                while t.idx + 1 < t.textS and text[t.idx + 1] == " ":
                    t.idx += 1
                continue

            # 代码块
            elif (
                not t.textMode
                and t.idx + 2 <= t.textS
                and text[t.idx : t.idx + 3] in ["```", "~~~"]
            ):
                name = ""
                while t.idx < t.textS - 1 and text[t.idx + 1] != "\n":
                    t.idx += 1
                    name += text[t.idx]
                drawEffect.rectangle(
                    (
                        s.lb,
                        s.ub + t.ny,
                        s.lb + t.nmaxX,
                        s.ub + t.ny + s.codeUb + s.fontC.size,
                    ),
                    s.codeBlockUnderpainting,
                )
                draw.text(
                    (s.lb + s.codeLb + 2, s.ub + t.ny),
                    name[2:],
                    s.codeBlockTitleColor,
                    s.fontC,
                )
                if not t.codeMode:
                    t.fontK = t.nowf
                    t.nowf = s.fontC
                else:
                    t.nowf = t.fontK
                    drawEffect.rectangle(
                        (
                            s.lb,
                            s.ub + t.ny - s.lineb,
                            s.lb + t.nmaxX,
                            s.ub + t.ny + s.codeUb,
                        ),
                        s.codeBlockUnderpainting,
                    )
                t.ny += s.codeUb
                t.nx += s.codeLb
                t.codeMode = not t.codeMode
                continue

            # 表格
            elif (
                not t.textMode
                and i == "|"
                and t.formIdx + 1 < len(t.forms)
                and t.forms[t.formIdx + 1]["beginIdx"] == t.idx
                and not t.codeMode
            ):
                t.formIdx += 1
                formData = t.forms[t.formIdx]
                form = formData["form"]
                rowSizes = formData["rowSizes"]
                colunmSizes = formData["colunmSizes"]
                formHeight = formData["height"]
                formWidth = formData["width"]
                t.idx = formData["endIdx"]
                # ny += lineSpace
                halfFormLineSpace: int = s.formLineb // 2
                exterNum = 0
                bx, by = (
                    int(s.lb + halfFormLineSpace),
                    s.ub + t.ny + exterNum + halfFormLineSpace,
                )

                # 表格背景
                draw.rectangle(
                    (
                        bx,
                        by,
                        int(s.lb - halfFormLineSpace + formWidth),
                        s.ub
                        + t.ny
                        + int(halfFormLineSpace)
                        + s.formLineb * len(rowSizes)
                        + sum(rowSizes),
                    ),
                    s.formUnderpainting,
                )

                # 表头背景
                draw.rectangle(
                    (
                        bx,
                        by,
                        int(bx - halfFormLineSpace * 2 + formWidth),
                        by + rowSizes[0] + s.formLineb,
                    ),
                    s.formTitleUnderpainting,
                )

                # 横线
                for num in rowSizes:
                    draw.line(
                        (
                            int(s.lb + halfFormLineSpace),
                            s.ub + t.ny + int(halfFormLineSpace) + exterNum,
                            int(s.lb - halfFormLineSpace + formWidth),
                            s.ub + t.ny + int(halfFormLineSpace) + exterNum,
                        ),
                        s.formLineColor,
                        2,
                    )
                    exterNum += num + s.formLineb
                draw.line(
                    (
                        int(s.lb + halfFormLineSpace),
                        s.ub + t.ny + int(halfFormLineSpace) + exterNum,
                        int(s.lb - halfFormLineSpace + formWidth),
                        s.ub + t.ny + int(halfFormLineSpace) + exterNum,
                    ),
                    s.formLineColor,
                    2,
                )

                # 竖线
                exterNum = 0
                for num in colunmSizes:
                    draw.line(
                        (
                            int(s.lb + halfFormLineSpace) + exterNum,
                            s.ub + t.ny + int(halfFormLineSpace),
                            int(s.lb + halfFormLineSpace) + exterNum,
                            s.ub + t.ny + int(formHeight - halfFormLineSpace),
                        ),
                        s.formLineColor,
                        2,
                    )
                    exterNum += num + s.formLineb
                draw.line(
                    (
                        int(s.lb + halfFormLineSpace) + exterNum,
                        s.ub + t.ny + int(halfFormLineSpace),
                        int(s.lb + halfFormLineSpace) + exterNum,
                        s.ub + t.ny + int(formHeight - halfFormLineSpace),
                    ),
                    s.formLineColor,
                    2,
                )

                # 单元格文字
                formRow = len(form)
                formHeadNum = len(form[0])

                formTextX = s.formLineb
                formTextY = s.formLineb

                for ii in range(formRow):
                    formTextX = s.formLineb

                    for j in range(formHeadNum):
                        formNx = 0
                        formNy = 0
                        formTextIdx = -1
                        formText = form[ii][j]
                        formTextSize = len(formText)

                        while formTextIdx + 1 < formTextSize:
                            formTextIdx += 1
                            char = formText[formTextIdx]
                            formCharX = s.mainFont.GetSize(char)[0]

                            if formNx + formCharX > colunmSizes[j]:
                                formNx = 0
                                formNy += s.mainFont.size

                            draw.text(
                                (
                                    s.lb + formTextX + formNx,
                                    s.ub + t.ny + formTextY + formNy,
                                ),
                                char,
                                s.formTextColor,
                                s.mainFont,
                            )

                            formNx += formCharX

                        formTextX += colunmSizes[j] + s.formLineb

                    formTextY += rowSizes[ii] + s.formLineb
                t.ny += s.lineb * (formData["endIdx"] < t.textS) + formHeight
                continue
            else:
                t.textMode = True

            # 颜色
            if len(t.colors) and t.colors[0]["beginIdx"] == t.idx:
                ChangeLockColor(t.colors[0]["color"])
                t.idx = t.colors[0]["endIdx"]
                del t.colors[0]
                continue

            # 加粗
            if (
                i == "*"
                and t.idx + 1 < t.textS
                and text[t.idx + 1] == "*"
                and not t.codeMode
            ):
                t.idx += 1
                ChangeBlodMode(not hMode)
                continue

            # 删除线
            if (
                i == "~"
                and t.idx + 1 < t.textS
                and text[t.idx + 1] == "~"
                and not t.codeMode
            ):
                t.idx += 1
                ChangeDeleteLineMode(not lMode)
                continue

            # 行内公式
            if (
                i == "$"
                and (text[t.idx - 1] != "\\" if t.idx >= 1 else True)
                and (t.idx + 1 < t.textS and text[t.idx + 1] == "$")
                and not t.codeMode
                and not t.bMode2
            ):
                tempIdx = t.idx
                flag = False
                while tempIdx < t.textS - 1:
                    tempIdx += 1
                    if (
                        text[tempIdx] == "$"
                        and tempIdx + 1 < t.textS
                        and text[tempIdx + 1] == "$"
                    ):
                        flag = True
                        break
                if flag or t.bMode:
                    if not t.bMode:
                        if t.xidx != 1:
                            t.nmaxX = max(t.nx, t.nmaxX)
                            t.maxxs.append(t.nx)
                            t.nx = t.codeMode * s.codeLb
                            t.ny += t.nmaxh + s.lineb
                            t.xidx = 0
                            t.yidx += 1
                            t.hs.append(t.nmaxh)
                            t.nmaxh = int(s.fontC.size / 3)
                            t.citeNum = 0
                            t.dr = 0

                        t.fontK = t.nowf
                        t.nowf = s.get_gfont(t.nowf)
                        fs = t.nowf.size

                        xbase = t.nmaxX // 2 - t.maxxs[t.yidx - 1] // 2

                        drawEffect.rectangle(
                            (
                                xbase + s.lb + t.nx - 1,
                                s.ub + t.ny,
                                xbase + s.lb + t.nx + 1,
                                s.ub + t.ny + t.hs[t.yidx - 1],
                            ),
                            s.expressionUnderpainting,
                        )

                    else:
                        xbase = t.nmaxX // 2 - t.maxxs[t.yidx - 1] // 2

                        drawEffect.rectangle(
                            (
                                xbase + s.lb + t.nx - 1,
                                s.ub + t.ny,
                                xbase + s.lb + t.nx + 1,
                                s.ub + t.ny + t.hs[t.yidx - 1],
                            ),
                            s.expressionUnderpainting,
                        )

                        t.nmaxX = max(t.nx, t.nmaxX)
                        t.maxxs.append(t.nx)
                        t.nx = t.codeMode * s.codeLb
                        t.ny += t.nmaxh + s.lineb
                        t.xidx = 0
                        t.yidx += 1
                        t.hs.append(t.nmaxh)
                        t.nmaxh = int(s.fontC.size / 3)
                        t.citeNum = 0
                        t.dr = 0

                        fs = t.nowf.size
                        t.nowf = t.fontK

                    t.bMode = not t.bMode

                    t.nx += 2
                    t.idx += 1
                    continue

            if (
                i == "$"
                and (text[t.idx - 1] != "\\" if t.idx >= 1 else True)
                and not t.codeMode
                and not t.bMode2
            ):
                tempIdx = t.idx
                flag = False
                while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                    tempIdx += 1
                    if text[tempIdx] == "$":
                        flag = True
                        break
                if flag or t.bMode:
                    if not t.bMode:
                        t.fontK = t.nowf
                        t.nowf = s.get_gfont(t.nowf)
                        fs = t.nowf.size
                    else:
                        fs = t.nowf.size
                        t.nowf = t.fontK
                    t.bMode = not t.bMode
                    # zx,zy = lb+nx,ub+ny+hs[yidx-1]
                    drawEffect.rectangle(
                        (
                            s.lb + t.nx - 1,
                            s.ub + t.ny,
                            s.lb + t.nx + 1,
                            s.ub + t.ny + t.hs[t.yidx - 1],
                        ),
                        s.expressionUnderpainting,
                    )
                    t.nx += 2
                    continue

            # 行内代码
            if (
                i == "`"
                and (text[t.idx - 1] != "\\" if t.idx >= 1 else True)
                and not t.codeMode
                and not t.bMode
            ):
                if not (
                    t.xidx == 1
                    and t.idx + 2 <= t.textS
                    and text[t.idx : t.idx + 3] == "```"
                ):
                    tempIdx = t.idx
                    flag = False
                    while tempIdx < t.textS - 1 and text[tempIdx + 1] != "\n":
                        tempIdx += 1
                        if text[tempIdx] == "`":
                            flag = True
                            break
                    if flag or t.bMode2:
                        if not t.bMode2:
                            t.fontK = t.nowf
                            t.nowf = s.get_gfont(t.nowf)
                            fs = t.nowf.size
                        else:
                            fs = t.nowf.size
                            t.nowf = t.fontK
                        t.bMode2 = not t.bMode2
                        zx, zy = s.lb + t.nx, s.ub + t.ny + t.hs[t.yidx - 1]
                        draw.rectangle(
                            (zx, zy - fs - 2, zx + 2, zy), s.insertCodeUnderpainting
                        )
                        t.nx += 2
                        continue

            # 普通图片 ![alt](src)
            if (
                imageIdx + 1 < len(t.images)
                and t.idx == t.images[imageIdx + 1]["begin"]
            ):
                imageIdx += 1
                t.idx = t.images[imageIdx]["end"]
                t.nowImage = t.images[imageIdx]["image"]
                t.isImage = True
                xs, ys = t.nowImage.size  # type: ignore
                nowObjH = ys

            # 代码块背景
            if t.xidx == 1 and t.codeMode:
                drawEffect.rectangle(
                    (
                        s.lb,
                        s.ub + t.ny - s.lineb,
                        s.lb + t.nmaxX,
                        s.ub + t.ny + t.nowf.size,
                    ),
                    s.codeBlockUnderpainting,
                )

            # 换行
            if i == "\n":
                t.nx = t.codeMode * s.codeLb
                t.ny += t.nmaxh + s.lineb
                t.xidx = 0
                t.yidx += 1
                if t.ny + t.hs[t.yidx - 1] > PYL:
                    t.ny = 0
                    s.lb += tlb + s.rb + t.nmaxX
                t.nmaxh = int(s.fontC.size / 3)
                t.textMode = False
                t.citeNum = 0
                if (
                    t.nowf != s.mainFont
                    and t.nowf not in [s.fontG, s.font1G, s.font2G, s.font3G]
                    and not t.codeMode
                ):
                    draw.line(
                        (s.lb, s.ub + t.ny - 2, s.lb + t.nmaxX, s.ub + t.ny - 2),
                        s.idlineColor,
                    )
                if not t.codeMode:
                    t.nowf = s.mainFont
                t.yMode = False
                continue

            # 自动换行
            if t.nx + xs > s.maxX:
                t.nx = t.codeMode * s.codeLb
                t.ny += t.nmaxh + s.lineb
                t.yidx += 1
                t.nmaxh = int(s.fontC.size)
                try:
                    if t.ny + t.hs[t.yidx - 1] > PYL:
                        t.ny = 0
                        s.lb += tlb + s.rb + t.nmaxX
                except Exception:
                    pass
                if t.citeNum:
                    t.nx += s.citeb * (t.citeNum - 1) + 5
                if t.yMode:
                    drawEffect.rectangle(
                        (
                            s.lb,
                            s.ub + t.ny - s.lineb // 2,
                            s.lb + t.nmaxX,
                            s.ub + t.ny + t.hs[t.yidx - 1] + s.lineb // 2,
                        ),
                        s.citeUnderpainting,
                    )
                    for k in range(t.citeNum - 1):
                        drawEffect.line(
                            (
                                s.lb + s.citeb * (k + 1),
                                s.ub + t.ny - s.lineb // 2,
                                s.lb + s.citeb * (k + 1),
                                s.ub + t.ny + t.hs[t.yidx - 1] + s.lineb // 2,
                            ),
                            s.citeSplitLineColor,
                            5,
                        )

            # 文字颜色
            b = s.title1FontSize - s.fontSize
            normalColor = tuple(
                int(
                    s.textColor[i]
                    + (s.textGradientEndColor[i] - s.textColor[i])
                    / b
                    * (t.nowf.size - s.fontSize)
                )
                for i in range(min(len(s.textColor), len(s.textGradientEndColor)))
            )
            if t.linkMode:
                normalColor = s.linkColor

            if islatex:
                xbase = 0

                if t.latexs[0]["super"]:
                    xbase = t.nmaxX // 2 - t.maxxs[t.yidx - 1] // 2
                else:
                    xbase = 0
                img: pillowlatex.LaTeXImage = t.latexs[0]["images"][t.nowlatexImageIdx]
                drawEffect.rectangle(
                    (
                        s.lb + t.nx + xbase,
                        s.ub + t.ny,
                        s.lb + t.nx + img.width + xbase,
                        s.ub + t.ny + t.hs[t.yidx - 1],
                    ),
                    s.expressionUnderpainting,
                )
                imgText.alpha_composite(
                    img.img,
                    (
                        s.lb + t.nx - img.space + xbase,
                        s.ub + t.ny + (t.hs[t.yidx - 1] - img.height) // 2 - img.space,
                    ),
                )
            elif t.isImage and isinstance(t.nowImage, Image.Image):
                imgImages.alpha_composite(
                    t.nowImage.convert("RGBA"),
                    (
                        int(s.lb + t.nx),
                        s.ub + t.ny + t.hs[t.yidx - 1] - t.nowImage.size[1],
                    ),
                )
            elif t.bMode or t.bMode2:
                if t.bMode:
                    drawEffect.rectangle(
                        (
                            s.lb + t.nx,
                            s.ub + t.ny + t.hs[t.yidx - 1] - t.nowf.size - 2,
                            s.lb + t.nx + xs,
                            s.ub + t.ny + t.hs[t.yidx - 1],
                        ),
                        s.expressionUnderpainting,
                    )
                    draw.text(
                        (s.lb + t.nx, s.ub + t.ny + t.hs[t.yidx - 1] - t.nowf.size - 2),
                        i,
                        s.expressionTextColor,
                        t.nowf,
                    )
                elif t.bMode2:
                    drawEffect.rectangle(
                        (
                            s.lb + t.nx,
                            s.ub + t.ny + t.hs[t.yidx - 1] - t.nowf.size - 2,
                            s.lb + t.nx + xs,
                            s.ub + t.ny + t.hs[t.yidx - 1],
                        ),
                        s.insertCodeUnderpainting,
                    )
                    draw.text(
                        (s.lb + t.nx, s.ub + t.ny + t.hs[t.yidx - 1] - t.nowf.size - 2),
                        i,
                        s.insertCodeTextColor,
                        t.nowf,
                    )
            elif t.codeMode:
                draw.text(
                    (s.lb + t.nx, s.ub + t.ny + t.hs[t.yidx - 1] - t.nowf.size - 2),
                    i,
                    s.codeBlockTextColor,
                    t.nowf,
                    **dict.fromkeys(
                        [
                            "use_under_line_mode",
                            "use_delete_line_mode",
                            "use_blod_mode",
                        ],
                        False,
                    ),
                )
            else:
                draw.text(
                    (s.lb + t.nx, s.ub + t.ny + t.hs[t.yidx - 1] - t.nowf.size),
                    i,
                    normalColor,
                    t.nowf,
                )

            t.xidx += 1
            t.nx += xs
            t.nmaxh = int(max(t.nmaxh, nowObjH))

        ChangeLockColor(None)
        ChangeBlodMode(False)
        ChangeDeleteLineMode(False)
        ChangeLinkMode(False)

        imgEffect.alpha_composite(imgText)
        imgEffect.alpha_composite(imgImages)


        outImage.alpha_composite(imgEffect)

        if bt and paintImage:
            outImage.alpha_composite(
                paintImage,
                (int(txs - s.rb - paintImage.size[0]), tys - paintImage.size[1] - s.db),
            )

        if s.decorates:
            outImage.alpha_composite(s.decorates.DrawTop(int(txs), tys))

        return outImage
