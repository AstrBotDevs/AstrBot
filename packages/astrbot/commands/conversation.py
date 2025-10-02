import datetime
import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.message_type import MessageType
from astrbot.core.provider.sources.dify_source import ProviderDify
from astrbot.core.provider.sources.coze_source import ProviderCoze
from astrbot.api import sp, logger
from typing import Union
from enum import Enum


class RstScene(Enum):
    GROUP_UNIQUE_ON = ("group_unique_on", "群聊+会话隔离开启")
    GROUP_UNIQUE_OFF = ("group_unique_off", "群聊+会话隔离关闭")
    PRIVATE = ("private", "私聊")

    @property
    def key(self) -> str:
        return self.value[0]

    @property
    def name(self) -> str:
        return self.value[1]

    @classmethod
    def from_index(cls, index: int) -> "RstScene":
        mapping = {1: cls.GROUP_UNIQUE_ON, 2: cls.GROUP_UNIQUE_OFF, 3: cls.PRIVATE}
        return mapping[index]

    @classmethod
    def get_scene(cls, is_group: bool, is_unique_session: bool) -> "RstScene":
        if is_group:
            return cls.GROUP_UNIQUE_ON if is_unique_session else cls.GROUP_UNIQUE_OFF
        return cls.PRIVATE


class ConversationCommands:
    def __init__(self, context: star.Context, ltm=None):
        self.context = context
        self.ltm = ltm

    def ltm_enabled(self, event: AstrMessageEvent):
        if not self.ltm:
            return False
        ltmse = self.context.get_config(umo=event.unified_msg_origin)[
            "provider_ltm_settings"
        ]
        return ltmse["group_icl_enable"] or ltmse["active_reply"]["enable"]

    async def reset(self, message: AstrMessageEvent):
        """重置 LLM 会话"""

        is_unique_session = self.context.get_config()["platform_settings"][
            "unique_session"
        ]
        is_group = bool(message.get_group_id())

        scene = RstScene.get_scene(is_group, is_unique_session)

        alter_cmd_cfg = await sp.get_async("global", "global", "alter_cmd", {})
        plugin_config = alter_cmd_cfg.get("astrbot", {})
        reset_cfg = plugin_config.get("reset", {})

        required_perm = reset_cfg.get(
            scene.key, "admin" if is_group and not is_unique_session else "member"
        )

        if required_perm == "admin" and message.role != "admin":
            message.set_result(
                MessageEventResult().message(
                    f"在{scene.name}场景下，reset命令需要管理员权限，"
                    f"您 (ID {message.get_sender_id()}) 不是管理员，无法执行此操作。"
                )
            )
            return

        if not self.context.get_using_provider(message.unified_msg_origin):
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。")
            )
            return

        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type in ["dify", "coze"]:
            assert isinstance(provider, (ProviderDify, ProviderCoze)), (
                "provider type is not dify or coze"
            )
            await provider.forget(message.unified_msg_origin)
            message.set_result(
                MessageEventResult().message(
                    "已重置当前 Dify / Coze 会话，新聊天将更换到新的会话。"
                )
            )
            return

        cid = await self.context.conversation_manager.get_curr_conversation_id(
            message.unified_msg_origin
        )

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "当前未处于对话状态，请 /switch 切换或者 /new 创建。"
                )
            )
            return

        await self.context.conversation_manager.update_conversation(
            message.unified_msg_origin, cid, []
        )

        ret = "清除会话 LLM 聊天历史成功。"
        if self.ltm and self.ltm_enabled(message):
            cnt = await self.ltm.remove_session(event=message)
            ret += f"\n聊天增强: 已清除 {cnt} 条聊天记录。"

        message.set_result(MessageEventResult().message(ret))

    async def his(self, message: AstrMessageEvent, page: int = 1):
        """查看对话记录"""
        if not self.context.get_using_provider(message.unified_msg_origin):
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。")
            )
            return

        size_per_page = 6

        conv_mgr = self.context.conversation_manager
        umo = message.unified_msg_origin
        session_curr_cid = await conv_mgr.get_curr_conversation_id(umo)

        if not session_curr_cid:
            session_curr_cid = await conv_mgr.new_conversation(
                umo, message.get_platform_id()
            )

        contexts, total_pages = await conv_mgr.get_human_readable_context(
            umo, session_curr_cid, page, size_per_page
        )

        history = ""
        for context in contexts:
            if len(context) > 150:
                context = context[:150] + "..."
            history += f"{context}\n"

        ret = (
            f"当前对话历史记录："
            f"{history or '无历史记录'}\n\n"
            f"第 {page} 页 | 共 {total_pages} 页\n"
            f"*输入 /history 2 跳转到第 2 页"
        )

        message.set_result(MessageEventResult().message(ret).use_t2i(False))

    async def convs(self, message: AstrMessageEvent, page: int = 1):
        """查看对话列表"""

        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type == "dify":
            """原有的Dify处理逻辑保持不变"""
            ret = "Dify 对话列表:\n"
            assert isinstance(provider, ProviderDify)
            data = await provider.api_client.get_chat_convs(message.unified_msg_origin)
            idx = 1
            for conv in data["data"]:
                ts_h = datetime.datetime.fromtimestamp(conv["updated_at"]).strftime(
                    "%m-%d %H:%M"
                )
                ret += f"{idx}. {conv['name']}({conv['id'][:4]})\n  上次更新:{ts_h}\n"
                idx += 1
            if idx == 1:
                ret += "没有找到任何对话。"
            dify_cid = provider.conversation_ids.get(message.unified_msg_origin, None)
            ret += f"\n\n用户: {message.unified_msg_origin}\n当前对话: {dify_cid}\n使用 /switch <序号> 切换对话。"
            message.set_result(MessageEventResult().message(ret))
            return

        size_per_page = 6
        """获取所有对话列表"""
        conversations_all = await self.context.conversation_manager.get_conversations(
            message.unified_msg_origin
        )
        """计算总页数"""
        total_pages = (len(conversations_all) + size_per_page - 1) // size_per_page
        """确保页码有效"""
        page = max(1, min(page, total_pages))
        """分页处理"""
        start_idx = (page - 1) * size_per_page
        end_idx = start_idx + size_per_page
        conversations_paged = conversations_all[start_idx:end_idx]

        ret = "对话列表：\n---\n"
        """全局序号从当前页的第一个开始"""
        global_index = start_idx + 1

        """生成所有对话的标题字典"""
        _titles = {}
        for conv in conversations_all:
            title = conv.title if conv.title else "新对话"
            _titles[conv.cid] = title

        """遍历分页后的对话生成列表显示"""
        for conv in conversations_paged:
            persona_id = conv.persona_id
            if not persona_id or persona_id == "[%None]":
                persona = await self.context.persona_manager.get_default_persona_v3(
                    umo=message.unified_msg_origin
                )
                persona_id = persona["name"]
            title = _titles.get(conv.cid, "新对话")
            ret += f"{global_index}. {title}({conv.cid[:4]})\n  人格情景: {persona_id}\n  上次更新: {datetime.datetime.fromtimestamp(conv.updated_at).strftime('%m-%d %H:%M')}\n"
            global_index += 1

        ret += "---\n"
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
            message.unified_msg_origin
        )
        if curr_cid:
            """从所有对话的标题字典中获取标题"""
            title = _titles.get(curr_cid, "新对话")
            ret += f"\n当前对话: {title}({curr_cid[:4]})"
        else:
            ret += "\n当前对话: 无"

        unique_session = self.context.get_config()["platform_settings"][
            "unique_session"
        ]
        if unique_session:
            ret += "\n会话隔离粒度: 个人"
        else:
            ret += "\n会话隔离粒度: 群聊"

        ret += f"\n第 {page} 页 | 共 {total_pages} 页"
        ret += "\n*输入 /ls 2 跳转到第 2 页"

        message.set_result(MessageEventResult().message(ret).use_t2i(False))
        return

    async def new_conv(self, message: AstrMessageEvent):
        """
        创建新对话
        """
        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type in ["dify", "coze"]:
            assert isinstance(provider, (ProviderDify, ProviderCoze)), (
                "provider type is not dify or coze"
            )
            await provider.forget(message.unified_msg_origin)
            message.set_result(
                MessageEventResult().message("成功，下次聊天将是新对话。")
            )
            return

        cid = await self.context.conversation_manager.new_conversation(
            message.unified_msg_origin, message.get_platform_id()
        )

        # 长期记忆
        if self.ltm and self.ltm_enabled(message):
            try:
                await self.ltm.remove_session(event=message)
            except Exception as e:
                logger.error(f"清理聊天增强记录失败: {e}")

        message.set_result(
            MessageEventResult().message(f"切换到新对话: 新对话({cid[:4]})。")
        )

    async def groupnew_conv(self, message: AstrMessageEvent, sid: str = ""):
        """创建新群聊对话"""
        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type in ["dify", "coze"]:
            assert isinstance(provider, (ProviderDify, ProviderCoze)), (
                "provider type is not dify or coze"
            )
            await provider.forget(message.unified_msg_origin)
            message.set_result(
                MessageEventResult().message("成功，下次聊天将是新对话。")
            )
            return
        if sid:
            session = str(
                MessageSesion(
                    platform_name=message.platform_meta.id,
                    message_type=MessageType("GroupMessage"),
                    session_id=sid,
                )
            )
            cid = await self.context.conversation_manager.new_conversation(
                session, message.get_platform_id()
            )
            message.set_result(
                MessageEventResult().message(
                    f"群聊 {session} 已切换到新对话: 新对话({cid[:4]})。"
                )
            )
        else:
            message.set_result(
                MessageEventResult().message("请输入群聊 ID。/groupnew 群聊ID。")
            )

    async def switch_conv(
        self, message: AstrMessageEvent, index: Union[int, None] = None
    ):
        """通过 /ls 前面的序号切换对话"""

        if not isinstance(index, int):
            message.set_result(
                MessageEventResult().message("类型错误，请输入数字对话序号。")
            )
            return

        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type == "dify":
            assert isinstance(provider, ProviderDify), "provider type is not dify"
            data = await provider.api_client.get_chat_convs(message.unified_msg_origin)
            if not data["data"]:
                message.set_result(MessageEventResult().message("未找到任何对话。"))
                return
            selected_conv = None
            if index is not None:
                try:
                    selected_conv = data["data"][index - 1]
                except IndexError:
                    message.set_result(
                        MessageEventResult().message("对话序号错误，请使用 /ls 查看")
                    )
                    return
            else:
                selected_conv = data["data"][0]
            ret = (
                f"Dify 切换到对话: {selected_conv['name']}({selected_conv['id'][:4]})。"
            )
            provider.conversation_ids[message.unified_msg_origin] = selected_conv["id"]
            message.set_result(MessageEventResult().message(ret))
            return

        if index is None:
            message.set_result(
                MessageEventResult().message(
                    "请输入对话序号。/switch 对话序号。/ls 查看对话 /new 新建对话"
                )
            )
            return
        conversations = await self.context.conversation_manager.get_conversations(
            message.unified_msg_origin
        )
        if index > len(conversations) or index < 1:
            message.set_result(
                MessageEventResult().message("对话序号错误，请使用 /ls 查看")
            )
        else:
            conversation = conversations[index - 1]
            title = conversation.title if conversation.title else "新对话"
            await self.context.conversation_manager.switch_conversation(
                message.unified_msg_origin, conversation.cid
            )
            message.set_result(
                MessageEventResult().message(
                    f"切换到对话: {title}({conversation.cid[:4]})。"
                )
            )

    async def rename_conv(self, message: AstrMessageEvent, new_name: str = ""):
        """重命名对话"""
        if not new_name:
            message.set_result(MessageEventResult().message("请输入新的对话名称。"))
            return

        provider = self.context.get_using_provider(message.unified_msg_origin)

        if provider and provider.meta().type == "dify":
            assert isinstance(provider, ProviderDify)
            cid = provider.conversation_ids.get(message.unified_msg_origin, None)
            if not cid:
                message.set_result(MessageEventResult().message("未找到当前对话。"))
                return
            await provider.api_client.rename(cid, new_name, message.unified_msg_origin)
            message.set_result(MessageEventResult().message("重命名对话成功。"))
            return

        await self.context.conversation_manager.update_conversation_title(
            message.unified_msg_origin, new_name
        )
        message.set_result(MessageEventResult().message("重命名对话成功。"))

    async def del_conv(self, message: AstrMessageEvent):
        """删除当前对话"""
        is_unique_session = self.context.get_config()["platform_settings"][
            "unique_session"
        ]
        if message.get_group_id() and not is_unique_session and message.role != "admin":
            # 群聊，没开独立会话，发送人不是管理员
            message.set_result(
                MessageEventResult().message(
                    f"会话处于群聊，并且未开启独立会话，并且您 (ID {message.get_sender_id()}) 不是管理员，因此没有权限删除当前对话。"
                )
            )
            return

        provider = self.context.get_using_provider(message.unified_msg_origin)
        if provider and provider.meta().type == "dify":
            assert isinstance(provider, ProviderDify)
            dify_cid = provider.conversation_ids.pop(message.unified_msg_origin, None)
            if dify_cid:
                await provider.api_client.delete_chat_conv(
                    message.unified_msg_origin, dify_cid
                )
            message.set_result(
                MessageEventResult().message(
                    "删除当前对话成功。不再处于对话状态，使用 /switch 序号 切换到其他对话或 /new 创建。"
                )
            )
            return

        session_curr_cid = (
            await self.context.conversation_manager.get_curr_conversation_id(
                message.unified_msg_origin
            )
        )

        if not session_curr_cid:
            message.set_result(
                MessageEventResult().message(
                    "当前未处于对话状态，请 /switch 序号 切换或 /new 创建。"
                )
            )
            return

        await self.context.conversation_manager.delete_conversation(
            message.unified_msg_origin, session_curr_cid
        )
        message.set_result(
            MessageEventResult().message(
                "删除当前对话成功。不再处于对话状态，使用 /switch 序号 切换到其他对话或 /new 创建。"
            )
        )
