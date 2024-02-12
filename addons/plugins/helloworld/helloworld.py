from nakuru.entities.components import *
from nakuru import (
    GroupMessage,
    FriendMessage
)
from botpy.message import Message, DirectMessage
from cores.qqbot.global_object import (
    AstrMessageEvent,
    CommandResult
)
import os
import shutil

'''
注意改插件名噢！格式：XXXPlugin 或 Main
小提示：把此模板仓库 fork 之后 clone 到机器人文件夹下的 addons/plugins/ 目录下，然后用 Pycharm/VSC 等工具打开可获更棒的编程体验（自动补全等）
'''
class HelloWorldPlugin:
    """
    初始化函数, 可以选择直接pass
    """
    def __init__(self) -> None:
        # 复制旧配置文件到 data 目录下。
        if os.path.exists("keyword.json"):
            shutil.move("keyword.json", "data/keyword.json")
        self.keywords = {}
        if os.path.exists("data/keyword.json"):
            self.keywords = json.load(open("data/keyword.json", "r"))
        else:
            self.save_keyword()

    """
    机器人程序会调用此函数。
    返回规范: bool: 插件是否响应该消息 (所有的消息均会调用每一个载入的插件, 如果不响应, 则应返回 False)
             Tuple: Non e或者长度为 3 的元组。如果不响应, 返回 None； 如果响应, 第 1 个参数为指令是否调用成功, 第 2 个参数为返回的消息链列表, 第 3 个参数为指令名称
    例子：一个名为"yuanshen"的插件；当接收到消息为“原神 可莉”, 如果不想要处理此消息，则返回False, None；如果想要处理，但是执行失败了，返回True, tuple([False, "请求失败。", "yuanshen"]) ；执行成功了，返回True, tuple([True, "结果文本", "yuanshen"])
    """
    def run(self, ame: AstrMessageEvent):
        if ame.message_str == "helloworld":
            return CommandResult(
                hit=True,
                success=True,
                message_chain=[Plain("Hello World!!")],
                command_name="helloworld"
            )
        if ame.message_str.startswith("/keyword") or ame.message_str.startswith("keyword"):
            return self.handle_keyword_command(ame)
            
        ret = self.check_keyword(ame.message_str)
        if ret: return ret

        return CommandResult(
            hit=False,
            success=False,
            message_chain=None,
            command_name=None
        )
        
    def handle_keyword_command(self, ame: AstrMessageEvent):
        l = ame.message_str.split(" ")
        
        # 获取图片
        image_url = ""
        for comp in ame.message_obj.message:
            if isinstance(comp, Image) and image_url == "":
                if comp.url is None:
                    image_url = comp.file
                else:
                    image_url = comp.url
    
        command_result = CommandResult(
            hit=True,
            success=False,
            message_chain=None,
            command_name="keyword"
        )
        if len(l) == 1 or (len(l) == 2 and image_url == ""):
            ret = """【设置关键词回复】
示例：
1. keyword <触发词> <回复词>
keyword hi 你好
发送 hi 回复你好
* 回复词支持图片

2. keyword d <触发词>
keyword d hi
删除 hi 触发词产生的回复"""
            command_result.success = True
            command_result.message_chain = [Plain(ret)]
            return command_result
        elif len(l) == 3 and l[1] == "d":
            if l[2] not in self.keywords:
                command_result.message_chain = [Plain(f"关键词 {l[2]} 不存在")]
                return command_result
            self.keywords.pop(l[2])
            self.save_keyword()
            command_result.success = True
            command_result.message_chain = [Plain("删除成功")]
            return command_result
        else:
            self.keywords[l[1]] = {
                "plain_text": " ".join(l[2:]),
                "image_url": image_url
            }
            self.save_keyword()
            command_result.success = True
            command_result.message_chain = [Plain("设置成功")]
            return command_result
        
    def save_keyword(self):
        json.dump(self.keywords, open("data/keyword.json", "w"), ensure_ascii=False)
        
        
    def check_keyword(self, message_str: str):
        for k in self.keywords:
            if message_str == k:
                plain_text = ""
                if 'plain_text' in self.keywords[k]:
                    plain_text = self.keywords[k]['plain_text']
                else:
                    plain_text = self.keywords[k]
                image_url = ""
                if 'image_url' in self.keywords[k]:
                    image_url = self.keywords[k]['image_url']
                if image_url != "":
                    res = [Plain(plain_text), Image.fromURL(image_url)]
                    return CommandResult(
                        hit=True,
                        success=True,
                        message_chain=res,
                        command_name="keyword"
                    )
                return CommandResult(
                    hit=True,
                    success=True,
                    message_chain=[Plain(plain_text)],
                    command_name="keyword"
                )

    """
    插件元信息。
    当用户输入 plugin v 插件名称 时，会调用此函数，返回帮助信息。
    返回参数要求(必填)：dict{
        "name": str, # 插件名称
        "desc": str, # 插件简短描述
        "help": str, # 插件帮助信息
        "version": str, # 插件版本
        "author": str, # 插件作者
        "repo": str, # 插件仓库地址 [ 可选 ]
        "homepage": str, # 插件主页  [ 可选 ]
    }
    """        
    def info(self):
        return {
            "name": "helloworld",
            "desc": "这是 AstrBot 的默认插件，支持关键词回复。",
            "help": "输入 /keyword 查看关键词回复帮助。",
            "version": "v1.3",
            "author": "Soulter"
        }