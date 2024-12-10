import traceback
from typing import Union, AsyncGenerator
from ...context import PipelineContext
from ..stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult, CommandResult
from astrbot.core.message.components import Image
from astrbot.core import logger
from astrbot.core.utils.metrics import Metric


class LLMRequestSubStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
        self.curr_provider = ctx.plugin_manager.context.get_using_provider()
        self.prompt_prefix = ctx.astrbot_config['provider_settings']['prompt_prefix']
        self.identifier = ctx.astrbot_config['provider_settings']['identifier']
        self.ctx = ctx
        
    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        if self.prompt_prefix:
            event.message_str = self.prompt_prefix + event.message_str
        if self.identifier:
            user_id = event.message_obj.sender.user_id
            user_nickname = event.message_obj.sender.nickname
            user_info = f"[User ID: {user_id}, Nickname: {user_nickname}]\n"
            event.message_str = user_info + event.message_str
            
        image_urls = []
        for comp in event.message_obj.message:
            if isinstance(comp, Image):
                image_url = comp.url if comp.url else comp.file
                image_urls.append(image_url)
        
        tools = self.ctx.plugin_manager.context.get_llm_tools()
        
        try:
            llm_response = await self.curr_provider.text_chat(
                prompt=event.message_str, 
                session_id=event.session_id, 
                image_urls=image_urls,
                tools=tools
            )
            await Metric.upload(llm_tick=1, model_name=self.curr_provider.get_model(), provider_type=self.curr_provider.meta().type)
            
            if llm_response.role == 'assistant':
                # text completion
                event.set_result(MessageEventResult().message(llm_response.completion_text))
            elif llm_response.role == 'tool':
                # function calling
                for func_tool_name, func_tool_args in zip(llm_response.tools_call_name, llm_response.tools_call_args):
                    func_tool = tools.get_func(func_tool_name)
                    logger.debug(f"调用工具函数：{func_tool_name}，参数：{func_tool_args}")
                    try:
                        ret = await func_tool(event=event, *func_tool_args)

                        if ret:
                            assert isinstance(ret, (MessageEventResult, CommandResult)), "如果有返回值，事件监听器的返回值必须是 MessageEventResult 或 CommandResult 类型。"
                            event.stop_event()
                            event.set_result(ret)
                        # 执行后续步骤来发送消息
                        yield

                    except BaseException:
                        logger.error(traceback.format_exc())
                
        except BaseException as e:
            logger.error(traceback.format_exc())
            event.set_result(MessageEventResult().message("AstrBot 请求 LLM 资源失败：" + str(e)))
            return