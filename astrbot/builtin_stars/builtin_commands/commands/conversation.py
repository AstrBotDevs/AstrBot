import datetime

from astrbot.api import sp, star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core import t
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.active_event_registry import active_event_registry

from .utils.rst_scene import RstScene

THIRD_PARTY_AGENT_RUNNER_KEY = {
    "dify": "dify_conversation_id",
    "coze": "coze_conversation_id",
    "dashscope": "dashscope_conversation_id",
}
THIRD_PARTY_AGENT_RUNNER_STR = ", ".join(THIRD_PARTY_AGENT_RUNNER_KEY.keys())


class ConversationCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def _get_current_persona_id(self, session_id):
        curr = await self.context.conversation_manager.get_curr_conversation_id(
            session_id,
        )
        if not curr:
            return None
        conv = await self.context.conversation_manager.get_conversation(
            session_id,
            curr,
        )
        if not conv:
            return None
        return conv.persona_id

    async def reset(self, message: AstrMessageEvent) -> None:
        """重置 LLM 会话"""
        umo = message.unified_msg_origin
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        is_unique_session = cfg["platform_settings"]["unique_session"]
        is_group = bool(message.get_group_id())

        scene = RstScene.get_scene(is_group, is_unique_session)

        alter_cmd_cfg = await sp.get_async("global", "global", "alter_cmd", {})
        plugin_config = alter_cmd_cfg.get("astrbot", {})
        reset_cfg = plugin_config.get("reset", {})

        required_perm = reset_cfg.get(
            scene.key,
            "admin" if is_group and not is_unique_session else "member",
        )

        if required_perm == "admin" and message.role != "admin":
            message.set_result(
                MessageEventResult().message(
                    t(
                        "builtin-stars-conversation-reset-permission-denied",
                        scene_name=scene.name,
                        sender_id=message.get_sender_id(),
                    ),
                ),
            )
            return

        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            active_event_registry.stop_all(umo, exclude=message)
            await sp.remove_async(
                scope="umo",
                scope_id=umo,
                key=THIRD_PARTY_AGENT_RUNNER_KEY[agent_runner_type],
            )
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-reset-success")
                )
            )
            return

        if not self.context.get_using_provider(umo):
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-no-llm-provider")
                ),
            )
            return

        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-no-active-conversation"),
                ),
            )
            return

        active_event_registry.stop_all(umo, exclude=message)

        await self.context.conversation_manager.update_conversation(
            umo,
            cid,
            [],
        )

        ret = t("builtin-stars-conversation-clear-history-success")

        message.set_extra("_clean_ltm_session", True)

        message.set_result(MessageEventResult().message(ret))

    async def his(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话记录"""
        if not self.context.get_using_provider(message.unified_msg_origin):
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-no-llm-provider")
                ),
            )
            return

        size_per_page = 6

        conv_mgr = self.context.conversation_manager
        umo = message.unified_msg_origin
        session_curr_cid = await conv_mgr.get_curr_conversation_id(umo)

        if not session_curr_cid:
            session_curr_cid = await conv_mgr.new_conversation(
                umo,
                message.get_platform_id(),
            )

        contexts, total_pages = await conv_mgr.get_human_readable_context(
            umo,
            session_curr_cid,
            page,
            size_per_page,
        )

        parts = []
        for context in contexts:
            if len(context) > 150:
                context = context[:150] + "..."
            parts.append(f"{context}\n")

        history = "".join(parts)
        ret = t(
            "builtin-stars-conversation-history-result",
            history=history or t("builtin-stars-conversation-no-history"),
            page=page,
            total_pages=total_pages,
        )

        message.set_result(MessageEventResult().message(ret).use_t2i(False))

    async def convs(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话列表"""
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            message.set_result(
                MessageEventResult().message(
                    t(
                        "builtin-stars-conversation-convs-not-supported",
                        runner_types=THIRD_PARTY_AGENT_RUNNER_STR,
                    ),
                ),
            )
            return

        size_per_page = 6
        """获取所有对话列表"""
        conversations_all = await self.context.conversation_manager.get_conversations(
            message.unified_msg_origin,
        )
        """计算总页数"""
        total_pages = (len(conversations_all) + size_per_page - 1) // size_per_page
        """确保页码有效"""
        page = max(1, min(page, total_pages))
        """分页处理"""
        start_idx = (page - 1) * size_per_page
        end_idx = start_idx + size_per_page
        conversations_paged = conversations_all[start_idx:end_idx]

        parts = [t("builtin-stars-conversation-list-title")]
        """全局序号从当前页的第一个开始"""
        global_index = start_idx + 1

        """生成所有对话的标题字典"""
        _titles = {}
        for conv in conversations_all:
            title = conv.title if conv.title else t("builtin-stars-conversation-new")
            _titles[conv.cid] = title

        """遍历分页后的对话生成列表显示"""
        for conv in conversations_paged:
            persona_id = conv.persona_id
            if not persona_id or persona_id == "[%None]":
                persona = await self.context.persona_manager.get_default_persona_v3(
                    umo=message.unified_msg_origin,
                )
                persona_id = persona["name"]
            title = _titles.get(conv.cid, t("builtin-stars-conversation-new"))
            parts.append(
                t(
                    "builtin-stars-conversation-list-line",
                    index=global_index,
                    title=title,
                    cid=conv.cid[:4],
                    persona_id=persona_id,
                    updated_at=datetime.datetime.fromtimestamp(
                        conv.updated_at
                    ).strftime("%m-%d %H:%M"),
                )
            )
            global_index += 1

        parts.append(t("builtin-stars-conversation-list-divider"))
        ret = "".join(parts)
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
            message.unified_msg_origin,
        )
        if curr_cid:
            """从所有对话的标题字典中获取标题"""
            title = _titles.get(curr_cid, t("builtin-stars-conversation-new"))
            ret += t(
                "builtin-stars-conversation-current-with-id",
                title=title,
                cid=curr_cid[:4],
            )
        else:
            ret += t("builtin-stars-conversation-current-none")

        cfg = self.context.get_config(umo=message.unified_msg_origin)
        unique_session = cfg["platform_settings"]["unique_session"]
        if unique_session:
            ret += t("builtin-stars-conversation-scope-personal")
        else:
            ret += t("builtin-stars-conversation-scope-group")

        ret += t(
            "builtin-stars-conversation-page-info",
            page=page,
            total_pages=total_pages,
        )
        ret += t("builtin-stars-conversation-page-jump-tip")

        message.set_result(MessageEventResult().message(ret).use_t2i(False))
        return

    async def new_conv(self, message: AstrMessageEvent) -> None:
        """创建新对话"""
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            active_event_registry.stop_all(message.unified_msg_origin, exclude=message)
            await sp.remove_async(
                scope="umo",
                scope_id=message.unified_msg_origin,
                key=THIRD_PARTY_AGENT_RUNNER_KEY[agent_runner_type],
            )
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-new-conv-created")
                )
            )
            return

        active_event_registry.stop_all(message.unified_msg_origin, exclude=message)
        cpersona = await self._get_current_persona_id(message.unified_msg_origin)
        cid = await self.context.conversation_manager.new_conversation(
            message.unified_msg_origin,
            message.get_platform_id(),
            persona_id=cpersona,
        )

        message.set_extra("_clean_ltm_session", True)

        message.set_result(
            MessageEventResult().message(
                t("builtin-stars-conversation-switch-to-new", cid=cid[:4])
            ),
        )

    async def groupnew_conv(self, message: AstrMessageEvent, sid: str = "") -> None:
        """创建新群聊对话"""
        if sid:
            session = str(
                MessageSession(
                    platform_name=message.platform_meta.id,
                    message_type=MessageType("GroupMessage"),
                    session_id=sid,
                ),
            )

            cpersona = await self._get_current_persona_id(session)
            cid = await self.context.conversation_manager.new_conversation(
                session,
                message.get_platform_id(),
                persona_id=cpersona,
            )
            message.set_result(
                MessageEventResult().message(
                    t(
                        "builtin-stars-conversation-group-switch-to-new",
                        session=session,
                        cid=cid[:4],
                    ),
                ),
            )
        else:
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-groupnew-need-group-id")
                ),
            )

    async def switch_conv(
        self,
        message: AstrMessageEvent,
        index: int | None = None,
    ) -> None:
        """通过 /ls 前面的序号切换对话"""
        if not isinstance(index, int):
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-switch-type-invalid")
                ),
            )
            return

        if index is None:
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-switch-need-index"),
                ),
            )
            return
        conversations = await self.context.conversation_manager.get_conversations(
            message.unified_msg_origin,
        )
        if index > len(conversations) or index < 1:
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-switch-index-invalid")
                ),
            )
        else:
            conversation = conversations[index - 1]
            title = (
                conversation.title
                if conversation.title
                else t("builtin-stars-conversation-new")
            )
            await self.context.conversation_manager.switch_conversation(
                message.unified_msg_origin,
                conversation.cid,
            )
            message.set_result(
                MessageEventResult().message(
                    t(
                        "builtin-stars-conversation-switch-success",
                        title=title,
                        cid=conversation.cid[:4],
                    ),
                ),
            )

    async def rename_conv(self, message: AstrMessageEvent, new_name: str = "") -> None:
        """重命名对话"""
        if not new_name:
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-rename-need-name")
                )
            )
            return
        await self.context.conversation_manager.update_conversation_title(
            message.unified_msg_origin,
            new_name,
        )
        message.set_result(
            MessageEventResult().message(t("builtin-stars-conversation-rename-success"))
        )

    async def del_conv(self, message: AstrMessageEvent) -> None:
        """删除当前对话"""
        umo = message.unified_msg_origin
        cfg = self.context.get_config(umo=umo)
        is_unique_session = cfg["platform_settings"]["unique_session"]
        if message.get_group_id() and not is_unique_session and message.role != "admin":
            # 群聊，没开独立会话，发送人不是管理员
            message.set_result(
                MessageEventResult().message(
                    t(
                        "builtin-stars-conversation-delete-permission-denied",
                        sender_id=message.get_sender_id(),
                    ),
                ),
            )
            return

        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            active_event_registry.stop_all(umo, exclude=message)
            await sp.remove_async(
                scope="umo",
                scope_id=umo,
                key=THIRD_PARTY_AGENT_RUNNER_KEY[agent_runner_type],
            )
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-reset-success")
                )
            )
            return

        session_curr_cid = (
            await self.context.conversation_manager.get_curr_conversation_id(umo)
        )

        if not session_curr_cid:
            message.set_result(
                MessageEventResult().message(
                    t("builtin-stars-conversation-no-active-conversation-with-index"),
                ),
            )
            return

        active_event_registry.stop_all(umo, exclude=message)

        await self.context.conversation_manager.delete_conversation(
            umo,
            session_curr_cid,
        )

        ret = t("builtin-stars-conversation-delete-success")
        message.set_extra("_clean_ltm_session", True)
        message.set_result(MessageEventResult().message(ret))
