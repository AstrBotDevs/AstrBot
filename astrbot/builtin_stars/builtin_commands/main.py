from typing import Annotated

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import GreedyStr, option

from .commands import (
    AdminCommands,
    ChatCommands,
    ConversationCommands,
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
        self.chat_c = ChatCommands(self.context)
        self.conversation_c = ConversationCommands(self.context)
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
        """Show help message"""
        await self.help_c.help(event, image=image)

    @filter.command_group("session")
    def session(self) -> None:
        """Manage the current message session"""

    @filter.permission("session.read")
    @session.command("info")
    async def sid(self, event: AstrMessageEvent) -> None:
        """Show IDs and metadata for the current session"""
        await self.session_c.info(event)

    @filter.permission("session.manage")
    @session.command("name")
    async def name(
        self, event: AstrMessageEvent, alias: GreedyStr = GreedyStr("")
    ) -> None:
        """Show or set the display name for the current session"""
        await self.session_c.name(event, alias)

    @filter.command_group("conversation")
    def conversation(self) -> None:
        """Manage conversations"""

    @filter.permission("session.manage")
    @conversation.command("reset")
    async def reset(self, message: AstrMessageEvent) -> None:
        """Reset conversation history"""
        await self.conversation_c.reset(message)

    @filter.command_group("task")
    def task(self) -> None:
        """Manage running tasks"""

    @filter.permission("session.manage")
    @task.command("stop")
    async def stop(self, message: AstrMessageEvent) -> None:
        """Stop running tasks in the current session"""
        await self.conversation_c.stop(message)

    @filter.permission("session.manage")
    @conversation.command("create")
    async def new_conv(self, message: AstrMessageEvent) -> None:
        """Create new conversation"""
        await self.conversation_c.create(message)

    @filter.permission("session.read")
    @conversation.command("stats")
    async def stats(self, message: AstrMessageEvent) -> None:
        """Show token usage statistics for the current conversation"""
        await self.conversation_c.stats(message)

    @filter.permission("session.read")
    @conversation.command("history")
    async def history(
        self,
        event: AstrMessageEvent,
        page: Annotated[int, option("--page", "-p")] = 1,
    ) -> None:
        """Show conversation history"""
        await self.conversation_c.history(event, page)

    @filter.permission("session.read")
    @conversation.command("list")
    async def convs(
        self,
        event: AstrMessageEvent,
        page: Annotated[int, option("--page", "-p")] = 1,
    ) -> None:
        """List conversations"""
        await self.conversation_c.list_conversations(event, page)

    @conversation.command("create-for")
    async def groupnew(self, event: AstrMessageEvent, session_id: str) -> None:
        """Create a conversation for a target group session"""
        await self.conversation_c.create_for(event, session_id)

    @filter.permission("session.manage")
    @conversation.command("switch")
    async def switch(self, event: AstrMessageEvent, index: int) -> None:
        """Switch to a listed conversation"""
        await self.conversation_c.switch(event, index)

    @filter.permission("session.manage")
    @conversation.command("rename")
    async def rename(
        self,
        event: AstrMessageEvent,
        title: GreedyStr,
    ) -> None:
        """Rename the current conversation"""
        await self.conversation_c.rename(event, title)

    @filter.permission("session.manage")
    @conversation.command("delete")
    async def delete(self, event: AstrMessageEvent) -> None:
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
    async def provider_llm(self, event: AstrMessageEvent, index: int) -> None:
        """Switch the LLM provider"""
        await self.provider_c.set_llm_provider(event, index)

    @filter.permission("provider.use")
    @provider_set.command("tts")
    async def provider_tts(self, event: AstrMessageEvent, index: int) -> None:
        """Switch the TTS provider"""
        await self.provider_c.set_tts_provider(event, index)

    @filter.permission("provider.use")
    @provider_set.command("stt")
    async def provider_stt(self, event: AstrMessageEvent, index: int) -> None:
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
    async def set_variable(self, event: AstrMessageEvent, key: str, value: str) -> None:
        """Set session variable"""
        await self.variable_c.set_variable(event, key, value)

    @filter.permission("session.manage")
    @variable.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str) -> None:
        """Unset session variable"""
        await self.variable_c.unset_variable(event, key)

    @filter.command_group("chat")
    def chat(self) -> None:
        """Manage LLM chat for the current session"""

    @filter.permission("session.manage")
    @chat.command("status")
    async def chat_status(self, event: AstrMessageEvent) -> None:
        """Show whether LLM chat is enabled"""
        await self.chat_c.status(event)

    @filter.permission("session.manage")
    @chat.command("enable")
    async def chat_enable(self, event: AstrMessageEvent) -> None:
        """Enable LLM chat for the current session"""
        await self.chat_c.set_enabled(event, True)

    @filter.permission("session.manage")
    @chat.command("disable")
    async def chat_disable(self, event: AstrMessageEvent) -> None:
        """Disable LLM chat for the current session"""
        await self.chat_c.set_enabled(event, False)

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
    async def op(self, event: AstrMessageEvent, user_id: str) -> None:
        """Grant administrator permission"""
        await self.admin_c.grant(event, user_id)

    @filter.permission("identity.manage")
    @admin.command("revoke")
    async def deop(self, event: AstrMessageEvent, user_id: str) -> None:
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
    async def persona_view(
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
    async def plugin_ls(self, event: AstrMessageEvent) -> None:
        """List loaded plugins"""
        await self.plugin_c.list_plugins(event)

    @filter.permission("extension.manage")
    @plugin.command("disable")
    async def plugin_off(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Disable a plugin"""
        await self.plugin_c.disable(event, plugin_name)

    @filter.permission("extension.manage")
    @plugin.command("enable")
    async def plugin_on(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Enable a plugin"""
        await self.plugin_c.enable(event, plugin_name)

    @filter.permission("extension.plugin_install")
    @plugin.command("install")
    async def plugin_get(self, event: AstrMessageEvent, repository_url: str) -> None:
        """Install a plugin"""
        await self.plugin_c.install(event, repository_url)

    @filter.permission("extension.read")
    @plugin.command("show")
    async def plugin_help(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Show plugin help"""
        await self.plugin_c.show(event, plugin_name)
