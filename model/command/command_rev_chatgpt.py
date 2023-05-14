from model.command.command import Command
from model.provider.provider_rev_chatgpt import ProviderRevChatGPT

class CommandRevChatGPT(Command):
    def __init__(self, provider: ProviderRevChatGPT):
        self.provider = provider
        self.cached_plugins = {}

    def check_command(self, 
                      message: str, 
                      role: str, 
                      platform: str,
                      message_obj,
                      cached_plugins: dict):
        hit, res = super().check_command(message, role, platform, message_obj=message_obj, cached_plugins=cached_plugins)
        if hit:
            return True, res
        if self.command_start_with(message, "help", "帮助"):
            return True, self.help()
        elif self.command_start_with(message, "reset"):
            return True, self.reset()
        elif self.command_start_with(message, "update"):
            return True, self.update(message, role)
        elif self.command_start_with(message, "keyword"):
            return True, self.keyword(message, role)
        
        if self.command_start_with(message, "/"):
            return True, (False, "未知指令", "unknown_command")
        return False, None
    
    def reset(self):
        return False, "此功能暂未开放", "reset"
    
    def help(self):
        return True, super().help_messager(super().general_commands()), "help"
