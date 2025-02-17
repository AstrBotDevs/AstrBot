import aiohttp
import datetime
import builtins
import json
import astrbot.api.star as star
import astrbot.api.event.filter as filter
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import sp
from astrbot.api.provider import ProviderRequest
from astrbot.core.provider.sources.dify_source import ProviderDify
from astrbot.core.utils.io import download_dashboard, get_dashboard_version
from astrbot.core.star.star_handler import star_handlers_registry, StarHandlerMetadata
from astrbot.core.star.star import star_map
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.config.default import VERSION
from .long_term_memory import LongTermMemory
from astrbot.core import logger

from typing import Union

@star.register(name="astrbot", desc="AstrBot 基础指令结合 + 拓展功能", author="Soulter", version="4.0.0")
class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context
        cfg = context.get_config()
        self.prompt_prefix = cfg['provider_settings']['prompt_prefix']
        self.identifier = cfg['provider_settings']['identifier']
        self.enable_datetime = cfg['provider_settings']["datetime_system_prompt"]
        
        self.ltm = None
        if self.context.get_config()['provider_ltm_settings']['group_icl_enable'] or self.context.get_config()['provider_ltm_settings']['active_reply']['enable']:
            try:
                self.ltm = LongTermMemory(self.context.get_config()['provider_ltm_settings'], self.context)
            except BaseException as e:
                logger.error(f"聊天增强 err: {e}")
    
    async def _query_astrbot_notice(self):
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get("https://astrbot.app/notice.json", timeout=2) as resp:
                    return (await resp.json())["notice"]
        except BaseException:
            return ""
        
    @filter.command("help")
    async def help(self, event: AstrMessageEvent):
        '''查看帮助'''
        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except BaseException:
            pass
        
        dashboard_version = await get_dashboard_version()

        msg = f"""AstrBot v{VERSION}(WebUI: {dashboard_version})
AstrBot 指令:
[System]
/plugin: 查看插件、插件帮助
/t2i: 开关文本转图片
/tts: 开关文本转语音
/sid: 获取会话 ID
/op <admin_id>: 授权管理员(op)
/deop <admin_id>: 取消管理员(op)
/wl <sid>: 添加白名单(op)
/dwl <sid>: 删除白名单(op)
/dashboard_update: 更新管理面板(op)
/alter_cmd: 设置指令权限(op)

[大模型]
/provider: 大模型提供商
/model: 模型列表
/ls: 对话列表
/new: 创建新对话
/switch 序号: 切换对话
/rename 新名字: 重命名当前对话
/del: 删除当前会话对话(op)
/reset: 重置 LLM 会话(op)
/history: 当前对话的对话记录
/persona: 人格情景(op)
/tool ls: 函数工具
/key: API Key(op)
/websearch: 网页搜索

[其他]
/set 变量名 值: 为会话定义变量(Dify 工作流输入)
{notice}"""

        event.set_result(MessageEventResult().message(msg).use_t2i(False))
        
    @filter.command_group("tool")
    def tool(self):
        pass
    
    @tool.command("ls")
    async def tool_ls(self, event: AstrMessageEvent):
        tm = self.context.get_llm_tool_manager()
        msg = "函数工具：\n"
        for tool in tm.func_list:
            active = " (启用)" if tool.active else "(停用)"
            msg += f"- {tool.name}: {tool.description} {active}\n"
            
        msg += "\n使用 /tool on/off <工具名> 激活或者停用函数工具。/tool off_all 停用所有函数工具。"
        event.set_result(MessageEventResult().message(msg).use_t2i(False))
        
    @tool.command("on")
    async def tool_on(self, event: AstrMessageEvent, tool_name: str):
        if self.context.activate_llm_tool(tool_name):
            event.set_result(MessageEventResult().message(f"激活工具 {tool_name} 成功。"))
        else:
            event.set_result(MessageEventResult().message(f"激活工具 {tool_name} 失败，未找到此工具。"))
            
    @tool.command("off")
    async def tool_off(self, event: AstrMessageEvent, tool_name: str):
        if self.context.deactivate_llm_tool(tool_name):
            event.set_result(MessageEventResult().message(f"停用工具 {tool_name} 成功。"))
        else:
            event.set_result(MessageEventResult().message(f"停用工具 {tool_name} 失败，未找到此工具。"))
            
    @tool.command("off_all")
    async def tool_all_off(self, event: AstrMessageEvent):
        tm = self.context.get_llm_tool_manager()
        for tool in tm.func_list:
            self.context.deactivate_llm_tool(tool.name)
        event.set_result(MessageEventResult().message("停用所有工具成功。"))

    @filter.command("plugin")
    async def plugin(self, event: AstrMessageEvent, oper1: str = None, oper2: str = None):
        if oper1 is None:
            plugin_list_info = "已加载的插件：\n"
            for plugin in self.context.get_all_stars():
                plugin_list_info += f"- `{plugin.name}` By {plugin.author}: {plugin.desc}\n"
            if plugin_list_info.strip() == "":
                plugin_list_info = "没有加载任何插件。"
            
            plugin_list_info += "\n使用 /plugin <插件名> 查看插件帮助和加载的指令。\n使用 /plugin on/off <插件名> 启用或者禁用插件。"
            event.set_result(MessageEventResult().message(f"{plugin_list_info}").use_t2i(False))
        else:
            if oper1 == "off":
                # 禁用插件
                if oper2 is None:
                    event.set_result(MessageEventResult().message("/plugin off <插件名> 禁用插件。"))
                    return
                await self.context._star_manager.turn_off_plugin(oper2)
                event.set_result(MessageEventResult().message(f"插件 {oper2} 已禁用。"))
            elif oper1 == "on":
                # 启用插件
                if oper2 is None:
                    event.set_result(MessageEventResult().message("/plugin on <插件名> 启用插件。"))
                    return
                await self.context._star_manager.turn_on_plugin(oper2)
                event.set_result(MessageEventResult().message(f"插件 {oper2} 已启用。"))
            
            else:
                # 获取插件帮助
                plugin = self.context.get_registered_star(oper1)
                if plugin is None:
                    event.set_result(MessageEventResult().message("未找到此插件。"))
                    return
                help_msg = plugin.star_cls.__doc__ if plugin.star_cls.__doc__ else "帮助信息: 未提供"
                help_msg += f"\n\n作者: {plugin.author}\n版本: {plugin.version}"
                command_handlers = []
                command_names = []
                for handler in star_handlers_registry:
                    assert isinstance(handler, StarHandlerMetadata)
                    if handler.handler_module_path != plugin.module_path:
                        continue
                    for filter_ in handler.event_filters:
                        if isinstance(filter_, CommandFilter):
                            command_handlers.append(handler)
                            command_names.append(filter_.command_name)
                            break
                        elif isinstance(filter_, CommandGroupFilter):
                            command_handlers.append(handler)
                            command_names.append(filter_.group_name)
                            
                if len(command_handlers) > 0:
                    help_msg += "\n\n指令列表：\n"
                    for i in range(len(command_handlers)):
                        help_msg += f"{command_names[i]}: {command_handlers[i].desc}\n"
                        
                    help_msg += "\nTip: 指令的触发需要添加唤醒前缀，默认为 /。"
                
                ret = f"插件 {oper1} 帮助信息：\n" + help_msg
                ret += "更多帮助信息请查看插件仓库 README。"
                event.set_result(MessageEventResult().message(ret).use_t2i(False))

    @filter.command("t2i")
    async def t2i(self, event: AstrMessageEvent):
        config = self.context.get_config()
        if config['t2i']:
            config['t2i'] = False
            config.save_config()
            event.set_result(MessageEventResult().message("已关闭文本转图片模式。"))
            return
        config['t2i'] = True
        config.save_config()
        event.set_result(MessageEventResult().message("已开启文本转图片模式。"))

    @filter.command("tts")
    async def tts(self, event: AstrMessageEvent):
        config = self.context.get_config()
        if config['provider_tts_settings']['enable']:
            config['provider_tts_settings']['enable'] = False
            config.save_config()
            event.set_result(MessageEventResult().message("已关闭文本转语音。"))
            return
        config['provider_tts_settings']['enable'] = True
        config.save_config()
        event.set_result(MessageEventResult().message("已开启文本转语音。"))
    
    @filter.command("sid")
    async def sid(self, event: AstrMessageEvent):
        sid = event.unified_msg_origin
        user_id = str(event.get_sender_id())
        ret = f"""SID: {sid} 此 ID 可用于设置会话白名单。/wl <SID> 添加白名单, /dwl <SID> 删除白名单。
UID: {user_id} 此 ID 可用于设置管理员。/op <UID> 授权管理员, /deop <UID> 取消管理员。"""
        event.set_result(MessageEventResult().message(ret).use_t2i(False))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("op")
    async def op(self, event: AstrMessageEvent, admin_id: str):
        self.context.get_config()['admins_id'].append(admin_id)
        self.context.get_config().save_config()
        event.set_result(MessageEventResult().message("授权成功。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("deop")
    async def deop(self, event: AstrMessageEvent, admin_id: str):
        try:
            self.context.get_config()['admins_id'].remove(admin_id)
            self.context.get_config().save_config()
            event.set_result(MessageEventResult().message("取消授权成功。"))
        except ValueError:
            event.set_result(MessageEventResult().message("此用户 ID 不在管理员名单内。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("wl")
    async def wl(self, event: AstrMessageEvent, sid: str):
        '''添加白名单。wl <sid>'''
        self.context.get_config()['platform_settings']['id_whitelist'].append(sid)
        self.context.get_config().save_config()
        event.set_result(MessageEventResult().message("添加白名单成功。"))
        
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dwl")
    async def dwl(self, event: AstrMessageEvent, sid: str):
        '''删除白名单。dwl <sid>'''
        try:
            self.context.get_config()['platform_settings']['id_whitelist'].remove(sid)
            self.context.get_config().save_config()
            event.set_result(MessageEventResult().message("删除白名单成功。"))
        except ValueError:
            event.set_result(MessageEventResult().message("此 SID 不在白名单内。"))

    @filter.command("provider")
    async def provider(self, event: AstrMessageEvent, idx: Union[str, int] = None, idx2: int = None):
        '''查看或者切换 LLM Provider'''
        
        if not self.context.get_using_provider():
            event.set_result(MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"))
            return
        
        if idx is None:            
            ret = "## 载入的 LLM 提供商\n"
            for idx, llm in enumerate(self.context.get_all_providers()):
                id_ = llm.meta().id
                ret += f"{idx + 1}. {id_} ({llm.meta().model})"
                if self.context.get_using_provider().meta().id == id_:
                    ret += " (当前使用)"
                ret += "\n"
                
            tts_providers = self.context.get_all_tts_providers()
            if tts_providers:
                ret += "\n## 载入的 TTS 提供商\n"
                for idx, tts in enumerate(tts_providers):
                    id_ = tts.meta().id
                    ret += f"{idx + 1}. {id_}"
                    tts_using = self.context.get_using_tts_provider()
                    if tts_using and tts_using.meta().id == id_:
                        ret += " (当前使用)"
                    ret += "\n"
            
            stt_providers = self.context.get_all_stt_providers()
            if stt_providers:
                ret += "\n## 载入的 STT 提供商\n"
                for idx, stt in enumerate(stt_providers):
                    id_ = stt.meta().id
                    ret += f"{idx + 1}. {id_}"
                    stt_using = self.context.get_using_stt_provider()
                    if stt_using and stt_using.meta().id == id_:
                        ret += " (当前使用)"
                    ret += "\n"

            ret += "\n使用 /provider <序号> 切换 LLM 提供商。"
            
            if tts_providers:
                ret += "\n使用 /provider tts <序号> 切换 TTS 提供商。"
            if stt_providers:
                ret += "\n使用 /provider stt <切换> STT 提供商。"    
            
            event.set_result(MessageEventResult().message(ret))
        else:
            if idx == "tts":
                if idx2 is None:
                    event.set_result(MessageEventResult().message("请输入序号。"))
                    return
                else:
                    if idx2 > len(self.context.get_all_tts_providers()) or idx2 < 1:
                        event.set_result(MessageEventResult().message("无效的序号。"))
                    provider = self.context.get_all_tts_providers()[idx2 - 1]
                    id_ = provider.meta().id
                    self.context.provider_manager.curr_tts_provider_inst = provider
                    sp.put("curr_provider_tts", id_)
                    event.set_result(MessageEventResult().message(f"成功切换到 {id_}。"))
            elif idx == "stt":
                if idx2 is None:
                    event.set_result(MessageEventResult().message("请输入序号。"))
                    return
                else:
                    if idx2 > len(self.context.get_all_stt_providers()) or idx2 < 1:
                        event.set_result(MessageEventResult().message("无效的序号。"))
                    provider = self.context.get_all_stt_providers()[idx2 - 1]
                    id_ = provider.meta().id
                    self.context.provider_manager.curr_stt_provider_inst = provider
                    sp.put("curr_provider_stt", id_)
                    event.set_result(MessageEventResult().message(f"成功切换到 {id_}。"))
            elif isinstance(idx, int):
                if idx > len(self.context.get_all_providers()) or idx < 1:
                    event.set_result(MessageEventResult().message("无效的序号。"))

                provider = self.context.get_all_providers()[idx - 1]
                id_ = provider.meta().id
                self.context.provider_manager.curr_provider_inst = provider
                sp.put("curr_provider", id_)

                event.set_result(MessageEventResult().message(f"成功切换到 {id_}。"))
            else:
                event.set_result(MessageEventResult().message("无效的参数。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("reset")
    async def reset(self, message: AstrMessageEvent):
        '''重置 LLM 会话'''
        if not self.context.get_using_provider():
            message.set_result(MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"))
            return
        
        provider = self.context.get_using_provider()
        print(provider.meta())
        if provider and provider.meta().type == 'dify':
            assert isinstance(provider, ProviderDify)
            await provider.forget(message.unified_msg_origin)
            message.set_result(MessageEventResult().message("已重置当前 Dify 会话，新聊天将更换到新的会话。"))
            return
        
        cid = await self.context.conversation_manager.get_curr_conversation_id(message.unified_msg_origin)
        
        if not cid:
            message.set_result(MessageEventResult().message("当前未处于对话状态，请 /switch 切换或者 /new 创建。"))
            return
        
        await self.context.conversation_manager.update_conversation(
            message.unified_msg_origin, cid, []
        )
        
        ret = "清除会话 LLM 聊天历史成功。"
        if self.ltm:
            cnt = await self.ltm.remove_session(event=message)
            ret += f"\n聊天增强: 已清除 {cnt} 条聊天记录。"
        
        message.set_result(MessageEventResult().message(ret))

    @filter.command("model")
    async def model_ls(self, message: AstrMessageEvent, idx_or_name: Union[int, str] = None):
        '''查看或者切换模型'''
        if not self.context.get_using_provider():
            message.set_result(MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"))
            return
        
        
        if idx_or_name is None:
            models = []
            try:
                models = await self.context.get_using_provider().get_models()
            except BaseException as e:
                message.set_result(MessageEventResult().message("获取模型列表失败: " + str(e)).use_t2i(False))
                return
            i = 1
            ret = "下面列出了此服务提供商可用模型:"
            for model in models:
                ret += f"\n{i}. {model}"
                i += 1
            
            curr_model = self.context.get_using_provider().get_model() or "无"
            ret += f"\n当前模型: [{curr_model}]"
                
            ret += "\nTips: 使用 /model <模型名/编号>，即可实时更换模型。如目标模型不存在于上表，请输入模型名。"
            message.set_result(MessageEventResult().message(ret).use_t2i(False))
        else:
            if isinstance(idx_or_name, int):
                models = []
                try:
                    models = await self.context.get_using_provider().get_models()
                except BaseException as e:
                    message.set_result(MessageEventResult().message("获取模型列表失败: " + str(e)))
                    return
                if idx_or_name > len(models) or idx_or_name < 1:
                    message.set_result(MessageEventResult().message("模型序号错误。"))
                else:
                    try:
                        new_model = models[idx_or_name-1]
                        self.context.get_using_provider().set_model(new_model)
                    except BaseException as e:
                        message.set_result(
                            MessageEventResult().message("切换模型未知错误: "+str(e)))
                    message.set_result(MessageEventResult().message("切换模型成功。"))
            else:
                self.context.get_using_provider().set_model(idx_or_name)
                message.set_result(
                    MessageEventResult().message(f"切换模型到 {self.context.get_using_provider().get_model()}。"))
                

    @filter.command("history")
    async def his(self, message: AstrMessageEvent, page: int = 1):
        '''查看对话记录'''
        if not self.context.get_using_provider():
            message.set_result(MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"))
            return
        
        size_per_page = 6
        session_curr_cid = await self.context.conversation_manager.get_curr_conversation_id(message.unified_msg_origin)
        
        if not session_curr_cid:
            message.set_result(MessageEventResult().message("当前未处于对话状态，请 /switch 序号 切换或者 /new 创建。"))
            return
        
        contexts, total_pages = await self.context.conversation_manager.get_human_readable_context(
            message.unified_msg_origin, session_curr_cid, page, size_per_page
        )

        history = ""
        for context in contexts:
            if len(context) > 150:
                context = context[:150] + "..."
            history += f"{context}\n"
            
        ret = f"""当前对话历史记录：
{history}
第 {page} 页 | 共 {total_pages} 页

*输入 /history 2 跳转到第 2 页
"""

        message.set_result(MessageEventResult().message(ret).use_t2i(False))

    @filter.command("ls")
    async def convs(self, message: AstrMessageEvent, page: int = 1):
        '''查看对话列表'''
        
        provider = self.context.get_using_provider()
        if provider and provider.meta().type == 'dify':
            """原有的Dify处理逻辑保持不变"""
            ret = "Dify 对话列表:\n"
            assert isinstance(provider, ProviderDify)
            data = await provider.api_client.get_chat_convs(message.unified_msg_origin)
            idx = 1
            for conv in data['data']:
                ts_h = datetime.datetime.fromtimestamp(conv['updated_at']).strftime('%m-%d %H:%M')
                ret += f"{idx}. {conv['name']}({conv['id'][:4]})\n  上次更新:{ts_h}\n"
                idx += 1
            if idx == 1:
                ret += "没有找到任何对话。"
            dify_cid = provider.conversation_ids.get(message.unified_msg_origin, None)
            ret += f"\n\n用户: {message.unified_msg_origin}\n当前对话: {dify_cid}\n使用 /switch <序号> 切换对话。"
            message.set_result(MessageEventResult().message(ret))
            return

        size_per_page = 6
        """获取所有对话列表"""
        conversations_all = await self.context.conversation_manager.get_conversations(message.unified_msg_origin)
        """计算总页数"""
        total_pages = (len(conversations_all) + size_per_page - 1) // size_per_page
        """确保页码有效"""
        page = max(1, min(page, total_pages))
        """分页处理"""
        start_idx = (page - 1) * size_per_page
        end_idx = start_idx + size_per_page
        conversations_paged = conversations_all[start_idx:end_idx]
        
        ret = "对话列表：\n---\n"
        """全局序号从当前页的第一个开始"""
        global_index = start_idx + 1  
        
        """生成所有对话的标题字典"""
        _titles = {}
        for conv in conversations_all:
            persona_id = conv.persona_id
            if not persona_id or persona_id == "[%None]":
                persona_id = self.context.provider_manager.selected_default_persona['name']
            title = conv.title if conv.title else "新对话"
            _titles[conv.cid] = title
        
        """遍历分页后的对话生成列表显示"""
        for conv in conversations_paged:
            persona_id = conv.persona_id
            if not persona_id or persona_id == "[%None]":
                persona_id = self.context.provider_manager.selected_default_persona['name']
            title = _titles.get(conv.cid, "新对话")
            ret += f"{global_index}. {title}({conv.cid[:4]})\n  人格情景: {persona_id}\n  上次更新: {datetime.datetime.fromtimestamp(conv.updated_at).strftime('%m-%d %H:%M')}\n"
            global_index += 1
        
        ret += "---\n"
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(message.unified_msg_origin)
        if curr_cid:
            """从所有对话的标题字典中获取标题"""
            title = _titles.get(curr_cid, "新对话")
            ret += f"\n当前对话: {title}({curr_cid[:4]})"
        else:
            ret += "\n当前对话: 无"
        
        unique_session = self.context.get_config()['platform_settings']['unique_session']
        if unique_session:
            ret += "\n会话隔离粒度: 个人"
        else:
            ret += "\n会话隔离粒度: 群聊"
        
        ret += f"\n第 {page} 页 | 共 {total_pages} 页"
        ret += "\n*输入 /ls 2 跳转到第 2 页"
        
        message.set_result(MessageEventResult().message(ret).use_t2i(False))
        return
        
    @filter.command("new")
    async def new_conv(self, message: AstrMessageEvent):
        '''创建新对话'''
        provider = self.context.get_using_provider()
        if provider and provider.meta().type == 'dify':
            assert isinstance(provider, ProviderDify)
            await provider.forget(message.unified_msg_origin)
            message.set_result(MessageEventResult().message("成功，下次聊天将是新对话。"))
            return

        cid = await self.context.conversation_manager.new_conversation(message.unified_msg_origin)
        message.set_result(MessageEventResult().message(f"切换到新对话: 新对话({cid[:4]})。"))
            
    @filter.command("switch")
    async def switch_conv(self, message: AstrMessageEvent, index: int = None):
        '''通过 /ls 前面的序号切换对话'''
        
        provider = self.context.get_using_provider()
        if provider and provider.meta().type == 'dify':
            assert isinstance(provider, ProviderDify)
            data = await provider.api_client.get_chat_convs(message.unified_msg_origin)
            if not data['data']:
                message.set_result(MessageEventResult().message("未找到任何对话。"))
                return
            selected_conv = None
            if index is not None:
                try:
                    selected_conv = data['data'][index-1]
                except IndexError:
                    message.set_result(MessageEventResult().message("对话序号错误，请使用 /ls 查看"))
                    return
            else:
                selected_conv = data['data'][0]
            ret = f"Dify 切换到对话: {selected_conv['name']}({selected_conv['id'][:4]})。"
            provider.conversation_ids[message.unified_msg_origin] = selected_conv['id']
            message.set_result(MessageEventResult().message(ret))
            return
        
        if index is None:
            message.set_result(MessageEventResult().message("请输入对话序号。/switch 对话序号。/ls 查看对话 /new 新建对话"))
            return
        conversations = await self.context.conversation_manager.get_conversations(message.unified_msg_origin)
        if index > len(conversations) or index < 1:
            message.set_result(MessageEventResult().message("对话序号错误，请使用 /ls 查看"))
        else:
            conversation = conversations[index-1]
            title = conversation.title if conversation.title else "新对话"
            await self.context.conversation_manager.switch_conversation(message.unified_msg_origin, conversation.cid)
            message.set_result(MessageEventResult().message(f"切换到对话: {title}({conversation.cid[:4]})。"))
            
    @filter.command("rename")
    async def rename_conv(self, message: AstrMessageEvent, new_name: str):
        '''重命名对话'''
        provider = self.context.get_using_provider()
        
        if provider and provider.meta().type == 'dify':
            assert isinstance(provider, ProviderDify)
            cid = provider.conversation_ids.get(message.unified_msg_origin, None)
            if not cid:
                message.set_result(MessageEventResult().message("未找到当前对话。"))
                return
            await provider.api_client.rename(cid, new_name, message.unified_msg_origin)
            message.set_result(MessageEventResult().message("重命名对话成功。"))
            return
        
        await self.context.conversation_manager.update_conversation_title(message.unified_msg_origin, new_name)
        message.set_result(MessageEventResult().message("重命名对话成功。"))
    
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("del")
    async def del_conv(self, message: AstrMessageEvent):
        '''删除当前对话'''
        
        provider = self.context.get_using_provider()
        if provider and provider.meta().type == 'dify':
            assert isinstance(provider, ProviderDify)
            await provider.api_client.delete_chat_conv(message.unified_msg_origin)
            provider.conversation_ids.pop(message.unified_msg_origin, None)
            message.set_result(MessageEventResult().message("删除当前对话成功。不再处于对话状态，使用 /switch 序号 切换到其他对话或 /new 创建。"))
            return
        
        session_curr_cid = await self.context.conversation_manager.get_curr_conversation_id(message.unified_msg_origin)
        
        if not session_curr_cid:
            message.set_result(MessageEventResult().message("当前未处于对话状态，请 /switch 序号 切换或 /new 创建。"))
            return
        
        await self.context.conversation_manager.delete_conversation(message.unified_msg_origin, session_curr_cid)
        message.set_result(MessageEventResult().message("删除当前对话成功。不再处于对话状态，使用 /switch 序号 切换到其他对话或 /new 创建。"))
        

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("key")
    async def key(self, message: AstrMessageEvent, index: int=None):
                
        if not self.context.get_using_provider():
            message.set_result(MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"))
            return
        
        if index is None:
            keys_data = self.context.get_using_provider().get_keys()
            curr_key = self.context.get_using_provider().get_current_key()
            ret = "Key:"
            for i, k in enumerate(keys_data):
                ret += f"\n{i+1}. {k[:8]}"

            ret += f"\n当前 Key: {curr_key[:8]}"
            ret += "\n当前模型: " + self.context.get_using_provider().get_model()
            ret += "\n使用 /key <idx> 切换 Key。"

            message.set_result(MessageEventResult().message(ret).use_t2i(False))
        else:
            keys_data = self.context.get_using_provider().get_keys()
            if index > len(keys_data) or index < 1:
                message.set_result(MessageEventResult().message("Key 序号错误。"))
            else:
                try:
                    new_key = keys_data[index-1]
                    self.context.get_using_provider().set_key(new_key)
                except BaseException as e:
                    message.set_result(
                        MessageEventResult().message("切换 Key 未知错误: "+str(e)))
                message.set_result(MessageEventResult().message("切换 Key 成功。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("persona")
    async def persona(self, message: AstrMessageEvent):
        l = message.message_str.split(" ")
        
        curr_persona_name = "无"
        cid = await self.context.conversation_manager.get_curr_conversation_id(message.unified_msg_origin)
        curr_cid_title = "无"
        if cid:
            conversation = await self.context.conversation_manager.get_conversation(message.unified_msg_origin, cid)
            if not conversation.persona_id and not conversation.persona_id == "[%None]":
                curr_persona_name = self.context.provider_manager.selected_default_persona['name']
            else:
                curr_persona_name = conversation.persona_id
            
            curr_cid_title = conversation.title if conversation.title else "新对话"
            curr_cid_title += f"({cid[:4]})"
        
        if len(l) == 1:
            message.set_result(
                MessageEventResult().message(f"""[Persona]

- 人格情景列表: `/persona list`
- 设置人格情景: `/persona 人格`
- 人格情景详细信息: `/persona view 人格`
- 取消人格: `/persona unset`

默认人格情景: {self.context.provider_manager.selected_default_persona['name']}
当前对话 {curr_cid_title} 的人格情景: {curr_persona_name}

配置人格情景请前往管理面板-配置页
""").use_t2i(False))
        elif l[1] == "list":
            msg = "人格列表：\n"
            for persona in self.context.provider_manager.personas:
                msg += f"- {persona['name']}\n"
            msg += '\n\n*输入 `/persona view 人格名` 查看人格详细信息'
            message.set_result(MessageEventResult().message(msg))
        elif l[1] == "view":
            if len(l) == 2:
                message.set_result(MessageEventResult().message("请输入人格情景名"))
                return
            ps = l[2].strip()
            if persona := next(builtins.filter(
                lambda persona: persona['name'] == ps, 
                self.context.provider_manager.personas
            ), None):
                msg = f"人格{ps}的详细信息：\n"
                msg += f"{persona['prompt']}\n"
            else:
                msg = f"人格{ps}不存在"
            message.set_result(MessageEventResult().message(msg))
        elif l[1] == "unset":
            if not cid:
                message.set_result(MessageEventResult().message("当前没有对话，无法取消人格。"))
                return
            await self.context.conversation_manager.update_conversation_persona_id(message.unified_msg_origin, "[%None]")
            message.set_result(MessageEventResult().message("取消人格成功。"))
        else:
            ps = "".join(l[1:]).strip()
            if persona := next(builtins.filter(
                lambda persona: persona['name'] == ps, 
                self.context.provider_manager.personas
            ), None):
                await self.context.conversation_manager.update_conversation_persona_id(message.unified_msg_origin, ps)
                message.set_result(MessageEventResult().message("设置成功。如果您正在切换到不同的人格，请注意使用 /reset 来清空上下文，防止原人格对话影响现人格。"))
            else:
                message.set_result(MessageEventResult().message("不存在该人格情景。使用 /persona list 查看所有。"))
    
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dashboard_update")
    async def update_dashboard(self, event: AstrMessageEvent):
        yield event.plain_result("正在尝试更新管理面板...")
        await download_dashboard()
        yield event.plain_result("管理面板更新完成。")

    @filter.command("set")
    async def set_variable(self, event: AstrMessageEvent, key: str, value: str):
        # session_id = event.get_session_id()
        uid = event.unified_msg_origin
        session_vars = sp.get("session_variables", {})
        
        session_var = session_vars.get(uid, {})
        session_var[key] = value
        
        session_vars[uid] = session_var
        
        sp.put("session_variables", session_vars)
        
        yield event.plain_result(f"会话 {uid} 变量 {key} 存储成功。使用 /unset 移除。")
        
    @filter.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str):
        uid = event.unified_msg_origin
        session_vars = sp.get("session_variables", {})
        
        session_var = session_vars.get(uid, {})
        
        if key not in session_var:
            yield event.plain_result("没有那个变量名。格式 /unset 变量名。")
        else:
            del session_var[key]
            sp.put("session_variables", session_vars)
            yield event.plain_result(f"会话 {uid} 变量 {key} 移除成功。")
            
    @filter.command("gewe_logout")
    async def gewe_logout(self, event: AstrMessageEvent):
        platforms = self.context.platform_manager.platform_insts
        for platform in platforms:
            if platform.meta().name == "gewechat":
                yield event.plain_result("正在登出 gewechat")
                await platform.logout()
                yield event.plain_result("已登出 gewechat，请重启 AstrBot")
                return
            
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        '''群聊记忆增强'''
        if self.ltm:
            need_active = await self.ltm.need_active_reply(event)
                        
            group_icl_enable = self.context.get_config()['provider_ltm_settings']['group_icl_enable']
            if group_icl_enable:
                '''记录对话'''
                try:
                    await self.ltm.handle_message(event)
                except BaseException as e:
                    logger.error(e)
                
            if need_active:
                '''主动回复'''
                provider = self.context.get_using_provider()
                if not provider:
                    logger.error("未找到任何 LLM 提供商。请先配置。无法主动回复")
                    return
                try:
                    conv = None
                    history = []
                    if provider.meta().type != 'dify':
                        # Dify 自己有维护对话，不需要 bot 端维护。
                        session_curr_cid = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
                        
                        if not session_curr_cid:
                            logger.error("当前未处于对话状态，无法主动回复，请确保 平台设置->会话隔离(unique_session) 未开启，并使用 /switch 序号 切换或者 /new 创建一个会话。")
                            return
                        
                        conv = await self.context.conversation_manager.get_conversation(
                            event.unified_msg_origin, 
                            session_curr_cid
                        )
                        history = []
                        if conv:
                            history = json.loads(conv.history)
                    else:
                        assert isinstance(provider, ProviderDify)
                        cid = provider.conversation_ids.get(event.unified_msg_origin, None)
                        if cid is None:
                            logger.error("[Dify] 当前未处于对话状态，无法主动回复，请确保 平台设置->会话隔离(unique_session) 未开启，并使用 /switch 序号 切换或者 /new 创建一个会话。")
                            return
                        
                    prompt = self.ltm.ar_prompt
                    if not prompt:
                        prompt = event.message_str
                    
                    yield event.request_llm(
                        prompt=prompt,
                        func_tool_manager=self.context.get_llm_tool_manager(),
                        session_id=event.session_id,
                        contexts=history if history else [],
                        conversation=conv,
                    )
                except BaseException as e:
                    logger.error(f"主动回复失败: {e}")
    
    
    @filter.on_llm_request()
    async def decorate_llm_req(self, event: AstrMessageEvent, req: ProviderRequest):
        '''在请求 LLM 前注入人格信息、Identifier、时间等 System Prompt'''
        if self.prompt_prefix:
            req.prompt = self.prompt_prefix + req.prompt
            
        if self.identifier:
            user_id = event.message_obj.sender.user_id
            user_nickname = event.message_obj.sender.nickname
            user_info = f"\n[User ID: {user_id}, Nickname: {user_nickname}]\n"
            req.prompt = user_info + req.prompt
            
        if self.enable_datetime:
            tz_offset = datetime.timedelta(hours=8)
            tz = datetime.timezone(tz_offset)
            current_time = datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M')
            req.system_prompt += f"\nCurrent datetime: {current_time}\n"
            
        if req.conversation:
            persona_id = req.conversation.persona_id
            if not persona_id and persona_id != "[%None]": # [%None] 为用户取消人格
                persona_id = self.context.provider_manager.selected_default_persona['name']
            persona = next(builtins.filter(
                lambda persona: persona['name'] == persona_id, 
                self.context.provider_manager.personas
            ), None)
            if persona:
                if prompt := persona['prompt']:
                    req.system_prompt += prompt
                if mood_dialogs := persona['_mood_imitation_dialogs_processed']:
                    req.system_prompt += "\nHere are few shots of dialogs, you need to imitate the tone of 'B' in the following dialogs to respond:\n"
                    req.system_prompt += mood_dialogs
                if begin_dialogs := persona["_begin_dialogs_processed"]:
                    req.contexts[:0] = begin_dialogs
                
        if self.ltm:
            try:
                await self.ltm.on_req_llm(event, req)
            except BaseException as e:
                logger.error(f"ltm: {e}")

    
    @filter.after_message_sent()
    async def after_llm_req(self, event: AstrMessageEvent):
        '''在 LLM 请求后记录对话'''
        if self.ltm:
            try:
                await self.ltm.after_req_llm(event)
            except BaseException as e:
                logger.error(f"ltm: {e}")
                
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("alter_cmd")
    async def alter_cmd(self, event: AstrMessageEvent):
        # token = event.message_str.split(" ")
        token = self.parse_commands(event.message_str)
        if token.len < 2:
            yield event.plain_result("可设置所有其他指令是否需要管理员权限。\n格式: /alter_cmd <cmd_name> <admin/member>\n 例如: /alter_cmd provider admin 将 provider 设置为管理员指令")
            return
        
        cmd_name = token.get(1)
        cmd_type = token.get(2)
        
        if cmd_type not in ["admin", "member"]:
            yield event.plain_result("指令类型错误，可选类型有 admin, member")
            return
        
        # 查找指令
        found_command = None
        for handler in star_handlers_registry:
            assert isinstance(handler, StarHandlerMetadata)
            for filter_ in handler.event_filters:
                if isinstance(filter_, CommandFilter):
                    if filter_.command_name == cmd_name:
                        found_command = handler
                        break
                elif isinstance(filter_, CommandGroupFilter):
                    if cmd_name == filter_.group_name:
                        found_command = handler
                        break
        
        if not found_command:
            yield event.plain_result("未找到该指令")
            return
        
        found_plugin = star_map[found_command.handler_module_path]
        
        alter_cmd_cfg = sp.get("alter_cmd", {})
        plugin_ = alter_cmd_cfg.get(found_plugin.name, {})
        cfg = plugin_.get(found_command.handler_name, {})
        cfg["permission"] = cmd_type
        plugin_[found_command.handler_name] = cfg
        alter_cmd_cfg[found_plugin.name] = plugin_
        
        sp.put("alter_cmd", alter_cmd_cfg)
        
        # 注入权限过滤器
        found_permission_filter = False
        for filter_ in found_command.event_filters:
            if isinstance(filter_, PermissionTypeFilter):
                if cmd_type == "admin":
                    filter_.permission_type = filter.PermissionType.ADMIN
                else:
                    filter_.permission_type = filter.PermissionType.MEMBER
                found_permission_filter = True
                break
        if not found_permission_filter:
            found_command.event_filters.insert(0, PermissionTypeFilter(filter.PermissionType.ADMIN if cmd_type == "admin" else filter.PermissionType.MEMBER))

        yield event.plain_result(f"已将 {cmd_name} 设置为 {cmd_type} 指令")

    # @filter.command_group("kdb")
    # def kdb(self):
    #     pass

    # @kdb.command("off")
    # async def off_kdb(self, event: AstrMessageEvent):
    #     self.kdb_enabled = False
    #     yield event.plain_result("知识库已关闭")
        
    # @filter.on_llm_request()
    # async def on_llm_response(self, event: AstrMessageEvent, req: ProviderRequest):
    #     curr_kdb_name = self.context.provider_manager.curr_kdb_name
    #     if self.kdb_enabled and curr_kdb_name:
    #         mgr = self.context.knowledge_db_manager
    #         results = await mgr.retrive_records(curr_kdb_name, req.prompt)
    #         if results:
    #             req.system_prompt += "\nHere are documents that related to user's query: \n"
    #             for result in results:
    #                 req.system_prompt += f"- {result}\n"7