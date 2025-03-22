import enum
import base64
from astrbot.core.utils.io import download_image_by_url
from astrbot import logger
from dataclasses import dataclass, field
from typing import List, Dict, Type
from .func_tool_manager import FuncCall
from openai.types.chat.chat_completion import ChatCompletion
from astrbot.core.db.po import Conversation
from astrbot.core.message.message_event_result import MessageChain
import astrbot.core.message.components as Comp


class ProviderType(enum.Enum):
    CHAT_COMPLETION = "chat_completion"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"


@dataclass
class ProviderMetaData:
    type: str
    """提供商适配器名称，如 openai, ollama"""
    desc: str = ""
    """提供商适配器描述."""
    provider_type: ProviderType = ProviderType.CHAT_COMPLETION
    cls_type: Type = None

    default_config_tmpl: dict = None
    """平台的默认配置模板"""
    provider_display_name: str = None
    """显示在 WebUI 配置页中的提供商名称，如空则是 type"""


@dataclass
class ProviderRequest:
    prompt: str
    """提示词"""
    session_id: str = ""
    """会话 ID"""
    image_urls: List[str] = None
    """图片 URL 列表"""
    func_tool: FuncCall = None
    """工具"""
    contexts: List = None
    """上下文。格式与 openai 的上下文格式一致：
    参考 https://platform.openai.com/docs/api-reference/chat/create#chat-create-messages
    """
    system_prompt: str = ""
    """系统提示词"""
    conversation: Conversation = None

    def __repr__(self):
        return f"ProviderRequest(prompt={self.prompt}, session_id={self.session_id}, image_urls={self.image_urls}, func_tool={self.func_tool}, contexts={self._print_friendly_context()}, system_prompt={self.system_prompt.strip()})"

    def __str__(self):
        return self.__repr__()


    def _print_friendly_context(self):
        """打印友好的消息上下文。将 image_url 的值替换为 <Image>"""
        if not self.contexts:
            return f"prompt: {self.prompt}, image_count: {len(self.image_urls or [])}"

        result_parts = []

        for ctx in self.contexts:
            role = ctx.get("role", "unknown")
            content = ctx.get("content", "")

            if isinstance(content, str):
                result_parts.append(f"{role}: {content}")
            elif isinstance(content, list):
                msg_parts = []
                image_count = 0

                for item in content:
                    item_type = item.get("type", "")

                    if item_type == "text":
                        msg_parts.append(item.get("text", ""))
                    elif item_type == "image_url":
                        image_count += 1

                if image_count > 0:
                    if msg_parts:
                        msg_parts.append(f"[+{image_count} images]")
                    else:
                        msg_parts.append(f"[{image_count} images]")

                result_parts.append(f"{role}: {''.join(msg_parts)}")

        return result_parts

    async def assemble_context(self) -> Dict:
        """将请求(prompt 和 image_urls)包装成 OpenAI 的消息格式。"""
        if self.image_urls:
            user_content = {
                "role": "user",
                "content": [{"type": "text", "text": self.prompt}],
            }
            for image_url in self.image_urls:
                if image_url.startswith("http"):
                    image_path = await download_image_by_url(image_url)
                    image_data = await self._encode_image_bs64(image_path)
                elif image_url.startswith("file:///"):
                    image_path = image_url.replace("file:///", "")
                    image_data = await self._encode_image_bs64(image_path)
                else:
                    image_data = await self._encode_image_bs64(image_url)
                if not image_data:
                    logger.warning(f"图片 {image_url} 得到的结果为空，将忽略。")
                    continue
                user_content["content"].append(
                    {"type": "image_url", "image_url": {"url": image_data}}
                )
            return user_content
        else:
            return {"role": "user", "content": self.prompt}

    async def _encode_image_bs64(self, image_url: str) -> str:
        """将图片转换为 base64"""
        if image_url.startswith("base64://"):
            return image_url.replace("base64://", "data:image/jpeg;base64,")
        with open(image_url, "rb") as f:
            image_bs64 = base64.b64encode(f.read()).decode("utf-8")
            return "data:image/jpeg;base64," + image_bs64
        return ""


@dataclass
class LLMResponse:
    role: str
    """角色, assistant, tool, err"""
    result_chain: MessageChain = None
    """返回的消息链"""
    tools_call_args: List[Dict[str, any]] = field(default_factory=list)
    """工具调用参数"""
    tools_call_name: List[str] = field(default_factory=list)
    """工具调用名称"""

    raw_completion: ChatCompletion = None
    _new_record: Dict[str, any] = None

    _completion_text: str = ""

    def __init__(
        self,
        role: str,
        completion_text: str = "",
        result_chain: MessageChain = None,
        tools_call_args: List[Dict[str, any]] = None,
        tools_call_name: List[str] = None,
        raw_completion: ChatCompletion = None,
        _new_record: Dict[str, any] = None,
    ):
        """初始化 LLMResponse

        Args:
            role (str): 角色, assistant, tool, err
            completion_text (str, optional): 返回的结果文本，已经过时，推荐使用 result_chain. Defaults to "".
            result_chain (MessageChain, optional): 返回的消息链. Defaults to None.
            tools_call_args (List[Dict[str, any]], optional): 工具调用参数. Defaults to None.
            tools_call_name (List[str], optional): 工具调用名称. Defaults to None.
            raw_completion (ChatCompletion, optional): 原始响应, OpenAI 格式. Defaults to None.
        """
        self.role = role
        self.completion_text = completion_text
        self.result_chain = result_chain
        self.tools_call_args = tools_call_args
        self.tools_call_name = tools_call_name
        self.raw_completion = raw_completion
        self._new_record = _new_record

    @property
    def completion_text(self):
        if self.result_chain:
            return self.result_chain.get_plain_text()
        return self._completion_text

    @completion_text.setter
    def completion_text(self, value):
        if self.result_chain:
            self.result_chain.chain = [
                comp
                for comp in self.result_chain.chain
                if not isinstance(comp, Comp.Plain)
            ]  # 清空 Plain 组件
            self.result_chain.chain.insert(0, Comp.Plain(value))
        else:
            self._completion_text = value
