from model.command.command import Command
from model.provider.provider_rev_edgegpt import ProviderRevEdgeGPT
import asyncio
class CommandRevEdgeGPT(Command):
    def __init__(self, provider: ProviderRevEdgeGPT):
        self.provider = provider
        
    def check_command(self, message: str, loop):
        if message.startswith("reset") or message.startswith("重置"):
            return True, self.reset(loop)
        elif message.startswith("help") or message.startswith("帮助"):
            return True, self.help()
        return False, None
    
    def reset(self, loop):
        res = asyncio.run_coroutine_threadsafe(self.provider.forget(), loop).result()
        print(res)
        if res:
            return res, "重置成功"
        else:
            return res, "重置失败"
    
    def help(self):
        return True, "[Github项目名: QQChannelChatGPT，有问题请前往提交issue，欢迎Star此项目~]\n\nRevBing指令面板:\nreset: 重置\nhelp: 帮助"
        
