import json
import textwrap
from typing import Dict, List, Awaitable
from dataclasses import dataclass
from astrbot import logger


@dataclass
class FuncTool:
    """
    用于描述一个函数调用工具。
    """

    name: str
    parameters: Dict
    description: str
    handler: Awaitable
    handler_module_path: str = None  # 必须要保留这个，handler 在初始化会被 functools.partial 包装，导致 handler 的 __module__ 为 functools

    active: bool = True
    """是否激活"""

    def __repr__(self):
        return f"FuncTool(name={self.name}, parameters={self.parameters}, description={self.description}), active={self.active})"


SUPPORTED_TYPES = [
    "string",
    "number",
    "object",
    "array",
    "boolean",
]  # json schema 支持的数据类型


class FuncCall:
    def __init__(self) -> None:
        self.func_list: List[FuncTool] = []

    def empty(self) -> bool:
        return len(self.func_list) == 0

    def add_func(
        self,
        name: str,
        func_args: list,
        desc: str,
        handler: Awaitable,
    ) -> None:
        """添加函数调用工具

        @param name: 函数名
        @param func_args: 函数参数列表，格式为 [{"type": "string", "name": "arg_name", "description": "arg_description"}, ...]
        @param desc: 函数描述
        @param func_obj: 处理函数
        """
        # check if the tool has been added before
        self.remove_func(name)

        params = {
            "type": "object",  # hard-coded here
            "properties": {},
        }
        for param in func_args:
            params["properties"][param["name"]] = {
                "type": param["type"],
                "description": param["description"],
            }
        _func = FuncTool(
            name=name,
            parameters=params,
            description=desc,
            handler=handler,
        )
        self.func_list.append(_func)
        logger.info(f"添加函数调用工具: {name}")

    def remove_func(self, name: str) -> None:
        """
        删除一个函数调用工具。
        """
        for i, f in enumerate(self.func_list):
            if f.name == name:
                self.func_list.pop(i)
                break

    def get_func(self, name) -> FuncTool:
        for f in self.func_list:
            if f.name == name:
                return f
        return None

    def get_func_desc_openai_style(self) -> list:
        """
        获得 OpenAI API 风格的**已经激活**的工具描述
        """
        _l = []
        for f in self.func_list:
            if not f.active:
                continue
            _l.append(
                {
                    "type": "function",
                    "function": {
                        "name": f.name,
                        "parameters": f.parameters,
                        "description": f.description,
                    },
                }
            )
        return _l

    def get_func_desc_anthropic_style(self) -> list:
        """
        获得 Anthropic API 风格的**已经激活**的工具描述
        """
        tools = []
        for f in self.func_list:
            if not f.active:
                continue

            # Convert internal format to Anthropic style
            tool = {
                "name": f.name,
                "description": f.description,
                "input_schema": {
                    "type": "object",
                    "properties": f.parameters.get("properties", {}),
                    # Keep the required field from the original parameters if it exists
                    "required": f.parameters.get("required", []),
                },
            }
            tools.append(tool)
        return tools

    def get_func_desc_google_genai_style(self) -> Dict:
        declarations = {}
        tools = []
        for f in self.func_list:
            if not f.active:
                continue

            func_declaration = {"name": f.name, "description": f.description}

            # 检查并添加非空的properties参数
            params = f.parameters if isinstance(f.parameters, dict) else {}
            if params.get("properties", {}):
                func_declaration["parameters"] = params

            tools.append(func_declaration)

        if tools:
            declarations["function_declarations"] = tools
        return declarations

    async def func_call(self, question: str, session_id: str, provider) -> tuple:
        _l = []
        for f in self.func_list:
            if not f.active:
                continue
            _l.append(
                {
                    "name": f["name"],
                    "parameters": f["parameters"],
                    "description": f["description"],
                }
            )
        func_definition = json.dumps(_l, ensure_ascii=False)

        prompt = textwrap.dedent(f"""
            ROLE:
            你是一个 Function calling AI Agent, 你的任务是将用户的提问转化为函数调用。

            TOOLS:
            可用的函数列表:

            {func_definition}

            LIMIT:
            1. 你返回的内容应当能够被 Python 的 json 模块解析的 Json 格式字符串。
            2. 你的 Json 返回的格式如下：`[{{"name": "<func_name>", "args": <arg_dict>}}, ...]`。参数根据上面提供的函数列表中的参数来填写。
            3. 允许必要时返回多个函数调用，但需保证这些函数调用的顺序正确。
            4. 如果用户的提问中不需要用到给定的函数，请直接返回 `{{"res": False}}`。

            EXAMPLE:
            1. `用户提问`：请问一下天气怎么样？ `函数调用`：[{{"name": "get_weather", "args": {{"city": "北京"}}}}]

            用户的提问是：{question}
        """)

        _c = 0
        while _c < 3:
            try:
                res = await provider.text_chat(prompt, session_id)
                if res.find("```") != -1:
                    res = res[res.find("```json") + 7 : res.rfind("```")]
                res = json.loads(res)
                break
            except Exception as e:
                _c += 1
                if _c == 3:
                    raise e
                if "The message you submitted was too long" in str(e):
                    raise e

        if "res" in res and not res["res"]:
            return "", False

        tool_call_result = []
        for tool in res:
            # 说明有函数调用
            func_name = tool["name"]
            args = tool["args"]
            # 调用函数
            tool_callable = None
            for func in self.func_list:
                if func.name == func_name:
                    tool_callable = func.star_handler_metadata.handler
                    break
            if not tool_callable:
                raise Exception(f"Request function {func_name} not found.")
            ret = await tool_callable(**args)
            if ret:
                tool_call_result.append(str(ret))
        return tool_call_result, True

    def __str__(self):
        return str(self.func_list)

    def __repr__(self):
        return str(self.func_list)
