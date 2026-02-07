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
            return "当前 Chain 中没有 agent 节点。"
        lines = []
        for idx, target in enumerate(targets, start=1):
            persona_id = target.config.get("persona_id") or "<继承>"
            provider_id = target.config.get("provider_id") or "<继承>"
            lines.append(
                f"{idx}. 节点={target.node.uuid[:8]} persona={persona_id} provider={provider_id}"
            )
        return "\n".join(lines)

    async def _render_persona_tree(self) -> str:
        folders = await self.context.persona_manager.get_folder_tree()
        personas = await self.context.persona_manager.get_all_personas()

        personas_by_folder: dict[str | None, list] = {}
        for persona in personas:
            personas_by_folder.setdefault(persona.folder_id, []).append(persona)

        for folder_personas in personas_by_folder.values():
            folder_personas.sort(key=lambda p: (p.sort_order, p.persona_id))

        lines: list[str] = ["人格树："]

        def append_personas(folder_id: str | None, indent: str) -> None:
            for persona in personas_by_folder.get(folder_id, []):
                lines.append(f"{indent}- {persona.persona_id}")

        def append_folders(folder_nodes: list[dict], indent: str) -> None:
            for folder in folder_nodes:
                folder_name = folder.get("name") or "<未命名文件夹>"
                lines.append(f"{indent}[{folder_name}]")

                folder_id = folder.get("folder_id")
                append_personas(folder_id, indent + "  ")

                children = folder.get("children") or []
                if children:
                    append_folders(children, indent + "  ")

        append_personas(None, "")
        if folders:
            if len(lines) > 1:
                lines.append("")
            append_folders(folders, "")

        if len(lines) == 1:
            lines.append("(空)")

        return "\n".join(lines)

    async def persona(self, message: AstrMessageEvent):
        chain = message.chain_config
        if not chain:
            message.set_result(MessageEventResult().message("未找到已路由的 Chain。"))
            return

        tokens = self._split_tokens(message.message_str)
        chain_config_id = chain.config_id if chain else None
        default_persona = await self.context.persona_manager.get_default_persona_v3(
            config_id=chain_config_id,
        )

        if not tokens:
            help_text = [
                f"当前 Chain: {chain.chain_id}",
                f"默认人格: {default_persona['name']}",
                "",
                self._render_agent_nodes(message),
                "",
                "用法：",
                "/persona list",
                "/persona view <persona_name>",
                "/persona <persona_name>  # 兼容单 agent 绑定",
                "/persona unset  # 兼容单 agent 解绑",
                "/persona node ls",
                "/persona node set <node_idx|node_uuid> <persona_name>",
                "/persona node unset <node_idx|node_uuid>",
            ]
            message.set_result(
                MessageEventResult().message("\n".join(help_text)).use_t2i(False)
            )
            return

        if tokens[0] == "list":
            message.set_result(
                MessageEventResult()
                .message(await self._render_persona_tree())
                .use_t2i(False)
            )
            return

        if tokens[0] == "view":
            if len(tokens) < 2:
                message.set_result(
                    MessageEventResult().message("请输入 persona 名称。")
                )
                return
            persona_name = tokens[1]
            persona = self._find_persona(persona_name)
            if not persona:
                message.set_result(
                    MessageEventResult().message(f"未找到 persona `{persona_name}`。")
                )
                return
            message.set_result(
                MessageEventResult().message(
                    f"persona {persona_name}:\n{persona['prompt']}"
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
                            f"未找到 persona `{persona_name}`。"
                        )
                    )
                    return
                target = get_node_target(
                    self.context, message, "agent", selector=selector
                )
                if not target:
                    message.set_result(
                        MessageEventResult().message("agent 节点选择器无效。")
                    )
                    return
                target.config.save_config({"persona_id": persona_name})
                message.set_result(
                    MessageEventResult().message(
                        f"已将 persona `{persona_name}` 绑定到 agent 节点 `{target.node.uuid[:8]}`。"
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
                        MessageEventResult().message("agent 节点选择器无效。")
                    )
                    return
                target.config.save_config({"persona_id": ""})
                message.set_result(
                    MessageEventResult().message(
                        f"已清除 agent 节点 `{target.node.uuid[:8]}` 的 persona 绑定。"
                    )
                )
                return

            message.set_result(
                MessageEventResult().message(
                    "用法: /persona node ls | /persona node set <node> <persona> | /persona node unset <node>"
                )
            )
            return

        if tokens[0] == "unset":
            targets = list_nodes_with_config(self.context, message, "agent")
            if len(targets) != 1:
                message.set_result(
                    MessageEventResult().message(
                        "检测到多个 agent 节点，请使用 /persona node unset <node_idx|node_uuid>。"
                    )
                )
                return
            targets[0].config.save_config({"persona_id": ""})
            message.set_result(MessageEventResult().message("已清除 persona 绑定。"))
            return

        persona_name = " ".join(tokens).strip()
        persona = self._find_persona(persona_name)
        if not persona:
            message.set_result(
                MessageEventResult().message(
                    f"未找到 persona `{persona_name}`，请使用 /persona list 查看。"
                )
            )
            return

        targets = list_nodes_with_config(self.context, message, "agent")
        if len(targets) != 1:
            message.set_result(
                MessageEventResult().message(
                    "检测到多个 agent 节点，请使用 /persona node set <node_idx|node_uuid> <persona_name>。"
                )
            )
            return

        targets[0].config.save_config({"persona_id": persona_name})
        message.set_result(
            MessageEventResult().message(
                f"已将 persona `{persona_name}` 绑定到当前 agent 节点。"
            )
        )
