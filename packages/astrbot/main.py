import aiohttp
import datetime
import builtins
import astrbot.api.star as star
import astrbot.api.event.filter as filter
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import sp
from astrbot.api.provider import Personality, ProviderRequest
from astrbot.api.platform import MessageType
from astrbot.core.utils.io import download_dashboard, get_dashboard_version
from astrbot.core.config.default import VERSION
from collections import defaultdict
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
        if self.context.get_config()['provider_ltm_settings']['group_icl_enable']:
            try:
                self.ltm = LongTermMemory(self.context.get_config()['provider_ltm_settings'], self.context)
            except BaseException as e:
                logger.error(f"聊天增强 err: {e}")
    
    async def _query_astrbot_notice(self):
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get("https://astrbot.soulter.top/notice.json", timeout=2) as resp:
                    return (await resp.json())["notice"]
        except BaseException:
            return ""
        
    @filter.command("help")
    async def help(self, event: AstrMessageEvent):
        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except BaseException:
            pass
        
        dashboard_version = await get_dashboard_version()

        msg = f"""AstrBot v{VERSION}(WebUI: {dashboard_version})
已注册的 AstrBot 内置指令:
[System]
/plugin: 查看注册的插件、插件帮助
/t2i: 开启/关闭文本转图片模式
/sid: 获取当前会话的 ID
/op <admin_id>: 授权管理员
/deop <admin_id>: 取消管理员
/wl <sid>: 添加会话白名单
/dwl <sid>: 删除会话白名单
/dashboard_update: 更新管理面板

[大模型]
/provider: 查看、切换大模型提供商
/model: 查看、切换提供商模型列表
/key: 查看、切换 API Key
/reset: 重置 LLM 会话
/history: 获取会话历史记录
/persona: 情境人格设置
/tool ls: 查看、激活、停用当前注册的函数工具

[其他]
/set <变量名> <值>: 为当前会话定义一个变量。适用于 Dify 工作流输入。
/unset <变量名>: 删除当前会话的变量。

提示：如果要查看插件指令，请输入 /plugin 查看具体信息。
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
            
        msg += "\n使用 /tool on/off <工具名> 激活或者停用工具。"
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

    @filter.command("plugin")
    async def plugin(self, event: AstrMessageEvent, oper1: str = None, oper2: str = None):
        if oper1 is None:
            plugin_list_info = "已加载的插件：\n"
            for plugin in self.context.get_all_stars():
                plugin_list_info += f"- `{plugin.name}` By {plugin.author}: {plugin.desc}\n"
            if plugin_list_info.strip() == "":
                plugin_list_info = "没有加载任何插件。"
            
            plugin_list_info += "\n使用 /plugin <插件名> 查看插件帮助。\n使用 /plugin on/off <插件名> 启用或者禁用插件。"
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
                else:
                    help_msg = plugin.star_cls.__doc__ if plugin.star_cls.__doc__ else "该插件未提供帮助信息"
                    ret = f"插件 {oper1} 帮助信息：\n" + help_msg
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
        self.context.get_config()['platform_settings']['id_whitelist'].append(sid)
        self.context.get_config().save_config()
        event.set_result(MessageEventResult().message("添加白名单成功。"))
        
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dwl")
    async def dwl(self, event: AstrMessageEvent, sid: str):
        try:
            self.context.get_config()['platform_settings']['id_whitelist'].remove(sid)
            self.context.get_config().save_config()
            event.set_result(MessageEventResult().message("删除白名单成功。"))
        except ValueError:
            event.set_result(MessageEventResult().message("此 SID 不在白名单内。"))

    @filter.command("provider")
    async def provider(self, event: AstrMessageEvent, idx: int = None):
        '''查看或者切换 LLM Provider'''
        
        if not self.context.get_using_provider():
            event.set_result(MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"))
            return
        
        if idx is None:
            ret = "## 当前载入的 LLM 提供商\n"
            for idx, llm in enumerate(self.context.get_all_providers()):
                id_ = llm.meta().id
                ret += f"{idx + 1}. {id_} ({llm.meta().model})"
                if self.context.get_using_provider().meta().id == id_:
                    ret += " (当前使用)"
                ret += "\n"

            ret += "\n使用 /provider <序号> 切换提供商。"
            event.set_result(MessageEventResult().message(ret))
        else:
            if idx > len(self.context.get_all_providers()) or idx < 1:
                event.set_result(MessageEventResult().message("无效的序号。"))

            provider = self.context.get_all_providers()[idx - 1]
            id_ = provider.meta().id
            self.context.provider_manager.curr_provider_inst = provider
            sp.put("curr_provider", id_)

            event.set_result(MessageEventResult().message(f"成功切换到 {id_}。"))

    @filter.command("reset")
    async def reset(self, message: AstrMessageEvent):
        
        if not self.context.get_using_provider():
            message.set_result(MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"))
            return
        
        await self.context.get_using_provider().forget(message.session_id)
        ret = "清除会话 LLM 聊天历史成功。"
        if self.ltm:
            cnt = await self.ltm.remove_session(event=message)
            ret += f"\n聊天增强: 已清除 {cnt} 条聊天记录。"
        
        message.set_result(MessageEventResult().message(ret))

    @filter.command("model")
    async def model_ls(self, message: AstrMessageEvent, idx_or_name: Union[int, str] = None):
                
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
                    MessageEventResult().message(f"切换模型成功。 \n模型信息: {idx_or_name}"))
                

    @filter.command("history")
    async def his(self, message: AstrMessageEvent, page: int = 1):
        
                
        if not self.context.get_using_provider():
            message.set_result(MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"))
            return
        
        size_per_page = 3
        contexts, total_pages = await self.context.get_using_provider().get_human_readable_context(message.session_id, page, size_per_page)

        history = ""
        for context in contexts:
            history += f"{context}\n"
            
        ret = f"""历史记录：
{history}
第 {page} 页 | 共 {total_pages} 页

