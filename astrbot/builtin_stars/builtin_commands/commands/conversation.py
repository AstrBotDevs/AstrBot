import datetime
from typing import TypedDict

from sqlalchemy import case, func, select
from sqlmodel import col

from astrbot.api import logger, sp, star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.agent.runners.deerflow.constants import (
    DEERFLOW_PROVIDER_TYPE,
    DEERFLOW_THREAD_ID_KEY,
)
from astrbot.core.agent.runners.deerflow.deerflow_api_client import DeerFlowAPIClient
from astrbot.core.db.po import ProviderStat
from astrbot.core.utils.active_event_registry import active_event_registry

from .utils.rst_scene import RstScene

THIRD_PARTY_AGENT_RUNNER_KEY = {
    "dify": "dify_conversation_id",
    "coze": "coze_conversation_id",
    "dashscope": "dashscope_conversation_id",
    DEERFLOW_PROVIDER_TYPE: DEERFLOW_THREAD_ID_KEY,
}
THIRD_PARTY_AGENT_RUNNER_STR = ", ".join(THIRD_PARTY_AGENT_RUNNER_KEY.keys())


class ResetPermissionConfig(TypedDict, total=False):
    group_unique_on: str
    group_unique_off: str
    private: str


class AlterCmdPluginConfig(TypedDict, total=False):
    reset: ResetPermissionConfig


def _normalize_alter_cmd_config(value: object) -> dict[str, AlterCmdPluginConfig]:
    if not isinstance(value, dict):
        return {}
    config: dict[str, AlterCmdPluginConfig] = {}
    for plugin_name, raw_plugin_config in value.items():
        if not isinstance(plugin_name, str) or not isinstance(raw_plugin_config, dict):
            continue
        normalized_plugin_config = {
            key: item for key, item in raw_plugin_config.items() if isinstance(key, str)
        }
        plugin_config: AlterCmdPluginConfig = {}
        raw_reset = normalized_plugin_config.get("reset")
        if isinstance(raw_reset, dict):
            normalized_reset = {
                key: item for key, item in raw_reset.items() if isinstance(key, str)
            }
            reset_config: ResetPermissionConfig = {}
            for key in ("group_unique_on", "group_unique_off", "private"):
                permission = normalized_reset.get(key)
                if isinstance(permission, str):
                    reset_config[key] = permission
            if reset_config:
                plugin_config["reset"] = reset_config
        config[plugin_name] = plugin_config
    return config


