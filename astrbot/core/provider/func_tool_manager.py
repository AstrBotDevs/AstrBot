from __future__ import annotations
import json
import textwrap
import os
import asyncio
import mcp

from typing import Dict, List, Awaitable, Literal, Any
from dataclasses import dataclass
from typing import Optional
from contextlib import AsyncExitStack

from mcp.client.stdio import stdio_client
from astrbot import logger

DEFAULT_MCP_CONFIG = {"mcpServers": {}}

SUPPORTED_TYPES = [
    "string",
    "number",
    "object",
    "array",
    "boolean",
]  # json schema 支持的数据类型


@dataclass
class FuncTool:
    """
    用于描述一个函数调用工具。
    """

    name: str
    parameters: Dict
    description: str
    handler: Awaitable = None
    """处理函数, 当 origin 为 mcp 时，这个为空"""
    handler_module_path: str = None
    """处理函数的模块路径，当 origin 为 mcp 时，这个为空

    必须要保留这个字段, handler 在初始化会被 functools.partial 包装，导致 handler 的 __module__ 为 functools
    """
    active: bool = True
    """是否激活"""

    origin: Literal["local", "mcp"] = "local"
    """函数工具的来源, local 为本地函数工具, mcp 为 MCP 服务"""

    # MCP 相关字段
    mcp_server_name: str = None
    """MCP 服务名称，当 origin 为 mcp 时有效"""
    mcp_client: MCPClient = None
    """MCP 客户端，当 origin 为 mcp 时有效"""

    def __repr__(self):
        return f"FuncTool(name={self.name}, parameters={self.parameters}, description={self.description}, active={self.active}, origin={self.origin})"

    async def execute(self, **args) -> Any:
        """执行函数调用"""
        if self.origin == "local":
            if not self.handler:
                raise Exception(f"Local function {self.name} has no handler")
            return await self.handler(**args)
        elif self.origin == "mcp":
            if not self.mcp_client or not self.mcp_client.session:
                raise Exception(f"MCP client for {self.name} is not available")
            # 使用name属性而不是额外的mcp_tool_name
            if ":" in self.name:
                # 如果名字是格式为 mcp:server:tool_name，提取实际的工具名
                actual_tool_name = self.name.split(":")[-1]
                return await self.mcp_client.session.call_tool(actual_tool_name, args)
            else:
                return await self.mcp_client.session.call_tool(self.name, args)
        else:
            raise Exception(f"Unknown function origin: {self.origin}")


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[mcp.ClientSession] = None
        self.exit_stack = AsyncExitStack()

        self.name = None
        self.active: bool = True
        self.tools: List[mcp.Tool] = []

    async def connect_to_server(self, mcp_server_config: dict):
        """Connect to an MCP server

        Args:
            mcp_server_config (dict): Configuration for the MCP server. See https://modelcontextprotocol.io/quickstart/server
        """
        cfg = mcp_server_config.copy()
        cfg.pop("active", None)
        server_params = mcp.StdioServerParameters(
            **cfg,
        )

        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            mcp.ClientSession(self.stdio, self.write)
        )

        await self.session.initialize()

    async def list_tools_and_save(self) -> mcp.ListToolsResult:
        """List all tools from the server and save them to self.tools"""
        response = await self.session.list_tools()
        logger.debug(f"MCP server {self.name} list tools response: {response}")
        self.tools = response.tools
        return response

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


