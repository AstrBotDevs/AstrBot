import re
import aiohttp
import ssl
import certifi
from io import BytesIO
from typing import List, Tuple
from abc import ABC, abstractmethod
from astrbot.core.config import VERSION

from . import RenderStrategy
from PIL import ImageFont, Image, ImageDraw
from astrbot.core.utils.io import save_temp_img


class FontManager:
    """字体管理类，负责加载和缓存字体"""
    
    _font_cache = {}
    
    @classmethod
    def get_font(cls, size: int) -> ImageFont.FreeTypeFont:
        """获取指定大小的字体，优先从缓存获取"""
        if size in cls._font_cache:
            return cls._font_cache[size]
        
        # 首先尝试加载自定义字体
        try:
            font = ImageFont.truetype("data/font.ttf", size)
            cls._font_cache[size] = font
            return font
        except Exception:
            pass
            
        # 跨平台常见字体列表
        fonts = [
            "msyh.ttc",           # Windows
            "NotoSansCJK-Regular.ttc",  # Linux
            "msyhbd.ttc",         # Windows
            "PingFang.ttc",       # macOS
            "Heiti.ttc",          # macOS
            "Arial.ttf",          # 通用
            "DejaVuSans.ttf",     # Linux
        ]
        
        for font_name in fonts:
            try:
                font = ImageFont.truetype(font_name, size)
                cls._font_cache[size] = font
                return font
            except Exception:
                continue
                
        # 如果所有字体都失败，使用默认字体
        try:
            default_font = ImageFont.load_default()
            # PIL默认字体大小固定，这里不缓存
            return default_font
        except Exception:
            raise RuntimeError("无法加载任何字体")