async def _clear_third_party_agent_runner_state(
    context: star.Context,
    session_id: str,
    provider_type: str,
) -> None:
    """清理第三方 Agent Runner 的状态: 先删除远端资源,再清理本地存储的状态。

    Args:
        context: 星尘上下文。
        session_id: 会话 ID (unified_msg_origin)。
        provider_type: 提供商类型 (如 deerflow)。
    """
    provider_config = context.provider_manager.get_provider_config_by_id(
        provider_type,
        merged=True,
    )
    if provider_config:
        try:
            client = DeerFlowAPIClient(
                api_base=provider_config.get("deerflow_api_base", ""),
                api_key=provider_config.get("deerflow_api_key", ""),
                auth_header=provider_config.get("deerflow_auth_header", ""),
                proxy=provider_config.get("proxy"),
            )
            try:
                thread_id = await sp.get_async(
                    scope="umo",
                    scope_id=session_id,
                    key=DEERFLOW_THREAD_ID_KEY,
                )
                if thread_id:
                    await client.delete_thread(thread_id, timeout=20)
            except Exception:
                logger.exception(
                    f"清理 {provider_type} Agent Runner 远程线程失败",
                )
            finally:
                await client.close()
        except Exception:
            logger.exception(
                f"初始化 {provider_type} Agent Runner 客户端失败",
            )

    await sp.remove_async(
        scope="umo",
        scope_id=session_id,
        key=DEERFLOW_THREAD_ID_KEY,
    )


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
        alter_cmd_cfg = _normalize_alter_cmd_config(
            await sp.get_async("global", "global", "alter_cmd", {}),
        )
        plugin_config = alter_cmd_cfg.get("astrbot", {})
        reset_cfg = plugin_config.get("reset", {})
        required_perm = reset_cfg.get(
            scene.key,
            "admin" if is_group and (not is_unique_session) else "member",
        )
        if required_perm == "admin" and message.role != "admin":
            message.set_result(
                MessageEventResult().message(
                    f"在{scene.name}场景下,reset命令需要管理员权限,您 (ID {message.get_sender_id()}) 不是管理员,无法执行此操作｡",
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
            message.set_result(MessageEventResult().message("重置对话成功｡"))
            return
        if not self.context.get_using_provider(umo):
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商｡请先配置｡"),
            )
            return
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "当前未处于对话状态,请 /switch 切换或者 /new 创建｡",
                ),
            )
            return
        active_event_registry.stop_all(umo, exclude=message)
        await self.context.conversation_manager.update_conversation(umo, cid, [])
        ret = "清除聊天历史成功!"
        message.set_extra("_clean_ltm_session", True)
        message.set_result(MessageEventResult().message(ret))

    async def stop(self, message: AstrMessageEvent) -> None:
        """停止当前会话正在运行的 Agent"""
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        umo = message.unified_msg_origin
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            stopped_count = active_event_registry.stop_all(umo, exclude=message)
        else:
            stopped_count = active_event_registry.request_agent_stop_all(
                umo,
                exclude=message,
            )
        if stopped_count > 0:
            message.set_result(
                MessageEventResult().message(
                    f"已请求停止 {stopped_count} 个运行中的任务｡",
                ),
            )
            return
        message.set_result(MessageEventResult().message("当前会话没有运行中的任务｡"))

    async def his(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话记录"""
        if not self.context.get_using_provider(message.unified_msg_origin):
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商｡请先配置｡"),
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
        ret = f"当前对话历史记录:{history or '无历史记录'}\n\n第 {page} 页 | 共 {total_pages} 页\n*输入 /history 2 跳转到第 2 页"
        message.set_result(MessageEventResult().message(ret).use_t2i(False))

    async def convs(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话列表"""
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            message.set_result(
                MessageEventResult().message(
                    f"{THIRD_PARTY_AGENT_RUNNER_STR} 对话列表功能暂不支持｡",
                ),
            )
            return
        size_per_page = 6
        "获取所有对话列表"
        conversations_all = await self.context.conversation_manager.get_conversations(
            message.unified_msg_origin,
        )
        "计算总页数"
        total_pages = (len(conversations_all) + size_per_page - 1) // size_per_page
        "确保页码有效"
        page = max(1, min(page, total_pages))
        "分页处理"
        start_idx = (page - 1) * size_per_page
        end_idx = start_idx + size_per_page
        conversations_paged = conversations_all[start_idx:end_idx]
        parts = ["对话列表:\n---\n"]
        "全局序号从当前页的第一个开始"
        global_index = start_idx + 1
        "生成所有对话的标题字典"
        _titles = {}
        for conv in conversations_all:
            title = conv.title or "新对话"
            _titles[conv.cid] = title
        "遍历分页后的对话生成列表显示"
        provider_settings = cfg.get("provider_settings", {})
        platform_name = message.get_platform_name()
        for conv in conversations_paged:
            (
                persona_id,
                _,
                force_applied_persona_id,
                _,
            ) = await self.context.persona_manager.resolve_selected_persona(
                umo=message.unified_msg_origin,
                conversation_persona_id=conv.persona_id,
                platform_name=platform_name,
                provider_settings=provider_settings,
            )
            if persona_id == "[%None]":
                persona_name = "无"
            elif persona_id:
                persona_name = persona_id
            else:
                persona_name = "无"
            if force_applied_persona_id:
                persona_name = f"{persona_name} (自定义规则)"
            title = _titles.get(conv.cid, "新对话")
            parts.append(
                f"{global_index}. {title}({conv.cid[:4]})\n  人格情景: {persona_name}\n  上次更新: {datetime.datetime.fromtimestamp(conv.updated_at).strftime('%m-%d %H:%M')}\n",
            )
            global_index += 1
        parts.append("---\n")
        ret = "".join(parts)
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
            message.unified_msg_origin,
        )
        if curr_cid:
            "从所有对话的标题字典中获取标题"
            title = _titles.get(curr_cid, "新对话")
            ret += f"\n当前对话: {title}({curr_cid[:4]})"
        else:
            ret += "\n当前对话: 无"
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        unique_session = cfg["platform_settings"]["unique_session"]
        if unique_session:
            ret += "\n会话隔离粒度: 个人"
        else:
            ret += "\n会话隔离粒度: 群聊"
        ret += f"\n第 {page} 页 | 共 {total_pages} 页"
        ret += "\n*输入 /ls 2 跳转到第 2 页"
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
            message.set_result(MessageEventResult().message("已创建新对话｡"))
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
            MessageEventResult().message(f"切换到新对话: 新对话({cid[:4]})｡"),
        )

    async def stats(self, message: AstrMessageEvent) -> None:
        """Show token usage statistics for the current conversation."""
        umo = message.unified_msg_origin
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "❌ You are not in a conversation. Use /new to create one."
                ),
            )
            return

        db = self.context.get_db()
        async with db.get_db() as session:
            result = await session.execute(
                select(
                    func.count(case((col(ProviderStat.id).is_not(None), 1))).label(
                        "record_count",
                    ),
                    func.coalesce(func.sum(ProviderStat.token_input_other), 0).label(
                        "total_input_other",
                    ),
                    func.coalesce(func.sum(ProviderStat.token_input_cached), 0).label(
                        "total_input_cached",
                    ),
                    func.coalesce(func.sum(ProviderStat.token_output), 0).label(
                        "total_output",
                    ),
                ).where(
                    col(ProviderStat.agent_type) == "internal",
                    col(ProviderStat.conversation_id) == cid,
                )
            )
            stats = result.one()

        if stats.record_count == 0:
            message.set_result(
                MessageEventResult().message(
                    "📊 No stats available for this conversation yet."
                ),
            )
            return

        total_input_other = stats.total_input_other
        total_input_cached = stats.total_input_cached
        total_output = stats.total_output
        total_tokens = total_input_other + total_input_cached + total_output

        ret = (
            f"📊 Conversation Token usage (ID: {cid[:8]}...)\n"
            f"Total:          {total_tokens:,}\n"
            f"Input (cached): {total_input_cached:,}\n"
            f"Input (other):  {total_input_other:,}\n"
            f"Output:         {total_output:,}\n"
        )

        message.set_result(MessageEventResult().message(ret))
