from dataclasses import dataclass
from type.register import RegisteredPlugins
from typing import List, Union, Callable
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot')


@dataclass
class CommandRegisterRequest():
    command_name: str
    description: str
    priority: int
    handler: Callable
    use_regex: bool = False
    plugin_name: str = None
    ignore_prefix: bool = False

class PluginCommandBridge():
    def __init__(self, cached_plugins: RegisteredPlugins):
        self.plugin_commands_waitlist: List[CommandRegisterRequest] = []
        self.cached_plugins = cached_plugins
        
    def register_command(self, plugin_name, command_name, description, priority, handler, use_regex=False, ignore_prefix=False):
        self.plugin_commands_waitlist.append(CommandRegisterRequest(command_name, description, priority, handler, use_regex, plugin_name, ignore_prefix))
