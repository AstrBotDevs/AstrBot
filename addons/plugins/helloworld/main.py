import os
import shutil
from nakuru.entities.components import *
flag_not_support = False
try:
    from util.plugin_dev.api.v1.config import *
    from util.plugin_dev.api.v1.bot import (
        AstrMessageEvent,
        CommandResult,
    )
except ImportError:
    flag_not_support = True
    print("导入接口失败。请升级到 AstrBot 最新版本。")


'''
注意改插件名噢！格式：XXXPlugin 或 Main
小提示：把此模板仓库 fork 之后 clone 到机器人文件夹下的 addons/plugins/ 目录下，然后用 Pycharm/VSC 等工具打开可获更棒的编程体验（自动补全等）
'''
class HelloWorldPlugin:
    """
    初始化函数, 可以选择直接pass
    """
    def __init__(self) -> None:
        pass

    """
    机器人程序会调用此函数。
    """
    def run(self, ame: AstrMessageEvent):
        if ame.message_str.startswith("helloworld"): # 如果消息文本以"helloworld"开头
            return CommandResult(
                hit=True, # 代表插件会响应此消息
                success=True, # 插件响应类型为成功响应
                message_chain=[Plain("Hello World!!")], # 消息链
                command_name="helloworld" # 指令名
            )
        return CommandResult(
            hit=False, # 插件不会响应此消息
            success=False,
            message_chain=None
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
            "author": "Soulter",
            "repo": "https://github.com/Soulter/helloworld"
        }
