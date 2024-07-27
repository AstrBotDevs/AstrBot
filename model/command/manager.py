import heapq
import inspect
import traceback
from typing import Dict
from type.types import Context
from type.plugin import PluginMetadata
from type.message_event import AstrMessageEvent
from type.command import CommandResult
from type.register import RegisteredPlugins
from model.command.parser import CommandParser
from model.plugin.command import PluginCommandBridge
from SparkleLogging.utils.core import LogManager
from logging import Logger
from dataclasses import dataclass

logger: Logger = LogManager.GetLogger(log_name='astrbot')

@dataclass
class CommandMetadata():
    inner_command: bool
    plugin_metadata: PluginMetadata
    handler: callable
    description: str

class CommandManager():
    def __init__(self):
        self.commands = []
        self.commands_handler: Dict[str, CommandMetadata] = {}
        self.command_parser = CommandParser()
        
    def register(self, 
                 command: str, 
                 description: str, 
                 priority: int,
                 handler: callable,
                 plugin_metadata: PluginMetadata = None,
                ):
        '''
        优先级越高，越先被处理。
        '''
        if command in self.commands_handler:
            raise ValueError(f"Command {command} already exists.")
        if not handler:
            raise ValueError(f"Handler of {command} is None.")
        
        heapq.heappush(self.commands, (-priority, command))
        self.commands_handler[command] = CommandMetadata(
            inner_command=plugin_metadata == None,
            plugin_metadata=plugin_metadata,
            handler=handler,
            description=description
        )
        if plugin_metadata:
            logger.info(f"已注册 {plugin_metadata.author}/{plugin_metadata.plugin_name} 的指令 {command}。")
        else:
            logger.info(f"已注册指令 {command}。")
        
    def register_from_pcb(self, pcb: PluginCommandBridge):
        for request in pcb.plugin_commands_waitlist:
            plugin = None
            for registered_plugin in pcb.cached_plugins:
                if registered_plugin.metadata.plugin_name == request.plugin_name:
                    plugin = registered_plugin
                    break
            if not plugin:
                logger.warning(f"插件 {request.plugin_name} 未找到，无法注册指令 {request.command_name}。")
            self.register(request.command_name, request.description, request.priority, request.handler, plugin.metadata)
        self.plugin_commands_waitlist = []

    async def scan_command(self, message_event: AstrMessageEvent, context: Context) -> CommandResult:
        message_str = message_event.message_str
        for _, command in self.commands:
            if message_str.startswith(command):
                logger.info(f"触发 {command} 指令。")
                command_result = await self.execute_handler(command, message_event, context)
                if command_result.hit:
                    return command_result

    async def execute_handler(self,
                        command: str,
                        message_event: AstrMessageEvent,
                        context: Context) -> CommandResult:
        command_metadata = self.commands_handler[command]
        handler = command_metadata.handler
        # call handler
        try:
            if inspect.iscoroutinefunction(handler):
                command_result = await handler(message_event, context)
            else:
                command_result = handler(message_event, context)
            
            if not isinstance(command_result, CommandResult):
                raise ValueError(f"Command {command} handler should return CommandResult.")
            
            context.metrics_uploader.command_stats[command] += 1
            
            return command_result
        except BaseException as e:
            logger.error(traceback.format_exc())
            
            if not command_metadata.inner_command:
                text = f"执行 {command}/({command_metadata.plugin_metadata.plugin_name} By {command_metadata.plugin_metadata.author}) 指令时发生了异常。{e}"
                logger.error(text)
            else:
                text = f"执行 {command} 指令时发生了异常。{e}"
                logger.error(text)
            return CommandResult().message(text)