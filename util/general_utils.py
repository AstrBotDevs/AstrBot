import datetime
import time
import socket
from PIL import Image, ImageDraw, ImageFont
import os
import re
import requests

PLATFORM_GOCQ = 'gocq'
PLATFORM_QQCHAN = 'qqchan'

FG_COLORS = {
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "purple": "35",
    "cyan": "36",
    "white": "37",
    "default": "39",
}

BG_COLORS = {
    "black": "40",
    "red": "41",
    "green": "42",
    "yellow": "43",
    "blue": "44",
    "purple": "45",
    "cyan": "46",
    "white": "47",
    "default": "49",
}

LEVEL_INFO = "INFO"
LEVEL_WARNING = "WARNING"
LEVEL_ERROR = "ERROR"
LEVEL_CRITICAL = "CRITICAL"

level_colors = {
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "purple",
}

def log(
        msg: str,
        level: str = "INFO",
        tag: str = "System",
        fg: str = None,
        bg: str = None,
        max_len: int = 100):
    """
    日志记录函数
    """
    if len(msg) > max_len:
        msg = msg[:max_len] + "..."
    now = datetime.datetime.now().strftime("%m-%d %H:%M:%S")
    pre = f"[{now}] [{level}] [{tag}]: {msg}"
    if level == "INFO":
        if fg is None:
            fg = FG_COLORS["green"]
        if bg is None:
            bg = BG_COLORS["default"]
    elif level == "WARNING":
        if fg is None:
            fg = FG_COLORS["yellow"]
        if bg is None:
            bg = BG_COLORS["default"]
    elif level == "ERROR":
        if fg is None:
            fg = FG_COLORS["red"]
        if bg is None:
            bg = BG_COLORS["default"]
    elif level == "CRITICAL":
        if fg is None:
            fg = FG_COLORS["purple"]
        if bg is None:
            bg = BG_COLORS["default"]
    
    print(f"\033[{fg};{bg}m{pre}\033[0m")


def port_checker(port: int, host: str = "localhost"):
    sk = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sk.settimeout(1)
    try:
        sk.connect((host, port))
        sk.close()
        return True
    except Exception:
        sk.close()
        return False
    
