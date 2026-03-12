"""旧版 Provider 实体兼容类型。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..message import components as Comp
from ..message.chain import MessageChain

try:
    from astr_agent_sdk.message import ToolCall as _ToolCall
except ImportError:

    @dataclass(slots=True)
    class _ToolCallFunctionBody:
        name: str
        arguments: str

    @dataclass(slots=True)
    class _ToolCall:
        id: str
        function: _ToolCallFunctionBody

        FunctionBody = _ToolCallFunctionBody


@dataclass(init=False)
class LLMResponse:
    """兼容旧版 LLM 响应对象。"""

    role: str
    result_chain: MessageChain | None
    tools_call_args: list[dict[str, Any]]
    tools_call_name: list[str]
    tools_call_ids: list[str]
    raw_completion: Any | None
    _new_record: dict[str, Any] | None
    _completion_text: str
    is_chunk: bool

    def __init__(
        self,
        role: str,
        completion_text: str = "",
        result_chain: MessageChain | None = None,
        tools_call_args: list[dict[str, Any]] | None = None,
        tools_call_name: list[str] | None = None,
        tools_call_ids: list[str] | None = None,
        raw_completion: Any | None = None,
        _new_record: dict[str, Any] | None = None,
        is_chunk: bool = False,
    ) -> None:
        self.role = role
        self.result_chain = result_chain
        self.tools_call_args = list(tools_call_args or [])
        self.tools_call_name = list(tools_call_name or [])
        self.tools_call_ids = list(tools_call_ids or [])
        self.raw_completion = raw_completion
        self._new_record = _new_record
        self._completion_text = completion_text
        self.is_chunk = is_chunk

    @property
    def completion_text(self) -> str:
        if self.result_chain:
            return self.result_chain.get_plain_text()
        return self._completion_text

    @completion_text.setter
    def completion_text(self, value: str) -> None:
        if self.result_chain:
            self.result_chain.chain = [
                component
                for component in self.result_chain.chain
                if not isinstance(component, Comp.Plain)
            ]
            self.result_chain.chain.insert(0, Comp.Plain(text=value))
            return
        self._completion_text = value

    def to_openai_tool_calls(self) -> list[dict[str, Any]]:
        ret: list[dict[str, Any]] = []
        for idx, tool_call_arg in enumerate(self.tools_call_args):
            ret.append(
                {
                    "id": self.tools_call_ids[idx],
                    "function": {
                        "name": self.tools_call_name[idx],
                        "arguments": json.dumps(tool_call_arg),
                    },
                    "type": "function",
                }
            )
        return ret

    def to_openai_to_calls_model(self) -> list[_ToolCall]:
        ret: list[_ToolCall] = []
        for idx, tool_call_arg in enumerate(self.tools_call_args):
            ret.append(
                _ToolCall(
                    id=self.tools_call_ids[idx],
                    function=_ToolCall.FunctionBody(
                        name=self.tools_call_name[idx],
                        arguments=json.dumps(tool_call_arg),
                    ),
                )
            )
        return ret
