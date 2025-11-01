import builtins

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class PersonaCommands:
    def __init__(self, context: star.Context):
        self.context = context

    async def persona(self, message: AstrMessageEvent):
        l = message.message_str.split(" ")  # noqa: E741
        umo = message.unified_msg_origin

        curr_persona_name = "无"
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        default_persona = await self.context.persona_manager.get_default_persona_v3(
            umo=umo,
        )
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
            if not conv.persona_id and conv.persona_id != "[%None]":
                curr_persona_name = default_persona["name"]
            else:
                curr_persona_name = conv.persona_id

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
            parts = ["人格列表：\n"]
            for persona in self.context.provider_manager.personas:
                parts.append(f"- {persona['name']}\n")
            parts.append("\n\n*输入 `/persona view 人格名` 查看人格详细信息")
            msg = "".join(parts)
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
                    MessageEventResult().message("当前没有对话，无法取消人格。"),
                )
                return
            await self.context.conversation_manager.update_conversation_persona_id(
                message.unified_msg_origin,
                "[%None]",
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
                message.set_result(
                    MessageEventResult().message(
                        "设置成功。如果您正在切换到不同的人格，请注意使用 /reset 来清空上下文，防止原人格对话影响现人格。",
                    ),
                )
            else:
                message.set_result(
                    MessageEventResult().message(
                        "不存在该人格情景。使用 /persona list 查看所有。",
                    ),
                )
