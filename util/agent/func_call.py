from model.provider.provider import Provider
import json
import time
import textwrap

class FuncCallJsonFormatError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class FuncNotFoundError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class FuncCall():
    def __init__(self, provider: Provider) -> None:
        self.func_list = []
        self.provider = provider

    def add_func(self, name: str, func_args: list, desc: str, func_obj: callable) -> None:
        '''
        为函数调用（function-calling / tools-use）添加工具。
        
        @param name: 函数名
        @param func_args: 函数参数列表，格式为 [{"type": "string", "name": "arg_name", "description": "arg_description"}, ...]
        @param desc: 函数描述
        @param func_obj: 处理函数
        '''
        params = {
            "type": "object",  # hardcore here
            "properties": {}
        }
        for param in func_args:
            params['properties'][param['name']] = {
                "type": param['type'],
                "description": param['description']
            }
        self._func = {
            "name": name,
            "parameters": params,
            "description": desc,
            "func_obj": func_obj,
        }
        self.func_list.append(self._func)

    def func_dump(self) -> str:
        _l = []
        for f in self.func_list:
            _l.append({
                "name": f["name"],
                "parameters": f["parameters"],
                "description": f["description"],
            })
        return json.dumps(_l, ensure_ascii=False)

    def get_func(self) -> list:
        _l = []
        for f in self.func_list:
            _l.append({
                "type": "function",
                "function": {
                    "name": f["name"],
                    "parameters": f["parameters"],
                    "description": f["description"],
                }
            })
        return _l

    async def func_call(self, question: str, func_definition: str, session_id: str, provider: Provider = None) -> tuple:
        
        if not provider:
            provider = self.provider

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
                print(res)
                if res.find('```') != -1:
                    res = res[res.find('```json') + 7: res.rfind('```')]
                res = json.loads(res)
                break
            except Exception as e:
                _c += 1
                if _c == 3:
                    raise e
                if "The message you submitted was too long" in str(e):
                    raise e
        
        if 'res' in res and not res['res']:
            return "", False

        tool_call_result = []
        for tool in res:
            # 说明有函数调用
            func_name = tool["name"]
            args = tool["args"]
            # 调用函数
            tool_callable = None
            for func in self.func_list:
                if func["name"] == func_name:
                    tool_callable = func["func_obj"]
                    break
            if not tool_callable:
                raise FuncNotFoundError(
                    f"Request function {func_name} not found.")
            ret = await tool_callable(**args)
            if ret:
                tool_call_result.append(str(ret))
        return tool_call_result, True
