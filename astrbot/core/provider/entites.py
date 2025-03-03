import enum
from dataclasses import dataclass, field
from typing import List, Dict, Type
from .func_tool_manager import FuncCall
from openai.types.chat.chat_completion import ChatCompletion
from astrbot.core.db.po import Conversation


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
        return f"ProviderRequest(prompt={self.prompt}, session_id={self.session_id}, image_urls={self.image_urls}, func_tool={self.func_tool}, contexts={self.contexts}, system_prompt={self.system_prompt})"

    def __str__(self):
        return self.__repr__()


@dataclass
class LLMResponse:
    role: str
    """角色, assistant, tool, err"""
    completion_text: str = ""
    """LLM 返回的文本"""
    tools_call_args: List[Dict[str, any]] = field(default_factory=list)
    """工具调用参数"""
    tools_call_name: List[str] = field(default_factory=list)
    """工具调用名称"""

    raw_completion: ChatCompletion = None
    _new_record: Dict[str, any] = None
