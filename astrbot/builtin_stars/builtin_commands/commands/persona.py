import builtins
from typing import TYPE_CHECKING

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.constants import PERSONA_NONE_MARKER

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

        curr_persona_name = "无"
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        default_persona = await self.context.persona_manager.get_default_persona_v3(
            umo=umo,
        )
        force_applied_persona_id = None

        curr_cid_title = "无"
        if cid:
            conv = await self.context.conversation_manager.get_conversation(
                unified_msg_origin=umo,
                conversation_id=cid,
                create_if_not_exists=True,
            )
            if conv is None:
                message.set_result(
                    MessageEventResult().message(
                        "当前对话不存在，请先使用 /new 新建一个对话。",
                    ),
                )
                return

            provider_settings = self.context.get_config(umo=umo).get(
                "provider_settings",
                {},
            )
            (
                persona_id,
                _,
                force_applied_persona_id,
                _,
            ) = await self.context.persona_manager.resolve_selected_persona(
                umo=umo,
                conversation_persona_id=conv.persona_id,
                platform_name=message.get_platform_name(),
                provider_settings=provider_settings,
            )

            if persona_id == PERSONA_NONE_MARKER:
                curr_persona_name = "无"
            elif persona_id:
                curr_persona_name = persona_id

            if force_applied_persona_id:
                curr_persona_name = f"{curr_persona_name} (自定义规则)"

            curr_cid_title = conv.title if conv.title else "新对话"
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

默认人格情景: {default_persona["name"]}
当前对话 {curr_cid_title} 的人格情景: {curr_persona_name}

配置人格情景请前往管理面板-配置页
""",
                )
                .use_t2i(False),
            )
        elif l[1] == "list":
            # 获取文件夹树和所有人格
            folder_tree = await self.context.persona_manager.get_folder_tree()
            all_personas = self.context.persona_manager.personas

            lines = ["📂 人格列表：\n"]

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
            lines.append(f"\n共 {total_count} 个人格")
            lines.append("\n*使用 `/persona <人格名>` 设置人格")
            lines.append("*使用 `/persona view <人格名>` 查看详细信息")

            msg = "\n".join(lines)
            message.set_result(MessageEventResult().message(msg).use_t2i(False))
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
                    MessageEventResult().message("当前没有对话，无法取消人格。"),
                )
                return
            await self.context.conversation_manager.update_conversation_persona_id(
                message.unified_msg_origin,
                PERSONA_NONE_MARKER,
            )
            message.set_result(MessageEventResult().message("取消人格成功。"))
        else:
            ps = "".join(l[1:]).strip()
            if not cid:
                message.set_result(
                    MessageEventResult().message(
                        "当前没有对话，请先开始对话或使用 /new 创建一个对话。",
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
                    force_warn_msg = (
                        "提醒：由于自定义规则，您现在切换的人格将不会生效。"
                    )

                message.set_result(
                    MessageEventResult().message(
                        f"设置成功。如果您正在切换到不同的人格，请注意使用 /reset 来清空上下文，防止原人格对话影响现人格。{force_warn_msg}",
                    ),
                )
            else:
                message.set_result(
                    MessageEventResult().message(
                        "不存在该人格情景。使用 /persona list 查看所有。",
                    ),
                )
