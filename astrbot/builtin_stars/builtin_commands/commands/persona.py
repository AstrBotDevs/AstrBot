import builtins
from typing import TYPE_CHECKING

from astrbot.api import sp, star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core import t

if TYPE_CHECKING:
    from astrbot.core.db.po import Persona


class PersonaCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    def _build_tree_output(
        self,
        folder_tree: list[dict],
        all_personas: list["Persona"],
        depth: int = 0,
    ) -> list[str]:
        """递归构建树状输出，使用短线条表示层级"""
        lines: list[str] = []
        # 使用短线条作为缩进前缀，每层只用 "│" 加一个空格
        prefix = "│ " * depth

        for folder in folder_tree:
            # 输出文件夹
            lines.append(f"{prefix}├ 📁 {folder['name']}/")

            # 获取该文件夹下的人格
            folder_personas = [
                p for p in all_personas if p.folder_id == folder["folder_id"]
            ]
            child_prefix = "│ " * (depth + 1)

            # 输出该文件夹下的人格
            for persona in folder_personas:
                lines.append(f"{child_prefix}├ 👤 {persona.persona_id}")

            # 递归处理子文件夹
            children = folder.get("children", [])
            if children:
                lines.extend(
                    self._build_tree_output(
                        children,
                        all_personas,
                        depth + 1,
                    )
                )

        return lines

    async def persona(self, message: AstrMessageEvent) -> None:
        l = message.message_str.split(" ")  # noqa: E741
        umo = message.unified_msg_origin

        curr_persona_name = t("builtin-stars-persona-none")
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        default_persona = await self.context.persona_manager.get_default_persona_v3(
            umo=umo,
        )

        force_applied_persona_id = (
            await sp.get_async(
                scope="umo", scope_id=umo, key="session_service_config", default={}
            )
        ).get("persona_id")

        curr_cid_title = t("builtin-stars-persona-none")
        if cid:
            conv = await self.context.conversation_manager.get_conversation(
                unified_msg_origin=umo,
                conversation_id=cid,
                create_if_not_exists=True,
            )
            if conv is None:
                message.set_result(
                    MessageEventResult().message(
                        t("builtin-stars-persona-current-conversation-not-found"),
                    ),
                )
                return
            if not conv.persona_id and conv.persona_id != "[%None]":
                curr_persona_name = default_persona["name"]
            else:
                curr_persona_name = conv.persona_id

            if force_applied_persona_id:
                curr_persona_name = t(
                    "builtin-stars-persona-name-with-custom-rule",
                    persona_name=curr_persona_name,
                )

            curr_cid_title = (
                conv.title
                if conv.title
                else t("builtin-stars-persona-new-conversation")
            )
            curr_cid_title += f"({cid[:4]})"

        if len(l) == 1:
            message.set_result(
                MessageEventResult()
                .message(
                    t(
                        "builtin-stars-persona-overview",
                        default_persona_name=default_persona["name"],
                        curr_cid_title=curr_cid_title,
                        curr_persona_name=curr_persona_name,
                    ),
                )
                .use_t2i(False),
            )
        elif l[1] == "list":
            # 获取文件夹树和所有人格
            folder_tree = await self.context.persona_manager.get_folder_tree()
            all_personas = self.context.persona_manager.personas

            lines = [t("builtin-stars-persona-list-title")]

            # 构建树状输出
            tree_lines = self._build_tree_output(folder_tree, all_personas)
            lines.extend(tree_lines)

            # 输出根目录下的人格（没有文件夹的）
            root_personas = [p for p in all_personas if p.folder_id is None]
            if root_personas:
                if tree_lines:  # 如果有文件夹内容，加个空行
                    lines.append("")
                for persona in root_personas:
                    lines.append(f"👤 {persona.persona_id}")

            # 统计信息
            total_count = len(all_personas)
            lines.append(t("builtin-stars-persona-list-total", total_count=total_count))
            lines.append(t("builtin-stars-persona-list-set-tip"))
            lines.append(t("builtin-stars-persona-list-view-tip"))

            msg = "\n".join(lines)
            message.set_result(MessageEventResult().message(msg).use_t2i(False))
        elif l[1] == "view":
            if len(l) == 2:
                message.set_result(
                    MessageEventResult().message(
                        t("builtin-stars-persona-view-need-name")
                    )
                )
                return
            ps = l[2].strip()
            if persona := next(
                builtins.filter(
                    lambda persona: persona["name"] == ps,
                    self.context.provider_manager.personas,
                ),
                None,
            ):
                msg = t("builtin-stars-persona-view-detail-title", persona_name=ps)
                msg += f"{persona['prompt']}\n"
            else:
                msg = t("builtin-stars-persona-view-not-found", persona_name=ps)
            message.set_result(MessageEventResult().message(msg))
        elif l[1] == "unset":
            if not cid:
                message.set_result(
                    MessageEventResult().message(
                        t("builtin-stars-persona-unset-no-conversation")
                    ),
                )
                return
            await self.context.conversation_manager.update_conversation_persona_id(
                message.unified_msg_origin,
                "[%None]",
            )
            message.set_result(
                MessageEventResult().message(t("builtin-stars-persona-unset-success"))
            )
        else:
            ps = "".join(l[1:]).strip()
            if not cid:
                message.set_result(
                    MessageEventResult().message(
                        t("builtin-stars-persona-set-no-conversation"),
                    ),
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
                    message.unified_msg_origin,
                    ps,
                )
                force_warn_msg = ""
                if force_applied_persona_id:
                    force_warn_msg = t("builtin-stars-persona-custom-rule-warning")

                message.set_result(
                    MessageEventResult().message(
                        t(
                            "builtin-stars-persona-set-success",
                            force_warn_msg=force_warn_msg,
                        ),
                    ),
                )
            else:
                message.set_result(
                    MessageEventResult().message(
                        t("builtin-stars-persona-set-not-found"),
                    ),
                )
