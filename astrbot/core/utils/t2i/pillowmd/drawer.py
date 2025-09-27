from PIL import Image, ImageDraw
from typing import Optional, Callable, Any, ParamSpec
from .mixfont import MixFont
import random
import inspect


class ImageDrawPro(ImageDraw.ImageDraw):
    def __init__(
        self,
        im,
        lock_color=None,
        blod_mode=None,
        delete_line_mode=None,
        under_line_mode=None,
        mode=None,
    ):
        super().__init__(im, mode)
        self.text_lock_color = lock_color
        self.text_blod_mode = blod_mode
        self.delete_line_mode = delete_line_mode
        self.under_line_mode = under_line_mode

    def text(
        self,
        xy,
        text,
        fill=None,
        font: Optional[MixFont] = None,
        use_lock_color=True,
        use_blod_mode=True,
        use_delete_line_mode=True,
        use_under_line_mode=True,
        *args,
        **kwargs,
    ):
        if font is None:
            raise SyntaxError("font为必选项")

        if self.text_lock_color and use_lock_color:
            fill = self.text_lock_color

        super().text((xy[0], xy[1]), text, fill, font.ft_font, *args, **kwargs)
        if self.text_blod_mode and use_blod_mode:
            for a, b in [(-1, 0), (1, 0)]:
                super().text(
                    (xy[0] + a, xy[1] + b), text, fill, font.ft_font, *args, **kwargs
                )

        if self.delete_line_mode or self.under_line_mode:
            xs, ys = font.GetSize(text)

        if self.delete_line_mode and use_delete_line_mode:
            super().line(
                (
                    xy[0],
                    xy[1] + int(font.size / 2),
                    xy[0] + xs,
                    xy[1] + int(font.size / 2),
                ),
                fill,
                int(font.size / 10) + 1,
            )

        if self.under_line_mode and use_under_line_mode:
            super().line(
                (xy[0], xy[1] + font.size + 2, xy[0] + xs, xy[1] + font.size + 2),
                fill,
                int(font.size / 10) + 1,
            )


def DefaultMdBackGroundDraw(xs: int, ys: int) -> Image.Image:
    image = Image.new("RGBA", (xs, ys), color=(0, 0, 0))

    drawUnder = ImageDrawPro(image)
    for i in range(11):
        drawUnder.rectangle(
            (0, i * int(ys / 10), xs, (i + 1) * int(ys / 10)),
            (52 - 3 * i, 73 - 4 * i, 94 - 2 * i),
        )

    imgUnder2 = Image.new("RGBA", (xs, ys), color=(0, 0, 0, 0))
    drawUnder2 = ImageDrawPro(imgUnder2)
    for i in range(int(xs * ys / 20000) + 1):
        temp = random.randint(1, 5)
        temp1 = random.randint(20, 40)
        temp2 = random.randint(10, 80)
        temp3 = random.randint(0, xs - temp * 4)
        temp4 = random.randint(-50, ys)
        for x in range(3):
            for y in range(temp1):
                if random.randint(1, 2) == 2:
                    continue
                drawUnder2.rectangle(
                    (
                        temp3 + (temp + 2) * x,
                        temp4 + (temp + 2) * y,
                        temp3 + (temp + 2) * x + temp,
                        temp4 + (temp + 2) * y + temp,
                    ),
                    (0, 255, 180, temp2),
                )

    image.alpha_composite(imgUnder2)

    return image



class MdExterImageDrawer:
    def __init__(self, drawer: Callable[..., Image.Image]):
        self.drawer = drawer

    def __call__(
        self, *args: Any, nowf: MixFont, style=None, lockColor, **kwds: Any
    ) -> Image.Image:
        kwds["nowf"] = nowf
        kwds["style"] = style
        kwds["lockColor"] = lockColor
        useVars = inspect.getfullargspec(self.drawer).args
        return self.drawer(*args, **{key: kwds[key] for key in kwds if key in useVars})


extendFuncs: dict[str, MdExterImageDrawer] = {}

P = ParamSpec("P")


def NewMdExterImageDrawer(
    name: str,
) -> Callable[[Callable[P, Image.Image]], Callable[P, Image.Image]]:
    def catch(func: Callable[P, Image.Image]) -> Callable[P, Image.Image]:
        extendFuncs[name] = MdExterImageDrawer(func)
        return func

    return catch


