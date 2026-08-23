from collections.abc import Sequence
from typing import TYPE_CHECKING

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n

if TYPE_CHECKING:
    from astrbot.core.db.po import Persona


class PersonaCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    def _build_tree_output(
        self,
        folder_tree: list[dict],
        all_personas: Sequence[Persona],
        depth: int = 0,
    ) -> list[str]:
        lines: list[str] = []
        prefix = "| " * depth

        for folder in folder_tree:
            lines.append(f"{prefix}+ {folder['name']}/")
            folder_personas = [
                persona
                for persona in all_personas
                if persona.folder_id == folder["folder_id"]
            ]
            child_prefix = "| " * (depth + 1)
            for persona in folder_personas:
                lines.append(f"{child_prefix}- {persona.persona_id}")

            children = folder.get("children", [])
            if children:
                lines.extend(self._build_tree_output(children, all_personas, depth + 1))

        return lines

    async def status(self, message: AstrMessageEvent) -> None:
        umo = message.unified_msg_origin
        none_label = await self.context.i18n.t(message, "persona.status.none")
        current_persona = none_label
        conversation_title = none_label

        conversation_id = await self.context.conversations.current_id(umo)
        default_persona = await self.context.personas.default(umo=umo)

        if conversation_id:
            conversation = await self.context.conversations.get(
                umo,
                conversation_id,
                create_if_missing=True,
            )
            if conversation is None:
                await reply_i18n(
                    self.context, message, "persona.status.no_conversation"
                )
                return

            provider_settings = self.context.config.get(umo=umo).get(
                "provider_settings", {}
            )
            (
                selected_persona_id,
                _,
                force_applied_persona_id,
                _,
            ) = await self.context.personas.resolve(
                umo=umo,
                conversation_persona_id=conversation.persona_id,
                platform_name=message.get_platform_name(),
                provider_settings=provider_settings,
            )
            if selected_persona_id == "[%None]":
                current_persona = none_label
            elif selected_persona_id:
                current_persona = selected_persona_id
            if force_applied_persona_id:
                current_persona += " " + await self.context.i18n.t(
                    message, "persona.status.session_rule"
                )

            new_title = await self.context.i18n.t(message, "persona.status.new")
            conversation_title = conversation.title or new_title
            conversation_title += f" ({conversation_id[:4]})"

        await reply_i18n(
            self.context,
            message,
            "persona.status.body",
            default_persona=default_persona["name"],
            conversation_title=conversation_title,
            current_persona=current_persona,
        )

    async def list_personas(self, message: AstrMessageEvent) -> None:
        folder_tree = await self.context.personas.folders()
        all_personas = self.context.personas.all()
        tree_lines = self._build_tree_output(folder_tree, all_personas)
        root_personas = [
            persona for persona in all_personas if persona.folder_id is None
        ]
        extra_lines: list[str] = []
        if root_personas:
            if tree_lines:
                extra_lines.append("")
            for persona in root_personas:
                extra_lines.append(f"- {persona.persona_id}")
        listing = "\n".join([*tree_lines, *extra_lines])
        await reply_i18n(
            self.context,
            message,
            "persona.list.body",
            listing=listing,
            total=len(all_personas),
        )

    async def show(self, message: AstrMessageEvent, persona_id: str) -> None:
        persona = self.context.personas.get(persona_id.strip())
        if persona is None:
            await reply_i18n(
                self.context,
                message,
                "persona.show.missing",
                persona_id=persona_id,
            )
            return
        prompt = persona["prompt"] or await self.context.i18n.t(
            message, "persona.show.empty_prompt"
        )
        await reply_i18n(
            self.context,
            message,
            "persona.show.body",
            persona_id=persona_id,
            prompt=prompt,
        )

    async def unset(self, message: AstrMessageEvent) -> None:
        umo = message.unified_msg_origin
        conversation_id = await self.context.conversations.current_id(umo)
        if not conversation_id:
            await reply_i18n(self.context, message, "persona.unset.none")
            return
        await self.context.conversations.update(
            umo,
            persona_id="[%None]",
        )
        await reply_i18n(self.context, message, "persona.unset.ok")

    async def set_persona(self, message: AstrMessageEvent, persona_id: str) -> None:
        persona_id = persona_id.strip()
        umo = message.unified_msg_origin
        conversation_id = await self.context.conversations.current_id(umo)
        if not conversation_id:
            await reply_i18n(self.context, message, "persona.set.none")
            return

        persona = self.context.personas.get(persona_id)
        if persona is None:
            await reply_i18n(self.context, message, "persona.set.missing")
            return

        conversation = await self.context.conversations.get(
            umo,
            conversation_id,
            create_if_missing=True,
        )
        if conversation is None:
            await reply_i18n(self.context, message, "persona.set.no_conversation")
            return

        provider_settings = self.context.config.get(umo=umo).get(
            "provider_settings", {}
        )
        (
            _,
            _,
            force_applied_persona_id,
            _,
        ) = await self.context.personas.resolve(
            umo=umo,
            conversation_persona_id=conversation.persona_id,
            platform_name=message.get_platform_name(),
            provider_settings=provider_settings,
        )
        await self.context.conversations.update(
            umo,
            persona_id=persona_id,
        )
        force_warning = ""
        if force_applied_persona_id:
            force_warning = await self.context.i18n.t(
                message, "persona.set.force_warning"
            )
        await reply_i18n(
            self.context,
            message,
            "persona.set.ok",
            force_warning=force_warning,
        )
