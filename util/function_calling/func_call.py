
import json
import util.general_utils as gu

import time
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
    def __init__(self, provider) -> None:
        self.func_list = []
        self.provider = provider

    def add_func(self, name: str = None, func_args: list = None, desc: str = None, func_obj = None) -> None:
        if name == None or func_args == None or desc == None or func_obj == None:
            raise FuncCallJsonFormatError("name, func_args, desc must be provided.")
        params = {
            "type": "object", # hardcore here
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

    def func_dump(self, intent: int = 2) -> str:
        _l = []
        for f in self.func_list:
            _l.append({
                "name": f["name"],
                "parameters": f["parameters"],
                "description": f["description"],
            })
        return json.dumps(_l, indent=intent, ensur_ascii=False)
    
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
    
    def func_call(self, question, func_definition, is_task = False, tasks = None, taskindex = -1, is_summary = True, session_id = None):

        funccall_prompt = """
我正实现function call功能，该功能旨在让你变成给定的问题到给定的函数的解析器（意味着你不是创造函数）。
下面会给你提供可能用到的函数相关信息和一个问题，你需要将其转换成给定的函数调用。
- 你的返回信息只含json，请严格仿照以下内容（不含注释），必须含有`res`,`func_call`字段:
```
{
    "res": string // 如果没有找到对应的函数，那么你可以在这里正常输出内容。如果有，这里是空字符串。
    "func_call": [ // 这是一个数组，里面包含了所有的函数调用，如果没有函数调用，那么这个数组是空数组。
        {
            "res": string // 如果没有找到对应的函数，那么你可以在这里正常输出内容。如果有，这里是空字符串。
            "name": str, // 函数的名字
            "args_type": {
                "arg1": str, // 函数的参数的类型
                "arg2": str,
                ...
            },
            "args": {
                "arg1": any, // 函数的参数
                "arg2": any,
                ...
            }
        },
        ... // 可能在这个问题中会有多个函数调用
    ],
}
```
- 如果用户的要求较复杂，允许返回多个函数调用，但需保证这些函数调用的顺序正确。
- 当问题没有提到给定的函数时，相当于提问方不打算使用function call功能，这时你可以在res中正常输出这个问题的回答（以AI的身份正常回答该问题，并将答案输出在res字段中，回答不要涉及到任何函数调用的内容，就只是正常讨论这个问题。）

提供的函数是：

"""

        prompt = f"{funccall_prompt}\n```\n{func_definition}\n```\n"
        prompt += f"""
用户的提问是：
```
{question}
```
"""

        # if is_task:
        #     # task_prompt = f"\n任务列表为{str(tasks)}\n你目前进行到了任务{str(taskindex)}, **你不需要重新进行已经进行过的任务, 不要生成已经进行过的**"
        #     prompt += task_prompt

        # provider.forget()

        _c = 0
        while _c < 3:
            try:
                res = self.provider.text_chat(prompt, session_id)
                if res.find('```') != -1:
                    res = res[res.find('```json') + 7: res.rfind('```')]
                gu.log("REVGPT func_call json result", bg=gu.BG_COLORS["green"], fg=gu.FG_COLORS["white"])
                print(res)
                res = json.loads(res)
                break
            except Exception as e:
                _c += 1
                if _c == 3:
                    raise e
                if "The message you submitted was too long" in str(e):
                    raise e

        invoke_func_res = ""

        if "func_call" in res and len(res["func_call"]) > 0:
            task_list = res["func_call"]

            invoke_func_res_list = []

            for res in task_list:
                # 说明有函数调用
                func_name = res["name"]
                # args_type = res["args_type"]
                args = res["args"]
                # 调用函数
                # func = eval(func_name)
                func_target = None
                for func in self.func_list:
                    if func["name"] == func_name:
                        func_target = func["func_obj"]
                        break
                if func_target == None:
                    raise FuncNotFoundError(f"Request function {func_name} not found.")
                t_res = str(func_target(**args))
                invoke_func_res += f"{func_name} 调用结果：\n```\n{t_res}\n```\n"
                invoke_func_res_list.append(invoke_func_res)
                gu.log(f"[FUNC| {func_name} invoked]", bg=gu.BG_COLORS["green"], fg=gu.FG_COLORS["white"])
                # print(str(t_res))

            if is_summary:

                # 生成返回结果
                after_prompt = """
有以下内容："""+invoke_func_res+"""
请以AI助手的身份结合返回的内容对用户提问做详细全面的回答。
用户的提问是：
```""" + question + """```
- 在res字段中，不要输出函数的返回值，也不要针对返回值的字段进行分析，也不要输出用户的提问，而是理解这一段返回的结果，并以AI助手的身份回答问题，只需要输出回答的内容，不需要在回答的前面加上身份词。
- 你的返回信息必须只能是json，且需严格遵循以下内容（不含注释）:
```json
{
    "res": string, // 回答的内容
    "func_call_again": bool // 如果函数返回的结果有错误或者问题，可将其设置为true，否则为false
}
```
- 如果func_call_again为true，res请你设为空值，否则请你填写回答的内容。"""

                _c = 0
                while _c < 5:
                    try:
                        res = self.provider.text_chat(after_prompt, session_id)
                        # 截取```之间的内容
                        gu.log("DEBUG BEGIN", bg=gu.BG_COLORS["yellow"], fg=gu.FG_COLORS["white"])
                        print(res)
                        gu.log("DEBUG END", bg=gu.BG_COLORS["yellow"], fg=gu.FG_COLORS["white"])
                        if res.find('```') != -1:
                            res = res[res.find('```json') + 7: res.rfind('```')]
                        gu.log("REVGPT after_func_call json result", bg=gu.BG_COLORS["green"], fg=gu.FG_COLORS["white"])
                        after_prompt_res = res
                        after_prompt_res = json.loads(after_prompt_res)
                        break
                    except Exception as e:
                        _c += 1
                        if _c == 5:
                            raise e
                        if "The message you submitted was too long" in str(e):
                            # 如果返回的内容太长了，那么就截取一部分
                            time.sleep(3)
                            invoke_func_res = invoke_func_res[:int(len(invoke_func_res) / 2)]
                            after_prompt = """
函数返回以下内容："""+invoke_func_res+"""
请以AI助手的身份结合返回的内容对用户提问做详细全面的回答。
用户的提问是：
```""" + question + """```
- 在res字段中，不要输出函数的返回值，也不要针对返回值的字段进行分析，也不要输出用户的提问，而是理解这一段返回的结果，并以AI助手的身份回答问题，只需要输出回答的内容，不需要在回答的前面加上身份词。
- 你的返回信息必须只能是json，且需严格遵循以下内容（不含注释）:
```json
{
    "res": string, // 回答的内容
    "func_call_again": bool // 如果函数返回的结果有错误或者问题，可将其设置为true，否则为false
}
```
- 如果func_call_again为true，res请你设为空值，否则请你填写回答的内容。"""
                        else:
                            raise e

                if "func_call_again" in after_prompt_res and after_prompt_res["func_call_again"]:
                    # 如果需要重新调用函数
                    # 重新调用函数
                    gu.log("REVGPT func_call_again", bg=gu.BG_COLORS["purple"], fg=gu.FG_COLORS["white"])
                    res = self.func_call(question, func_definition)
                    return res, True

                gu.log("REVGPT func callback:", bg=gu.BG_COLORS["green"], fg=gu.FG_COLORS["white"])
                # print(after_prompt_res["res"])
                return after_prompt_res["res"], True
            else:
                return str(invoke_func_res_list), True
        else:
            # print(res["res"])
            return res["res"], False





