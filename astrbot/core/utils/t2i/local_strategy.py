import re
import aiohttp
from io import BytesIO

from . import RenderStrategy
from PIL import ImageFont, Image, ImageDraw
from astrbot.core.utils.io import save_temp_img


class LocalRenderStrategy(RenderStrategy):
    async def render_custom_template(
        self, tmpl_str: str, tmpl_data: dict, return_url: bool = True
    ) -> str:
        raise NotImplementedError

    def get_font(self, size: int) -> ImageFont.FreeTypeFont:
        # common and default fonts on Windows, macOS and Linux
        fonts = [
            "msyh.ttc",
            "NotoSansCJK-Regular.ttc",
            "msyhbd.ttc",
            "PingFang.ttc",
            "Heiti.ttc",
        ]
        for font in fonts:
            try:
                font = ImageFont.truetype(font, size)
                return font
            except Exception:
                pass

    async def render(self, text: str, return_url: bool = False) -> str:
        font_size = 26
        image_width = 800
        image_height = 600
        font_color = (0, 0, 0)
        bg_color = (255, 255, 255)

        HEADER_MARGIN = 20
        HEADER_FONT_STANDARD_SIZE = 42

        QUOTE_LEFT_LINE_MARGIN = 10
        QUOTE_FONT_LINE_MARGIN = 6  # 引用文字距离左边线的距离和上下的距离
        QUOTE_LEFT_LINE_HEIGHT = font_size + QUOTE_FONT_LINE_MARGIN * 2
        QUOTE_LEFT_LINE_WIDTH = 5
        QUOTE_LEFT_LINE_COLOR = (180, 180, 180)
        QUOTE_FONT_SIZE = font_size
        QUOTE_FONT_COLOR = (180, 180, 180)
        # QUOTE_BG_COLOR = (255, 255, 255)

        CODE_BLOCK_MARGIN = 10
        CODE_BLOCK_FONT_SIZE = font_size
        CODE_BLOCK_FONT_COLOR = (255, 255, 255)
        CODE_BLOCK_BG_COLOR = (240, 240, 240)
        CODE_BLOCK_CODES_MARGIN_VERTICAL = 5  # 代码块和代码之间的距离
        CODE_BLOCK_CODES_MARGIN_HORIZONTAL = 5  # 代码块和代码之间的距离
        CODE_BLOCK_TEXT_MARGIN = 4  # 代码和代码之间的距离

        INLINE_CODE_MARGIN = 8
        INLINE_CODE_FONT_SIZE = font_size
        INLINE_CODE_FONT_COLOR = font_color
        INLINE_CODE_FONT_MARGIN = 4
        INLINE_CODE_BG_COLOR = (230, 230, 230)
        INLINE_CODE_BG_HEIGHT = INLINE_CODE_FONT_SIZE + INLINE_CODE_FONT_MARGIN * 2

        LIST_MARGIN = 8
        LIST_FONT_SIZE = font_size
        LIST_FONT_COLOR = font_color

        TEXT_LINE_MARGIN = 8

        IMAGE_MARGIN = 15
        # 用于匹配图片的正则表达式
        IMAGE_REGEX = r"!\s*\[.*?\]\s*\((.*?)\)"

        # 加载字体
        font = self.get_font(font_size)

        images: Image = {}

        # pre_process, get height of each line
        pre_lines = text.split("\n")
        height = 0
        pre_in_code = False
        i = -1
        _pre_lines = []
        for line in pre_lines:
            i += 1
            # 处理图片
            if re.search(IMAGE_REGEX, line):
                try:
                    image_url = re.findall(IMAGE_REGEX, line)[0]
                    print(image_url)
                    async with aiohttp.ClientSession(trust_env=True) as session:
                        async with session.get(image_url) as resp:
                            image_res = Image.open(BytesIO(await resp.read()))
                    images[i] = image_res
                    # 最大不得超过image_width的50%
                    img_height = image_res.size[1]

                    if image_res.size[0] > image_width * 0.5:
                        image_res = image_res.resize(
                            (
                                int(image_width * 0.5),
                                int(
                                    image_res.size[1]
                                    * image_width
                                    * 0.5
                                    / image_res.size[0]
                                ),
                            )
                        )
                        img_height = image_res.size[1]

                    height += img_height + IMAGE_MARGIN * 2

                    line = re.sub(IMAGE_REGEX, "", line)
                except Exception as e:
                    print(e)
                    line = re.sub(IMAGE_REGEX, "\n[加载失败的图片]\n", line)
                    continue

            line.replace("\t", "    ")
            if font.getsize(line)[0] > image_width:
                cp = line
                _width = 0
                _word_cnt = 0
                for ii in range(len(line)):
                    # 检测是否是中文
                    _width += font.getsize(line[ii])[0]
                    _word_cnt += 1
                    if _width > image_width:
                        _pre_lines.append(cp[:_word_cnt])
                        cp = cp[_word_cnt:]
                        _word_cnt = 0
                        _width = 0
                _pre_lines.append(cp)
            else:
                _pre_lines.append(line)
        pre_lines = _pre_lines

        i = -1
        for line in pre_lines:
            if line == "":
                height += TEXT_LINE_MARGIN
                continue
            i += 1
            line = line.strip()
            if pre_in_code and not line.startswith("```"):
                height += font_size + CODE_BLOCK_TEXT_MARGIN
                # pre_codes.append(line)
                continue
            if line.startswith("#"):
                header_level = line.count("#")
                height += (
                    HEADER_FONT_STANDARD_SIZE + HEADER_MARGIN * 2 - header_level * 4
                )
            elif line.startswith("-"):
                height += font_size + LIST_MARGIN * 2
            elif line.startswith(">"):
                height += font_size + QUOTE_LEFT_LINE_MARGIN * 2
            elif line.startswith("```"):
                if pre_in_code:
                    pre_in_code = False
                    # pre_codes = []
                    height += CODE_BLOCK_MARGIN
                else:
                    pre_in_code = True
                    height += CODE_BLOCK_MARGIN
            elif re.search(r"`(.*?)`", line):
                height += (
                    font_size + INLINE_CODE_FONT_MARGIN * 2 + INLINE_CODE_MARGIN * 2
                )
            else:
                height += font_size + TEXT_LINE_MARGIN * 2

        text = "\n".join(pre_lines)
        image_height = height
        if image_height < 100:
            image_height = 100
        image_width += 20

        # 创建空白图像
        image = Image.new("RGB", (image_width, image_height), bg_color)
        draw = ImageDraw.Draw(image)

        # 设置初始位置
        x, y = 10, 10

        # 解析Markdown文本
        lines = text.split("\n")
        # lines = pre_lines

        in_code_block = False
        code_block_start_y = 0
        code_block_codes = []

        index = -1
        for line in lines:
            index += 1
            if in_code_block and not line.startswith("```"):
                code_block_codes.append(line)
                y += font_size + CODE_BLOCK_TEXT_MARGIN
                continue
            line = line.strip()

            if line.startswith("#"):
                # 处理标题
                header_level = line.count("#")
                line = line.strip("#").strip()
                font_size_header = HEADER_FONT_STANDARD_SIZE - header_level * 4
                font = self.get_font(font_size_header)
                y += HEADER_MARGIN  # 上边距
                # 字间距
                draw.text((x, y), line, font=font, fill=font_color)
                draw.line(
                    (
                        x,
                        y + font_size_header + 8,
                        image_width - 10,
                        y + font_size_header + 8,
                    ),
                    fill=(230, 230, 230),
                    width=3,
                )
                y += font_size_header + HEADER_MARGIN

            elif line.startswith(">"):
                # 处理引用
                quote_text = line.strip(">")
                y += QUOTE_LEFT_LINE_MARGIN
                draw.line(
                    (x, y, x, y + QUOTE_LEFT_LINE_HEIGHT),
                    fill=QUOTE_LEFT_LINE_COLOR,
                    width=QUOTE_LEFT_LINE_WIDTH,
                )
                font = self.get_font(QUOTE_FONT_SIZE)
                draw.text(
                    (x + QUOTE_FONT_LINE_MARGIN, y + QUOTE_FONT_LINE_MARGIN),
                    quote_text,
                    font=font,
                    fill=QUOTE_FONT_COLOR,
                )
                y += font_size + QUOTE_LEFT_LINE_HEIGHT + QUOTE_LEFT_LINE_MARGIN

            elif line.startswith("-"):
                # 处理列表
                list_text = line.strip("-").strip()
                font = self.get_font(LIST_FONT_SIZE)
                y += LIST_MARGIN
                draw.text((x, y), "  ·  " + list_text, font=font, fill=LIST_FONT_COLOR)
                y += font_size + LIST_MARGIN

            elif line.startswith("```"):
                if not in_code_block:
                    code_block_start_y = y + CODE_BLOCK_MARGIN
                    in_code_block = True
                else:
                    # print(code_block_codes)
                    in_code_block = False
                    codes = "\n".join(code_block_codes)
                    code_block_codes = []
                    draw.rounded_rectangle(
                        (
                            x,
                            code_block_start_y,
                            image_width - 10,
                            y
                            + CODE_BLOCK_CODES_MARGIN_VERTICAL
                            + CODE_BLOCK_TEXT_MARGIN,
                        ),
                        radius=5,
                        fill=CODE_BLOCK_BG_COLOR,
                        width=2,
                    )
                    font = self.get_font(CODE_BLOCK_FONT_SIZE)
                    draw.text(
                        (
                            x + CODE_BLOCK_CODES_MARGIN_HORIZONTAL,
                            code_block_start_y + CODE_BLOCK_CODES_MARGIN_VERTICAL,
                        ),
                        codes,
                        font=font,
                        fill=font_color,
                    )
                    y += CODE_BLOCK_CODES_MARGIN_VERTICAL + CODE_BLOCK_MARGIN
            # y += font_size+10
            elif re.search(r"`(.*?)`", line):
                y += INLINE_CODE_MARGIN  # 上边距
                # 处理行内代码
                code_regex = r"`(.*?)`"
                parts_inline = re.findall(code_regex, line)
                parts = re.split(code_regex, line)
                for part in parts:
                    # the judge has a tiny bug.
                    # when line is like "hi`hi`". all the parts will be in parts_inline.
                    if part in parts_inline:
                        font = self.get_font(INLINE_CODE_FONT_SIZE)
                        code_text = part.strip("`")
                        code_width = (
                            font.getsize(code_text)[0] + INLINE_CODE_FONT_MARGIN * 2
                        )
                        x += INLINE_CODE_MARGIN
                        code_box = (x, y, x + code_width, y + INLINE_CODE_BG_HEIGHT)
                        draw.rounded_rectangle(
                            code_box, radius=5, fill=INLINE_CODE_BG_COLOR, width=2
                        )  # 使用灰色填充矩形框作为引用背景
                        draw.text(
                            (x + INLINE_CODE_FONT_MARGIN, y),
                            code_text,
                            font=font,
                            fill=font_color,
                        )
                        x += code_width + INLINE_CODE_MARGIN - INLINE_CODE_FONT_MARGIN
                    else:
                        font = self.get_font(font_size)
                        draw.text((x, y), part, font=font, fill=font_color)
                        x += font.getsize(part)[0]
                y += font_size + INLINE_CODE_MARGIN
                x = 10

            else:
                # 处理普通文本
                if line == "":
                    y += TEXT_LINE_MARGIN
                else:
                    font = self.get_font(font_size)

                    draw.text((x, y), line, font=font, fill=font_color)
                    y += font_size + TEXT_LINE_MARGIN * 2

            # 图片特殊处理
            if index in images:
                image_res = images[index]
                # 最大不得超过image_width的50%
                if image_res.size[0] > image_width * 0.5:
                    image_res = image_res.resize(
                        (
                            int(image_width * 0.5),
                            int(
                                image_res.size[1]
                                * image_width
                                * 0.5
                                / image_res.size[0]
                            ),
                        )
                    )
                image.paste(image_res, (IMAGE_MARGIN, y))
                y += image_res.size[1] + IMAGE_MARGIN * 2
        return save_temp_img(image)
