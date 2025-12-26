from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter

from .commands import (
    AdminCommands,
    AlterCmdCommands,
    ConversationCommands,
    HelpCommand,
    LLMCommands,
    PersonaCommands,
    PluginCommands,
    ProviderCommands,
    SetUnsetCommands,
    SIDCommand,
    T2ICommand,
    ToolCommands,
    TTSCommand,
)


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context

        self.help_c = HelpCommand(self.context)
        self.llm_c = LLMCommands(self.context)
        self.tool_c = ToolCommands(self.context)
        self.plugin_c = PluginCommands(self.context)
        self.admin_c = AdminCommands(self.context)
        self.conversation_c = ConversationCommands(self.context)
        self.provider_c = ProviderCommands(self.context)
        self.persona_c = PersonaCommands(self.context)
        self.alter_cmd_c = AlterCmdCommands(self.context)
        self.setunset_c = SetUnsetCommands(self.context)
        self.t2i_c = T2ICommand(self.context)
        self.tts_c = TTSCommand(self.context)
        self.sid_c = SIDCommand(self.context)

    @filter.command("help")
    async def help(self, event: AstrMessageEvent):
        """查看帮助"""
        await self.help_c.help(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("llm")
    async def llm(self, event: AstrMessageEvent):
        """开启/关闭 LLM"""
        await self.llm_c.llm(event)

    @filter.command_group("tool")
    def tool(self):
        """函数工具管理"""

    @tool.command("ls")
    async def tool_ls(self, event: AstrMessageEvent):
        """查看函数工具列表"""
        await self.tool_c.tool_ls(event)

    @tool.command("on")
    async def tool_on(self, event: AstrMessageEvent, tool_name: str):
        """启用一个函数工具"""
        await self.tool_c.tool_on(event, tool_name)

    @tool.command("off")
    async def tool_off(self, event: AstrMessageEvent, tool_name: str):
        """停用一个函数工具"""
        await self.tool_c.tool_off(event, tool_name)

    @tool.command("off_all")
    async def tool_all_off(self, event: AstrMessageEvent):
        """停用所有函数工具"""
        await self.tool_c.tool_all_off(event)

    @filter.command_group("plugin")
    def plugin(self):
        """插件管理"""

    @plugin.command("ls")
    async def plugin_ls(self, event: AstrMessageEvent):
        """获取已经安装的插件列表。"""
        await self.plugin_c.plugin_ls(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("off")
    async def plugin_off(self, event: AstrMessageEvent, plugin_name: str = ""):
        """禁用插件"""
        await self.plugin_c.plugin_off(event, plugin_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("on")
    async def plugin_on(self, event: AstrMessageEvent, plugin_name: str = ""):
        """启用插件"""
        await self.plugin_c.plugin_on(event, plugin_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("get")
    async def plugin_get(self, event: AstrMessageEvent, plugin_repo: str = ""):
        """安装插件"""
        await self.plugin_c.plugin_get(event, plugin_repo)

    @plugin.command("help")
    async def plugin_help(self, event: AstrMessageEvent, plugin_name: str = ""):
        """获取插件帮助"""
        await self.plugin_c.plugin_help(event, plugin_name)

    @filter.command("t2i")
    async def t2i(self, event: AstrMessageEvent):
        """开关文本转图片"""
        await self.t2i_c.t2i(event)

    @filter.command("tts")
    async def tts(self, event: AstrMessageEvent):
        """开关文本转语音（会话级别）"""
        await self.tts_c.tts(event)

    @filter.command("sid")
    async def sid(self, event: AstrMessageEvent):
        """获取会话 ID 和 管理员 ID"""
        await self.sid_c.sid(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("op")
    async def op(self, event: AstrMessageEvent, admin_id: str = ""):
        """授权管理员。op <admin_id>"""
        await self.admin_c.op(event, admin_id)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("deop")
    async def deop(self, event: AstrMessageEvent, admin_id: str):
        """取消授权管理员。deop <admin_id>"""
        await self.admin_c.deop(event, admin_id)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("wl")
    async def wl(self, event: AstrMessageEvent, sid: str = ""):
        """添加白名单。wl <sid>"""
        await self.admin_c.wl(event, sid)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dwl")
    async def dwl(self, event: AstrMessageEvent, sid: str):
        """删除白名单。dwl <sid>"""
        await self.admin_c.dwl(event, sid)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("provider")
    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ):
        """查看或者切换 LLM Provider"""
        await self.provider_c.provider(event, idx, idx2)

    @filter.command("reset")
    async def reset(self, message: AstrMessageEvent):
        """重置 LLM 会话"""
        await self.conversation_c.reset(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("model")
    async def model_ls(
        self,
        message: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ):
        """查看或者切换模型"""
        await self.provider_c.model_ls(message, idx_or_name)

    @filter.command("history")
    async def his(self, message: AstrMessageEvent, page: int = 1):
        """查看对话记录"""
        await self.conversation_c.his(message, page)

    @filter.command("ls")
    async def convs(self, message: AstrMessageEvent, page: int = 1):
        """查看对话列表"""
        await self.conversation_c.convs(message, page)

    @filter.command("new")
    async def new_conv(self, message: AstrMessageEvent):
        """创建新对话"""
        await self.conversation_c.new_conv(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("groupnew")
    async def groupnew_conv(self, message: AstrMessageEvent, sid: str):
        """创建新群聊对话"""
        await self.conversation_c.groupnew_conv(message, sid)

    @filter.command("switch")
    async def switch_conv(self, message: AstrMessageEvent, index: int | None = None):
        """通过 /ls 前面的序号切换对话"""
        await self.conversation_c.switch_conv(message, index)

    @filter.command("rename")
    async def rename_conv(self, message: AstrMessageEvent, new_name: str):
        """重命名对话"""
        await self.conversation_c.rename_conv(message, new_name)

    @filter.command("del")
    async def del_conv(self, message: AstrMessageEvent):
        """删除当前对话"""
        await self.conversation_c.del_conv(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("key")
    async def key(self, message: AstrMessageEvent, index: int | None = None):
        """查看或者切换 Key"""
        await self.provider_c.key(message, index)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("persona")
    async def persona(self, message: AstrMessageEvent):
        """查看或者切换 Persona"""
        await self.persona_c.persona(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dashboard_update")
    async def update_dashboard(self, event: AstrMessageEvent):
        """更新管理面板"""
        await self.admin_c.update_dashboard(event)

    @filter.command("set")
    async def set_variable(self, event: AstrMessageEvent, key: str, value: str):
        await self.setunset_c.set_variable(event, key, value)

    @filter.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str):
        await self.setunset_c.unset_variable(event, key)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("alter_cmd", alias={"alter"})
    async def alter_cmd(self, event: AstrMessageEvent):
        """修改命令权限"""
        await self.alter_cmd_c.alter_cmd(event)
