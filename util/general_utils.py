import datetime
import time
import socket
from PIL import Image, ImageDraw, ImageFont
import os

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
    height_factor = 1.8
    # 格式化文本宽度最大为30
    lines = text.split('\n')
    i = 0
    length = len(lines)
    for l in lines:
        if len(l) > max_width:
            lines[i] = l[:max_width] + '\n' + l[max_width:]
            length += 1
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