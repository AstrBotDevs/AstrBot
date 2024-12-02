import json, traceback
from typing import List, Dict
from astrbot.api import Context, AstrMessageEvent, MessageEventResult
from .openai_adapter import ProviderOpenAIOfficial
from .commands import OpenAIAdapterCommand
from astrbot.api import logger
from . import PLUGIN_NAME
from astrbot.api import MessageChain
from astrbot.api.message_components import Image, Plain
from openai._exceptions import *
from openai.types.chat.chat_completion_message_tool_call import Function
from astrbot.api import command_parser
from .web_searcher import search_from_bing, fetch_website_content
from astrbot.core.utils.metrics import Metric
from astrbot.core.config.astrbot_config import LLMConfig
from .atri import ATRI

class Main:
    def __init__(self, context: Context) -> None:
        supported_provider_names = ["openai", "ollama", "gemini", "deepseek", "zhipu"]
        self.context = context
        
        # 各 Provider 实例
        self.provider_insts: List[ProviderOpenAIOfficial] = []
        # Provider 的配置
        self.provider_llm_configs: List[LLMConfig] = []
        # 当前使用的 Provider
        self.provider = None
        # 当前使用的 Provider 的配置
        self.provider_config = None
        
        atri_config = self.context.get_config().project_atri
        
        loaded = False
        for llm in self.context.get_config().llm:
            if llm.enable:
                if llm.name in supported_provider_names:
                    if not llm.key or not llm.enable:
                        logger.warning("没有开启 LLM Provider 或 API Key 未填写。")
                        continue
                    self.provider_insts.append(ProviderOpenAIOfficial(llm, self.context.get_db()))
                    self.provider_llm_configs.append(llm)
                    loaded = True
                    logger.info(f"已启用 LLM Provider(OpenAI API 适配器): {llm.id}({llm.name})。")
        if loaded:
            self.command_handler = OpenAIAdapterCommand(self.context)
            self.command_handler.set_provider(self.provider_insts[0])
            self.context.register_listener(PLUGIN_NAME, "llm_chat_listener", self.chat, "llm_chat_listener", after_commands=True)
            self.provider = self.command_handler.provider
            self.provider_config = self.provider_llm_configs[0]
        self.context.register_commands(PLUGIN_NAME, "provider", "查看当前 LLM Provider", 10, self.provider_info)
        self.context.register_commands(PLUGIN_NAME, "websearch", "启用/关闭网页搜索", 10, self.web_search)
        
        if self.context.get_config().llm_settings.web_search:
            self.add_web_search_tools()
            
        # load atri
        self.atri = None
        if atri_config.enable:
            try:
                self.atri = ATRI(self.provider_llm_configs, atri_config, self.context)
                self.command_handler.provider = self.atri.atri_chat_provider
            except ImportError as e:
                logger.error(traceback.format_exc())
                logger.error("载入 ATRI 失败。请确保使用 pip 安装了 requirements_atri.txt 下的库。")
                self.atri = None
            except BaseException as e:
                logger.error(traceback.format_exc())
                logger.error("载入 ATRI 失败。")
                self.atri = None
            
    def add_web_search_tools(self):
        self.context.register_llm_tool("web_search", [{
            "type": "string",
            "name": "keyword",
            "description": "搜索关键词"
        }],
            "通过搜索引擎搜索。如果问题需要获取近期、实时的消息，在网页上搜索(如天气、新闻或任何需要通过网页获取信息的问题)，则调用此函数；如果没有，不要调用此函数。",
            search_from_bing
        )
        self.context.register_llm_tool("fetch_website_content", [{
            "type": "string",
            "name": "url",
            "description": "要获取内容的网页链接"
        }],
            "获取网页的内容。如果问题带有合法的网页链接并且用户有需求了解网页内容(例如: `帮我总结一下 https://github.com 的内容`), 就调用此函数。如果没有，不要调用此函数。",
            fetch_website_content
        )
    
    def remove_web_search_tools(self):
        self.context.unregister_llm_tool("web_search")
        self.context.unregister_llm_tool("fetch_website_content")
        
    async def provider_info(self, event: AstrMessageEvent):
        if len(self.provider_insts) == 0:
            event.set_result(MessageEventResult().message("未启用任何 LLM Provider。"))

        tokens = command_parser.parse(event.get_message_str())
        
        if tokens.len == 1:
            ret = "## 当前载入的 LLM 接入源\n"
            for idx, llm in enumerate(self.provider_insts):
                ret += f"{idx}. {llm.llm_config.id} ({llm.llm_config.model_config.model})"
                if self.provider == llm:
                    ret += " (当前使用)"
                ret += "\n"
            
            ret += "\n使用 /provider <序号> 切换 LLM 接入源。" 
            event.set_result(MessageEventResult().message(ret))
            return
        else:
            try:
                idx = int(tokens.get(1))
                if idx >= len(self.provider_insts):
                    event.set_result(MessageEventResult().message("无效的序号。"))
                self.provider = self.provider_insts[idx]
                self.provider_config = self.provider_llm_configs[idx]
                self.command_handler.set_provider(self.provider)
                event.set_result(MessageEventResult().message(f"已经成功切换到 LLM 接入源 {self.provider.llm_config.id}。"))
                return 
            except BaseException as e:
                event.set_result(MessageEventResult().message("provider: 参数错误。"))
                return

    async def web_search(self, event: AstrMessageEvent):
        websearch = self.context.get_config().llm_settings.web_search
        if websearch:
            # turn off
            self.context.get_config().llm_settings.web_search = False
            self.context.get_config().save_config()
            self.remove_web_search_tools()
            event.set_result(MessageEventResult().message("已关闭网页搜索。"))
            return
        # turn on
        self.context.get_config().llm_settings.web_search = True
        self.context.get_config().save_config()
        self.add_web_search_tools()
        event.set_result(MessageEventResult().message("已开启网页搜索。"))
            
    async def chat(self, event: AstrMessageEvent):
        if not event.is_wake_up():
            return
        if self.atri:
            await self.atri.chat(event)
            return

        # prompt 前缀
        if self.provider_config.prompt_prefix:
            event.message_str = self.provider_config.prompt_prefix + event.message_str
        
        image_url = None
        for comp in event.message_obj.message:
            if isinstance(comp, Image):
                image_url = comp.url if comp.url else comp.file
                break
        
        tool_use_flag = False
        llm_result = None
        try:
            if not self.context.llm_tools.empty():
                # tools-use
                tool_use_flag = True
                llm_result = await self.provider.text_chat(
                    prompt=event.message_str, 
                    session_id=event.session_id, 
                    tools=self.context.llm_tools.get_func()
                )
                await Metric.upload(llm_tick=1, llm_name=self.provider.get_model(), llm_api_base=self.provider.base_url)
                
                if isinstance(llm_result, Function):
                    logger.debug(f"function-calling: {llm_result}")
                    func_obj = None
                    for i in self.context.llm_tools.func_list:
                        if i["name"] == llm_result.name:
                            func_obj = i["func_obj"]
                            break
                    if not func_obj:
                        event.set_result(MessageEventResult().message("AstrBot Function-calling 异常：未找到请求的函数调用。"))
                        return
                    try:
                        args = json.loads(llm_result.arguments)
                        args['event'] = event
                        args['provider'] = self.provider
                        try:
                            func_result = await func_obj(**args)
                        except TypeError as e:
                            args.pop('event')
                            args.pop('provider')
                            func_result = await func_obj(**args)
                        if func_result:
                            logger.warning(f"function-calling: 工具函数 {llm_result.name} 返回了非空值，该值将被忽略。请使用 event.set_result() 设置返回值。")
                            return
                        if event.get_result():
                            return
                    except BaseException as e:
                        traceback.print_exc()
                        event.set_result(MessageEventResult().message("AstrBot Function-calling 异常：" + str(e)))
                        return
                else:
                    event.set_result(MessageEventResult().message(llm_result))
                    return
            else:
                # normal chat
                # add user info to the prompt
                if self.context.get_config().llm_settings.identifier:
                    user_id = event.message_obj.sender.user_id
                    user_nickname = event.message_obj.sender.nickname
                    user_info = f"[User ID: {user_id}, Nickname: {user_nickname}]\n"
                    event.message_str = user_info + event.message_str
                llm_result = await self.provider.text_chat(
                    prompt=event.message_str, 
                    session_id=event.session_id, 
                    image_url=image_url
                )
                await Metric.upload(llm_tick=1, llm_name=self.provider.get_model(), llm_api_base=self.provider.base_url)
        except BadRequestError as e:
            if tool_use_flag:
                # seems like the model don't support function-calling
                logger.error(f"error: {e}. Using local function-calling implementation")
                
                try:
                    # use local function-calling implementation
                    args = {
                        'question': llm_result,
                        'func_definition': self.context.llm_tools.func_dump(),
                    }
                    _, has_func = await self.context.llm_tools.func_call(**args)
                    
                    if not has_func:
                        # normal chat
                        llm_result = await self.provider.text_chat(
                            prompt=event.message_str, 
                            session_id=event.session_id, 
                            image_url=image_url
                        )
                except BaseException as e:
                    logger.error(traceback.format_exc())
                    event.set_result(MessageEventResult().message("AstrBot Function-calling 异常：" + str(e)))
                    return
            else:
                logger.error(traceback.format_exc())
                logger.error(f"LLM 调用失败。")
                event.set_result(MessageEventResult().message("AstrBot 请求 LLM 资源失败：" + str(e)))
                return
        except BaseException as e:
            logger.error(traceback.format_exc())
            logger.error(f"LLM 调用失败。")
            event.set_result(MessageEventResult().message("AstrBot 请求 LLM 资源失败：" + str(e)))
            return
        
        if llm_result:
            event.set_result(MessageEventResult().message(llm_result))
            return
