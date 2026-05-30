import json

from sqlalchemy import case, func, select
from sqlmodel import col

from astrbot.api import sp, star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core import logger
from astrbot.core.agent.context.token_counter import EstimateTokenCounter
from astrbot.core.agent.message import Message
from astrbot.core.agent.runners.deerflow.constants import (
    DEERFLOW_AGENT_RUNNER_PROVIDER_ID_KEY,
    DEERFLOW_PROVIDER_TYPE,
    DEERFLOW_THREAD_ID_KEY,
)
from astrbot.core.agent.runners.deerflow.deerflow_api_client import DeerFlowAPIClient
from astrbot.core.db.po import ProviderStat
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.llm_metadata import LLM_METADATAS

from .utils.rst_scene import RstScene

THIRD_PARTY_AGENT_RUNNER_KEY = {
    "dify": "dify_conversation_id",
    "coze": "coze_conversation_id",
    "dashscope": "dashscope_conversation_id",
    DEERFLOW_PROVIDER_TYPE: DEERFLOW_THREAD_ID_KEY,
}
THIRD_PARTY_AGENT_RUNNER_STR = ", ".join(THIRD_PARTY_AGENT_RUNNER_KEY.keys())


async def _cleanup_deerflow_thread_if_present(
    context: star.Context,
    umo: str,
) -> None:
    try:
        thread_id = await sp.get_async(
            scope="umo",
            scope_id=umo,
            key=DEERFLOW_THREAD_ID_KEY,
            default="",
        )
        if not thread_id:
            return

        cfg = context.get_config(umo=umo)
        provider_id = cfg["provider_settings"].get(
            DEERFLOW_AGENT_RUNNER_PROVIDER_ID_KEY,
            "",
        )
        if not provider_id:
            return

        merged_provider_config = context.provider_manager.get_provider_config_by_id(
            provider_id,
            merged=True,
        )
        if not merged_provider_config:
            logger.warning(
                "Failed to resolve DeerFlow provider config for remote thread cleanup: provider_id=%s",
                provider_id,
            )
            return

        client = DeerFlowAPIClient(
            api_base=merged_provider_config.get(
                "deerflow_api_base",
                "http://127.0.0.1:2026",
            ),
            api_key=merged_provider_config.get("deerflow_api_key", ""),
            auth_header=merged_provider_config.get("deerflow_auth_header", ""),
            proxy=merged_provider_config.get("proxy", ""),
        )
        try:
            await client.delete_thread(thread_id)
        finally:
            try:
                await client.close()
            except Exception as e:
                logger.warning(
                    "Failed to close DeerFlow API client after thread cleanup: %s",
                    e,
                )
    except Exception as e:
        logger.warning(
            "Failed to clean up DeerFlow thread for session %s: %s",
            umo,
            e,
        )