class TextMeasurer:
    """测量文本尺寸的工具类"""
    
    @staticmethod
    def get_text_size(text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
        """获取文本的尺寸"""
        try:
            # PIL 9.0.0 以上版本
            return font.getbbox(text)[2:] if hasattr(font, 'getbbox') else font.getsize(text)
        except Exception:
            # 兼容旧版本
            return font.getsize(text)

    @staticmethod
    def split_text_to_fit_width(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        """将文本拆分为多行，确保每行不超过指定宽度"""
        lines = []
        if not text:
            return lines
            
        remaining_text = text
        while remaining_text:
            # 如果文本宽度小于最大宽度，直接添加
            text_width = TextMeasurer.get_text_size(remaining_text, font)[0]
            if text_width <= max_width:
                lines.append(remaining_text)
                break
                
            # 尝试逐字计算能放入当前行的最多字符
            for i in range(len(remaining_text), 0, -1):
                width = TextMeasurer.get_text_size(remaining_text[:i], font)[0]
                if width <= max_width:
                    lines.append(remaining_text[:i])
                    remaining_text = remaining_text[i:]
                    break
            else:
                # 如果单个字符都放不下，强制放一个字符
                lines.append(remaining_text[0])
                remaining_text = remaining_text[1:]
                
        return lines


class MarkdownElement(ABC):
    """Markdown元素的基类"""
    
    def __init__(self, content: str):
        self.content = content
        
    @abstractmethod
    def calculate_height(self, image_width: int, font_size: int) -> int:
        """计算元素的高度"""
        pass
        
    @abstractmethod
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        """渲染元素到图像，返回新的y坐标"""
        pass


class TextElement(MarkdownElement):
    """普通文本元素"""
    
    def calculate_height(self, image_width: int, font_size: int) -> int:
        if not self.content.strip():
            return 10  # 空行高度
            
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
        return len(lines) * (font_size + 8)
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        if not self.content.strip():
            return y + 10  # 空行
            
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
        
        for line in lines:
            draw.text((x, y), line, font=font, fill=(0, 0, 0))
            y += font_size + 8
            
        return y


class BoldTextElement(MarkdownElement):
    """粗体文本元素"""
    
    def calculate_height(self, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
        return len(lines) * (font_size + 8)
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        # 尝试使用粗体字体，如果没有则绘制两次模拟粗体效果
        try:
            bold_fonts = [
                "msyhbd.ttc",     # 微软雅黑粗体 (Windows)
                "Arial-Bold.ttf",  # Arial粗体
                "DejaVuSans-Bold.ttf",  # Linux粗体
            ]
            
            bold_font = None
            for font_name in bold_fonts:
                try:
                    bold_font = ImageFont.truetype(font_name, font_size)
                    break
                except Exception:
                    continue
                    
            if bold_font:
                lines = TextMeasurer.split_text_to_fit_width(self.content, bold_font, image_width - 20)
                for line in lines:
                    draw.text((x, y), line, font=bold_font, fill=(0, 0, 0))
                    y += font_size + 8
            else:
                # 如果没有粗体字体，则绘制两次文本轻微偏移以模拟粗体
                font = FontManager.get_font(font_size)
                lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
                for line in lines:
                    draw.text((x, y), line, font=font, fill=(0, 0, 0))
                    draw.text((x+1, y), line, font=font, fill=(0, 0, 0))
                    y += font_size + 8
        except Exception:
            # 兜底方案：使用普通字体
            font = FontManager.get_font(font_size)
            lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
            for line in lines:
                draw.text((x, y), line, font=font, fill=(0, 0, 0))
                y += font_size + 8
                
        return y


class ItalicTextElement(MarkdownElement):
    """斜体文本元素"""
    
    def calculate_height(self, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
        return len(lines) * (font_size + 8)
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        # 尝试使用斜体字体，如果没有则使用倾斜变换模拟斜体效果
        try:
            italic_fonts = [
                "msyhi.ttc",      # 微软雅黑斜体 (Windows)
                "Arial-Italic.ttf",  # Arial斜体
                "DejaVuSans-Oblique.ttf",  # Linux斜体
            ]
            
            italic_font = None
            for font_name in italic_fonts:
                try:
                    italic_font = ImageFont.truetype(font_name, font_size)
                    break
                except Exception:
                    continue
                    
            if italic_font:
                lines = TextMeasurer.split_text_to_fit_width(self.content, italic_font, image_width - 20)
                for line in lines:
                    draw.text((x, y), line, font=italic_font, fill=(0, 0, 0))
                    y += font_size + 8
            else:
                # 如果没有斜体字体，使用变换
                font = FontManager.get_font(font_size)
                lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
                
                for line in lines:
                    # 先创建一个临时图像用于倾斜处理
                    text_width, text_height = TextMeasurer.get_text_size(line, font)
                    text_img = Image.new('RGBA', (text_width + 20, text_height + 10), (0, 0, 0, 0))
                    text_draw = ImageDraw.Draw(text_img)
                    text_draw.text((0, 0), line, font=font, fill=(0, 0, 0, 255))
                    
                    # 倾斜变换，使用仿射变换实现斜体效果
                    # 变换矩阵: [1, 0.2, 0, 0, 1, 0]
                    italic_img = text_img.transform(
                        text_img.size, 
                        Image.AFFINE, 
                        (1, 0.2, 0, 0, 1, 0), 
                        Image.BICUBIC
                    )
                    
                    # 粘贴到原图像
                    image.paste(italic_img, (x, y), italic_img)
                    y += font_size + 8
        except Exception:
            # 兜底方案：使用普通字体
            font = FontManager.get_font(font_size)
            lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
            for line in lines:
                draw.text((x, y), line, font=font, fill=(0, 0, 0))
                y += font_size + 8
                
        return y


class UnderlineTextElement(MarkdownElement):
    """下划线文本元素"""
    
    def calculate_height(self, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
        return len(lines) * (font_size + 8)
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
        
        for line in lines:
            # 绘制文本
            draw.text((x, y), line, font=font, fill=(0, 0, 0))
            
            # 绘制下划线
            text_width, _ = TextMeasurer.get_text_size(line, font)
            underline_y = y + font_size + 2
            draw.line((x, underline_y, x + text_width, underline_y), fill=(0, 0, 0), width=1)
            
            y += font_size + 8
            
        return y


class StrikethroughTextElement(MarkdownElement):
    """删除线文本元素"""
    
    def calculate_height(self, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
        return len(lines) * (font_size + 8)
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
        
        for line in lines:
            # 绘制文本
            draw.text((x, y), line, font=font, fill=(0, 0, 0))
            
            # 绘制删除线
            text_width, _ = TextMeasurer.get_text_size(line, font)
            strike_y = y + font_size // 2
            draw.line((x, strike_y, x + text_width, strike_y), fill=(0, 0, 0), width=1)
            
            y += font_size + 8
            
        return y


class HeaderElement(MarkdownElement):
    """标题元素"""
    
    def __init__(self, content: str):
        # 去除开头的 # 并计算级别
        level = 0
        for char in content:
            if char == '#':
                level += 1
            else:
                break
                
        super().__init__(content[level:].strip())
        self.level = min(level, 6)  # h1-h6
        
    def calculate_height(self, image_width: int, font_size: int) -> int:
        header_font_size = 42 - (self.level - 1) * 4
        font = FontManager.get_font(header_font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 20)
        return len(lines) * header_font_size + 30  # 包含上下间距和分隔线
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        header_font_size = 42 - (self.level - 1) * 4
        font = FontManager.get_font(header_font_size)
        
        y += 10  # 上间距
        draw.text((x, y), self.content, font=font, fill=(0, 0, 0))
        
        # 添加分隔线
        y += header_font_size + 8
        draw.line(
            (x, y, image_width - 10, y),
            fill=(230, 230, 230),
            width=3
        )
        
        return y + 10  # 返回包含下间距的新y坐标


class QuoteElement(MarkdownElement):
    """引用元素"""
    
    def __init__(self, content: str):
        # 去除开头的 >
        super().__init__(content[1:].strip())
        
    def calculate_height(self, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 30)  # 左边留出引用线的空间
        return len(lines) * (font_size + 6) + 12  # 包含上下间距
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 30)
        
        total_height = len(lines) * (font_size + 6)
        
        # 绘制引用线
        quote_line_x = x + 3
        draw.line(
            (quote_line_x, y + 6, quote_line_x, y + total_height + 6),
            fill=(180, 180, 180),
            width=5
        )
        
        # 绘制文本
        text_x = x + 15
        text_y = y + 6
        for line in lines:
            draw.text((text_x, text_y), line, font=font, fill=(180, 180, 180))
            text_y += font_size + 6
            
        return y + total_height + 12


class ListItemElement(MarkdownElement):
    """列表项元素"""
    
    def calculate_height(self, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 30)  # 左边留出项目符号的空间
        return len(lines) * (font_size + 6) + 16  # 包含上下间距
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = TextMeasurer.split_text_to_fit_width(self.content, font, image_width - 30)
        
        y += 8  # 上间距
        
        # 绘制项目符号
        bullet_x = x + 5
        draw.text((bullet_x, y), "•", font=font, fill=(0, 0, 0))
        
        # 绘制文本
        text_x = x + 25
        text_y = y
        for line in lines:
            draw.text((text_x, text_y), line, font=font, fill=(0, 0, 0))
            text_y += font_size + 6
            
        return text_y + 8  # 包含下间距


class CodeBlockElement(MarkdownElement):
    """代码块元素"""
    
    def __init__(self, content: List[str]):
        super().__init__("\n".join(content))
        
    def calculate_height(self, image_width: int, font_size: int) -> int:
        if not self.content:
            return 40  # 空代码块的最小高度
            
        font = FontManager.get_font(font_size)
        lines = self.content.split("\n")
        wrapped_lines = []
        
        for line in lines:
            wrapped = TextMeasurer.split_text_to_fit_width(line, font, image_width - 40)
            wrapped_lines.extend(wrapped)
            
        return len(wrapped_lines) * (font_size + 4) + 40  # 包含内边距和上下间距
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        lines = self.content.split("\n")
        wrapped_lines = []
        
        for line in lines:
            wrapped = TextMeasurer.split_text_to_fit_width(line, font, image_width - 40)
            wrapped_lines.extend(wrapped)
            
        content_height = len(wrapped_lines) * (font_size + 4)
        total_height = content_height + 30  # 包含内边距
        
        # 绘制背景
        draw.rounded_rectangle(
            (x, y + 5, image_width - 10, y + total_height),
            radius=5,
            fill=(240, 240, 240),
            width=1
        )
        
        # 绘制代码
        text_y = y + 15
        for line in wrapped_lines:
            draw.text((x + 15, text_y), line, font=font, fill=(0, 0, 0))
            text_y += font_size + 4
            
        return y + total_height + 10


class InlineCodeElement(MarkdownElement):
    """行内代码元素"""
    
    def calculate_height(self, image_width: int, font_size: int) -> int:
        return font_size + 16  # 包含内边距和上下间距
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        font = FontManager.get_font(font_size)
        
        # 计算文本大小
        text_width, _ = TextMeasurer.get_text_size(self.content, font)
        text_height = font_size
        
        # 绘制背景
        padding = 4
        draw.rounded_rectangle(
            (
                x, 
                y + 4, 
                x + text_width + padding * 2, 
                y + text_height + padding * 2 + 4
            ),
            radius=5,
            fill=(230, 230, 230),
            width=1
        )
        
        # 绘制文本
        draw.text((x + padding, y + padding + 4), self.content, font=font, fill=(0, 0, 0))
        
        return y + text_height + 16  # 返回新的y坐标


class ImageElement(MarkdownElement):
    """图片元素"""
    
    def __init__(self, content: str, image_url: str):
        super().__init__(content)
        self.image_url = image_url
        self.image = None
        
    async def load_image(self):
        """加载图片"""
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            async with aiohttp.ClientSession(trust_env=True, connector=connector) as session:
                async with session.get(self.image_url) as resp:
                    if (resp.status == 200):
                        image_data = await resp.read()
                        self.image = Image.open(BytesIO(image_data))
                    else:
                        print(f"Failed to load image: HTTP {resp.status}")
        except Exception as e:
            print(f"Failed to load image: {e}")
            
    def calculate_height(self, image_width: int, font_size: int) -> int:
        if self.image is None:
            return font_size + 20  # 图片加载失败的默认高度
            
        # 计算调整大小后的图片高度
        max_width = image_width * 0.8
        if self.image.width > max_width:
            ratio = max_width / self.image.width
            height = int(self.image.height * ratio)
        else:
            height = self.image.height
            
        return height + 30  # 包含上下间距
        
    def render(self, image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, image_width: int, font_size: int) -> int:
        if self.image is None:
            # 图片加载失败
            font = FontManager.get_font(font_size)
            draw.text((x, y + 10), "[图片加载失败]", font=font, fill=(255, 0, 0))
            return y + font_size + 20
            
        # 调整图片大小
        max_width = image_width * 0.8
        pasted_image = self.image
        
        if pasted_image.width > max_width:
            ratio = max_width / pasted_image.width
            new_size = (int(max_width), int(pasted_image.height * ratio))
            pasted_image = pasted_image.resize(new_size, Image.LANCZOS)
            
        # 计算居中位置
        paste_x = x + (image_width - pasted_image.width) // 2 - 10
        
        # 粘贴图片
        if pasted_image.mode == 'RGBA':
            # 处理透明图片
            image.paste(pasted_image, (paste_x, y + 15), pasted_image)
        else:
            image.paste(pasted_image, (paste_x, y + 15))
            
        return y + pasted_image.height + 30


class MarkdownParser:
    """Markdown解析器，将文本解析为元素"""
    
    @staticmethod
    async def parse(text: str) -> List[MarkdownElement]:
        elements = []
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            
            # 图片检测
            image_match = re.search(r'!\s*\[(.*?)\]\s*\((.*?)\)', line)
            if image_match:
                image_url = image_match.group(2)
                element = ImageElement(line, image_url)
                await element.load_image()
                elements.append(element)
                i += 1
                continue
                
            # 标题
            if line.startswith('#'):
                elements.append(HeaderElement(line))
                i += 1
                continue
                
            # 引用
            if line.startswith('>'):
                elements.append(QuoteElement(line))
                i += 1
                continue
                
            # 列表项
            if line.startswith('-') or line.startswith('*'):
                elements.append(ListItemElement(line[1:].strip()))
                i += 1
                continue
                
            # 代码块
            if line.startswith('```'):
                code_lines = []
                i += 1  # 跳过开始标记行
                
                while i < len(lines) and not lines[i].startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                    
                i += 1  # 跳过结束标记行
                elements.append(CodeBlockElement(code_lines))
                continue
            
            # 检查行内样式（粗体、斜体、下划线、删除线、行内代码）
            if re.search(r'(\*\*.*?\*\*)|(\*.*?\*)|(__.*?__)|(_.*?_)|(~~.*?~~)|(`.*?`)', line):
                # 分析行内样式:
                # - 粗体: **text** 或 __text__
                # - 斜体: *text* 或 _text_
                # - 删除线: ~~text~~
                # - 行内代码: `text`
                
                # 定义正则模式和对应的元素类型
                patterns = [
                    (r'\*\*(.*?)\*\*', BoldTextElement),  # **粗体**
                    (r'__(.*?)__', BoldTextElement),      # __粗体__
                    (r'\*((?!\*\*).*?)\*', ItalicTextElement),  # *斜体* (但不匹配 ** 开头)
                    (r'_((?!__).*?)_', ItalicTextElement),      # _斜体_ (但不匹配 __ 开头)
                    (r'~~(.*?)~~', StrikethroughTextElement),   # ~~删除线~~
                    (r'__(.*?)__', UnderlineTextElement),       # __下划线__
                    (r'`(.*?)`', InlineCodeElement)             # `行内代码`
                ]
                
                # 创建标记位置列表
                markers = []
                for pattern, element_class in patterns:
                    for match in re.finditer(pattern, line):
                        markers.append({
                            'start': match.start(),
                            'end': match.end(),
                            'text': match.group(1),  # 提取内容部分
                            'element_class': element_class
                        })
                
                # 按开始位置排序
                markers.sort(key=lambda x: x['start'])
                
                # 如果没有找到任何匹配，直接添加为普通文本
                if not markers:
                    elements.append(TextElement(line))
                    i += 1
                    continue
                
                # 处理每个文本片段
                current_pos = 0
                for marker in markers:
                    # 添加前面的普通文本
                    if marker['start'] > current_pos:
                        normal_text = line[current_pos:marker['start']]
                        if normal_text:
                            elements.append(TextElement(normal_text))
                    
                    # 添加特殊样式的文本
                    elements.append(marker['element_class'](marker['text']))
                    current_pos = marker['end']
                
                # 添加最后一段普通文本
                if current_pos < len(line):
                    elements.append(TextElement(line[current_pos:]))
                
                i += 1
                continue
                
            # 行内代码 (如果之前没匹配到混合样式)
            inline_code_matches = re.findall(r'`([^`]+)`', line)
            if inline_code_matches:
                parts = re.split(r'`([^`]+)`', line)
                for j, part in enumerate(parts):
                    if j % 2 == 0:  # 普通文本
                        if part:
                            elements.append(TextElement(part))
                    else:  # 行内代码
                        elements.append(InlineCodeElement(part))
                i += 1
                continue
                
            # 普通文本
            elements.append(TextElement(line))
            i += 1
            
        return elements


class MarkdownRenderer:
    """Markdown渲染器，将元素渲染为图像"""
    
    def __init__(self, font_size: int = 26, width: int = 800, bg_color: Tuple[int, int, int] = (255, 255, 255)):
        self.font_size = font_size
        self.width = width
        self.bg_color = bg_color
        
    async def render(self, markdown_text: str) -> Image.Image:
        # 解析Markdown文本
        elements = await MarkdownParser.parse(markdown_text)
        
        # 计算总高度
        total_height = 20  # 初始边距
        for element in elements:
            total_height += element.calculate_height(self.width, self.font_size)
            
        # 为页脚添加额外空间
        footer_height = 40
        total_height += 20 + footer_height  # 结束边距 + 页脚高度
        
        # 创建图像
        image = Image.new('RGB', (self.width, max(100, total_height)), self.bg_color)
        draw = ImageDraw.Draw(image)
        
        # 渲染元素
        y = 10
        for element in elements:
            y = element.render(image, draw, 10, y, self.width, self.font_size)
            
        # 添加页脚
        # 克莱因蓝色，近似RGB为(0, 47, 167)
        klein_blue = (0, 47, 167)
        # 灰色
        grey_color = (130, 130, 130)
        
        # 绘制"Powered by AstrBot"文本
        footer_font_size = 20
        footer_font = FontManager.get_font(footer_font_size)
        
        # 获取"Powered by "和"AstrBot"的宽度以便居中
        powered_by_text = "Powered by "
        astrbot_text = f"AstrBot v{VERSION}"
        
        powered_by_width, _ = TextMeasurer.get_text_size(powered_by_text, footer_font)
        astrbot_width, _ = TextMeasurer.get_text_size(astrbot_text, footer_font)
        
        total_width = powered_by_width + astrbot_width
        x_start = (self.width - total_width) // 2
        
        footer_y = total_height - footer_height
        
        # 绘制"Powered by "（灰色）
        draw.text(
            (x_start, footer_y), 
            powered_by_text, 
            font=footer_font, 
            fill=grey_color
        )
        
        # 绘制"AstrBot"（克莱因蓝）
        draw.text(
            (x_start + powered_by_width, footer_y), 
            astrbot_text, 
            font=footer_font, 
            fill=klein_blue
        )
        
        return image


class LocalRenderStrategy(RenderStrategy):
    """本地渲染策略实现"""
    
    async def render_custom_template(
        self, tmpl_str: str, tmpl_data: dict, return_url: bool = True
    ) -> str:
        raise NotImplementedError

    async def render(self, text: str, return_url: bool = False) -> str:
        # 创建渲染器
        renderer = MarkdownRenderer(font_size=26, width=800)
        
        # 渲染Markdown文本
        image = await renderer.render(text)
        
        # 保存图像并返回路径/URL
        return save_temp_img(image)
