from nakuru.entities.components import *
from nakuru import (
    GroupMessage,
    FriendMessage
)
from botpy.message import Message, DirectMessage
from model.platform.qq import QQ
from cores.qqbot.global_object import (
    AstrMessageEvent,
    CommandResult
)

'''
注意改插件名噢！格式：XXXPlugin 或 Main
小提示：把此模板仓库 fork 之后 clone 到机器人文件夹下的 addons/plugins/ 目录下，然后用 Pycharm/VSC 等工具打开可获更棒的编程体验（自动补全等）
'''
class HelloWorldPlugin:
    """
    初始化函数, 可以选择直接pass
    """
    def __init__(self) -> None:
        print("hello, world!")

    """
    机器人程序会调用此函数。
    返回规范: bool: 插件是否响应该消息 (所有的消息均会调用每一个载入的插件, 如果不响应, 则应返回 False)
             Tuple: Non e或者长度为 3 的元组。如果不响应, 返回 None； 如果响应, 第 1 个参数为指令是否调用成功, 第 2 个参数为返回的消息链列表, 第 3 个参数为指令名称
    例子：一个名为"yuanshen"的插件；当接收到消息为“原神 可莉”, 如果不想要处理此消息，则返回False, None；如果想要处理，但是执行失败了，返回True, tuple([False, "请求失败。", "yuanshen"]) ；执行成功了，返回True, tuple([True, "结果文本", "yuanshen"])
    """
    def run(self, ame: AstrMessageEvent):
        if ame.message_str == "helloworld":
            # return True, tuple([True, "Hello World!!", "helloworld"])
            return CommandResult(
                hit=True,
                success=True,
                message_chain=[Plain("Hello World!!")],
                command_name="helloworld"
            )
        else:
            return CommandResult(
                hit=False,
                success=False,
                message_chain=None,
                command_name=None
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
            "desc": "测试插件",
            "help": "测试插件, 回复 helloworld 即可触发",
            "version": "v1.2",
            "author": "Soulter"
        }