async def _clear_third_party_agent_runner_state(
    context: star.Context,
    umo: str,
    agent_runner_type: str,
) -> None:
    session_key = THIRD_PARTY_AGENT_RUNNER_KEY.get(agent_runner_type)
    if not session_key:
        return

    if agent_runner_type == DEERFLOW_PROVIDER_TYPE:
        await _cleanup_deerflow_thread_if_present(context, umo)

    await sp.remove_async(
        scope="umo",
        scope_id=umo,
        key=session_key,
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
                    f"在{scene.name}场景下，重置命令需要管理员权限，"
                    f"您 (ID {message.get_sender_id()}) 不是管理员，无法执行此操作。",
                ),
            )
            return

        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            active_event_registry.stop_all(umo, exclude=message)
            await _clear_third_party_agent_runner_state(
                self.context,
                umo,
                agent_runner_type,
            )
            message.set_result(MessageEventResult().message("✅ 会话重置成功。"))
            return

        if not self.context.get_using_provider(umo):
            message.set_result(
                MessageEventResult().message("😕 未找到任何 LLM Provider，请先配置。"),
            )
            return

        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "😕 您当前不在任何会话中，请使用 /new 创建一个。",
                ),
            )
            return

        active_event_registry.stop_all(umo, exclude=message)

        await self.context.conversation_manager.update_conversation(
            umo,
            cid,
            [],
        )

        ret = "✅ 会话重置成功。"

        # 清理该会话下的所有 subagent
        try:
            from astrbot.core.subagent_manager import SubAgentManager

            cleanup_result = await SubAgentManager.cleanup_session(umo)
            if cleanup_result["status"] == "cleaned":
                cleaned_count = len(cleanup_result["cleaned_agents"])
                if cleaned_count > 0:
                    ret += f" 🧹 同时清理了 {cleaned_count} 个子智能体: {', '.join(cleanup_result['cleaned_agents'])}。"
        except Exception as e:
            logger.warning(f"[SubAgent] Failed to cleanup subagents on /reset: {e}")

        # 清理该会话下的所有 subagent
        try:
            from astrbot.core.subagent_manager import SubAgentManager

            cleanup_result = await SubAgentManager.cleanup_session(umo)
            if cleanup_result["status"] == "cleaned":
                cleaned_count = len(cleanup_result["cleaned_agents"])
                if cleaned_count > 0:
                    ret += f" 🧹 Also cleaned {cleaned_count} subagent(s): {', '.join(cleanup_result['cleaned_agents'])}."
        except Exception as e:
            logger.warning(f"[SubAgent] Failed to cleanup subagents on /reset: {e}")

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
                    f"✅ 已请求停止 {stopped_count} 个运行中的任务。"
                )
            )
            return

        message.set_result(
            MessageEventResult().message("✅ 当前会话中没有运行中的任务。")
        )

    async def new_conv(self, message: AstrMessageEvent) -> None:
        """创建新对话"""
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            active_event_registry.stop_all(message.unified_msg_origin, exclude=message)
            await _clear_third_party_agent_runner_state(
                self.context,
                message.unified_msg_origin,
                agent_runner_type,
            )
            message.set_result(MessageEventResult().message("✅ 新对话已创建。"))
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
            MessageEventResult().message(f"✅ 已切换到新对话: {cid[:4]}。"),
        )

    async def cmd_context(self, message: AstrMessageEvent) -> None:
        """显示当前会话上下文窗口的 token 占用情况"""
        umo = message.unified_msg_origin
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "\u274c 当前不在任何会话中。使用 /new 创建一个。"
                ),
            )
            return

        conv = await self.context.conversation_manager.get_conversation(umo, cid)
        if not conv:
            message.set_result(
                MessageEventResult().message("\u274c 无法获取会话信息。")
            )
            return

        # 获取当前 provider 及 max_context_tokens
        provider = self.context.get_using_provider(umo)
        if not provider:
            message.set_result(
                MessageEventResult().message("\u274c 未配置 LLM Provider。")
            )
            return

        model_name = provider.get_model() or "unknown"
        max_tokens = provider.provider_config.get("max_context_tokens", 0)
        if max_tokens <= 0:
            model_info = LLM_METADATAS.get(model_name)
            if model_info:
                max_tokens = model_info["limit"]["context"]
            else:
                max_tokens = 128000

        # 解析 history 为 Message 列表并估算 token
        raw_history = json.loads(conv.history) if conv.history else []
        messages = [Message(**msg) for msg in raw_history]

        counter = EstimateTokenCounter()
        trusted = conv.token_usage if messages else 0
        estimated = counter.count_tokens(messages, trusted_token_usage=trusted)

        # 计算使用率 + 进度条
        usage_pct = (estimated / max_tokens * 100) if max_tokens > 0 else 0
        bar_width = 20
        filled = int(bar_width * min(usage_pct, 100) / 100)
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)

        if usage_pct < 50:
            level = "\U0001f7e2 充裕"
            hint = ""
        elif usage_pct < 75:
            level = "\U0001f7e1 适中"
            hint = ""
        else:
            level = "\U0001f534 紧张"
            hint = "\U0001f4a1 上下文即将用尽，建议发送 /reset 重置或 /new 新建会话。如果继续会话，将在用量超过 82% 时进行自动压缩。"

        ret = [
            f"\U0001f4ca 上下文占用 (会话: {cid[:8]}...)",
            f"模型: {model_name}",
            f"占用: {estimated:,} / {max_tokens:,} tokens",
            f"使用率: {usage_pct:.1f}%  [{bar}]",
            f"状态: {level}",
        ]
        if hint:
            ret.append(hint)
        if trusted > 0:
            ret.append("\U0001f4a1 精度: 基于 LLM 返回的精确值")
        elif messages:
            ret.append("\U0001f4a1 精度: 本地字符估算 (仅供参考)")

        message.set_result(MessageEventResult().message("\n".join(ret)))

    async def stats(self, message: AstrMessageEvent) -> None:
        """显示当前会话的 Token 用量统计。"""
        umo = message.unified_msg_origin
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "❌ 您当前不在任何会话中，请使用 /new 创建一个。"
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
                MessageEventResult().message("📊 该会话暂无统计数据。"),
            )
            return

        total_input_other = stats.total_input_other
        total_input_cached = stats.total_input_cached
        total_output = stats.total_output
        total_tokens = total_input_other + total_input_cached + total_output

        ret = (
            f"📊 会话 Token 用量 (ID: {cid[:8]}...)\n"
            f"总计:              {total_tokens:,}\n"
            f"输入 (缓存命中):    {total_input_cached:,}\n"
            f"输入 (其他):        {total_input_other:,}\n"
            f"输出:              {total_output:,}\n"
        )

        message.set_result(MessageEventResult().message(ret))
