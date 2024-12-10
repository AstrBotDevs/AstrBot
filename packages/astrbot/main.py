import aiohttp
import astrbot.api.star as star
import astrbot.api.event.filter as filter
from typing import Dict
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.platform import MessageType
from astrbot.api import logger
from astrbot.api import personalities
from astrbot.api.provider import Personality

from typing import Union

@star.register(name="astrbot", desc="AstrBot 基础指令集合", author="Soulter", version="4.0.0")
class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context
        
    @filter.command("help")
    async def help(self, event: AstrMessageEvent):
        notice = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://astrbot.soulter.top/notice.json") as resp:
                    notice = (await resp.json())["notice"]
        except BaseException as e:
            pass

        msg = "已注册的 AstrBot 内置指令:"
        msg += f"""[System]
/plugin: 插件管理
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

提示：如果要查看插件指令，请输入 /plugin 查看具体信息。
{notice}"""

        event.set_result(MessageEventResult().message(msg).use_t2i(False))

    @filter.command("plugin")
    async def plugin(self, event: AstrMessageEvent):
        plugin_list_info = "已加载的插件：\n"
        for plugin in self.context.get_all_stars():
            plugin_list_info += f"- `{plugin.name}` By {plugin.author}: {plugin.desc}\n"
        if plugin_list_info.strip() == "":
            plugin_list_info = "没有加载任何插件。"

        event.set_result(MessageEventResult().message(f"{plugin_list_info}"))

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
        event.set_result(MessageEventResult().message(ret))

    @filter.command("op")
    async def op(self, event: AstrMessageEvent, admin_id: str):
        self.context.get_config()['admins_id'].append(admin_id)
        self.context.get_config().save_config()
        event.set_result(MessageEventResult().message("授权成功。"))

    @filter.command("deop")
    async def deop(self, event: AstrMessageEvent, admin_id: str):
        try:
            self.context.get_config()['admins_id'].remove(admin_id)
            self.context.get_config().save_config()
            event.set_result(MessageEventResult().message("取消授权成功。"))
        except ValueError:
            event.set_result(MessageEventResult().message("此用户 ID 不在管理员名单内。"))
        
    @filter.command("wl")
    async def wl(self, event: AstrMessageEvent, sid: str):
        self.context.get_config()['platform_settings']['id_whitelist'].append(sid)
        self.context.get_config().save_config()
        event.set_result(MessageEventResult().message("添加白名单成功。"))
        
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
                ret += f"{idx + 1}. {llm.meta().id} ({llm.meta().model})"
                if self.provider == llm:
                    ret += " (当前使用)"
                ret += "\n"

            ret += "\n使用 /provider <序号> 切换提供商。"
            event.set_result(MessageEventResult().message(ret))
        else:
            if idx > len(self.context.get_all_providers()) or idx < 1:
                event.set_result(MessageEventResult().message("无效的序号。"))

            self.context.provider_manager.curr_provider_inst = self.context.get_all_providers()[idx - 1]

            event.set_result(MessageEventResult().message(f"成功切换到 {self.context.provider_manager.curr_provider_inst.meta().id}。"))

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
                message.set_result(MessageEventResult().message("获取模型列表失败: " + str(e)))
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

    @filter.command("key")
    async def key(self, message: AstrMessageEvent, index: int=None):
        
        if index == None:
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
"""))
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
