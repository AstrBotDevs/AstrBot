from model.command.command import Command
from model.provider.provider_rev_chatgpt import ProviderRevChatGPT

class CommandRevChatGPT(Command):
    def __init__(self, provider: ProviderRevChatGPT):
        self.provider = provider
        
    def check_command(self, message: str, role):
        if self.command_start_with(message, "help", "帮助"):
            return True, self.help()
        elif self.command_start_with(message, "update"):
            return True, self.update(message, role)
        elif self.command_start_with(message, "keyword"):
            return True, self.keyword(message, role)
        return False, None
    
    def help(self):
        return True, "[Github项目名: QQChannelChatGPT，有问题请前往提交issue，欢迎Star此项目~]\n\nRevChatGPT指令面板：\n当前语言模型RevChatGPT未实现任何指令\n", "help"
    