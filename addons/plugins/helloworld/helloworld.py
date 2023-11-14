from nakuru.entities.components import *
from nakuru import (
    GroupMessage,
    FriendMessage
)
from botpy.message import Message, DirectMessage
from model.platform.qq import QQ
import time
import threading
from cores.qqbot.global_object import AstrMessageEvent

class HelloWorldPlugin:
    """
    初始化函数, 可以选择直接pass
    """
    def __init__(self) -> None:
        self.myThread = None # 线程对象，如果要使用线程，需要在此处定义。在run处定义会被释放掉
        print("这是HelloWorld测试插件, 发送 helloworld 即可触发此插件。")

    """
    入口函数，机器人会调用此函数。
    参数规范: message: 消息文本; role: 身份; platform: 消息平台; message_obj: 消息对象; qq_platform: QQ平台对象，可以通过调用qq_platform.send()直接发送消息。详见Helloworld插件示例
    参数详情: role为admin或者member; platform为qqchan或者gocq; message_obj为nakuru的GroupMessage对象或者FriendMessage对象或者频道的Message, DirectMessage对象。
    返回规范: bool: 是否hit到此插件(所有的消息均会调用每一个载入的插件, 如果没有hit到, 则应返回False)
             Tuple: None或者长度为3的元组。当没有hit到时, 返回None. hit到时, 第1个参数为指令是否调用成功, 第2个参数为返回的消息文本或者gocq的消息链列表, 第3个参数为指令名称
    例子：做一个名为"yuanshen"的插件；当接收到消息为“原神 可莉”, 如果不想要处理此消息，则返回False, None；如果想要处理，但是执行失败了，返回True, tuple([False, "请求失败啦~", "yuanshen"])
          ；执行成功了，返回True, tuple([True, "结果文本", "yuanshen"])
    """
    def run(self, ame: AstrMessageEvent):

        if ame.platform == "gocq":
            """
            QQ平台指令处理逻辑
            """
            img_url = "https://gchat.qpic.cn/gchatpic_new/905617992/720871955-2246763964-C6EE1A52CC668EC982453065C4FA8747/0?term=2&amp;is_origin=0"
            if ame.message_str == "helloworld":
                return True, tuple([True, [Plain("Hello World!!"), Image.fromURL(url=img_url)], "helloworld"])
            elif ame.message_str == "hiloop":
                if self.myThread is None:
                    self.myThread = threading.Thread(target=self.helloworldThread, args=(ame.message_obj, ame.gocq_platform))
                    self.myThread.start()
                return True, tuple([True, [Plain("A lot of Helloworlds!!"), Image.fromURL(url=img_url)], "helloworld"]) 
            else:
                return False, None
        elif ame.platform == "qqchan":
            """
            频道处理逻辑(频道暂时只支持回复字符串类型的信息，返回的信息都会被转成字符串，如果不想处理某一个平台的信息，直接返回False, None就行)
            """
            if ame.message_str == "helloworld":
                return True, tuple([True, "Hello World!!", "helloworld"])
            else:
                return False, None
    """
    帮助函数，当用户输入 plugin v 插件名称 时，会调用此函数，返回帮助信息
    返回参数要求(必填)：dict{
        "name": str, # 插件名称
        "desc": str, # 插件简短描述
        "help": str, # 插件帮助信息
        "version": str, # 插件版本
        "author": str, # 插件作者
    }
    """        
    def info(self):
        return {
            "name": "helloworld",
            "desc": "测试插件",
            "help": "测试插件, 回复helloworld即可触发",
            "version": "v1.0.1 beta",
            "author": "Soulter"
        }
    
    def helloworldThread(self, meseage_obj, qq_platform: QQ):
        while True:
            qq_platform.send(meseage_obj, [Plain("Hello World!!")]) # 第一个参数可以是message_obj, 也可以是qq群号
            time.sleep(3) # 睡眠3秒。 用while True一定要记得sleep，不然会卡死
        

        # 热知识：检测消息开头指令，使用以下方法
        # if message.startswith("原神"):
        #     pass