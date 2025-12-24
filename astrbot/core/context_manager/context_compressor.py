"""
上下文压缩器：摘要压缩接口
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider


class ContextCompressor(ABC):
    """
    上下文压缩器抽象基类
    为后续实现摘要压缩策略预留接口
    当前实现：保留原始内容
    后续可扩展为：调用LLM生成摘要
    """

    @abstractmethod
    async def compress(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        压缩消息列表
        Args:
            messages: 原始消息列表
        Returns:
            压缩后的消息列表
        """
        pass


class DefaultCompressor(ContextCompressor):
    """
    默认压缩器实现
    当前实现：直接返回原始消息（预留接口）
    """

    async def compress(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        默认实现：返回原始消息
        后续可扩展为调用LLM进行摘要压缩
        """
        return messages


class LLMSummaryCompressor(ContextCompressor):
    """
    基于LLM的智能摘要压缩器
    通过调用LLM对旧对话历史进行摘要，保留最新消息
    """

    def __init__(self, provider: "Provider", keep_recent: int = 4):
        """
        初始化LLM摘要压缩器
        Args:
            provider: LLM提供商实例
            keep_recent: 保留的最新消息数量（默认4条）
        """
        self.provider = provider
        self.keep_recent = keep_recent

        # 从Markdown文件加载指令文本
        prompt_file = Path(__file__).parent / "summary_prompt.md"
        with open(prompt_file, encoding="utf-8") as f:
            self.instruction_text = f.read()

    async def compress(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        使用LLM对对话历史进行智能摘要
        流程：
        1. 划分消息：保留系统消息和最新N条消息
        2. 将旧消息 + 指令消息发送给LLM
        3. 重构消息列表：[系统消息, 摘要消息, 最新消息]
        Args:
            messages: 原始消息列表
        Returns:
            压缩后的消息列表
        """
        if len(messages) <= self.keep_recent + 1:
            return messages

        # 划分消息
        system_msg = (
            messages[0] if messages and messages[0].get("role") == "system" else None
        )
        start_idx = 1 if system_msg else 0

        messages_to_summarize = messages[start_idx : -self.keep_recent]
        recent_messages = messages[-self.keep_recent :]

        if not messages_to_summarize:
            return messages

        # 构建LLM请求载荷
        instruction_message = {"role": "user", "content": self.instruction_text}
        llm_payload = messages_to_summarize + [instruction_message]

        # 调用LLM生成摘要
        try:
            response = await self.provider.text_chat(messages=llm_payload)
            summary_content = response.completion_text
        except Exception as e:
            # 如果摘要失败，返回原始消息
            logger.error(f"Failed to generate summary: {e}")
            return messages

        # 重构消息列表
        result = []
        if system_msg:
            result.append(system_msg)

        result.append({"role": "system", "content": f"历史会话摘要：{summary_content}"})

        result.extend(recent_messages)

        return result
