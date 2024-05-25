import time
import socket
import os
import re
import requests
import aiohttp
import socket
import platform
import json
import sys
import psutil
import ssl

from PIL import Image, ImageDraw, ImageFont
from type.types import GlobalObject
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot-core')


def port_checker(port: int, host: str = "localhost"):
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.settimeout(1)
    try:
        sk.connect((host, port))
        sk.close()
        return True
    except Exception:
        sk.close()
        return False


def get_font_path() -> str:
    if os.path.exists("resources/fonts/syst.otf"):
        font_path = "resources/fonts/syst.otf"
    elif os.path.exists("QQChannelChatGPT/resources/fonts/syst.otf"):
        font_path = "QQChannelChatGPT/resources/fonts/syst.otf"
    elif os.path.exists("AstrBot/resources/fonts/syst.otf"):
        font_path = "AstrBot/resources/fonts/syst.otf"
    elif os.path.exists("C:/Windows/Fonts/simhei.ttf"):
        font_path = "C:/Windows/Fonts/simhei.ttf"
    elif os.path.exists("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    else:
        raise Exception("找不到字体文件")
    return font_path


def word2img(title: str, text: str, max_width=30, font_size=20):
    font_path = get_font_path()
    width_factor = 1.0
    height_factor = 1.5
    # 格式化文本宽度最大为30
    lines = text.split('\n')
    i = 0
    length = len(lines)
    for l in lines:
        if len(l) > max_width:
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
    draw.text(((width - title_width) / 2, 10),
              title, fill=(0, 0, 0), font=title_font)
    # 文本不居中
    draw.text((10, title_height+20), text, fill=(0, 0, 0), font=text_font)

    return image


def render_markdown(markdown_text, image_width=800, image_height=600, font_size=26, font_color=(0, 0, 0), bg_color=(255, 255, 255)):

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

    font_path = get_font_path()
    font_path1 = font_path

    # 加载字体
    font = ImageFont.truetype(font_path, font_size)

    images: Image = {}

    # pre_process, get height of each line
    pre_lines = markdown_text.split('\n')
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
                image_res = Image.open(requests.get(
                    image_url, stream=True, timeout=5).raw)
                images[i] = image_res
                # 最大不得超过image_width的50%
                img_height = image_res.size[1]

                if image_res.size[0] > image_width*0.5:
                    image_res = image_res.resize(
                        (int(image_width*0.5), int(image_res.size[1]*image_width*0.5/image_res.size[0])))
                    img_height = image_res.size[1]

                height += img_height + IMAGE_MARGIN*2

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
            height += HEADER_FONT_STANDARD_SIZE + HEADER_MARGIN*2 - header_level * 4
        elif line.startswith("-"):
            height += font_size+LIST_MARGIN*2
        elif line.startswith(">"):
            height += font_size+QUOTE_LEFT_LINE_MARGIN*2
        elif line.startswith("```"):
            if pre_in_code:
                pre_in_code = False
                # pre_codes = []
                height += CODE_BLOCK_MARGIN
            else:
                pre_in_code = True
                height += CODE_BLOCK_MARGIN
        elif re.search(r"`(.*?)`", line):
            height += font_size+INLINE_CODE_FONT_MARGIN*2+INLINE_CODE_MARGIN*2
        else:
            height += font_size + TEXT_LINE_MARGIN*2

    markdown_text = '\n'.join(pre_lines)
    image_height = height
    if image_height < 100:
        image_height = 100
    image_width += 20

    # 创建空白图像
    image = Image.new('RGB', (image_width, image_height), bg_color)
    draw = ImageDraw.Draw(image)

    # 设置初始位置
    x, y = 10, 10

    # 解析Markdown文本
    lines = markdown_text.split("\n")
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
            font = ImageFont.truetype(font_path, font_size_header)
            y += HEADER_MARGIN  # 上边距
            # 字间距
            draw.text((x, y), line, font=font, fill=font_color)
            draw.line((x, y + font_size_header + 8, image_width - 10,
                      y + font_size_header + 8), fill=(230, 230, 230), width=3)
            y += font_size_header + HEADER_MARGIN

        elif line.startswith(">"):
            # 处理引用
            quote_text = line.strip(">")
            y += QUOTE_LEFT_LINE_MARGIN
            draw.line((x, y, x, y + QUOTE_LEFT_LINE_HEIGHT),
                      fill=QUOTE_LEFT_LINE_COLOR, width=QUOTE_LEFT_LINE_WIDTH)
            font = ImageFont.truetype(font_path, QUOTE_FONT_SIZE)
            draw.text((x + QUOTE_FONT_LINE_MARGIN, y + QUOTE_FONT_LINE_MARGIN),
                      quote_text, font=font, fill=QUOTE_FONT_COLOR)
            y += font_size + QUOTE_LEFT_LINE_HEIGHT + QUOTE_LEFT_LINE_MARGIN

        elif line.startswith("-"):
            # 处理列表
            list_text = line.strip("-").strip()
            font = ImageFont.truetype(font_path, LIST_FONT_SIZE)
            y += LIST_MARGIN
            draw.text((x, y), "  ·  " + list_text,
                      font=font, fill=LIST_FONT_COLOR)
            y += font_size + LIST_MARGIN

        elif line.startswith("```"):
            if not in_code_block:
                code_block_start_y = y+CODE_BLOCK_MARGIN
                in_code_block = True
            else:
                # print(code_block_codes)
                in_code_block = False
                codes = "\n".join(code_block_codes)
                code_block_codes = []
                draw.rounded_rectangle((x, code_block_start_y, image_width - 10, y+CODE_BLOCK_CODES_MARGIN_VERTICAL +
                                       CODE_BLOCK_TEXT_MARGIN), radius=5, fill=CODE_BLOCK_BG_COLOR, width=2)
                font = ImageFont.truetype(font_path1, CODE_BLOCK_FONT_SIZE)
                draw.text((x + CODE_BLOCK_CODES_MARGIN_HORIZONTAL, code_block_start_y +
                          CODE_BLOCK_CODES_MARGIN_VERTICAL), codes, font=font, fill=font_color)
                y += CODE_BLOCK_CODES_MARGIN_VERTICAL + CODE_BLOCK_MARGIN
        # y += font_size+10
        elif re.search(r"`(.*?)`", line):
            y += INLINE_CODE_MARGIN  # 上边距
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
                    font = ImageFont.truetype(font_path, INLINE_CODE_FONT_SIZE)
                    code_text = part.strip("`")
                    code_width = font.getsize(
                        code_text)[0] + INLINE_CODE_FONT_MARGIN*2
                    x += INLINE_CODE_MARGIN
                    code_box = (x, y, x + code_width,
                                y + INLINE_CODE_BG_HEIGHT)
                    draw.rounded_rectangle(
                        code_box, radius=5, fill=INLINE_CODE_BG_COLOR, width=2)  # 使用灰色填充矩形框作为引用背景
                    draw.text((x+INLINE_CODE_FONT_MARGIN, y),
                              code_text, font=font, fill=font_color)
                    x += code_width+INLINE_CODE_MARGIN-INLINE_CODE_FONT_MARGIN
                else:
                    font = ImageFont.truetype(font_path, font_size)
                    draw.text((x, y), part, font=font, fill=font_color)
                    x += font.getsize(part)[0]
            y += font_size + INLINE_CODE_MARGIN
            x = 10

        else:
            # 处理普通文本
            if line == "":
                y += TEXT_LINE_MARGIN
            else:
                font = ImageFont.truetype(font_path, font_size)

                draw.text((x, y), line, font=font, fill=font_color)
                y += font_size + TEXT_LINE_MARGIN*2

        # 图片特殊处理
        if index in images:
            image_res = images[index]
            # 最大不得超过image_width的50%
            if image_res.size[0] > image_width*0.5:
                image_res = image_res.resize(
                    (int(image_width*0.5), int(image_res.size[1]*image_width*0.5/image_res.size[0])))
            image.paste(image_res, (IMAGE_MARGIN, y))
            y += image_res.size[1] + IMAGE_MARGIN*2
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
        print(f"清除临时文件失败: {e}")

    # 获得时间戳
    timestamp = int(time.time())
    p = f"temp/{timestamp}.jpg"

    if isinstance(img, Image.Image):
        img.save(p)
    else:
        with open(p, "wb") as f:
            f.write(img)
    logger.info(f"保存临时图片: {p}")
    return p

async def download_image_by_url(url: str) -> str:
    '''
    下载图片
    '''
    try:
        logger.info(f"下载图片: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return save_temp_img(await resp.read())
    except aiohttp.client_exceptions.ClientConnectorSSLError as e:
        # 关闭SSL验证
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession(trust_env=False) as session:
            async with session.get(url, ssl=ssl_context) as resp:
                return save_temp_img(await resp.read())
    except Exception as e:
        raise e


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


def get_local_ip_addresses():
    ip = ''
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except BaseException as e:
        pass
    finally:
        s.close()
    return ip


def get_sys_info(global_object: GlobalObject):
    mem = None
    stats = global_object.dashboard_data.stats
    os_name = platform.system()
    os_version = platform.version()

    if 'sys_perf' in stats and 'memory' in stats['sys_perf']:
        mem = stats['sys_perf']['memory']
    return {
        'mem': mem,
        'os': os_name + '_' + os_version,
        'py': platform.python_version(),
    }


def upload(_global_object: GlobalObject):
    '''
    上传相关非敏感统计数据
    '''
    time.sleep(10)
    while True:
        platform_stats = {}
        llm_stats = {}
        plugin_stats = {}
        for platform in _global_object.platforms:
            platform_stats[platform.platform_name] = {
                "cnt_receive": platform.platform_instance.cnt_receive,
                "cnt_reply": platform.platform_instance.cnt_reply
            }
            
        for llm in _global_object.llms:
            stat = llm.llm_instance.model_stat
            for k in stat:
                llm_stats[llm.llm_name + "#" + k] = stat[k]
            llm.llm_instance.reset_model_stat()
            
        for plugin in _global_object.cached_plugins:
            plugin_stats[plugin.metadata.plugin_name] = {
                "metadata": plugin.metadata,
                "trig_cnt": plugin.trig_cnt
            }
            plugin.reset_trig_cnt()
        
        try:
            res = {
                "stat_version": "moon",
                "version": _global_object.version, # 版本号
                "platform_stats": platform_stats, # 过去 30 分钟各消息平台交互消息数
                "llm_stats": llm_stats,
                "plugin_stats": plugin_stats,
                "sys": sys.platform, # 系统版本
            }
            resp = requests.post(
                'https://api.soulter.top/upload', data=json.dumps(res), timeout=5)
            if resp.status_code == 200:
                ok = resp.json()
                if ok['status'] == 'ok':
                    _global_object.cnt_total = 0
        except BaseException as e:
            pass
        time.sleep(30*60)

def retry(n: int = 3):
    '''
    重试装饰器
    '''
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(n):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == n-1: raise e
                    logger.warning(f"函数 {func.__name__} 第 {i+1} 次重试... {e}")
        return wrapper
    return decorator


def run_monitor(global_object: GlobalObject):
    '''
    监测机器性能
    - Bot 内存使用量
    - CPU 占用率
    '''
    start_time = time.time()
    while True:
        stat = global_object.dashboard_data.stats
        # 程序占用的内存大小
        mem = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        stat['sys_perf'] = {
            'memory': mem,
            'cpu': psutil.cpu_percent()
        }
        stat['sys_start_time'] = start_time
        time.sleep(30)
