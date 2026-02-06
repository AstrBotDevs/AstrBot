import builtins

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ._node_binding import get_node_target, list_nodes_with_config


class PersonaCommands:
    def __init__(self, context: star.Context):
        self.context = context

    @staticmethod
    def _split_tokens(message: str) -> list[str]:
        parts = [p for p in message.strip().split() if p]
        if parts and parts[0].startswith("/"):
            parts = parts[1:]
        if parts and parts[0] == "persona":
            parts = parts[1:]
        return parts

    def _find_persona(self, persona_name: str):
        return next(
            builtins.filter(
                lambda persona: persona["name"] == persona_name,
                self.context.provider_manager.personas,
            ),
            None,
        )

    def _render_agent_nodes(self, event: AstrMessageEvent) -> str:
        targets = list_nodes_with_config(self.context, event, "agent")
        if not targets:
            return "Current chain has no agent node."
        lines = []
        for idx, target in enumerate(targets, start=1):
            persona_id = target.config.get("persona_id") or "<inherit>"
            provider_id = target.config.get("provider_id") or "<inherit>"
            lines.append(
                f"{idx}. node={target.node.uuid[:8]} persona={persona_id} provider={provider_id}"
            )
        return "\n".join(lines)

    async def persona(self, message: AstrMessageEvent):
        chain = message.chain_config
        if not chain:
            message.set_result(MessageEventResult().message("No routed chain found."))
            return

        tokens = self._split_tokens(message.message_str)
        default_persona = await self.context.persona_manager.get_default_persona_v3(
            umo=message.unified_msg_origin,
        )

        if not tokens:
            help_text = [
                f"Chain: {chain.chain_id}",
                f"Default persona: {default_persona['name']}",
                "",
                self._render_agent_nodes(message),
                "",
                "Usage:",
                "/persona list",
                "/persona view <persona_name>",
                "/persona <persona_name>  # single-agent compatibility",
                "/persona unset  # single-agent compatibility",
                "/persona node ls",
                "/persona node set <node_idx|node_uuid> <persona_name>",
                "/persona node unset <node_idx|node_uuid>",
            ]
            message.set_result(
                MessageEventResult().message("\n".join(help_text)).use_t2i(False)
            )
            return

        if tokens[0] == "list":
            all_personas = self.context.persona_manager.personas
            lines = ["Personas:"]
            for persona in all_personas:
                lines.append(f"- {persona.persona_id}")
            message.set_result(
                MessageEventResult().message("\n".join(lines)).use_t2i(False)
            )
            return

        if tokens[0] == "view":
            if len(tokens) < 2:
                message.set_result(
                    MessageEventResult().message("Please input persona name.")
                )
                return
            persona_name = tokens[1]
            persona = self._find_persona(persona_name)
            if not persona:
                message.set_result(
                    MessageEventResult().message(f"Persona `{persona_name}` not found.")
                )
                return
            message.set_result(
                MessageEventResult().message(
                    f"Persona {persona_name}:\n{persona['prompt']}"
                )
            )
            return

        if tokens[0] == "node":
            if len(tokens) >= 2 and tokens[1] == "ls":
                message.set_result(
                    MessageEventResult()
                    .message(self._render_agent_nodes(message))
                    .use_t2i(False)
                )
                return
            if len(tokens) >= 4 and tokens[1] == "set":
                selector = tokens[2]
                persona_name = " ".join(tokens[3:]).strip()
                persona = self._find_persona(persona_name)
                if not persona:
                    message.set_result(
                        MessageEventResult().message(
                            f"Persona `{persona_name}` not found."
                        )
                    )
                    return
                target = get_node_target(
                    self.context, message, "agent", selector=selector
                )
                if not target:
                    message.set_result(
                        MessageEventResult().message("Invalid agent node selector.")
                    )
                    return
                target.config.save_config({"persona_id": persona_name})
                message.set_result(
                    MessageEventResult().message(
                        f"Bound persona `{persona_name}` to agent node `{target.node.uuid[:8]}`."
                    )
                )
                return
            if len(tokens) >= 3 and tokens[1] == "unset":
                selector = tokens[2]
                target = get_node_target(
                    self.context, message, "agent", selector=selector
                )
                if not target:
                    message.set_result(
                        MessageEventResult().message("Invalid agent node selector.")
                    )
                    return
                target.config.save_config({"persona_id": ""})
                message.set_result(
                    MessageEventResult().message(
                        f"Cleared persona binding for agent node `{target.node.uuid[:8]}`."
                    )
                )
                return

            message.set_result(
                MessageEventResult().message(
                    "Usage: /persona node ls | /persona node set <node> <persona> | /persona node unset <node>"
                )
            )
            return

        if tokens[0] == "unset":
            targets = list_nodes_with_config(self.context, message, "agent")
            if len(targets) != 1:
                message.set_result(
                    MessageEventResult().message(
                        "Multiple agent nodes found. Use /persona node unset <node_idx|node_uuid>."
                    )
                )
                return
            targets[0].config.save_config({"persona_id": ""})
            message.set_result(MessageEventResult().message("Persona cleared."))
            return

        persona_name = " ".join(tokens).strip()
        persona = self._find_persona(persona_name)
        if not persona:
            message.set_result(
                MessageEventResult().message(
                    f"Persona `{persona_name}` not found. Use /persona list."
                )
            )
            return

        targets = list_nodes_with_config(self.context, message, "agent")
        if len(targets) != 1:
            message.set_result(
                MessageEventResult().message(
                    "Multiple agent nodes found. Use /persona node set <node_idx|node_uuid> <persona_name>."
                )
            )
            return

        targets[0].config.save_config({"persona_id": persona_name})
        message.set_result(
            MessageEventResult().message(
                f"Bound persona `{persona_name}` to the current agent node."
            )
        )