@NewMdExterImageDrawer("probar")
def MakeProbar(
    label: str,
    pro: float,
    size: int,
    show: str,
    nowf: MixFont,
    style = None,
) -> Image.Image:
    tempFs = nowf.GetSize(label)
    temp = int(nowf.size / 6) + 1
    halfTemp = int(temp / 2)
    exterImage = Image.new(
        "RGBA",
        (tempFs[0] + temp * 3 + size, int(nowf.size + temp * 2)),
        color=(0, 0, 0, 0),
    )
    drawEm = ImageDraw.Draw(exterImage)
    for i in range(11):
        drawEm.rectangle(
            (
                0,
                i * int((exterImage.size[1]) / 10),
                exterImage.size[0],
                (i + 1) * int((exterImage.size[1]) / 10),
            ),
            (40 + 80 - 8 * i, 40 + 80 - 8 * i, 40 + 80 - 8 * i),
        )
    drawEm.text((temp - 1, halfTemp), label, "#00CCCC", nowf.ft_font)
    drawEm.text((temp + 1, halfTemp), label, "#CCFFFF", nowf.ft_font)
    drawEm.text((temp, halfTemp), label, "#33FFFF", nowf.ft_font)
    drawEm.rectangle(
        (temp * 2 + tempFs[0], temp, temp * 2 + tempFs[0] + size, temp + nowf.size),
        (0, 0, 0),
    )
    for i in range(20):
        drawEm.rectangle(
            (
                temp * 2 + tempFs[0] + int(size * pro / 20 * i),
                temp,
                temp * 2 + tempFs[0] + int(size * pro / 20 * (i + 1)),
                temp + nowf.size,
            ),
            (
                int(78 + 78 * ((i / 20) ** 3)),
                int(177 + 177 * ((i / 20) ** 3)),
                int(177 + 177 * ((i / 20) ** 3)),
            ),
        )
    drawEm.text((temp * 3 + tempFs[0], halfTemp), show, (0, 102, 102), nowf.ft_font)
    return exterImage


@NewMdExterImageDrawer("balbar")
def MakeBalbar(
    label: str, bal: float, size: int, nowf: MixFont, style = None
) -> Image.Image:
    tempFs = nowf.GetSize(label)
    temp = int(nowf.size / 6) + 1
    halfTemp = int(temp / 2)
    exterImage = Image.new(
        "RGBA",
        (tempFs[0] + temp * 3 + size, int(nowf.size + temp * 2)),
        color=(0, 0, 0, 0),
    )
    drawEm = ImageDraw.Draw(exterImage)
    for i in range(11):
        drawEm.rectangle(
            (
                0,
                i * int((exterImage.size[1]) / 10),
                exterImage.size[0],
                (i + 1) * int((exterImage.size[1]) / 10),
            ),
            (40 + 80 - 8 * i, 40 + 80 - 8 * i, 40 + 80 - 8 * i),
        )
    drawEm.text((temp - 1, halfTemp), label, "#00CCCC", nowf.ft_font)
    drawEm.text((temp + 1, halfTemp), label, "#CCFFFF", nowf.ft_font)
    drawEm.text((temp, halfTemp), label, "#33FFFF", nowf.ft_font)
    drawEm.rectangle(
        (temp * 2 + tempFs[0], temp, temp * 2 + tempFs[0] + size, temp + nowf.size),
        (0, 0, 0),
    )
    for i in range(20):
        drawEm.rectangle(
            (
                temp * 2 + tempFs[0] + int(size * bal / 20 * i),
                temp,
                temp * 2 + tempFs[0] + int(size * bal / 20 * (i + 1)),
                temp + nowf.size,
            ),
            (
                int(78 + 78 * ((i / 20) ** 3)),
                int(177 + 177 * ((i / 20) ** 3)),
                int(177 + 177 * ((i / 20) ** 3)),
            ),
        )
        drawEm.rectangle(
            (
                temp * 2 + tempFs[0] + size - int(size * (1 - bal) / 20 * (i + 1)),
                temp,
                temp * 2 + tempFs[0] + size - int(size * (1 - bal) / 20 * i),
                temp + nowf.size,
            ),
            (
                int(177 + 177 * ((i / 20) ** 3)),
                int(21 + 21 * ((i / 20) ** 3)),
                int(21 + 21 * ((i / 20) ** 3)),
            ),
        )
    drawEm.line(
        (
            temp * 2 + tempFs[0] + int(size * bal),
            temp - halfTemp,
            temp * 2 + tempFs[0] + int(size * bal),
            temp + nowf.size + halfTemp,
        ),
        (255, 255, 255),
        5,
    )
    if bal == 0.5:
        drawEm.text(
            (temp * 2 + tempFs[0] + int(size * bal) + 3, halfTemp),
            "+0%",
            (102, 0, 0),
            nowf.ft_font,
        )
    elif bal > 0.5:
        if bal == 1:
            text = "+∞%"
        else:
            text = f"+{round(bal / (1 - bal) * 100 - 100, 2)}%"
        drawEm.text(
            (
                temp * 2 + tempFs[0] + int(size * bal) - nowf.GetSize(text)[0] - 3,
                halfTemp,
            ),
            text,
            (0, 102, 102),
            nowf.ft_font,
        )
    elif bal < 0.5:
        if bal == 0:
            text = "-∞%"
        else:
            text = f"-{round((1 - bal) / bal * 100 - 100, 2)}%"
        drawEm.text(
            (temp * 2 + tempFs[0] + int(size * bal) + 3, halfTemp),
            text,
            (102, 0, 0),
            nowf.ft_font,
        )

    return exterImage


