from cores.qqbot.core import oper_msg
from cores.qqbot.types import AstrMessageEvent, CommandResult
from model.platform._message_result import MessageResult

'''
消息处理。在消息平台接收到消息后，调用此函数进行处理。
集成了指令检测、指令处理、LLM 调用等功能。
'''
message_handler = oper_msg 
