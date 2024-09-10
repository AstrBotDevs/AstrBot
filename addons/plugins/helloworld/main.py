flag_not_support = False
try:
    from util.plugin_dev.api.v1.bot import Context, AstrMessageEvent, CommandResult
    from util.plugin_dev.api.v1.config import *
except ImportError:
    flag_not_support = True
    print("导入接口失败。请升级到 AstrBot 最新版本。")

'''
注意以格式 XXXPlugin 或 Main 来修改插件名。
提示：把此模板仓库 fork 之后 clone 到机器人文件夹下的 addons/plugins/ 目录下，然后用 Pycharm/VSC 等工具打开可获更棒的编程体验（自动补全等）
'''
class HelloWorldPlugin:
    """
    AstrBot 会传递 context 给插件。
    
    - context.register_commands: 注册指令
    - context.register_task: 注册任务
    - context.message_handler: 消息处理器(平台类插件用)
    """
    def __init__(self, context: Context) -> None:
        self.context = context
        self.context.register_commands("helloworld", "helloworld", "内置测试指令。", 1, self.helloworld)
        self.context.register_llm_tool("welcome_somebody", [{
            "type": "string",
            "name": "name",
            "description": "要欢迎的人的名字"
        }], "给一个用户发送欢迎文本。", self.welcome_somebody)
        
    async def welcome_somebody(self, name: str):
        return CommandResult().message(f"欢迎{name}！")

    """
    指令处理函数。
    
    - 需要接收两个参数：message: AstrMessageEvent, context: Context
    - 返回 CommandResult 对象
    """
    def helloworld(self, message: AstrMessageEvent, context: Context):
        return CommandResult().message("Hello, World!")