@NewMdExterImageDrawer("chabar")
def MakeChabar(
    objs: list[tuple[str, int]],
    xSize: int,
    ySize: int,
    nowf: MixFont,
    style = None,
) -> Image.Image:
    if not style:
        from .style import MdStyle
        style = MdStyle()
    nums = [nowf.GetSize(str(i[1])) for i in objs]
    strs = [nowf.GetSize(i[0]) for i in objs]
    space = int(xSize / (len(objs) * 2 + 1))
    halfSpace = int(space / 2)

    exterImage = Image.new(
        "RGBA",
        (
            int(
                max([i[0] for i in nums])
                + xSize
                + max(strs[-1][0] / 2 - space * 1.5, 0)
            )
            + 5,
            int(ySize + nums[0][1] / 2 + max([i[1] for i in strs])) + 5,
        ),
        color=(0, 0, 0, 0),
    )
    drawEm = ImageDraw.Draw(exterImage)

    lineY = int(ySize + nums[0][1] / 2) - 5
    lineX = int(max([i[0] for i in nums]) + 5)

    maxM = max([i[1] for i in objs])

    for i in range(len(objs)):
        X = space * (1 + i * 2)
        Y = int(ySize * 0.8 * objs[i][1] / maxM)
        color = style.textGradientEndColor
        drawEm.line(
            (lineX, lineY - Y, lineX + X + space, lineY - Y),
            (int(color[0] * 0.6), int(color[1] * 0.6), int(color[2] * 0.6)),
            1,
        )
        drawEm.text(
            (lineX - nums[i][0] - 5, lineY - Y - int(nums[i][1] / 2)),
            str(objs[i][1]),
            style.textColor,
            nowf.ft_font,
        )
        drawEm.text(
            (int(lineX + X + space / 2 - strs[i][0] / 2), lineY + 5),
            objs[i][0],
            style.textColor,
            nowf.ft_font,
        )
        drawEm.rectangle(
            (lineX + X, lineY - Y, lineX + X + space, lineY), style.textGradientEndColor
        )
        drawEm.text(
            (lineX + X + halfSpace - int(nums[i][0] / 2), lineY - Y - nowf.size - 2),
            str(objs[i][1]),
            style.textColor,
            nowf.ft_font,
        )

    drawEm.line((lineX, lineY, lineX + xSize, lineY), style.textColor, 1)
    drawEm.polygon(
        [
            (lineX + xSize, lineY),
            (lineX + xSize - 3, lineY - 3),
            (lineX + xSize - 3, lineY + 3),
        ],
        style.textColor,
    )
    drawEm.line((lineX, lineY - ySize, lineX, lineY), style.textColor, 1)
    drawEm.polygon(
        [
            (lineX, lineY - ySize),
            (lineX - 3, lineY - ySize + 3),
            (lineX + 3, lineY - ySize + 3),
        ],
        style.textColor,
    )

    return exterImage


@NewMdExterImageDrawer("card")
def MakeCard(
    title: str,
    text: str,
    xSize: int,
    ySize: int,
    file: str,
    nowf: MixFont,
    style = None,
) -> Image.Image:
    """创建卡片"""
    if xSize < ySize:
        raise ValueError("xSize必须比ySize大")
    im = Image.open(file)
    back = Image.new("RGBA", (xSize, ySize), (0, 0, 0))
    d = ImageDrawPro(back)

    im = im.resize((ySize - 8, ySize - 8))
    d.rectangle((0, 0, xSize, ySize), (27, 26, 85))
    d.rectangle((0, 0, ySize, ySize), (83, 92, 145))
    d.rectangle((2, 2, ySize - 2, ySize - 2), (83, 92, 145))

    back.paste(im, (4, 4))

    d.text((ySize + 8, 8), title, (30, 255, 255), nowf)
    x, y = ySize + 8, 8 + nowf.size + 8
    for i in text:
        s = nowf.GetSize(i)
        if x + s[0] > xSize or i == "\n":
            x = ySize + 8
            y += nowf.size + 8
        d.text((x, y), i, (255, 255, 255), nowf)
        x += s[0]

    return back


