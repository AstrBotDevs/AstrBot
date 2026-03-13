"""legacy LLM 与 tool 兼容辅助。

这个模块只承接 ``_legacy_api.py`` 中相对独立的旧 LLM/tool 兼容逻辑：

- 旧版 tool manager 与 tool schema 组装
- 旧 provider 请求对象
- 新响应到旧 ``LLMResponse`` 的转换

它不暴露新的公开 API，只用于减轻 ``LegacyContext`` 所在模块的职责。
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .api.provider.entities import LLMResponse


@dataclass(slots=True)
class _CompatToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    active: bool = True


@dataclass(slots=True)
class _CompatProviderRequest:
    prompt: str | None = None
    session_id: str | None = ""
    image_urls: list[str] | None = None
    contexts: list[dict[str, Any]] | None = None
    system_prompt: str = ""
    conversation: Any | None = None
    tool_calls_result: Any | None = None
    model: str | None = None


def _tool_parameters_from_legacy_args(
    func_args: list[dict[str, Any]],
) -> dict[str, Any]:
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for item in func_args:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        if not name:
            continue
        schema = {key: value for key, value in item.items() if key != "name"}
        parameters["properties"][name] = schema
        parameters["required"].append(name)
    return parameters


class CompatLLMToolManager:
    """旧版 llm tool manager 的最小兼容实现。"""

    def __init__(self) -> None:
        self.func_list: list[_CompatToolSpec] = []

    def add_tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        self.remove_func(name)
        self.func_list.append(
            _CompatToolSpec(
                name=name,
                description=description,
                parameters=parameters,
                handler=handler,
            )
        )

    def add_func(
        self,
        name: str,
        func_args: list[dict[str, Any]],
        desc: str,
        handler: Callable[..., Any],
    ) -> None:
        self.add_tool(
            name=name,
            description=desc,
            parameters=_tool_parameters_from_legacy_args(func_args),
            handler=handler,
        )

    def remove_func(self, name: str) -> None:
        self.func_list = [tool for tool in self.func_list if tool.name != name]

    def get_func(self, name: str) -> _CompatToolSpec | None:
        for tool in self.func_list:
            if tool.name == name:
                return tool
        return None

    def activate_llm_tool(self, name: str) -> bool:
        tool = self.get_func(name)
        if tool is None:
            return False
        tool.active = True
        return True

    def deactivate_llm_tool(self, name: str) -> bool:
        tool = self.get_func(name)
        if tool is None:
            return False
        tool.active = False
        return True

    def get_func_desc_openai_style(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.func_list
            if tool.active
        ]


def _legacy_tool_calls(
    response_payload: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    tool_calls = list((response_payload or {}).get("tool_calls") or [])
    tool_args: list[dict[str, Any]] = []
    tool_names: list[str] = []
    tool_ids: list[str] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function_payload = tool_call.get("function")
        if isinstance(function_payload, dict):
            name = str(function_payload.get("name") or "")
            raw_arguments = function_payload.get("arguments")
        else:
            name = str(tool_call.get("name") or "")
            raw_arguments = tool_call.get("arguments")
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                try:
                    arguments = ast.literal_eval(raw_arguments)
                except (SyntaxError, ValueError):
                    arguments = {}
        elif isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        tool_names.append(name)
        tool_args.append(arguments)
        tool_ids.append(str(tool_call.get("id") or f"tool-{len(tool_ids) + 1}"))
    return tool_args, tool_names, tool_ids


def _legacy_llm_response(response: Any) -> LLMResponse:
    from .api.provider.entities import LLMResponse

    if isinstance(response, LLMResponse):
        return response

    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        payload = model_dump()
    elif isinstance(response, dict):
        payload = dict(response)
    else:
        payload = {
            "text": getattr(response, "text", ""),
            "usage": getattr(response, "usage", None),
            "finish_reason": getattr(response, "finish_reason", None),
            "tool_calls": getattr(response, "tool_calls", []),
        }

    tool_args, tool_names, tool_ids = _legacy_tool_calls(payload)
    return LLMResponse(
        role=str(payload.get("role") or "assistant"),
        completion_text=str(payload.get("text") or ""),
        tools_call_args=tool_args,
        tools_call_name=tool_names,
        tools_call_ids=tool_ids,
        raw_completion=response,
        _new_record=payload,
    )
