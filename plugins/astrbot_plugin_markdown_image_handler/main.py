from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import LLMResponse
from astrbot.api.message_components import Image, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api import logger
import re
from typing import List

@register("astrbot_plugin_markdown_image_handler", "AlanBacker", "移除LLM输出中的Markdown格式并提取发送图片", "1.0.0", "https://github.com/AlanBacker/astrbot_plugin_markdown_image_handler")
class MarkdownImageHandlerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

        # 配置项（可以在这里直接修改）
        self.dify_host = "http://223.109.141.49:8081"
        self.enable_markdown_removal = True
        self.enable_image_extraction = True  # 启用图片提取和发送功能

        # 尝试从配置文件读取（如果支持的话）
        try:
            if hasattr(self.context, 'config_helper'):
                config = self.context.config_helper.get_all()
                self.dify_host = config.get("dify_host", self.dify_host)
                self.enable_markdown_removal = config.get("enable_markdown_removal", self.enable_markdown_removal)
                self.enable_image_extraction = config.get("enable_image_extraction", self.enable_image_extraction)
        except Exception as e:
            logger.warning(f"[Markdown Image Handler] 无法读取配置文件，使用默认配置: {e}")

        logger.info(f"[Markdown Image Handler] 插件已加载")
        logger.info(f"[Markdown Image Handler] Dify 服务器地址: {self.dify_host}")
        logger.info(f"[Markdown Image Handler] Markdown 移除: {'启用' if self.enable_markdown_removal else '禁用'}")
        logger.info(f"[Markdown Image Handler] 图片提取: {'启用' if self.enable_image_extraction else '禁用'}")

    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse, *args):
        """
        监听LLM回复，移除Markdown格式并提取图片，将图片添加到消息链中
        注意：由于 OneBot 协议端限制，图文混排时顺序可能无法保持
        """
        if not resp or not resp.completion_text:
            return

        original_text = resp.completion_text

        # 调试：记录原始回复内容
        logger.info(f"[Markdown Image Handler] 收到 LLM 回复，长度: {len(original_text)} 字符")
        logger.debug(f"[Markdown Image Handler] 原始内容: {original_text[:200]}...")

        # 构建消息链，保持原始顺序
        new_chain = self.build_message_chain(original_text)

        # 更新 resp.result_chain
        if new_chain:
            if resp.result_chain is None:
                resp.result_chain = MessageChain(chain=new_chain)
            else:
                resp.result_chain.chain = new_chain
            logger.info(f"[Markdown Image Handler] 消息链已更新，包含 {len(new_chain)} 个组件")

    def build_message_chain(self, text: str) -> List:
        """
        按原始顺序构建消息链：文本和图片交替出现
        例如: "文字1 ![img](url) 文字2" -> [Plain(文字1), Image(url), Plain(文字2)]
        """
        chain = []

        # 匹配 Markdown 图片语法: ![alt](url)
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

        last_end = 0
        for match in re.finditer(pattern, text):
            # 添加图片前的文本
            text_before = text[last_end:match.start()]
            if text_before:
                # 移除这段文本中的 Markdown 格式
                cleaned_text = self.remove_markdown(text_before)
                if cleaned_text.strip():
                    chain.append(Plain(cleaned_text))

            # 添加图片
            alt_text, url = match.groups()
            real_url = self.convert_dify_url(url)
            logger.info(f"[Markdown Image Handler] 添加图片到消息链: {alt_text} -> {real_url}")
            chain.append(Image.fromURL(real_url))

            last_end = match.end()

        # 添加最后一张图片后的文本
        text_after = text[last_end:]
        if text_after:
            cleaned_text = self.remove_markdown(text_after)
            if cleaned_text.strip():
                chain.append(Plain(cleaned_text))

        # 如果没有图片，整段文本作为一个 Plain
        if not chain and text.strip():
            cleaned_text = self.remove_markdown(text)
            if cleaned_text.strip():
                chain.append(Plain(cleaned_text))

        return chain

    def convert_dify_url(self, url: str) -> str:
        """
        将 Dify 容器内地址转换为真实地址
        例如: /files/xxx/file-preview?... -> http://223.109.141.49:8081/files/xxx/file-preview?...
        """
        if url.startswith('/files/'):
            # 相对路径，需要添加主机地址
            return f"{self.dify_host}{url}"
        elif url.startswith('http://') or url.startswith('https://'):
            # 已经是完整 URL
            return url
        else:
            # 其他情况，尝试添加主机地址
            return f"{self.dify_host}/{url.lstrip('/')}"


    def remove_markdown(self, text: str) -> str:
        """
        移除文本中的Markdown格式
        """
        # 移除图片 ![alt](url) -> alt (或者完全移除)
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

        # 移除代码块 (保留内容)
        text = re.sub(r"```(?:[a-zA-Z0-9+\-]*\s+)?([\s\S]*?)```", r"\1", text)

        # 移除行内代码 `code` -> code
        text = re.sub(r"`([^`]+)`", r"\1", text)

        # 移除粗体/斜体
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)

        # Italic: *text* or _text_
        text = re.sub(r"(^|[^\w\*])\*(?!\s)([^*]+)(?<!\s)\*(?=$|[^\w\*])", r"\1\2", text)
        text = re.sub(r"(^|[^\w_])_(?!\s)([^_]+)(?<!\s)_(?=$|[^\w_])", r"\1\2", text)

        # 移除标题 (移除 # 但保留文本)
        text = re.sub(r"^(#{1,6})\s+(.*)", r"\2", text, flags=re.MULTILINE)

        # 移除引用 (移除 > 但保留文本)
        text = re.sub(r"^>\s+(.*)", r"\1", text, flags=re.MULTILINE)

        # 移除链接 [text](url) -> text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # 移除列表标记 (移除行首的 - 或 *)
        text = re.sub(r"^\s*[-*]\s+(.*)", r"\1", text, flags=re.MULTILINE)

        return text
