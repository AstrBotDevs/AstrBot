from model.command.command import Command
from model.provider.rev_edgegpt import ProviderRevEdgeGPT
import asyncio
from model.platform.qq import QQ
from cores.qqbot.global_object import GlobalObject

class CommandRevEdgeGPT(Command):
    def __init__(self, provider: ProviderRevEdgeGPT, global_object: GlobalObject):
        self.provider = provider
        self.cached_plugins = {}
        self.global_object = global_object
        super().__init__(provider, global_object)

    def check_command(self, 
                      message: str, 
                      session_id: str, 
                      role: str, 
                      platform: str,
                      message_obj):
        self.platform = platform

        hit, res = super().check_command(
            message,
            session_id,
            role,
            platform,
            message_obj
        )
        
        if hit:
            return True, res
        if self.command_start_with(message, "reset"):
            return True, self.reset()
        elif self.command_start_with(message, "help"):
            return True, self.help()
        elif self.command_start_with(message, "update"):
            return True, self.update(message, role)

        return False, None
    
    def reset(self, loop = None):
        if self.provider is None:
            return False, "未启动Bing语言模型.", "reset"
        res = asyncio.run_coroutine_threadsafe(self.provider.forget(), loop).result()
        print(res)
        if res:
            return res, "重置成功", "reset"
        else:
            return res, "重置失败", "reset"
    
    def help(self):
        return True, super().help_messager(super().general_commands(), self.platform, self.global_object.cached_plugins), "help"
