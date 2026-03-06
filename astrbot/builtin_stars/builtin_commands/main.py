from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.core.extensions import InstallResultStatus
from astrbot.core.extensions.runtime import get_extension_orchestrator
from astrbot.core.star.filter.command import GreedyStr

from .commands import (
    AdminCommands,
    AlterCmdCommands,
    ConversationCommands,
    ExtensionCommands,
    HelpCommand,
    LLMCommands,
    PersonaCommands,
    PluginCommands,
    ProviderCommands,
    SetUnsetCommands,
    SIDCommand,
    T2ICommand,
    TTSCommand,
)


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context

        self.help_c = HelpCommand(self.context)
        self.llm_c = LLMCommands(self.context)
        self.plugin_c = PluginCommands(self.context)
        self.admin_c = AdminCommands(self.context)
        self.conversation_c = ConversationCommands(self.context)
        self.provider_c = ProviderCommands(self.context)
        self.persona_c = PersonaCommands(self.context)
        self.extension_c = ExtensionCommands(self.context)
        self.alter_cmd_c = AlterCmdCommands(self.context)
        self.setunset_c = SetUnsetCommands(self.context)
        self.t2i_c = T2ICommand(self.context)
        self.tts_c = TTSCommand(self.context)
        self.sid_c = SIDCommand(self.context)

    def _get_extension_confirm_keywords(self) -> tuple[str, str]:
        config = self.context.get_config()
        provider_settings = config.get("provider_settings", {})
        extension_cfg = provider_settings.get("extension_install", {})
        keywords = extension_cfg.get("confirm_keywords", [])
        if isinstance(keywords, list) and len(keywords) >= 2:
            confirm_keyword = str(keywords[0]).strip() or "确认安装"
            deny_keyword = str(keywords[1]).strip() or "拒绝安装"
            return confirm_keyword, deny_keyword
        return "确认安装", "拒绝安装"

    @staticmethod
    def _normalize_intent_text(raw_text: str) -> str:
        text = raw_text.lower()
        for ch in [",", ".", "!", "?", "，", "。", "！", "？", "；", ";", "：", ":"]:
            text = text.replace(ch, " ")
        return " ".join(text.split())

    @staticmethod
    def _contains_intent_word(normalized: str, word: str) -> bool:
        if not word:
            return False
        is_ascii_word = all(
            ch.isascii() and (ch.isalnum() or ch in {"_", "-"}) for ch in word
        )
        if not is_ascii_word:
            return word in normalized
        parts = normalized.split()
        return word in parts

    def _detect_install_intent(self, raw_text: str) -> str | None:
        normalized = self._normalize_intent_text(raw_text)
        confirm_keyword, deny_keyword = self._get_extension_confirm_keywords()

        deny_words = {
            deny_keyword.lower(),
            "deny",
            "denied",
            "reject",
            "rejected",
            "cancel",
            "abort",
            "stop",
            "no",
            "refuse",
            "拒绝",
            "取消",
            "不要",
            "不同意",
            "否认",
            "停止",
        }
        confirm_words = {
            confirm_keyword.lower(),
            "confirm",
            "confirmed",
            "approve",
            "approved",
            "accept",
            "accepted",
            "allow",
            "proceed",
            "yes",
            "ok",
            "okay",
            "sure",
            "确认",
            "同意",
            "批准",
            "允许",
            "继续",
            "可以",
            "好的",
            "行",
        }
        if any(self._contains_intent_word(normalized, word) for word in deny_words):
            return "deny"
        if any(self._contains_intent_word(normalized, word) for word in confirm_words):
            return "confirm"
        return None

    def _is_install_confirmation_candidate_message(self, raw_text: str) -> bool:
        if raw_text.startswith("/"):
            return False
        return self._detect_install_intent(raw_text) is not None

    @filter.command("help")
    async def help(self, event: AstrMessageEvent) -> None:
        """查看帮助"""
        await self.help_c.help(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("llm")
    async def llm(self, event: AstrMessageEvent) -> None:
        """开启/关闭 LLM"""
        await self.llm_c.llm(event)

    @filter.command_group("plugin")
    def plugin(self) -> None:
        """插件管理"""

    @plugin.command("ls")
    async def plugin_ls(self, event: AstrMessageEvent) -> None:
        """获取已经安装的插件列表。"""
        await self.plugin_c.plugin_ls(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("off")
    async def plugin_off(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """禁用插件"""
        await self.plugin_c.plugin_off(event, plugin_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("on")
    async def plugin_on(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """启用插件"""
        await self.plugin_c.plugin_on(event, plugin_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("get")
    async def plugin_get(self, event: AstrMessageEvent, plugin_repo: str = "") -> None:
        """安装插件"""
        await self.plugin_c.plugin_get(event, plugin_repo)

    @plugin.command("help")
    async def plugin_help(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """获取插件帮助"""
        await self.plugin_c.plugin_help(event, plugin_name)

    @filter.command_group("extend")
    def extend(self) -> None:
        """能力扩展管理"""

    @filter.permission_type(filter.PermissionType.ADMIN)
    @extend.command("search")
    async def extend_search(
        self, event: AstrMessageEvent, query: GreedyStr = ""
    ) -> None:
        """搜索可安装扩展"""
        await self.extension_c.extend_search(event, query)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @extend.command("install")
    async def extend_install(
        self, event: AstrMessageEvent, target: GreedyStr = ""
    ) -> None:
        """安装扩展"""
        await self.extension_c.extend_install(event, target)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @extend.command("confirm")
    async def extend_confirm(
        self, event: AstrMessageEvent, operation_id_or_token: str = ""
    ) -> None:
        """确认安装待办"""
        await self.extension_c.extend_confirm(event, operation_id_or_token)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @extend.command("deny")
    async def extend_deny(
        self, event: AstrMessageEvent, operation_id_or_token: str = ""
    ) -> None:
        """拒绝安装待办"""
        await self.extension_c.extend_deny(event, operation_id_or_token)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @extend.command("pending")
    async def extend_pending(self, event: AstrMessageEvent, kind: str = "") -> None:
        """查看安装待确认列表"""
        await self.extension_c.extend_pending(event, kind)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.regex(r"^.+$")
    async def handle_install_confirmation_intent(self, event: AstrMessageEvent) -> None:
        """Natural-language intent based install confirmation/rejection."""
        message = event.get_message_str().strip()
        if not self._is_install_confirmation_candidate_message(message):
            return
        intent = self._detect_install_intent(message)
        orchestrator = get_extension_orchestrator(self.context)
        if intent == "confirm":
            result = await orchestrator.confirm_for_conversation(
                conversation_id=event.unified_msg_origin,
                actor_id=event.get_sender_id(),
                actor_role=event.role,
            )
            if result.status == InstallResultStatus.SUCCESS:
                event.set_result(
                    MessageEventResult().message(
                        "Confirmation accepted, install completed."
                    )
                )
            elif result.status != InstallResultStatus.FAILED:
                event.set_result(
                    MessageEventResult().message(
                        f"Confirmation denied: {result.message}"
                    )
                )
        elif intent == "deny":
            result = await orchestrator.deny_for_conversation(
                conversation_id=event.unified_msg_origin,
                actor_id=event.get_sender_id(),
                actor_role=event.role,
                reason="rejected by chat confirmation",
            )
            if result.status == InstallResultStatus.DENIED:
                event.set_result(
                    MessageEventResult().message("Install operation rejected.")
                )

    @filter.command("t2i")
    async def t2i(self, event: AstrMessageEvent) -> None:
        """开关文本转图片"""
        await self.t2i_c.t2i(event)

    @filter.command("tts")
    async def tts(self, event: AstrMessageEvent) -> None:
        """开关文本转语音（会话级别）"""
        await self.tts_c.tts(event)

    @filter.command("sid")
    async def sid(self, event: AstrMessageEvent) -> None:
        """获取会话 ID 和 管理员 ID"""
        await self.sid_c.sid(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("op")
    async def op(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """授权管理员。op <admin_id>"""
        await self.admin_c.op(event, admin_id)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("deop")
    async def deop(self, event: AstrMessageEvent, admin_id: str) -> None:
        """取消授权管理员。deop <admin_id>"""
        await self.admin_c.deop(event, admin_id)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("wl")
    async def wl(self, event: AstrMessageEvent, sid: str = "") -> None:
        """添加白名单。wl <sid>"""
        await self.admin_c.wl(event, sid)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dwl")
    async def dwl(self, event: AstrMessageEvent, sid: str) -> None:
        """删除白名单。dwl <sid>"""
        await self.admin_c.dwl(event, sid)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("provider")
    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ) -> None:
        """查看或者切换 LLM Provider"""
        await self.provider_c.provider(event, idx, idx2)

    @filter.command("reset")
    async def reset(self, message: AstrMessageEvent) -> None:
        """重置 LLM 会话"""
        await self.conversation_c.reset(message)

    @filter.command("stop")
    async def stop(self, message: AstrMessageEvent) -> None:
        """停止当前会话中正在运行的 Agent"""
        await self.conversation_c.stop(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("model")
    async def model_ls(
        self,
        message: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ) -> None:
        """查看或者切换模型"""
        await self.provider_c.model_ls(message, idx_or_name)

    @filter.command("history")
    async def his(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话记录"""
        await self.conversation_c.his(message, page)

    @filter.command("ls")
    async def convs(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话列表"""
        await self.conversation_c.convs(message, page)

    @filter.command("new")
    async def new_conv(self, message: AstrMessageEvent) -> None:
        """创建新对话"""
        await self.conversation_c.new_conv(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("groupnew")
    async def groupnew_conv(self, message: AstrMessageEvent, sid: str) -> None:
        """创建新群聊对话"""
        await self.conversation_c.groupnew_conv(message, sid)

    @filter.command("switch")
    async def switch_conv(
        self, message: AstrMessageEvent, index: int | None = None
    ) -> None:
        """通过 /ls 前面的序号切换对话"""
        await self.conversation_c.switch_conv(message, index)

    @filter.command("rename")
    async def rename_conv(self, message: AstrMessageEvent, new_name: str) -> None:
        """重命名对话"""
        await self.conversation_c.rename_conv(message, new_name)

    @filter.command("del")
    async def del_conv(self, message: AstrMessageEvent) -> None:
        """删除当前对话"""
        await self.conversation_c.del_conv(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("key")
    async def key(self, message: AstrMessageEvent, index: int | None = None) -> None:
        """查看或者切换 Key"""
        await self.provider_c.key(message, index)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("persona")
    async def persona(self, message: AstrMessageEvent) -> None:
        """查看或者切换 Persona"""
        await self.persona_c.persona(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dashboard_update")
    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """更新管理面板"""
        await self.admin_c.update_dashboard(event)

    @filter.command("set")
    async def set_variable(self, event: AstrMessageEvent, key: str, value: str) -> None:
        await self.setunset_c.set_variable(event, key, value)

    @filter.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str) -> None:
        await self.setunset_c.unset_variable(event, key)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("alter_cmd", alias={"alter"})
    async def alter_cmd(self, event: AstrMessageEvent) -> None:
        """修改命令权限"""
        await self.alter_cmd_c.alter_cmd(event)
