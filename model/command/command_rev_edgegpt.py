from model.command.command import Command
from model.provider.provider_rev_edgegpt import ProviderRevEdgeGPT
import asyncio
class CommandRevEdgeGPT(Command):
    def __init__(self, provider: ProviderRevEdgeGPT):
        self.provider = provider
        
    def check_command(self, message: str, loop, role):
        if self.command_start_with(message, "reset"):
            return True, self.reset(loop)
        elif self.command_start_with(message, "help"):
            return True, self.help()
        elif self.command_start_with(message, "update"):
            return True, self.update(message, role)
        elif self.command_start_with(message, "keyword"):
            return True, self.keyword(message, role)
        return False, None
    
    def reset(self, loop):
        res = asyncio.run_coroutine_threadsafe(self.provider.forget(), loop).result()
        print(res)
        if res:
            return res, "重置成功", "reset"
        else:
            return res, "重置失败", "reset"
    
    def help(self):
        return True, super().help_messager(super().general_commands()), "help"
        
