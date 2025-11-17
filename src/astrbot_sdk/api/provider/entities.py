from __future__ import annotations
import json
from anthropic.types import Message as AnthropicMessage
from google.genai.types import GenerateContentResponse
from openai.types.chat.chat_completion import ChatCompletion
from dataclasses import dataclass, field
from ..message.chain import MessageChain
from ..message import components as Comp
from typing import Any
from astr_agent_sdk.message import ToolCall


@dataclass
class LLMResponse:
    role: str
    """角色, assistant, tool, err"""
    result_chain: MessageChain | None = None
    """返回的消息链"""
    tools_call_args: list[dict[str, Any]] = field(default_factory=list)
    """工具调用参数"""
    tools_call_name: list[str] = field(default_factory=list)
    """工具调用名称"""
    tools_call_ids: list[str] = field(default_factory=list)
    """工具调用 ID"""

    raw_completion: (
        ChatCompletion | GenerateContentResponse | AnthropicMessage | None
    ) = None
    _new_record: dict[str, Any] | None = None

    _completion_text: str = ""

    is_chunk: bool = False
    """是否是流式输出的单个 Chunk"""

    def __init__(
        self,
        role: str,
        completion_text: str = "",
        result_chain: MessageChain | None = None,
        tools_call_args: list[dict[str, Any]] | None = None,
        tools_call_name: list[str] | None = None,
        tools_call_ids: list[str] | None = None,
        raw_completion: ChatCompletion
        | GenerateContentResponse
        | AnthropicMessage
        | None = None,
        _new_record: dict[str, Any] | None = None,
        is_chunk: bool = False,
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
        if tools_call_args is None:
            tools_call_args = []
        if tools_call_name is None:
            tools_call_name = []
        if tools_call_ids is None:
            tools_call_ids = []

        self.role = role
        self.completion_text = completion_text
        self.result_chain = result_chain
        self.tools_call_args = tools_call_args
        self.tools_call_name = tools_call_name
        self.tools_call_ids = tools_call_ids
        self.raw_completion = raw_completion
        self._new_record = _new_record
        self.is_chunk = is_chunk

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
            self.result_chain.chain.insert(0, Comp.Plain(text=value))
        else:
            self._completion_text = value

    def to_openai_tool_calls(self) -> list[dict]:
        """Convert to OpenAI tool calls format. Deprecated, use to_openai_to_calls_model instead."""
        ret = []
        for idx, tool_call_arg in enumerate(self.tools_call_args):
            ret.append(
                {
                    "id": self.tools_call_ids[idx],
                    "function": {
                        "name": self.tools_call_name[idx],
                        "arguments": json.dumps(tool_call_arg),
                    },
                    "type": "function",
                },
            )
        return ret

    def to_openai_to_calls_model(self) -> list[ToolCall]:
        """The same as to_openai_tool_calls but return pydantic model."""
        ret = []
        for idx, tool_call_arg in enumerate(self.tools_call_args):
            ret.append(
                ToolCall(
                    id=self.tools_call_ids[idx],
                    function=ToolCall.FunctionBody(
                        name=self.tools_call_name[idx],
                        arguments=json.dumps(tool_call_arg),
                    ),
                ),
            )
        return ret