class FuncCall:
    def __init__(self) -> None:
        self.func_list: List[FuncTool] = []
        """内部加载的 func tools"""
        self.mcp_client_dict: Dict[str, MCPClient] = {}
        """MCP 服务列表"""
        self.mcp_service_queue = asyncio.Queue()
        """用于外部控制 MCP 服务的启停"""

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

    async def _init_mcp_clients(self) -> None:
        """从项目根目录读取 mcp_server.json 文件，初始化 MCP 服务列表。文件格式如下：
        ```
        {
            "mcpServers": {
                "weather": {
                    "command": "uv",
                    "args": [
                        "--directory",
                        "/ABSOLUTE/PATH/TO/PARENT/FOLDER/weather",
                        "run",
                        "weather.py"
                    ]
                }
            }
            ...
        }
        ```
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.abspath(os.path.join(current_dir, "../../../data"))

        mcp_json_file = os.path.join(data_dir, "mcp_server.json")
        if not os.path.exists(mcp_json_file):
            # 配置文件不存在错误处理
            with open(mcp_json_file, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MCP_CONFIG, f, ensure_ascii=False, indent=4)
            logger.info(f"未找到 MCP 服务配置文件，已创建默认配置文件 {mcp_json_file}")
            return

        mcp_server_json_obj: Dict[str, Dict] = json.load(
            open(mcp_json_file, "r", encoding="utf-8")
        )["mcpServers"]

        for name in mcp_server_json_obj.keys():
            cfg = mcp_server_json_obj[name]
            if cfg.get("active", True):
                asyncio.create_task(self._init_mcp_client(name, cfg))

    async def mcp_service_selector(self):
        """为了避免在不同异步任务中控制 MCP 服务导致的报错，整个项目统一通过这个 Task 来控制

        使用 self.mcp_service_queue.put_nowait() 来控制 MCP 服务的启停，数据格式如下：

        {"type": "init"} 初始化所有MCP客户端

        {"type": "init", "name": "mcp_server_name", "cfg": {...}} 初始化指定的MCP客户端

        {"type": "terminate"} 终止所有MCP客户端

        {"type": "terminate", "name": "mcp_server_name"} 终止指定的MCP客户端
        """
        while True:
            data = await self.mcp_service_queue.get()
            if data["type"] == "init":
                if "name" in data:
                    asyncio.create_task(
                        self._init_mcp_client(data["name"], data["cfg"])
                    )
                else:
                    await self._init_mcp_clients()
            elif data["type"] == "terminate":
                if "name" in data:
                    await self._terminate_mcp_client(data["name"])
                else:
                    for name in self.mcp_client_dict.keys():
                        await self._terminate_mcp_client(name)

    async def _init_mcp_client(self, name: str, config: dict) -> None:
        """初始化单个MCP客户端"""
        try:
            # 先清理之前的客户端，如果存在
            if name in self.mcp_client_dict:
                await self._terminate_mcp_client(name)

            mcp_client = MCPClient()
            mcp_client.name = name
            await mcp_client.connect_to_server(config)
            tools_res = await mcp_client.list_tools_and_save()
            tool_names = [tool.name for tool in tools_res.tools]
            self.mcp_client_dict[name] = mcp_client

            # 移除该MCP服务之前的工具（如有）
            self.func_list = [
                f
                for f in self.func_list
                if not (f.origin == "mcp" and f.mcp_server_name == name)
            ]

            # 将 MCP 工具转换为 FuncTool 并添加到 func_list
            for tool in mcp_client.tools:
                func_tool = FuncTool(
                    name=tool.name,
                    parameters=tool.inputSchema,
                    description=tool.description,
                    origin="mcp",
                    mcp_server_name=name,
                    mcp_client=mcp_client,
                )
                self.func_list.append(func_tool)

            logger.info(f"已连接 MCP 服务 {name}, Tools: {tool_names}")
            return True
        except Exception as e:
            logger.error(f"初始化 MCP 客户端 {name} 失败: {e}")
            # 发生错误时确保客户端被清理
            if name in self.mcp_client_dict:
                await self._terminate_mcp_client(name)
            return False

    async def _terminate_mcp_client(self, name: str) -> None:
        """关闭并清理MCP客户端"""
        if name in self.mcp_client_dict:
            try:
                # 关闭MCP连接
                await self.mcp_client_dict[name].cleanup()
                del self.mcp_client_dict[name]
            except Exception as e:
                logger.info(f"清空 MCP 客户端资源 {name}: {e}。")
            # 移除关联的FuncTool
            self.func_list = [
                f
                for f in self.func_list
                if not (f.origin == "mcp" and f.mcp_server_name == name)
            ]
            logger.info(f"已关闭 MCP 服务 {name}")

    def get_func_desc_openai_style(self) -> list:
        """
        获得 OpenAI API 风格的**已经激活**的工具描述
        """
        _l = []
        # 处理所有工具（包括本地和MCP工具）
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
                    "name": f.name,
                    "parameters": f.parameters,
                    "description": f.description,
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
            func_tool = self.get_func(func_name)
            if not func_tool:
                raise Exception(f"Request function {func_name} not found.")

            ret = await func_tool.execute(**args)
            if ret:
                tool_call_result.append(str(ret))
        return tool_call_result, True

    def __str__(self):
        return str(self.func_list)

    def __repr__(self):
        return str(self.func_list)

    async def terminate(self):
        for name in self.mcp_client_dict.keys():
            await self._terminate_mcp_client(name)
            logger.debug(f"清理 MCP 客户端 {name} 资源")