*输入 /history 2 跳转到第 2 页
"""

        message.set_result(MessageEventResult().message(ret).use_t2i(False))

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

    @filter.command("persona")
    async def persona(self, message: AstrMessageEvent):
                
        if not self.context.get_using_provider():
            message.set_result(MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"))
            return
        
        
        l = message.message_str.split(" ")
        
        curr_persona_name = "无"
        if self.context.get_using_provider().curr_personality:
            curr_persona_name = self.context.get_using_provider().curr_personality['name']
        
        if len(l) == 1:
            message.set_result(
                MessageEventResult().message(f"""[Persona]

- 设置人格情景: `/persona 人格名`, 如 /persona 编剧
- 人格情景列表: `/persona list`
- 人格情景详细信息: `/persona view 人格名`

当前人格情景: {curr_persona_name}

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
        else:
            ps = "".join(l[1:]).strip()
            if persona := next(builtins.filter(
                lambda persona: persona['name'] == ps, 
                self.context.provider_manager.personas
            ), None):
                self.context.get_using_provider().curr_personality = persona
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
        session_id = event.get_session_id()
        session_vars = sp.get("session_variables", {})
        
        session_var = session_vars.get(session_id, {})
        session_var[key] = value
        
        session_vars[session_id] = session_var
        
        sp.put("session_variables", session_vars)
        
        yield event.plain_result(f"会话 {session_id} 变量 {key} 存储成功。")
        
    @filter.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str):
        session_id = event.get_session_id()
        session_vars = sp.get("session_variables", {})
        
        session_var = session_vars.get(session_id, {})
        
        if key not in session_var:
            yield event.plain_result("没有那个变量名。")
        else:
            del session_var[key]
            sp.put("session_variables", session_vars)
            yield event.plain_result(f"会话 {session_id} 变量 {key} 移除成功。")
            
    @filter.command("gewe_logout")
    async def gewe_logout(self, event: AstrMessageEvent):
        platforms = self.context.platform_manager.platform_insts
        for platform in platforms:
            if platform.meta().name == "gewechat":
                yield event.plain_result("正在登出 gewechat")
                await platform.logout()
                yield event.plain_result("已登出 gewechat")
                return
            
            
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        '''长期记忆'''
        if self.ltm:
            try:
                await self.ltm.handle_message(event)
            except BaseException as e:
                logger.error(e)
    
    
    @filter.on_llm_request()
    async def decorate_llm_req(self, event: AstrMessageEvent, req: ProviderRequest):
        '''在请求 LLM 前注入人格信息、Identifier、时间等 System Prompt'''
        provider = self.context.get_using_provider()
        if self.prompt_prefix:
            req.prompt = self.prompt_prefix + req.prompt
            
        if self.identifier:
            user_id = event.message_obj.sender.user_id
            user_nickname = event.message_obj.sender.nickname
            user_info = f"\n[User ID: {user_id}, Nickname: {user_nickname}]\n"
            req.prompt = user_info + req.prompt
            
        if self.enable_datetime:
            req.system_prompt += f"\nCurrent datetime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        
        if persona := provider.curr_personality:
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

    # @filter.command_group("kdb")
    # def kdb(self):
    #     pass
        
    # @kdb.command("on")
    # async def on_kdb(self, event: AstrMessageEvent):
    #     self.kdb_enabled = True
    #     curr_kdb_name = self.context.provider_manager.curr_kdb_name
    #     if not curr_kdb_name:
    #         yield event.plain_result("未载入任何知识库")
    #     else:
    #         yield event.plain_result(f"知识库已打开。当前载入的知识库: {curr_kdb_name}")
        
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
    #                 req.system_prompt += f"- {result}\n"