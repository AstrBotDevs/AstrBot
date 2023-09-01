from model.command.command import Command
from model.provider.provider_rev_edgegpt import ProviderRevEdgeGPT
import asyncio
from model.platform.qq import QQ

class CommandRevEdgeGPT(Command):
    def __init__(self, provider: ProviderRevEdgeGPT, global_object: dict):
        self.provider = provider
        self.cached_plugins = {}
        self.global_object = global_object
        super().__init__(provider, global_object)

    def check_command(self, 
                      message: str, 
                      session_id: str,
                      loop, 
                      role: str, 
                      platform: str,
                      message_obj,
                      cached_plugins: dict, 
                      qq_platform: QQ):
        self.platform = platform

        hit, res = super().check_command(
            message,
            session_id,
            loop,
            role,
            platform,
            message_obj,
            cached_plugins,
            qq_platform
        )
        
        if hit:
            return True, res
        if self.command_start_with(message, "reset"):
            return True, self.reset(loop)
        elif self.command_start_with(message, "help"):
            return True, self.help(cached_plugins)
        elif self.command_start_with(message, "update"):
            return True, self.update(message, role)
        elif self.command_start_with(message, "keyword"):
            return True, self.keyword(message, role)
        
        if self.command_start_with(message, "/"):
            return True, (False, "未知指令", "unknown_command")
        return False, None
    
    def reset(self, loop):
        if self.provider is None:
            return False, "未启动Bing语言模型.", "reset"
        res = asyncio.run_coroutine_threadsafe(self.provider.forget(), loop).result()
        print(res)
        if res:
            return res, "重置成功", "reset"
        else:
            return res, "重置失败", "reset"
    
    def help(self, cached_plugins: dict):
        return True, super().help_messager(super().general_commands(), self.platform, cached_plugins), "help"
        
