from model.command.command import Command
from model.provider.provider_rev_chatgpt import ProviderRevChatGPT

class CommandRevChatGPT(Command):
    def __init__(self, provider: ProviderRevChatGPT):
        self.provider = provider
        
    def check_command(self, message: str):
        # hit, res = super().check_command(message)
        # if hit:
        #     return res
        # if message.startswith("reset") or message.startswith("重置"):
        #     return True, self.reset()
        if message.startswith("help") or message.startswith("帮助"):
            return True, self.help()
        return False, None
    
    def help(self):
        return True, "当前语言模型RevChatGPT未实现任何指令\n"
    