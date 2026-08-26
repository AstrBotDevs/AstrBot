from typing import Annotated

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import GreedyStr, option

from .commands import (
    AdminCommands,
    BotCommands,
    ChatCommands,
    ConversationCommands,
    FlowCommands,
    HelpCommand,
    PersonaCommands,
    PluginCommands,
    ProviderCommands,
    SessionCommands,
    VariableCommands,
)


class Main(star.Star):
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

        self.admin_c = AdminCommands(self.context)
        self.bot_c = BotCommands(self.context)
        self.chat_c = ChatCommands(self.context)
        self.conversation_c = ConversationCommands(self.context)
        self.flow_c = FlowCommands(self.context)
        self.help_c = HelpCommand(self.context)
        self.persona_c = PersonaCommands(self.context)
        self.plugin_c = PluginCommands(self.context)
        self.provider_c = ProviderCommands(self.context)
        self.session_c = SessionCommands(self.context)
        self.variable_c = VariableCommands(self.context)

    @filter.command("help")
    async def help(
        self,
        event: AstrMessageEvent,
        image: Annotated[bool, option("--image", "-i")] = False,
    ) -> None:
        """Show help for enabled built-in commands"""
        await self.help_c.help(event, image=image)

    @filter.command_group("bot")
    def bot(self) -> None:
        """Manage bot presence in the current session"""

    @filter.permission("session.read")
    @bot.command("status")
    async def bot_status(self, event: AstrMessageEvent) -> None:
        """Show version and session, LLM, and TTS switches"""
        await self.bot_c.status(event)

    @filter.permission("session.manage")
    @bot.command("enable")
    async def bot_enable(self, event: AstrMessageEvent) -> None:
        """Enable the current session"""
        await self.bot_c.set_enabled(event, True)

    @filter.permission("session.manage")
    @bot.command("disable")
    async def bot_disable(self, event: AstrMessageEvent) -> None:
        """Disable the current session"""
        await self.bot_c.set_enabled(event, False)

    @filter.permission("session.manage")
    @bot.command("leave")
    async def bot_leave(
        self,
        event: AstrMessageEvent,
        confirm: Annotated[bool, option("--confirm", "-c")] = False,
    ) -> None:
        """Leave the current group after confirmation"""
        await self.bot_c.leave(event, confirm=confirm)

    @filter.command_group("session")
    def session(self) -> None:
        """Manage the current message session"""

    @filter.permission("session.read")
    @session.command("info")
    async def session_info(self, event: AstrMessageEvent) -> None:
        """Show IDs and metadata for the current session"""
        await self.session_c.info(event)

    @filter.permission("session.manage")
    @session.command("name")
    async def session_name(
        self, event: AstrMessageEvent, alias: GreedyStr = GreedyStr("")
    ) -> None:
        """Show or set the display name for the current session"""
        await self.session_c.name(event, alias)

    @filter.command_group("conversation")
    def conversation(self) -> None:
        """Manage conversations"""

    @filter.permission("session.manage")
    @conversation.command("reset")
    async def conversation_reset(self, message: AstrMessageEvent) -> None:
        """Reset conversation history"""
        await self.conversation_c.reset(message)

    @filter.command_group("task")
    def task(self) -> None:
        """Manage running tasks"""

    @filter.permission("session.manage")
    @task.command("stop")
    async def task_stop(self, message: AstrMessageEvent) -> None:
        """Stop running tasks in the current session"""
        await self.conversation_c.stop(message)

    @filter.permission("session.manage")
    @conversation.command("create")
    async def conversation_create(self, message: AstrMessageEvent) -> None:
        """Create a new conversation"""
        await self.conversation_c.create(message)

    @filter.permission("session.read")
    @conversation.command("stats")
    async def conversation_stats(self, message: AstrMessageEvent) -> None:
        """Show token usage for the current conversation"""
        await self.conversation_c.stats(message)

    @filter.permission("session.read")
    @conversation.command("history")
    async def conversation_history(
        self,
        event: AstrMessageEvent,
        page: Annotated[int, option("--page", "-p")] = 1,
    ) -> None:
        """Show conversation history"""
        await self.conversation_c.history(event, page)

    @filter.permission("session.read")
    @conversation.command("list")
    async def conversation_list(
        self,
        event: AstrMessageEvent,
        page: Annotated[int, option("--page", "-p")] = 1,
    ) -> None:
        """List conversations"""
        await self.conversation_c.list_conversations(event, page)

    @filter.permission("session.assign")
    @conversation.command("create-for")
    async def conversation_create_for(
        self, event: AstrMessageEvent, session_id: str
    ) -> None:
        """Create a conversation for a target group session"""
        await self.conversation_c.create_for(event, session_id)

    @filter.permission("session.manage")
    @conversation.command("switch")
    async def conversation_switch(self, event: AstrMessageEvent, index: int) -> None:
        """Switch to a listed conversation"""
        await self.conversation_c.switch(event, index)

    @filter.permission("session.manage")
    @conversation.command("rename")
    async def conversation_rename(
        self,
        event: AstrMessageEvent,
        title: GreedyStr,
    ) -> None:
        """Rename the current conversation"""
        await self.conversation_c.rename(event, title)

    @filter.permission("session.manage")
    @conversation.command("delete")
    async def conversation_delete(self, event: AstrMessageEvent) -> None:
        """Delete the current conversation"""
        await self.conversation_c.delete(event)

    @filter.command_group("provider")
    def provider(self) -> None:
        """Manage providers"""

    @filter.permission("provider.read")
    @provider.command("list")
    async def provider_list(self, event: AstrMessageEvent) -> None:
        """List configured providers"""
        await self.provider_c.list_providers(event)

    @provider.group("set")
    def provider_set(self) -> None:
        """Select a provider by capability"""

    @filter.permission("provider.use")
    @provider_set.command("llm")
    async def provider_set_llm(self, event: AstrMessageEvent, index: int) -> None:
        """Switch the LLM provider"""
        await self.provider_c.set_llm_provider(event, index)

    @filter.permission("provider.use")
    @provider_set.command("tts")
    async def provider_set_tts(self, event: AstrMessageEvent, index: int) -> None:
        """Switch the TTS provider"""
        await self.provider_c.set_tts_provider(event, index)

    @filter.permission("provider.use")
    @provider_set.command("stt")
    async def provider_set_stt(self, event: AstrMessageEvent, index: int) -> None:
        """Switch the STT provider"""
        await self.provider_c.set_stt_provider(event, index)

    @filter.command_group("model")
    def model(self) -> None:
        """Manage models"""

    @filter.permission("provider.read")
    @model.command("list")
    async def model_list(self, event: AstrMessageEvent) -> None:
        """List models for the current provider"""
        await self.provider_c.list_models(event)

    @filter.permission("provider.use")
    @model.command("set")
    async def model_set(
        self, event: AstrMessageEvent, model_or_index: GreedyStr
    ) -> None:
        """Switch the current model"""
        await self.provider_c.set_model(event, model_or_index)

    @filter.command_group("variable")
    def variable(self) -> None:
        """Manage session variables"""

    @filter.permission("session.manage")
    @variable.command("set")
    async def variable_set(self, event: AstrMessageEvent, key: str, value: str) -> None:
        """Set a session variable"""
        await self.variable_c.set_variable(event, key, value)

    @filter.permission("session.manage")
    @variable.command("unset")
    async def variable_unset(self, event: AstrMessageEvent, key: str) -> None:
        """Remove a session variable"""
        await self.variable_c.unset_variable(event, key)

    @filter.command_group("llm")
    def llm(self) -> None:
        """Manage LLM chat for the current session"""

    @filter.permission("session.manage")
    @llm.command("status")
    async def llm_status(self, event: AstrMessageEvent) -> None:
        """Show whether LLM chat is enabled"""
        await self.chat_c.status(event)

    @filter.permission("session.manage")
    @llm.command("enable")
    async def llm_enable(self, event: AstrMessageEvent) -> None:
        """Enable LLM chat for the current session"""
        await self.chat_c.set_enabled(event, True)

    @filter.permission("session.manage")
    @llm.command("disable")
    async def llm_disable(self, event: AstrMessageEvent) -> None:
        """Disable LLM chat for the current session"""
        await self.chat_c.set_enabled(event, False)

    @filter.command_group("flow")
    def flow(self) -> None:
        """Manage session streaming override"""

    @filter.permission("session.manage")
    @flow.command("enable")
    async def flow_enable(self, event: AstrMessageEvent) -> None:
        """Force streaming for the current session"""
        await self.flow_c.set_override(event, True)

    @filter.permission("session.manage")
    @flow.command("disable")
    async def flow_disable(self, event: AstrMessageEvent) -> None:
        """Force non-streaming for the current session"""
        await self.flow_c.set_override(event, False)

    @filter.permission("session.manage")
    @flow.command("unset")
    async def flow_unset(self, event: AstrMessageEvent) -> None:
        """Remove the session streaming override"""
        await self.flow_c.unset(event)

    @filter.permission("session.manage")
    @flow.command("status")
    async def flow_status(self, event: AstrMessageEvent) -> None:
        """Show the session streaming override"""
        await self.flow_c.status(event)

    @filter.command_group("admin")
    def admin(self) -> None:
        """Manage administrators"""

    @filter.permission("identity.manage")
    @admin.command("list")
    async def admin_list(self, event: AstrMessageEvent) -> None:
        """List administrator IDs"""
        await self.admin_c.list_admins(event)

    @filter.permission("identity.manage")
    @admin.command("grant")
    async def admin_grant(self, event: AstrMessageEvent, user_id: str) -> None:
        """Grant administrator permission"""
        await self.admin_c.grant(event, user_id)

    @filter.permission("identity.manage")
    @admin.command("revoke")
    async def admin_revoke(self, event: AstrMessageEvent, user_id: str) -> None:
        """Revoke administrator permission"""
        await self.admin_c.revoke(event, user_id)

    @filter.command_group("persona")
    def persona(self) -> None:
        """Manage personas"""

    @filter.permission("agent.manage")
    @persona.command("status")
    async def persona_status(self, event: AstrMessageEvent) -> None:
        """Show the current persona"""
        await self.persona_c.status(event)

    @filter.permission("agent.manage")
    @persona.command("list")
    async def persona_list(self, event: AstrMessageEvent) -> None:
        """List personas"""
        await self.persona_c.list_personas(event)

    @filter.permission("agent.manage")
    @persona.command("set")
    async def persona_set(self, event: AstrMessageEvent, persona_id: GreedyStr) -> None:
        """Set the current conversation persona"""
        await self.persona_c.set_persona(event, persona_id)

    @filter.permission("agent.manage")
    @persona.command("show")
    async def persona_show(
        self, event: AstrMessageEvent, persona_id: GreedyStr
    ) -> None:
        """View persona details"""
        await self.persona_c.show(event, persona_id)

    @filter.permission("agent.manage")
    @persona.command("unset")
    async def persona_unset(self, event: AstrMessageEvent) -> None:
        """Unset the current conversation persona"""
        await self.persona_c.unset(event)

    @filter.command_group("plugin")
    def plugin(self) -> None:
        """Plugin management"""

    @filter.permission("extension.read")
    @plugin.command("list")
    async def plugin_list(self, event: AstrMessageEvent) -> None:
        """List loaded plugins"""
        await self.plugin_c.list_plugins(event)

    @filter.permission("extension.manage")
    @plugin.command("disable")
    async def plugin_disable(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Disable a plugin"""
        await self.plugin_c.disable(event, plugin_name)

    @filter.permission("extension.manage")
    @plugin.command("enable")
    async def plugin_enable(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Enable a plugin"""
        await self.plugin_c.enable(event, plugin_name)

    @filter.permission("extension.plugin_install")
    @plugin.command("install")
    async def plugin_install(
        self, event: AstrMessageEvent, repository_url: str
    ) -> None:
        """Install a plugin"""
        await self.plugin_c.install(event, repository_url)

    @filter.permission("extension.read")
    @plugin.command("show")
    async def plugin_show(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Show plugin help"""
        await self.plugin_c.show(event, plugin_name)
