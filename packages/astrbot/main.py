import aiohttp
import datetime
import astrbot.api.star as star
import astrbot.api.event.filter as filter
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import personalities, sp
from astrbot.api.provider import Personality, ProviderRequest

from typing import Union

@star.register(name="astrbot", desc="AstrBot 基础指令集合", author="Soulter", version="4.0.0")
class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context
        cfg = context.get_config()
        self.prompt_prefix = cfg['provider_settings']['prompt_prefix']
        self.identifier = cfg['provider_settings']['identifier']
        self.enable_datetime = cfg['provider_settings']["datetime_system_prompt"]
        
        self.kdb_enabled = False
    
    async def _query_astrbot_notice(self):
        try:
            async with aiohttp.ClientSession() as session:
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

        msg = "已注册的 AstrBot 内置指令:\n"
        msg += f"""[System]
/plugin: 查看注册的插件、插件帮助
/t2i: 开启/关闭文本转图片模式
/sid: 获取当前会话的 ID
/op <admin_id>: 授权管理员
/deop <admin_id>: 取消管理员
/wl <sid>: 添加会话白名单
/dwl <sid>: 删除会话白名单

[大模型]
/provider: 查看、切换大模型提供商
/model: 查看、切换提供商模型列表
/key: 查看、切换 API Key
/reset: 重置 LLM 会话
/history: 获取会话历史记录
/persona: 情境人格设置
/tool ls: 查看、激活、停用当前注册的函数工具

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
        await self.context.get_using_provider().forget(message.session_id)
        message.set_result(MessageEventResult().message("重置成功"))

    @filter.command("model")
    async def model_ls(self, message: AstrMessageEvent, idx_or_name: Union[int, str] = None):
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
        l = message.message_str.split(" ")
        if len(l) == 1:
            message.set_result(
                MessageEventResult().message(f"""[Persona]

- 设置人格: `/persona 人格名`, 如 /persona 编剧
- 人格列表: `/persona list`
- 人格详细信息: `/persona view 人格名`
- 自定义人格: /persona 人格文本
- 重置 LLM 会话(清除人格): /reset
- 重置 LLM 会话(保留人格): /reset p

【当前人格】: {str(self.context.get_using_provider().curr_personality['prompt'])}
""").use_t2i(False))
        elif l[1] == "list":
            msg = "人格列表：\n"
            for key in personalities.keys():
                msg += f"- {key}\n"
            msg += '\n\n*输入 `/persona view 人格名` 查看人格详细信息'
            message.set_result(MessageEventResult().message(msg))
        elif l[1] == "view":
            if len(l) == 2:
                message.set_result(MessageEventResult().message("请输入人格名"))
            ps = l[2].strip()
            if ps in personalities:
                msg = f"人格{ps}的详细信息：\n"
                msg += f"{personalities[ps]}\n"
            else:
                msg = f"人格{ps}不存在"
            message.set_result(MessageEventResult().message(msg))
        else:
            ps = "".join(l[1:]).strip()
            if ps in personalities:
                self.context.get_using_provider().curr_personality = Personality(
                    name=ps, prompt=personalities[ps])
                message.set_result(
                    MessageEventResult().message(f"人格已设置。 \n人格信息: {ps}"))
            else:
                self.context.get_using_provider().curr_personality = Personality(
                    name="自定义人格", prompt=ps)
                message.set_result(
                    MessageEventResult().message(f"人格已设置。 \n人格信息: {ps}"))

    @filter.on_llm_request()
    async def decorate_llm_req(self, event: AstrMessageEvent, req: ProviderRequest):
        provider = self.context.get_using_provider()
        if self.prompt_prefix:
            req.prompt = self.prompt_prefix + req.prompt
        if self.identifier:
            user_id = event.message_obj.sender.user_id
            user_nickname = event.message_obj.sender.nickname
            user_info = f"[User ID: {user_id}, Nickname: {user_nickname}]\n"
            req.prompt = user_info + req.prompt
        if self.enable_datetime:
            req.system_prompt += f"\nCurrent datetime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        if provider.curr_personality['prompt']:
            req.system_prompt += f"\n{provider.curr_personality['prompt']}"
            
    @filter.event_message_type(filter.EventMessageType.OTHER_MESSAGE)
    async def other_message(self, event: AstrMessageEvent):
        print("triggered")
        event.stop_event()
        
    @filter.command_group("kdb")
    def kdb(self):
        pass
        
    @kdb.command("on")
    async def on_kdb(self, event: AstrMessageEvent):
        self.kdb_enabled = True
        curr_kdb_name = self.context.provider_manager.curr_kdb_name
        if not curr_kdb_name:
            yield event.plain_result("未载入任何知识库")
        else:
            yield event.plain_result(f"知识库已打开。当前载入的知识库: {curr_kdb_name}")
        
    @kdb.command("off")
    async def off_kdb(self, event: AstrMessageEvent):
        self.kdb_enabled = False
        yield event.plain_result("知识库已关闭")
        
    @filter.on_llm_request()
    async def on_llm_response(self, event: AstrMessageEvent, req: ProviderRequest):
        curr_kdb_name = self.context.provider_manager.curr_kdb_name
        if self.kdb_enabled and curr_kdb_name:
            mgr = self.context.knowledge_db_manager
            results = await mgr.retrive_records(curr_kdb_name, req.prompt)
            if results:
                req.system_prompt += "\nHere are documents that related to user's query: \n"
                for result in results:
                    req.system_prompt += f"- {result}\n"