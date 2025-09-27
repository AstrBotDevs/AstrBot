from PIL import Image
from pathlib import Path


class MDDecorates:
    """
    管理 Markdown 渲染所需的背景与装饰图层。
    支持：
    - 背景模式（0 单图填充 / 1 九宫格）
    - 顶部/底部装饰图（九宫格时可选“包含在中心区域”）
    """

    def __init__(
        self,
        backGroundMode: int,
        backGroundData: dict,
        topDecorates: dict,
        bottomDecorates: dict,
        backGroundsPath: Path,
    ) -> None:
        self.backGroundMode = backGroundMode
        self.backGroundData = backGroundData
        self.topDecorates = topDecorates
        self.bottomDecorates = bottomDecorates
        self.backGroundsPath = backGroundsPath
        self.imageCache = {}

    def _get_image(self, name: str) -> Image.Image:
        if name not in self.imageCache:
            p: Path = self.backGroundsPath / name
            if not p.is_file():
                raise FileNotFoundError(f"背景图片不存在: {p.resolve()}")
            self.imageCache[name] = Image.open(p)
        return self.imageCache[name]

    def _calc_nine_patch_bounds(self, x: int, y: int, bdata: dict):
        """九宫格模式下计算四角宽高及调整画布大小"""

        corner1 = self._get_image(bdata["left-up"])
        corner2 = self._get_image(bdata["right-up"])
        corner3 = self._get_image(bdata["right-down"])
        corner4 = self._get_image(bdata["left-down"])

        cxs1 = max(corner1.width, corner4.width)
        cxs2 = max(corner2.width, corner3.width)
        cys1 = max(corner1.height, corner2.height)
        cys2 = max(corner3.height, corner4.height)

        x = max(cxs1 + cxs2 + 1, x)
        y = max(cys1 + cys2 + 1, y)

        return (corner1, corner2, corner3, corner4), (cxs1, cys1, cxs2, cys2, x, y)

    def _fill_image(self, bg: Image.Image, img: Image.Image, mode: int) -> None:
        """按模式填充背景"""
        w, h = bg.size
        iw, ih = img.size

        def tile(
            img: Image.Image, dx: int, dy: int, offset_x: int = 0, offset_y: int = 0
        ):
            for y0 in range(offset_y, h, dy):
                for x0 in range(offset_x, w, dx):
                    bg.paste(img, (x0, y0))

        if mode == 0:  # 单图拉伸
            bg.paste(img.resize((w, h)))

        elif mode == 1:  # 九宫格（注意：一般用于 Android NinePatch，这里保留原逻辑）
            iw3, ih3 = iw // 3, ih // 3
            parts = [
                img.crop((i * iw3, j * ih3, (i + 1) * iw3, (j + 1) * ih3))
                for j in range(3)
                for i in range(3)
            ]
            bg.paste(parts[4].resize((w - 2 * iw3, h - 2 * ih3)), (iw3, ih3))
            for i in range(3):
                bg.paste(parts[i].resize((iw3, h - 2 * ih3)), (i * iw3, ih3))
                bg.paste(parts[6 + i].resize((iw3, h - 2 * ih3)), (i * iw3, h - ih3))
            for j in range(3):
                bg.paste(parts[j * 3].resize((w - 2 * iw3, ih3)), (iw3, j * ih3))
                bg.paste(
                    parts[j * 3 + 2].resize((w - 2 * iw3, ih3)), (w - iw3, j * ih3)
                )
            for j in range(3):
                for i in range(3):
                    if (i, j) == (1, 1):
                        continue
                    bg.paste(parts[j * 3 + i], (i * iw3, j * ih3))

        elif mode in (3, 4, 5, 6):  # 平铺模式
            if mode == 3:  # 横向平铺
                img = img.resize((iw, h))
                tile(img, iw, h)
            elif mode == 4:  # 纵向平铺
                img = img.resize((w, ih))
                tile(img, w, ih)
            elif mode == 5:  # 横纵平铺
                tile(img, iw, ih)
            elif mode == 6:  # 居中平铺
                offset_x, offset_y = (w - iw) // 2 % iw, (h - ih) // 2 % ih
                tile(img, iw, ih, offset_x, offset_y)

    def _image_resize(
        self, x: int, y: int, img: Image.Image, data: dict
    ) -> Image.Image:
        match data["mode"]:
            case 0:
                ...
            case 1:
                rawSize = img.size
                xs1 = int(x * data["xlimit"])
                xs2 = int((y * data["ylimit"]) / rawSize[0] * rawSize[1])
                if xs1 > xs2:
                    size = (xs2, int(y * data["ylimit"]))
                else:
                    size = (xs1, int(xs1 / rawSize[0] * rawSize[1]))
                if "min" in data and size[0] < img.size[0] * data["min"]:
                    size = (int(size[0] * data["min"]), int(size[1] * data["min"]))
                if "max" in data and size[0] > img.size[0] * data["max"]:
                    size = (int(size[0] * data["max"]), int(size[1] * data["max"]))
                img = img.resize(size)
        return img


    def _draw_decorates(
        self,
        oimg: Image.Image,
        decoratesDict: dict,
        x: int,
        y: int,
        bmode: int,
        cxs1: int,
        cys1: int,
        cxs2: int,
        cys2: int,
    ) -> None:
        def pos_func(pos: str, kx: int, ky: int, img: Image.Image) -> tuple[int, int]:
            w, h = img.size
            return {
                "left-up": (0, 0),
                "left": (0, int(ky / 2 - h / 2)),
                "left-down": (0, ky - h),
                "up": (int(kx / 2 - w / 2), 0),
                "down": (int(kx / 2 - w / 2), ky - h),
                "right-up": (kx - w, 0),
                "right": (kx - w, int(ky / 2 - h / 2)),
                "right-down": (kx - w, ky - h),
                "middle": (int(kx / 2 - w / 2), int(ky / 2 - h / 2)),
            }[pos]

        for pos, lst in decoratesDict.items():
            for decorates in lst:
                kx, ky = x, y
                icMode = False
                if bmode == 1 and decorates.get("include"):
                    kx, ky = max(x - cxs1 - cxs2, 1), max(y - cys1 - cys2, 1)
                    icMode = True
                img = self._image_resize(
                    kx, ky, self._get_image(decorates["img"]), decorates
                )
                k = Image.new("RGBA", (kx, ky))
                k.paste(img, pos_func(pos, kx, ky, img))
                oimg.alpha_composite(k, (cxs1, cys1) if icMode else (0, 0))

    def Draw(self, x: int, y: int) -> Image.Image:
        rx, ry = x, y
        oimg = Image.new("RGBA", (x, y))
        bdata = self.backGroundData
        cxs1 = cys1 = cxs2 = cys2 = 0

        if self.backGroundMode == 0:
            self._fill_image(oimg, self._get_image(bdata["img"]), bdata["mode"])
        elif self.backGroundMode == 1:
            (corner1, corner2, corner3, corner4), (cxs1, cys1, cxs2, cys2, x, y) = (
                self._calc_nine_patch_bounds(x, y, bdata)
            )
            oimg = Image.new("RGBA", (x, y))
            oimg.paste(corner1, (0, 0))
            oimg.paste(corner2, (x - cxs2, 0))
            oimg.paste(corner3, (x - cxs2, y - cys2))
            oimg.paste(corner4, (0, y - cys2))

            img = self._get_image(bdata["up"])
            temp = Image.new("RGBA", (x - cxs1 - cxs2, cys1))
            self._fill_image(temp, img, {0: 0, 1: 3, 2: 5}[bdata["ud-mode"]])
            oimg.paste(temp, (cxs1, 0))

            img = self._get_image(bdata["down"])
            temp = Image.new("RGBA", (x - cxs1 - cxs2, cys2))
            self._fill_image(temp, img, {0: 0, 1: 3, 2: 5}[bdata["ud-mode"]])
            oimg.paste(temp, (cxs1, y - cys2))

            img = self._get_image(bdata["left"])
            temp = Image.new("RGBA", (cxs1, y - cys1 - cys2))
            self._fill_image(temp, img, {0: 0, 1: 4, 2: 6}[bdata["lr-mode"]])
            oimg.paste(temp, (0, cys1))

            img = self._get_image(bdata["right"])
            temp = Image.new("RGBA", (cxs2, y - cys1 - cys2))
            self._fill_image(temp, img, {0: 0, 1: 4, 2: 6}[bdata["lr-mode"]])
            oimg.paste(temp, (x - cxs2, cys1))

            img = self._get_image(bdata["middle"])
            temp = Image.new("RGBA", (x - cxs1 - cxs2, y - cys1 - cys2))
            self._fill_image(temp, img, bdata["middle-mode"])
            oimg.paste(temp, (cxs1, cys1))

        self._draw_decorates(
            oimg,
            self.bottomDecorates,
            x,
            y,
            self.backGroundMode,
            cxs1,
            cys1,
            cxs2,
            cys2,
        )
        if rx != x:
            oimg = oimg.resize((rx, ry))
        return oimg

    def DrawTop(self, x: int, y: int) -> Image.Image:
        rx, ry = x, y
        oimg = Image.new("RGBA", (x, y))
        cxs1 = cys1 = cxs2 = cys2 = 0

        if self.backGroundMode == 1:
            _, (cxs1, cys1, cxs2, cys2, x, y) = self._calc_nine_patch_bounds(
                x, y, self.backGroundData
            )
            oimg = Image.new("RGBA", (x, y))

        self._draw_decorates(
            oimg, self.topDecorates, x, y, self.backGroundMode, cxs1, cys1, cxs2, cys2
        )
        if rx != x:
            oimg = oimg.resize((rx, ry))
        return oimg