def word2img(title: str, text: str, max_width=30, font_size=20):
    if os.path.exists("resources/fonts/genshin.ttf"):
        font_path = "resources/fonts/genshin.ttf"
    elif os.path.exists("QQChannelChatGPT/resources/fonts/genshin.ttf"):
        font_path = "QQChannelChatGPT/resources/fonts/genshin.ttf"
    elif os.path.exists("C:/Windows/Fonts/simhei.ttf"):
        font_path = "C:/Windows/Fonts/simhei.ttf"
    elif os.path.exists("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    else:
        raise Exception("找不到字体文件")
    
    width_factor = 1.0
    height_factor = 1.5
    # 格式化文本宽度最大为30
    lines = text.split('\n')
    i = 0
    length = len(lines)
    for l in lines:
        if len(l) > max_width:
            # lines[i] = l[:max_width] + '\n' + l[max_width:]
            # for
            cp = l
            for ii in range(len(l)):
                if ii % max_width == 0:
                    cp = cp[:ii] + '\n' + cp[ii:]
                    length += 1
            lines[i] = cp
        i += 1
    text = '\n'.join(lines)
    width = int(max_width * font_size * width_factor)
    height = int(length * font_size * height_factor)
    image = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    text_font = ImageFont.truetype(font_path, font_size)
    title_font = ImageFont.truetype(font_path, font_size + 5)
    # 标题居中
    title_width, title_height = title_font.getsize(title)
    draw.text(((width - title_width) / 2, 10), title, fill=(0, 0, 0), font=title_font)
    # 文本不居中
    draw.text((10, title_height+20), text, fill=(0, 0, 0), font=text_font)

    return image


def word2img_markdown(markdown: str, max_width=35, font_size=25):
    
    if os.path.exists("resources/fonts/genshin.ttf"):
        font_path = "resources/fonts/genshin.ttf"
    elif os.path.exists("QQChannelChatGPT/resources/fonts/genshin.ttf"):
        font_path = "QQChannelChatGPT/resources/fonts/genshin.ttf"
    elif os.path.exists("C:/Windows/Fonts/simhei.ttf"):
        font_path = "C:/Windows/Fonts/simhei.ttf"
    elif os.path.exists("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    else:
        raise Exception("找不到字体文件")
    
    # try to render markdown



def render_markdown(markdown_text, image_width=800, image_height=600, font_size=16, font_color=(0, 0, 0), bg_color=(255, 255, 255)):

    if os.path.exists("resources/fonts/genshin.ttf"):
        font_path = "resources/fonts/genshin.ttf"
    elif os.path.exists("QQChannelChatGPT/resources/fonts/genshin.ttf"):
        font_path = "QQChannelChatGPT/resources/fonts/genshin.ttf"
    elif os.path.exists("C:/Windows/Fonts/simhei.ttf"):
        font_path = "C:/Windows/Fonts/simhei.ttf"
    elif os.path.exists("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    else:
        raise Exception("找不到字体文件")
    # backup
    if os.path.exists("resources/fonts/simhei.ttf"):
        font_path1 = "resources/fonts/simhei.ttf"
    elif os.path.exists("QQChannelChatGPT/resources/fonts/simhei.ttf"):
        font_path1 = "QQChannelChatGPT/resources/fonts/simhei.ttf"
    else:
        font_path1 = font_path
    # 加载字体
    font = ImageFont.truetype(font_path, font_size)

    # pre_process, get height of each line
    pre_lines = markdown_text.split('\n')
    height = 0
    pre_in_code = False
    i = -1
    _pre_lines = []
    for line in pre_lines:
        i += 1
        if font.getsize(line)[0] > image_width:
            cp = line
            single_size = font.getsize("步")[0]
            max_words_per_line = image_width // single_size - 1
            # 步长为单个字符的宽度
            _t = 0
            for ii in range(len(line)):
                _t += 1
                if _t > max_words_per_line:
                    # splited.append(cp[:ii] + '\n')
                    _pre_lines.append(cp[:ii])
                    cp = cp[ii:]
                    _t = 0
            _pre_lines.append(cp)
        else:
            _pre_lines.append(line)
    pre_lines = _pre_lines

    i=-1
    for line in pre_lines:
        i += 1
        line = line.strip()
        if pre_in_code and not line.startswith("```"):
            height += font_size+4
            # pre_codes.append(line)
            continue
        if line.startswith("#"):
            header_level = line.count("#")
            height += 62 - header_level * 4
        elif line.startswith("-"):
            height += font_size+5
        elif line.startswith(">"):
            height += font_size+20
        elif line.startswith("```"):
            if pre_in_code:
                pre_in_code = False
                # pre_codes = []
                height += 20
            else:
                pre_in_code = True
                height += 10
        elif re.search(r"`(.*?)`", line):
            height += font_size+25
        else:
            height += font_size + 15

    markdown_text = '\n'.join(pre_lines)
    print("Pre process done, height: ", height)
    image_height = height
    
    
    # 创建空白图像
    image = Image.new('RGB', (image_width, image_height), bg_color)
    draw = ImageDraw.Draw(image)


    # # get all the emojis unicode in the markdown text
    # unicode_text = markdown_text.encode('unicode_escape').decode()
    # # print(unicode_text)
    # unicode_emojis = re.findall(r'\\U\w{8}', unicode_text)
    # emoji_base_url = "https://abs.twimg.com/emoji/v1/72x72/{unicode_emoji}.png"

    # 设置初始位置
    x, y = 10, 10

    # 解析Markdown文本
    lines = markdown_text.split("\n")
    # lines = pre_lines

    in_code_block = False
    code_block_start_y = 0
    code_block_codes = []

    for line in lines:
        if in_code_block and not line.startswith("```"):
            code_block_codes.append(line)
            y += font_size + 4
            continue
        line = line.strip()

        # y +=  28 - header_level * 4 + 20

        
        if line.startswith("#"):
            # unicode_emojis = re.findall(r'\\U0001\w{4}', line)
            # for unicode_emoji in unicode_emojis:
            #     line = line.replace(unicode_emoji, "")
            # unicode_emoji = ""
            # if len(unicode_emojis) > 0:
            #     unicode_emoji = unicode_emojis[0]
            
            # 处理标题
            header_level = line.count("#")
            line = line.strip("#").strip()
            font_size_header = 32 - header_level * 4

            # if unicode_emoji != "":
            #     emoji_url = emoji_base_url.format(unicode_emoji=unicode_emoji[-5:])
            #     emoji = Image.open(requests.get(emoji_url, stream=True).raw)
            #     emoji = emoji.resize((font_size, font_size))
            #     image.paste(emoji, (x, y))
            #     x += font_size

            font = ImageFont.truetype(font_path, font_size_header)
            draw.text((x, y), line, font=font, fill=font_color)

            # material design color: blue 500
            draw.line((x, y + font_size_header + 8, image_width - 10, y + font_size_header + 8), fill=(230, 230, 230), width=3)
            y += font_size_header + 30
        
        # y += font_size + 10
        elif line.startswith(">"):
            # 处理引用
            quote_text = line.strip(">")
            # quote_width = image_width - 20  # 引用框的宽度为图像宽度减去左右边距
            # quote_height = font_size + 10  # 引用框的高度为字体大小加上上下边距
            # quote_box = (x, y, x + quote_width, y + quote_height)
            # draw.rounded_rectangle(quote_box, radius=5, fill=(230, 230, 230), width=2)  # 使用灰色填充矩形框作为引用背景

            draw.line((x, y, x, y + font_size + 10), fill=(230, 230, 230), width=5)
            font = ImageFont.truetype(font_path, font_size)
            draw.text((x + 5, y + 5), quote_text, font=font, fill=(180, 180, 180))
            y += font_size + 25
        
        # y += 16+5
        elif line.startswith("-"):
            # 处理列表
            list_text = line.strip("-").strip()
            font_size = 16
            font = ImageFont.truetype(font_path, font_size)
            draw.text((x, y), "  ·  " + list_text, font=font, fill=font_color)
            y += font_size + 5

        # y += 5+10+font_size*line.count
        elif line.startswith("```"):
            if not in_code_block:
                code_block_start_y = y+5
                in_code_block = True
            else:
                # print(code_block_codes)
                in_code_block = False
                codes = "\n".join(code_block_codes)
                code_block_codes = []

                draw.rounded_rectangle((x, code_block_start_y, image_width - 10, y+15), radius=5, fill=(240, 240, 240), width=2)
                font = ImageFont.truetype(font_path1, 16)
                draw.text((x + 10, code_block_start_y + 5), codes, font=font, fill=font_color)

                y += 20
        # y += font_size+10
        elif re.search(r"`(.*?)`", line):
            # 处理行内代码
            code_regex = r"`(.*?)`"
            parts_inline = re.findall(code_regex, line)
            # print(parts_inline)
            parts = re.split(code_regex, line)
            # print(parts)
            for part in parts:
                # the judge has a tiny bug.
                # when line is like "hi`hi`". all the parts will be in parts_inline.
                if part in parts_inline:
                    code_text = part.strip("`")
                    font_size = 16
                    code_width = font.getsize(code_text)[0] + 10
                    code_height = font_size + 10
                    code_box = (x, y-5, x + code_width, y + code_height)
                    font = ImageFont.truetype(font_path, font_size)
                    draw.rounded_rectangle(code_box, radius=5, fill=(230, 230, 230), width=2)  # 使用灰色填充矩形框作为引用背景
                    draw.text((x+5, y), code_text, font=font, fill=font_color)
                    x += code_width
                else:
                    font_size = 16
                    font = ImageFont.truetype(font_path, font_size)
                    draw.text((x, y), part, font=font, fill=font_color)
                    x += font.getsize(part)[0]
            y += font_size + 20
            x = 10
        else:
            # 处理普通文本
            font_size = 16
            font = ImageFont.truetype(font_path, font_size)
            draw.text((x, y), line, font=font, fill=font_color)
            y += font_size + 8

    return image


def save_temp_img(img: Image) -> str:
    if not os.path.exists("temp"):
        os.makedirs("temp")

    # 获得文件创建时间，清除超过1小时的
    try:
        for f in os.listdir("temp"):
            path = os.path.join("temp", f)
            if os.path.isfile(path):
                ctime = os.path.getctime(path)
                if time.time() - ctime > 3600:
                    os.remove(path)
    except Exception as e:
        log(f"清除临时文件失败: {e}", level=LEVEL_WARNING, tag="GeneralUtils")

    # 获得时间戳
    timestamp = int(time.time())
    p = f"temp/{timestamp}.png"
    img.save(p)
    return p


def create_text_image(title: str, text: str, max_width=30, font_size=20):
    '''
    文本转图片。
    title: 标题
    text: 文本内容
    max_width: 文本宽度最大值（默认30）
    font_size: 字体大小（默认20）

    返回：文件路径
    '''
    try:
        img = word2img(title, text, max_width, font_size)
        p = save_temp_img(img)
        return p
    except Exception as e:
        raise e
    
def create_markdown_image(text: str):
    '''
    markdown文本转图片。
    返回：文件路径
    '''
    try:
        img = render_markdown(text)
        p = save_temp_img(img)
        return p
    except Exception as e:
        raise e
    
def test_markdown():
    # 示例使用
    markdown_text = """
    # Help Center
    ## 指令列表
    `/help` - 显示帮助中心
    `/start` - 开始使用
    `/about` - 关于
    `/feedback` - 反馈

    ## Plugins列表
    `/plugins` - 显示插件列表
    `/plugins enable <plugin_name>` - 启用插件
    `/plugins disable <plugin_name>` - 禁用插件

    > Hi, thanks for using this bot. If you have any questions, please contact me.

    """

    image = render_markdown(markdown_text)
    image.show()  # 显示渲染后的图像
