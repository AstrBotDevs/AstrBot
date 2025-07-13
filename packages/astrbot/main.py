import os
import aiohttp
import datetime
import builtins
import traceback
import re
import zoneinfo
import astrbot.api.star as star
import astrbot.api.event.filter as filter
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import sp
from astrbot.api.provider import ProviderRequest
from astrbot.core import DEMO_MODE
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.message_type import MessageType
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.sources.dify_source import ProviderDify
from astrbot.core.utils.io import download_dashboard, get_dashboard_version
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.star.star_handler import star_handlers_registry, StarHandlerMetadata
from astrbot.core.star.star import star_map
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.config.default import VERSION
from .long_term_memory import LongTermMemory
from astrbot.core import logger
from astrbot.api.message_components import Plain, Image, Reply
from astrbot.core.star.session_llm_manager import SessionServiceManager
from typing import Union
from enum import Enum


class RstScene(Enum):
    GROUP_UNIQUE_ON = ("group_unique_on", "群聊+会话隔离开启")
    GROUP_UNIQUE_OFF = ("group_unique_off", "群聊+会话隔离关闭")
    PRIVATE = ("private", "私聊")

    @property
    def key(self) -> str:
        return self.value[0]

    @property
    def name(self) -> str:
        return self.value[1]

    @classmethod
    def from_index(cls, index: int) -> "RstScene":
        mapping = {1: cls.GROUP_UNIQUE_ON, 2: cls.GROUP_UNIQUE_OFF, 3: cls.PRIVATE}
        return mapping[index]

    @classmethod
    def get_scene(cls, is_group: bool, is_unique_session: bool) -> "RstScene":
        if is_group:
            return cls.GROUP_UNIQUE_ON if is_unique_session else cls.GROUP_UNIQUE_OFF
        return cls.PRIVATE


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context
        cfg = context.get_config()
        self.prompt_prefix = cfg["provider_settings"]["prompt_prefix"]
        self.identifier = cfg["provider_settings"]["identifier"]
        self.enable_datetime = cfg["provider_settings"]["datetime_system_prompt"]
        self.timezone = cfg.get("timezone")
        if not self.timezone:
            # 系统默认时区
            self.timezone = None
        else:
            logger.info(f"Timezone set to: {self.timezone}")
        self.ltm = None
        if (
            self.context.get_config()["provider_ltm_settings"]["group_icl_enable"]
            or self.context.get_config()["provider_ltm_settings"]["active_reply"][
                "enable"
            ]
        ):
            try:
                self.ltm = LongTermMemory(
                    self.context.get_config()["provider_ltm_settings"], self.context
                )
            except BaseException as e:
                logger.error(f"聊天增强 err: {e}")

    async def _query_astrbot_notice(self):
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(
                    "https://astrbot.app/notice.json", timeout=2
                ) as resp:
                    return (await resp.json())["notice"]
        except BaseException:
            return ""

    @filter.command("help")
    async def help(self, event: AstrMessageEvent):
        """查看帮助"""
        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except BaseException:
            pass

        dashboard_version = await get_dashboard_version()

        msg = f"""AstrBot v{VERSION}(WebUI: {dashboard_version})
内置指令:
[System]
/plugin: 查看插件、插件帮助
/t2i: 开关文本转图片
/tts: 开关文本转语音
/mcp: 开关MCP工具调用
/sid: 获取会话 ID
/op: 管理员
/wl: 白名单
/dashboard_update: 更新管理面板(op)
/alter_cmd: 设置指令权限(op)

[大模型]
/llm: 开启/关闭 LLM
/provider: 大模型提供商
/model: 模型列表
/ls: 对话列表
/new: 创建新对话
/groupnew 群号: 为群聊创建新对话(op)
/switch 序号: 切换对话
/rename 新名字: 重命名当前对话
/del: 删除当前会话对话(op)
/reset: 重置 LLM 会话
/history: 当前对话的对话记录
/persona: 人格情景(op)
/tool ls: 函数工具
/key: API Key(op)
/websearch: 网页搜索
{notice}"""

        event.set_result(MessageEventResult().message(msg).use_t2i(False))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("llm")
    async def llm(self, event: AstrMessageEvent):
        """开启/关闭 LLM"""
        cfg = self.context.get_config()
        enable = cfg["provider_settings"]["enable"]
        if enable:
            cfg["provider_settings"]["enable"] = False
            status = "关闭"
        else:
            cfg["provider_settings"]["enable"] = True
            status = "开启"
        cfg.save_config()
        yield event.plain_result(f"{status} LLM 聊天功能。")

    @filter.command_group("tool")
    def tool(self):
        pass

    @tool.command("ls")
    async def tool_ls(self, event: AstrMessageEvent):
        """查看函数工具列表"""
        tm = self.context.get_llm_tool_manager()
        msg = "函数工具：\n"
        for tool in tm.func_list:
            active = " (启用)" if tool.active else "(停用)"
            msg += f"- {tool.name}: {tool.description} {active}\n"

        msg += "\n使用 /tool on/off <工具名> 激活或者停用函数工具。/tool off_all 停用所有函数工具。"
        event.set_result(MessageEventResult().message(msg).use_t2i(False))

    @tool.command("on")
    async def tool_on(self, event: AstrMessageEvent, tool_name: str):
        """启用一个函数工具"""
        if self.context.activate_llm_tool(tool_name):
            event.set_result(
                MessageEventResult().message(f"激活工具 {tool_name} 成功。")
            )
        else:
            event.set_result(
                MessageEventResult().message(
                    f"激活工具 {tool_name} 失败，未找到此工具。"
                )
            )

    @tool.command("off")
    async def tool_off(self, event: AstrMessageEvent, tool_name: str):
        """停用一个函数工具"""
        if self.context.deactivate_llm_tool(tool_name):
            event.set_result(
                MessageEventResult().message(f"停用工具 {tool_name} 成功。")
            )
        else:
            event.set_result(
                MessageEventResult().message(
                    f"停用工具 {tool_name} 失败，未找到此工具。"
                )
            )

    @tool.command("off_all")
    async def tool_all_off(self, event: AstrMessageEvent):
        """停用所有函数工具"""
        tm = self.context.get_llm_tool_manager()
        for tool in tm.func_list:
            self.context.deactivate_llm_tool(tool.name)
        event.set_result(MessageEventResult().message("停用所有工具成功。"))

    @filter.command_group("plugin")
    def plugin(self):
        pass

    @plugin.command("ls")
    async def plugin_ls(self, event: AstrMessageEvent):
        """获取已经安装的插件列表。"""
        plugin_list_info = "已加载的插件：\n"
        for plugin in self.context.get_all_stars():
            plugin_list_info += f"- `{plugin.name}` By {plugin.author}: {plugin.desc}"
            if not plugin.activated:
                plugin_list_info += " (未启用)"
            plugin_list_info += "\n"
        if plugin_list_info.strip() == "":
            plugin_list_info = "没有加载任何插件。"

        plugin_list_info += "\n使用 /plugin help <插件名> 查看插件帮助和加载的指令。\n使用 /plugin on/off <插件名> 启用或者禁用插件。"
        event.set_result(
            MessageEventResult().message(f"{plugin_list_info}").use_t2i(False)
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("off")
    async def plugin_off(self, event: AstrMessageEvent, plugin_name: str = None):
        """禁用插件"""
        if DEMO_MODE:
            event.set_result(MessageEventResult().message("演示模式下无法禁用插件。"))
            return
        if not plugin_name:
            event.set_result(
                MessageEventResult().message("/plugin off <插件名> 禁用插件。")
            )
            return
        await self.context._star_manager.turn_off_plugin(plugin_name)
        event.set_result(MessageEventResult().message(f"插件 {plugin_name} 已禁用。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("on")
    async def plugin_on(self, event: AstrMessageEvent, plugin_name: str = None):
        """启用插件"""
        if DEMO_MODE:
            event.set_result(MessageEventResult().message("演示模式下无法启用插件。"))
            return
        if not plugin_name:
            event.set_result(
                MessageEventResult().message("/plugin on <插件名> 启用插件。")
            )
            return
        await self.context._star_manager.turn_on_plugin(plugin_name)
        event.set_result(MessageEventResult().message(f"插件 {plugin_name} 已启用。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("get")
    async def plugin_get(self, event: AstrMessageEvent, plugin_repo: str = None):
        """安装插件"""
        if DEMO_MODE:
            event.set_result(MessageEventResult().message("演示模式下无法安装插件。"))
            return
        if not plugin_repo:
            event.set_result(
                MessageEventResult().message("/plugin get <插件仓库地址> 安装插件")
            )
            return
        logger.info(f"准备从 {plugin_repo} 安装插件。")
        if self.context._star_manager:
            star_mgr: PluginManager = self.context._star_manager
            try:
                await star_mgr.install_plugin(plugin_repo)
                event.set_result(MessageEventResult().message("安装插件成功。"))
            except Exception as e:
                logger.error(f"安装插件失败: {e}")
                event.set_result(MessageEventResult().message(f"安装插件失败: {e}"))
                return

    @plugin.command("help")
    async def plugin_help(self, event: AstrMessageEvent, plugin_name: str = None):
        """获取插件帮助"""
        if not plugin_name:
            event.set_result(
                MessageEventResult().message("/plugin help <插件名> 查看插件信息。")
            )
            return
        plugin = self.context.get_registered_star(plugin_name)
        if plugin is None:
            event.set_result(MessageEventResult().message("未找到此插件。"))
            return
        help_msg = ""
        help_msg += f"\n\n✨ 作者: {plugin.author}\n✨ 版本: {plugin.version}"
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
            help_msg += "\n\n🔧 指令列表：\n"
            for i in range(len(command_handlers)):
                help_msg += f"- {command_names[i]}"
                if command_handlers[i].desc:
                    help_msg += f": {command_handlers[i].desc}"
                help_msg += "\n"

            help_msg += "\nTip: 指令的触发需要添加唤醒前缀，默认为 /。"

        ret = f"🧩 插件 {plugin_name} 帮助信息：\n" + help_msg
        ret += "更多帮助信息请查看插件仓库 README。"
        event.set_result(MessageEventResult().message(ret).use_t2i(False))

    @filter.command("t2i")
    async def t2i(self, event: AstrMessageEvent):
        """开关文本转图片"""
        config = self.context.get_config()
        if config["t2i"]:
            config["t2i"] = False
            config.save_config()
            event.set_result(MessageEventResult().message("已关闭文本转图片模式。"))
            return
        config["t2i"] = True
        config.save_config()
        event.set_result(MessageEventResult().message("已开启文本转图片模式。"))

    @filter.command("tts")
    async def tts(self, event: AstrMessageEvent):
        """开关文本转语音（会话级别）"""
        session_id = event.unified_msg_origin
        current_status = SessionServiceManager.is_tts_enabled_for_session(session_id)

        # 切换状态
        new_status = not current_status
        SessionServiceManager.set_tts_status_for_session(session_id, new_status)

        status_text = "已开启" if new_status else "已关闭"
        event.set_result(
            MessageEventResult().message(f"{status_text}当前会话的文本转语音。")
        )

    @filter.command("sid")
    async def sid(self, event: AstrMessageEvent):
        """获取会话 ID 和 管理员 ID"""
        sid = event.unified_msg_origin
        user_id = str(event.get_sender_id())
        ret = f"""SID: {sid} 此 ID 可用于设置会话白名单。
/wl <SID> 添加白名单, /dwl <SID> 删除白名单。

UID: {user_id} 此 ID 可用于设置管理员。
/op <UID> 授权管理员, /deop <UID> 取消管理员。"""

        if (
            self.context.get_config()["platform_settings"]["unique_session"]
            and event.get_group_id()
        ):
            ret += f"\n\n当前处于独立会话模式, 此群 ID: {event.get_group_id()}, 也可将此 ID 加入白名单来放行整个群聊。"

        event.set_result(MessageEventResult().message(ret).use_t2i(False))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("op")
    async def op(self, event: AstrMessageEvent, admin_id: str = None):
        """授权管理员。op <admin_id>"""
        if admin_id is None:
            event.set_result(
                MessageEventResult().message(
                    "使用方法: /op <id> 授权管理员；/deop <id> 取消管理员。可通过 /sid 获取 ID。"
                )
            )
            return
        self.context.get_config()["admins_id"].append(str(admin_id))
        self.context.get_config().save_config()
        event.set_result(MessageEventResult().message("授权成功。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("deop")
    async def deop(self, event: AstrMessageEvent, admin_id: str):
        """取消授权管理员。deop <admin_id>"""
        try:
            self.context.get_config()["admins_id"].remove(str(admin_id))
            self.context.get_config().save_config()
            event.set_result(MessageEventResult().message("取消授权成功。"))
        except ValueError:
            event.set_result(
                MessageEventResult().message("此用户 ID 不在管理员名单内。")
            )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("wl")
    async def wl(self, event: AstrMessageEvent, sid: str = None):
        """添加白名单。wl <sid>"""
        if sid is None:
            event.set_result(
                MessageEventResult().message(
                    "使用方法: /wl <id> 添加白名单；/dwl <id> 删除白名单。可通过 /sid 获取 ID。"
                )
            )
        self.context.get_config()["platform_settings"]["id_whitelist"].append(str(sid))
        self.context.get_config().save_config()
        event.set_result(MessageEventResult().message("添加白名单成功。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dwl")
    async def dwl(self, event: AstrMessageEvent, sid: str):
        """删除白名单。dwl <sid>"""
        try:
            self.context.get_config()["platform_settings"]["id_whitelist"].remove(
                str(sid)
            )
            self.context.get_config().save_config()
            event.set_result(MessageEventResult().message("删除白名单成功。"))
        except ValueError:
            event.set_result(MessageEventResult().message("此 SID 不在白名单内。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("provider")
    async def provider(
        self, event: AstrMessageEvent, idx: Union[str, int] = None, idx2: int = None
    ):
        """查看或者切换 LLM Provider"""
        umo = event.unified_msg_origin

        if idx is None:
            ret = "## 载入的 LLM 提供商\n"
            for idx, llm in enumerate(self.context.get_all_providers()):
                id_ = llm.meta().id
                ret += f"{idx + 1}. {id_} ({llm.meta().model})"
                provider_using = self.context.get_using_provider(umo=umo)
                if provider_using and provider_using.meta().id == id_:
                    ret += " (当前使用)"
                ret += "\n"

            tts_providers = self.context.get_all_tts_providers()
            if tts_providers:
                ret += "\n## 载入的 TTS 提供商\n"
                for idx, tts in enumerate(tts_providers):
                    id_ = tts.meta().id
                    ret += f"{idx + 1}. {id_}"
                    tts_using = self.context.get_using_tts_provider(umo=umo)
                    if tts_using and tts_using.meta().id == id_:
                        ret += " (当前使用)"
                    ret += "\n"

            stt_providers = self.context.get_all_stt_providers()
            if stt_providers:
                ret += "\n## 载入的 STT 提供商\n"
                for idx, stt in enumerate(stt_providers):
                    id_ = stt.meta().id
                    ret += f"{idx + 1}. {id_}"
                    stt_using = self.context.get_using_stt_provider(umo=umo)
                    if stt_using and stt_using.meta().id == id_:
                        ret += " (当前使用)"
                    ret += "\n"

            ret += "\n使用 /provider <序号> 切换 LLM 提供商。"

            if tts_providers:
                ret += "\n使用 /provider tts <序号> 切换 TTS 提供商。"
            if stt_providers:
                ret += "\n使用 /provider stt <切换> STT 提供商。"

            event.set_result(MessageEventResult().message(ret))
        elif idx == "tts":
            if idx2 is None:
                event.set_result(MessageEventResult().message("请输入序号。"))
                return
            else:
                if idx2 > len(self.context.get_all_tts_providers()) or idx2 < 1:
                    event.set_result(MessageEventResult().message("无效的序号。"))
                provider = self.context.get_all_tts_providers()[idx2 - 1]
                id_ = provider.meta().id
                await self.context.provider_manager.set_provider(
                    provider_id=id_,
                    provider_type=ProviderType.TEXT_TO_SPEECH,
                    umo=umo,
                )
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
                await self.context.provider_manager.set_provider(
                    provider_id=id_,
                    provider_type=ProviderType.SPEECH_TO_TEXT,
                    umo=umo,
                )
                event.set_result(MessageEventResult().message(f"成功切换到 {id_}。"))
        elif isinstance(idx, int):
            if idx > len(self.context.get_all_providers()) or idx < 1:
                event.set_result(MessageEventResult().message("无效的序号。"))

            provider = self.context.get_all_providers()[idx - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.CHAT_COMPLETION,
                umo=umo,
            )
            event.set_result(MessageEventResult().message(f"成功切换到 {id_}。"))
        else:
            event.set_result(MessageEventResult().message("无效的参数。"))

    @filter.command("reset")
    async def reset(self, message: AstrMessageEvent):
        """重置 LLM 会话"""

        # ==============================
        #       读取当前情况和配置
        # ==============================
        is_unique_session = self.context.get_config()["platform_settings"][
            "unique_session"
        ]
        is_group = bool(message.get_group_id())

        scene = RstScene.get_scene(is_group, is_unique_session)

        alter_cmd_cfg = sp.get("alter_cmd", {})
        plugin_config = alter_cmd_cfg.get("astrbot", {})
        reset_cfg = plugin_config.get("reset", {})

        required_perm = reset_cfg.get(
            scene.key, "admin" if is_group and not is_unique_session else "member"
        )

        if required_perm == "admin" and message.role != "admin":
            message.set_result(
                MessageEventResult().message(
                    f"在{scene.name}场景下，reset命令需要管理员权限，"
                    f"您 (ID {message.get_sender_id()}) 不是管理员，无法执行此操作。"
                )
            )
            return

        if not self.context.get_using_provider(message.unified_msg_origin):
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。")
            )
            return

        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type == "dify":
            assert isinstance(provider, ProviderDify)
            await provider.forget(message.unified_msg_origin)
            message.set_result(
                MessageEventResult().message(
                    "已重置当前 Dify 会话，新聊天将更换到新的会话。"
                )
            )
            return

        cid = await self.context.conversation_manager.get_curr_conversation_id(
            message.unified_msg_origin
        )

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "当前未处于对话状态，请 /switch 切换或者 /new 创建。"
                )
            )
            return

        await self.context.conversation_manager.update_conversation(
            message.unified_msg_origin, cid, []
        )

        ret = "清除会话 LLM 聊天历史成功。"
        if self.ltm:
            cnt = await self.ltm.remove_session(event=message)
            ret += f"\n聊天增强: 已清除 {cnt} 条聊天记录。"

        message.set_result(MessageEventResult().message(ret))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("model")
    async def model_ls(
        self, message: AstrMessageEvent, idx_or_name: Union[int, str] = None
    ):
        """查看或者切换模型"""
        prov = self.context.get_using_provider(message.unified_msg_origin)
        if not prov:
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。")
            )
            return
        # 定义正则表达式匹配 API 密钥
        api_key_pattern = re.compile(r"key=[^&'\" ]+")

        if idx_or_name is None:
            models = []
            try:
                models = await prov.get_models()
            except BaseException as e:
                err_msg = api_key_pattern.sub("key=***", str(e))
                message.set_result(
                    MessageEventResult()
                    .message("获取模型列表失败: " + err_msg)
                    .use_t2i(False)
                )
                return
            i = 1
            ret = "下面列出了此服务提供商可用模型:"
            for model in models:
                ret += f"\n{i}. {model}"
                i += 1

            curr_model = prov.get_model() or "无"
            ret += f"\n当前模型: [{curr_model}]"

            ret += "\nTips: 使用 /model <模型名/编号>，即可实时更换模型。如目标模型不存在于上表，请输入模型名。"
            message.set_result(MessageEventResult().message(ret).use_t2i(False))
        else:
            if isinstance(idx_or_name, int):
                models = []
                try:
                    models = await prov.get_models()
                except BaseException as e:
                    message.set_result(
                        MessageEventResult().message("获取模型列表失败: " + str(e))
                    )
                    return
                if idx_or_name > len(models) or idx_or_name < 1:
                    message.set_result(MessageEventResult().message("模型序号错误。"))
                else:
                    try:
                        new_model = models[idx_or_name - 1]
                        prov.set_model(new_model)
                    except BaseException as e:
                        message.set_result(
                            MessageEventResult().message("切换模型未知错误: " + str(e))
                        )
                    message.set_result(MessageEventResult().message("切换模型成功。"))
            else:
                prov.set_model(idx_or_name)
                message.set_result(
                    MessageEventResult().message(f"切换模型到 {prov.get_model()}。")
                )

    @filter.command("history")
    async def his(self, message: AstrMessageEvent, page: int = 1):
        """查看对话记录"""
        if not self.context.get_using_provider(message.unified_msg_origin):
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。")
            )
            return

        size_per_page = 6

        conv_mgr = self.context.conversation_manager
        umo = message.unified_msg_origin
        session_curr_cid = await conv_mgr.get_curr_conversation_id(umo)

        if not session_curr_cid:
            session_curr_cid = await conv_mgr.new_conversation(umo)

        contexts, total_pages = await conv_mgr.get_human_readable_context(
            umo, session_curr_cid, page, size_per_page
        )

        history = ""
        for context in contexts:
            if len(context) > 150:
                context = context[:150] + "..."
            history += f"{context}\n"

        ret = (
            f"当前对话历史记录："
            f"{history if history else '无历史记录'}\n\n"
            f"第 {page} 页 | 共 {total_pages} 页\n"
            f"*输入 /history 2 跳转到第 2 页"
        )

        message.set_result(MessageEventResult().message(ret).use_t2i(False))

    @filter.command("ls")
    async def convs(self, message: AstrMessageEvent, page: int = 1):
        """查看对话列表"""

        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type == "dify":
            """原有的Dify处理逻辑保持不变"""
            ret = "Dify 对话列表:\n"
            assert isinstance(provider, ProviderDify)
            data = await provider.api_client.get_chat_convs(message.unified_msg_origin)
            idx = 1
            for conv in data["data"]:
                ts_h = datetime.datetime.fromtimestamp(conv["updated_at"]).strftime(
                    "%m-%d %H:%M"
                )
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
        conversations_all = await self.context.conversation_manager.get_conversations(
            message.unified_msg_origin
        )
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
                persona_id = self.context.provider_manager.selected_default_persona[
                    "name"
                ]
            title = conv.title if conv.title else "新对话"
            _titles[conv.cid] = title

        """遍历分页后的对话生成列表显示"""
        for conv in conversations_paged:
            persona_id = conv.persona_id
            if not persona_id or persona_id == "[%None]":
                persona_id = self.context.provider_manager.selected_default_persona[
                    "name"
                ]
            title = _titles.get(conv.cid, "新对话")
            ret += f"{global_index}. {title}({conv.cid[:4]})\n  人格情景: {persona_id}\n  上次更新: {datetime.datetime.fromtimestamp(conv.updated_at).strftime('%m-%d %H:%M')}\n"
            global_index += 1

        ret += "---\n"
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
            message.unified_msg_origin
        )
        if curr_cid:
            """从所有对话的标题字典中获取标题"""
            title = _titles.get(curr_cid, "新对话")
            ret += f"\n当前对话: {title}({curr_cid[:4]})"
        else:
            ret += "\n当前对话: 无"

        unique_session = self.context.get_config()["platform_settings"][
            "unique_session"
        ]
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
        """
        创建新对话
        """
        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type == "dify":
            assert isinstance(provider, ProviderDify)
            await provider.forget(message.unified_msg_origin)
            message.set_result(
                MessageEventResult().message("成功，下次聊天将是新对话。")
            )
            return

        cid = await self.context.conversation_manager.new_conversation(
            message.unified_msg_origin
        )

        # 长期记忆
        if self.ltm:
            try:
                await self.ltm.remove_session(event=message)
            except Exception as e:
                logger.error(f"清理聊天增强记录失败: {e}")

        message.set_result(
            MessageEventResult().message(f"切换到新对话: 新对话({cid[:4]})。")
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("groupnew")
    async def groupnew_conv(self, message: AstrMessageEvent, sid: str):
        """创建新群聊对话"""
        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type == "dify":
            assert isinstance(provider, ProviderDify)
            await provider.forget(message.unified_msg_origin)
            message.set_result(
                MessageEventResult().message("成功，下次聊天将是新对话。")
            )
            return
        if sid:
            session = str(
                MessageSesion(
                    platform_name=message.platform_meta.name,
                    message_type=MessageType("GroupMessage"),
                    session_id=sid,
                )
            )
            cid = await self.context.conversation_manager.new_conversation(session)
            message.set_result(
                MessageEventResult().message(
                    f"群聊 {session} 已切换到新对话: 新对话({cid[:4]})。"
                )
            )
        else:
            message.set_result(
                MessageEventResult().message("请输入群聊 ID。/groupnew 群聊ID。")
            )

    @filter.command("switch")
    async def switch_conv(self, message: AstrMessageEvent, index: int = None):
        """通过 /ls 前面的序号切换对话"""

        if not isinstance(index, int):
            message.set_result(
                MessageEventResult().message("类型错误，请输入数字对话序号。")
            )
            return

        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type == "dify":
            assert isinstance(provider, ProviderDify)
            data = await provider.api_client.get_chat_convs(message.unified_msg_origin)
            if not data["data"]:
                message.set_result(MessageEventResult().message("未找到任何对话。"))
                return
            selected_conv = None
            if index is not None:
                try:
                    selected_conv = data["data"][index - 1]
                except IndexError:
                    message.set_result(
                        MessageEventResult().message("对话序号错误，请使用 /ls 查看")
                    )
                    return
            else:
                selected_conv = data["data"][0]
            ret = (
                f"Dify 切换到对话: {selected_conv['name']}({selected_conv['id'][:4]})。"
            )
            provider.conversation_ids[message.unified_msg_origin] = selected_conv["id"]
            message.set_result(MessageEventResult().message(ret))
            return

        if index is None:
            message.set_result(
                MessageEventResult().message(
                    "请输入对话序号。/switch 对话序号。/ls 查看对话 /new 新建对话"
                )
            )
            return
        conversations = await self.context.conversation_manager.get_conversations(
            message.unified_msg_origin
        )
        if index > len(conversations) or index < 1:
            message.set_result(
                MessageEventResult().message("对话序号错误，请使用 /ls 查看")
            )
        else:
            conversation = conversations[index - 1]
            title = conversation.title if conversation.title else "新对话"
            await self.context.conversation_manager.switch_conversation(
                message.unified_msg_origin, conversation.cid
            )
            message.set_result(
                MessageEventResult().message(
                    f"切换到对话: {title}({conversation.cid[:4]})。"
                )
            )

    @filter.command("rename")
    async def rename_conv(self, message: AstrMessageEvent, new_name: str):
        """重命名对话"""
        provider = self.context.get_using_provider(message.unified_msg_origin)

        if provider and provider.meta().type == "dify":
            assert isinstance(provider, ProviderDify)
            cid = provider.conversation_ids.get(message.unified_msg_origin, None)
            if not cid:
                message.set_result(MessageEventResult().message("未找到当前对话。"))
                return
            await provider.api_client.rename(cid, new_name, message.unified_msg_origin)
            message.set_result(MessageEventResult().message("重命名对话成功。"))
            return

        await self.context.conversation_manager.update_conversation_title(
            message.unified_msg_origin, new_name
        )
        message.set_result(MessageEventResult().message("重命名对话成功。"))

    @filter.command("del")
    async def del_conv(self, message: AstrMessageEvent):
        """删除当前对话"""
        is_unique_session = self.context.get_config()["platform_settings"][
            "unique_session"
        ]
        if message.get_group_id() and not is_unique_session and message.role != "admin":
            # 群聊，没开独立会话，发送人不是管理员
            message.set_result(
                MessageEventResult().message(
                    f"会话处于群聊，并且未开启独立会话，并且您 (ID {message.get_sender_id()}) 不是管理员，因此没有权限删除当前对话。"
                )
            )
            return

        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type == "dify":
            assert isinstance(provider, ProviderDify)
            dify_cid = provider.conversation_ids.pop(message.unified_msg_origin, None)
            if dify_cid:
                await provider.api_client.delete_chat_conv(
                    message.unified_msg_origin, dify_cid
                )
            message.set_result(
                MessageEventResult().message(
                    "删除当前对话成功。不再处于对话状态，使用 /switch 序号 切换到其他对话或 /new 创建。"
                )
            )
            return

        session_curr_cid = (
            await self.context.conversation_manager.get_curr_conversation_id(
                message.unified_msg_origin
            )
        )

        if not session_curr_cid:
            message.set_result(
                MessageEventResult().message(
                    "当前未处于对话状态，请 /switch 序号 切换或 /new 创建。"
                )
            )
            return

        await self.context.conversation_manager.delete_conversation(
            message.unified_msg_origin, session_curr_cid
        )
        message.set_result(
            MessageEventResult().message(
                "删除当前对话成功。不再处于对话状态，使用 /switch 序号 切换到其他对话或 /new 创建。"
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("key")
    async def key(self, message: AstrMessageEvent, index: int = None):
        prov = self.context.get_using_provider(message.unified_msg_origin)
        if not prov:
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。")
            )
            return

        if index is None:
            keys_data = prov.get_keys()
            curr_key = prov.get_current_key()
            ret = "Key:"
            for i, k in enumerate(keys_data):
                ret += f"\n{i + 1}. {k[:8]}"

            ret += f"\n当前 Key: {curr_key[:8]}"
            ret += "\n当前模型: " + prov.get_model()
            ret += "\n使用 /key <idx> 切换 Key。"

            message.set_result(MessageEventResult().message(ret).use_t2i(False))
        else:
            keys_data = prov.get_keys()
            if index > len(keys_data) or index < 1:
                message.set_result(MessageEventResult().message("Key 序号错误。"))
            else:
                try:
                    new_key = keys_data[index - 1]
                    prov.set_key(new_key)
                except BaseException as e:
                    message.set_result(
                        MessageEventResult().message("切换 Key 未知错误: " + str(e))
                    )
                message.set_result(MessageEventResult().message("切换 Key 成功。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("persona")
    async def persona(self, message: AstrMessageEvent):
        l = message.message_str.split(" ")  # noqa: E741

        curr_persona_name = "无"
        cid = await self.context.conversation_manager.get_curr_conversation_id(
            message.unified_msg_origin
        )
        curr_cid_title = "无"
        if cid:
            conversation = await self.context.conversation_manager.get_conversation(
                unified_msg_origin=message.unified_msg_origin,
                conversation_id=cid,
                create_if_not_exists=True,
            )
            if not conversation.persona_id and not conversation.persona_id == "[%None]":
                curr_persona_name = (
                    self.context.provider_manager.selected_default_persona["name"]
                )
            else:
                curr_persona_name = conversation.persona_id

            curr_cid_title = conversation.title if conversation.title else "新对话"
            curr_cid_title += f"({cid[:4]})"

        if len(l) == 1:
            message.set_result(
                MessageEventResult()
                .message(
                    f"""[Persona]

- 人格情景列表: `/persona list`
- 设置人格情景: `/persona 人格`
- 人格情景详细信息: `/persona view 人格`
- 取消人格: `/persona unset`

默认人格情景: {self.context.provider_manager.selected_default_persona["name"]}
当前对话 {curr_cid_title} 的人格情景: {curr_persona_name}

配置人格情景请前往管理面板-配置页
"""
                )
                .use_t2i(False)
            )
        elif l[1] == "list":
            msg = "人格列表：\n"
            for persona in self.context.provider_manager.personas:
                msg += f"- {persona['name']}\n"
            msg += "\n\n*输入 `/persona view 人格名` 查看人格详细信息"
            message.set_result(MessageEventResult().message(msg))
        elif l[1] == "view":
            if len(l) == 2:
                message.set_result(MessageEventResult().message("请输入人格情景名"))
                return
            ps = l[2].strip()
            if persona := next(
                builtins.filter(
                    lambda persona: persona["name"] == ps,
                    self.context.provider_manager.personas,
                ),
                None,
            ):
                msg = f"人格{ps}的详细信息：\n"
                msg += f"{persona['prompt']}\n"
            else:
                msg = f"人格{ps}不存在"
            message.set_result(MessageEventResult().message(msg))
        elif l[1] == "unset":
            if not cid:
                message.set_result(
                    MessageEventResult().message("当前没有对话，无法取消人格。")
                )
                return
            await self.context.conversation_manager.update_conversation_persona_id(
                message.unified_msg_origin, "[%None]"
            )
            message.set_result(MessageEventResult().message("取消人格成功。"))
        else:
            ps = "".join(l[1:]).strip()
            if not cid:
                message.set_result(
                    MessageEventResult().message(
                        "当前没有对话，请先开始对话或使用 /new 创建一个对话。"
                    )
                )
                return
            if persona := next(
                builtins.filter(
                    lambda persona: persona["name"] == ps,
                    self.context.provider_manager.personas,
                ),
                None,
            ):
                await self.context.conversation_manager.update_conversation_persona_id(
                    message.unified_msg_origin, ps
                )
                message.set_result(
                    MessageEventResult().message(
                        "设置成功。如果您正在切换到不同的人格，请注意使用 /reset 来清空上下文，防止原人格对话影响现人格。"
                    )
                )
            else:
                message.set_result(
                    MessageEventResult().message(
                        "不存在该人格情景。使用 /persona list 查看所有。"
                    )
                )

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

    @filter.command("gewe_code")
    async def gewe_code(self, event: AstrMessageEvent, code: str):
        """保存 gewechat 验证码"""
        code_path = os.path.join(get_astrbot_data_path(), "temp", "gewe_code")
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)
        yield event.plain_result("验证码已保存。")

    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """群聊记忆增强"""

        has_image_or_plain = False
        for comp in event.message_obj.message:
            if isinstance(comp, Plain) or isinstance(comp, Image):
                has_image_or_plain = True
                break

        if self.ltm and has_image_or_plain:
            need_active = await self.ltm.need_active_reply(event)

            group_icl_enable = self.context.get_config()["provider_ltm_settings"][
                "group_icl_enable"
            ]
            if group_icl_enable:
                """记录对话"""
                try:
                    await self.ltm.handle_message(event)
                except BaseException as e:
                    logger.error(e)

            if need_active:
                """主动回复"""
                provider = self.context.get_using_provider(event.unified_msg_origin)
                if not provider:
                    logger.error("未找到任何 LLM 提供商。请先配置。无法主动回复")
                    return
                try:
                    conv = None
                    if provider.meta().type != "dify":
                        session_curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                            event.unified_msg_origin
                        )

                        if not session_curr_cid:
                            logger.error(
                                "当前未处于对话状态，无法主动回复，请确保 平台设置->会话隔离(unique_session) 未开启，并使用 /switch 序号 切换或者 /new 创建一个会话。"
                            )
                            return

                        conv = await self.context.conversation_manager.get_conversation(
                            event.unified_msg_origin, session_curr_cid
                        )
                    else:
                        # Dify 自己有维护对话，不需要 bot 端维护。
                        assert isinstance(provider, ProviderDify)
                        cid = provider.conversation_ids.get(
                            event.unified_msg_origin, None
                        )
                        if cid is None:
                            logger.error(
                                "[Dify] 当前未处于对话状态，无法主动回复，请确保 平台设置->会话隔离(unique_session) 未开启，并使用 /switch 序号 切换或者 /new 创建一个会话。"
                            )
                            return

                    prompt = self.ltm.ar_prompt
                    if not prompt:
                        prompt = event.message_str

                    yield event.request_llm(
                        prompt=prompt,
                        func_tool_manager=self.context.get_llm_tool_manager(),
                        session_id=event.session_id,
                        conversation=conv,
                    )
                except BaseException as e:
                    logger.error(traceback.format_exc())
                    logger.error(f"主动回复失败: {e}")

    @filter.on_llm_request()
    async def decorate_llm_req(self, event: AstrMessageEvent, req: ProviderRequest):
        """在请求 LLM 前注入人格信息、Identifier、时间、回复内容等 System Prompt"""
        if self.prompt_prefix:
            req.prompt = self.prompt_prefix + req.prompt

        # 解析引用内容
        quote = None
        for comp in event.message_obj.message:
            if isinstance(comp, Reply):
                quote = comp
                break

        if self.identifier:
            user_id = event.message_obj.sender.user_id
            user_nickname = event.message_obj.sender.nickname
            user_info = f"\n[User ID: {user_id}, Nickname: {user_nickname}]\n"
            req.prompt = user_info + req.prompt

        # 启用附加时间戳
        if self.enable_datetime:
            current_time = None
            if self.timezone:
                # 启用时区
                try:
                    now = datetime.datetime.now(zoneinfo.ZoneInfo(self.timezone))
                    current_time = now.strftime("%Y-%m-%d %H:%M (%Z)")
                except Exception as e:
                    logger.error(f"时区设置错误: {e}, 使用本地时区")
            if not current_time:
                current_time = (
                    datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M (%Z)")
                )
            req.system_prompt += f"\nCurrent datetime: {current_time}\n"

        if req.conversation:
            persona_id = req.conversation.persona_id
            if not persona_id and persona_id != "[%None]":  # [%None] 为用户取消人格
                persona_id = self.context.provider_manager.selected_default_persona[
                    "name"
                ]
            persona = next(
                builtins.filter(
                    lambda persona: persona["name"] == persona_id,
                    self.context.provider_manager.personas,
                ),
                None,
            )
            if persona:
                if prompt := persona["prompt"]:
                    req.system_prompt += prompt
                if mood_dialogs := persona["_mood_imitation_dialogs_processed"]:
                    req.system_prompt += "\nHere are few shots of dialogs, you need to imitate the tone of 'B' in the following dialogs to respond:\n"
                    req.system_prompt += mood_dialogs
                if (
                    begin_dialogs := persona["_begin_dialogs_processed"]
                ) and not req.contexts:
                    req.contexts[:0] = begin_dialogs

        if quote:
            sender_info = ""
            if quote.sender_nickname:
                sender_info = f"(Sent by {quote.sender_nickname})"
            message_str = quote.message_str or "[Empty Text]"
            req.system_prompt += (
                f"\nUser is quoting a message{sender_info}.\n"
                f"Here are the information of the quoted message: Text Content: {message_str}.\n"
            )
            image_seg = None
            if quote.chain:
                for comp in quote.chain:
                    if isinstance(comp, Image):
                        image_seg = comp
                        break
            if image_seg:
                try:
                    if prov := self.context.get_using_provider(
                        event.unified_msg_origin
                    ):
                        llm_resp = await prov.text_chat(
                            prompt="Please describe the image content.",
                            image_urls=[await image_seg.convert_to_file_path()],
                        )
                        if llm_resp.completion_text:
                            req.system_prompt += (
                                f"Image Caption: {llm_resp.completion_text}\n"
                            )
                except BaseException as e:
                    logger.error(f"处理引用图片失败: {e}")

        if self.ltm:
            try:
                await self.ltm.on_req_llm(event, req)
            except BaseException as e:
                logger.error(f"ltm: {e}")

    @filter.after_message_sent()
    async def after_llm_req(self, event: AstrMessageEvent):
        """在 LLM 请求后记录对话"""
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
            yield event.plain_result(
                "可设置所有其他指令是否需要管理员权限。\n格式: /alter_cmd <cmd_name> <admin/member>\n 例如: /alter_cmd provider admin 将 provider 设置为管理员指令\n /alter_cmd reset config 打开reset权限配置"
            )
            return

        cmd_name = token.get(1)
        cmd_type = token.get(2)

        # ============================
        #    对reset权限进行特殊处理
        # ============================
        if cmd_name == "reset" and cmd_type == "config":
            alter_cmd_cfg = sp.get("alter_cmd", {})
            plugin_ = alter_cmd_cfg.get("astrbot", {})
            reset_cfg = plugin_.get("reset", {})

            group_unique_on = reset_cfg.get("group_unique_on", "admin")
            group_unique_off = reset_cfg.get("group_unique_off", "admin")
            private = reset_cfg.get("private", "member")

            config_menu = f"""reset命令权限细粒度配置
                当前配置：
                1. 群聊+会话隔离开: {group_unique_on}
                2. 群聊+会话隔离关: {group_unique_off}
                3. 私聊: {private}
                修改指令格式：
                /alter_cmd reset scene <场景编号> <admin/member>
                例如: /alter_cmd reset scene 2 member"""
            yield event.plain_result(config_menu)
            return

        if cmd_name == "reset" and cmd_type == "scene" and token.len >= 4:
            scene_num = token.get(3)
            perm_type = token.get(4)

            if not scene_num.isdigit() or int(scene_num) < 1 or int(scene_num) > 3:
                yield event.plain_result("场景编号必须是1-3之间的数字")
                return

            if perm_type not in ["admin", "member"]:
                yield event.plain_result("权限类型错误，只能是admin或member")
                return

            scene_num = int(scene_num)
            scene = RstScene.from_index(scene_num)
            scene_key = scene.key

            self.update_reset_permission(scene_key, perm_type)

            yield event.plain_result(
                f"已将 reset 命令在{scene.name}场景下的权限设为{perm_type}"
            )
            return

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
            found_command.event_filters.insert(
                0,
                PermissionTypeFilter(
                    filter.PermissionType.ADMIN
                    if cmd_type == "admin"
                    else filter.PermissionType.MEMBER
                ),
            )

        yield event.plain_result(f"已将 {cmd_name} 设置为 {cmd_type} 指令")

    def update_reset_permission(self, scene_key: str, perm_type: str):
        """更新reset命令在特定场景下的权限设置

        Args:
            scene_key (str): 场景编号，1-3
            perm_type (str): 权限类型，admin或member
        """
        alter_cmd_cfg = sp.get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get("astrbot", {})
        reset_cfg = plugin_cfg.get("reset", {})
        reset_cfg[scene_key] = perm_type
        plugin_cfg["reset"] = reset_cfg
        alter_cmd_cfg["astrbot"] = plugin_cfg
        sp.put("alter_cmd", alter_cmd_cfg)
