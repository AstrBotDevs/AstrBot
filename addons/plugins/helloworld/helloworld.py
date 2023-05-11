class HelloWorldPlugin:
    """
    初始化函数, 可以选择直接pass
    """
    def __init__(self) -> None:
        print("这是HelloWorld测试插件, 发送 helloworld 即可触发此插件。")

    """
    入口函数，机器人会调用此函数。
    参数规范: message: 消息文本; role: 身份; platform: 消息平台
    返回规范: bool: 是否hit到此插件(所有的消息均会调用每一个载入的插件, 如果没有hit到, 则应返回False)
             Tuple: None或者长度为3的元组。当没有hit到时, 返回None. hit到时, 第1个参数为指令是否调用成功, 第2个参数为返回的消息文本, 第3个参数为指令名称
    例子：做一个名为"yuanshen"的插件；当接收到消息为“原神 可莉”, 如果不想要处理此消息，则返回False, None；如果想要处理，但是执行失败了，返回True, tuple([False, "请求失败啦~", "yuanshen"])
          ；执行成功了，返回True, tuple([True, "结果文本", "yuanshen"])
    """
    def run(self, message: str, role: str, platform: str):

        # 这里是插件核心处理逻辑
        if message == "helloworld":
            return True, tuple([True, "Hello World~", "helloworld"])
        else:
            return False, None
        
        # 热知识：检测消息开头指令，使用以下方法
        # if message.startswith("原神"):
        #     pass