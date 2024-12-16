import traceback
import inspect
from typing import Union, AsyncGenerator
from ...context import PipelineContext
from ..stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult, CommandResult
from astrbot.core.message.components import Image
from astrbot.core import logger
from astrbot.core.utils.metrics import Metric
from astrbot.core.star.star import star_map


class LLMRequestSubStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
        self.prompt_prefix = ctx.astrbot_config['provider_settings']['prompt_prefix']
        self.identifier = ctx.astrbot_config['provider_settings']['identifier']
        self.ctx = ctx
        
    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        # Chat 唤醒前缀
        if self.ctx.astrbot_config['provider_settings']['wake_prefix']:
            if not event.message_str.startswith(self.ctx.astrbot_config['provider_settings']['wake_prefix']):
                return
            event.message_str = event.message_str[len(self.ctx.astrbot_config['provider_settings']['wake_prefix']):]
        
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
        
        tools = self.ctx.plugin_manager.context.get_llm_tool_manager()
        
        provider = self.ctx.plugin_manager.context.get_using_provider()
        try:
            llm_response = await provider.text_chat(
                prompt=event.message_str, 
                session_id=event.session_id, 
                image_urls=image_urls,
                func_tool=tools
            )
            await Metric.upload(llm_tick=1, model_name=provider.get_model(), provider_type=provider.meta().type)
            
            if llm_response.role == 'assistant':
                # text completion
                event.set_result(MessageEventResult().message(llm_response.completion_text))
            elif llm_response.role == 'tool':
                # function calling
                for func_tool_name, func_tool_args in zip(llm_response.tools_call_name, llm_response.tools_call_args):
                    func_tool = tools.get_func(func_tool_name)
                    logger.info(f"调用工具函数：{func_tool_name}，参数：{func_tool_args}")
                    try:
                        # 尝试调用工具函数
                        
                        star_cls_obj = star_map.get(func_tool.module_name).star_cls
                        # 判断 handler 是否是类方法（通过装饰器注册的没有 __self__ 属性）
                        ready_to_call = None
                        if hasattr(func_tool.func_obj, '__self__'):
                            # 猜测没有通过装饰器去注册
                            try:
                                ready_to_call = func_tool.func_obj(event, **func_tool_args)
                            except TypeError:
                                # 向下兼容
                                ready_to_call = func_tool.func_obj(event, self.ctx.plugin_manager.context, **func_tool_args)
                        else:
                            ready_to_call = func_tool.func_obj(star_cls_obj, event, **func_tool_args)
                        if isinstance(ready_to_call, AsyncGenerator):
                            async for mer in ready_to_call:
                                # 如果处理函数是生成器，返回值只能是 MessageEventResult 或者 None（无返回值）
                                if mer:
                                    assert isinstance(mer, (MessageEventResult, CommandResult)), "如果有返回值，必须是 MessageEventResult 或 CommandResult 类型。"
                                    event.set_result(mer)
                                    yield
                                else:
                                    if event.get_result():
                                        yield
                        elif inspect.iscoroutine(ready_to_call):
                            # 如果只是一个 coroutine
                            ret = await ready_to_call
                            if ret:
                                # 如果有返回值
                                assert isinstance(ret, (MessageEventResult, CommandResult)), "如果有返回值，必须是 MessageEventResult 或 CommandResult 类型。"
                                event.set_result(ret)
                            # 执行后续步骤来发送消息
                            if event.is_stopped() and event.get_result():
                                # 主动停止事件传播，并且有结果
                                event.continue_event()
                                yield
                                event.clear_result()
                                event.stop_event()
                                yield
                            elif not event.is_stopped and not event.get_result():
                                continue
                            else:
                                yield
                        event.clear_result() # 清除上一个 handler 的结果

                    except BaseException:
                        logger.error(traceback.format_exc())
                
        except BaseException as e:
            logger.error(traceback.format_exc())
            event.set_result(MessageEventResult().message("AstrBot 请求 LLM 资源失败：" + str(e)))
            return