import asyncio
import datetime
import inspect
import random
import uuid
from collections import defaultdict, deque
from typing import Any

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.platform import MessageType
from astrbot.api.provider import LLMResponse, Provider, ProviderRequest
from astrbot.core.agent.message import TextPart
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.message.message_event_result import ResultContentType

from .constants import LTM_ACTIVE_REPLY_KEY

"""
聊天记忆增强 (LTM v2)
"""

# === 常量 ===

CHATROOM_SYSTEM_NOTE = (
    "You are now in a chatroom. "
    "Chat history messages below use the format '[username/time]: content'. "
    "Your own messages are presented via the standard assistant role.\n"
)

MAX_MSGS_PER_USER_SEGMENT = 50
MAX_CHARS_PER_USER_SEGMENT = 3000
MAX_RAW_BYTES = 500_000  # 500KB / 群
DEFAULT_HISTORY_TOOL_RESULT_MAX_CHARS = 8192
SUMMARY_RETRY_COOLDOWN = 5  # 轮数：LLM 摘要失败后等待多少轮再重试

TOOL_CALL_PREFIX = "<T:CALL>"
TOOL_RES_PREFIX = "<T:RES"
BOT_MARKER = "<BOT/"


class LongTermMemory:
    DEFAULT_MAX_GROUP_MESSAGES = 50
    DEFAULT_GROUP_ICL_TOKEN_BUDGET = 4000

    def __init__(self, acm: AstrBotConfigManager, context: star.Context) -> None:
        self.acm = acm
        self.context = context

        self._locks: dict[str, asyncio.Lock] = {}

        self.raw_records: dict[str, deque[str]] = defaultdict(deque)
        """群聊原始记录。deque 支持 O(1) popleft。"""

        self._raw_cursor: dict[str, int] = defaultdict(int)
        """raw_records 中已消费到 contexts 的位置（指向下一条未消费的索引）。"""

        self.contexts: dict[str, list[dict]] = defaultdict(list)
        """累积累积态 LLM 上下文。由 ContextManager 修改后保留。"""

        self._persisted_tool_call_ids: dict[str, set[str]] = defaultdict(set)
        """已持久化到 raw_records 的 <T:CALL> 的 tool_call_id。用于防重复注入。"""
        self._persisted_tool_result_ids: dict[str, set[str]] = defaultdict(set)
        """已持久化到 raw_records 的 <T:RES> 的 tool_call_id。用于防重复注入。"""

        self.summaries: dict[str, str] = defaultdict(str)
        """LLM summary 策略下每个群聊的长期摘要文本。"""

        self._summary_next_retry: dict[str, int] = defaultdict(int)
        """LLM 摘要失败后，下次允许重试的 rounds 数下限（冷却期内跳过）。"""

        self._summary_in_progress: set[str] = set()
        """正在生成 LLM summary 的 session，防止重复触发。"""

    def _get_lock(self, umo: str) -> asyncio.Lock:
        """Return the per-session lock for a unified message origin."""
        lock = self._locks.get(umo)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[umo] = lock
        return lock

    # =========================================================================
    # 配置
    # =========================================================================

    def cfg(self, event: AstrMessageEvent):
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        ltm_cfg = cfg["provider_ltm_settings"]
        try:
            max_cnt = int(ltm_cfg["group_message_max_cnt"])
        except BaseException as e:
            logger.error(e)
            max_cnt = 300
        try:
            flow_max_records = int(ltm_cfg.get("group_flow_max_records", 5000))
        except BaseException as e:
            logger.error(e)
            flow_max_records = 5000
        try:
            flow_max_delta_messages = int(
                ltm_cfg.get("group_flow_max_delta_messages", 200)
            )
        except BaseException as e:
            logger.error(e)
            flow_max_delta_messages = 200
        try:
            flow_max_message_chars = int(
                ltm_cfg.get("group_flow_max_message_chars", 1000)
            )
        except BaseException as e:
            logger.error(e)
            flow_max_message_chars = 1000
        image_caption_prompt = cfg["provider_settings"]["image_caption_prompt"]
        image_caption_provider_id = ltm_cfg.get("image_caption_provider_id")
        image_caption = ltm_cfg["image_caption"] and bool(image_caption_provider_id)
        active_reply = ltm_cfg["active_reply"]
        enable_active_reply = active_reply.get("enable", False)
        ar_method = active_reply["method"]
        ar_possibility = active_reply["possibility_reply"]
        ar_prompt = active_reply.get("prompt", "")
        ar_whitelist = active_reply.get("whitelist", [])
        ret = {
            "group_icl_enable": ltm_cfg.get("group_icl_enable", False),
            "group_context_mode": ltm_cfg.get("group_context_mode", "sliding_window"),
            "max_cnt": max_cnt,
            "flow_max_records": flow_max_records,
            "flow_max_delta_messages": flow_max_delta_messages,
            "flow_max_message_chars": flow_max_message_chars,
            "flow_record_bot_messages": ltm_cfg.get(
                "group_flow_record_bot_messages", False
            ),
            "image_caption": image_caption,
            "image_caption_prompt": image_caption_prompt,
            "image_caption_provider_id": image_caption_provider_id,
            "history_tool_result_truncate": history_tool_result_truncate,
            "history_tool_result_max_chars": max(1, history_tool_result_max_chars),
            "enable_active_reply": enable_active_reply,
            "ar_method": ar_method,
            "ar_possibility": ar_possibility,
            "ar_prompt": ar_prompt,
            "ar_whitelist": ar_whitelist,
            "ltm_compaction_strategy": ltm_compaction_strategy,
            "ltm_max_rounds": max(1, ltm_max_rounds),
            "ltm_truncate_drop_rounds": max(1, ltm_truncate_drop_rounds),
            "ltm_summary_trigger_rounds": max(1, ltm_summary_trigger_rounds),
            "ltm_summary_keep_recent_rounds": max(1, ltm_summary_keep_recent_rounds),
            "ltm_summary_provider_id": ltm_summary_provider_id,
            "ltm_summary_prompt": ltm_summary_prompt,
            "ltm_raw_records_max_bytes": ltm_cfg.get(
                "ltm_raw_records_max_bytes", MAX_RAW_BYTES
            ),
            "ltm_max_msgs_per_user_segment": max(1, ltm_max_msgs_per_user_segment),
            "ltm_max_chars_per_user_segment": max(1, ltm_max_chars_per_user_segment),
        }

    def _is_flow_mode(self, event: AstrMessageEvent, cfg: dict | None = None) -> bool:
        cfg = cfg or self.cfg(event)
        return (
            bool(cfg.get("group_icl_enable"))
            and cfg.get("group_context_mode") == "flow"
            and event.get_message_type() == MessageType.GROUP_MESSAGE
        )

    def _flow_session_id(self, event: AstrMessageEvent) -> str:
        group_id = event.get_group_id()
        if group_id:
            return f"{event.get_platform_id()}:{MessageType.GROUP_MESSAGE.value}:{group_id}"
        return event.unified_msg_origin

    def _append_sliding_message(
        self,
        event: AstrMessageEvent,
        message: str,
        max_cnt: int,
    ) -> None:
        logger.debug(f"ltm | {event.unified_msg_origin} | {message}")
        self.session_chats[event.unified_msg_origin].append(message)
        if len(self.session_chats[event.unified_msg_origin]) > max_cnt:
            self.session_chats[event.unified_msg_origin].pop(0)

    async def remove_session(self, event: AstrMessageEvent) -> int:
        cnt = 0
        if event.unified_msg_origin in self.session_chats:
            cnt = len(self.session_chats[event.unified_msg_origin])
            del self.session_chats[event.unified_msg_origin]
        if self._is_flow_mode(event):
            await self.reset_flow_cursor(event)
        return cnt

    async def reset_flow_cursor(self, event: AstrMessageEvent) -> None:
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
        if not curr_cid:
            return
        flow_session_id = self._flow_session_id(event)
        latest_id = await self.context.group_message_flow_manager.get_latest_record_id(
            flow_session_id
        )
        await self.context.group_message_flow_manager.set_cursor(
            platform_id=event.get_platform_id(),
            flow_session_id=flow_session_id,
            conversation_id=curr_cid,
            last_record_id=latest_id,
        )

    async def get_image_caption(
        self,
        image_url: str,
        image_caption_provider_id: str,
        image_caption_prompt: str,
    ) -> str:
        if not image_caption_provider_id:
            image_caption_provider_id = self.context.get_config()[
                "provider_settings"
            ].get("default_image_caption_provider_id")
        if not image_caption_provider_id:
            provider = self.context.get_using_provider()
        else:
            provider = self.context.get_provider_by_id(image_caption_provider_id)
            if not provider:
                raise Exception(f"没有找到 ID 为 {image_caption_provider_id} 的提供商")
        if not isinstance(provider, Provider):
            raise Exception(f"提供商类型错误({type(provider)}),无法获取图片描述")
        response = await provider.text_chat(
            prompt=image_caption_prompt,
            session_id=uuid.uuid4().hex,
            image_urls=[image_url],
            persist=False,
        )
        return response.completion_text

    # =========================================================================
    # 主动回复判断
    # =========================================================================

    async def need_active_reply(self, event: AstrMessageEvent) -> bool:
        cfg = self.cfg(event)
        if not cfg["enable_active_reply"]:
            return False
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return False
        if event.is_at_or_wake_command:
            return False
        if cfg["ar_whitelist"] and (
            event.unified_msg_origin not in cfg["ar_whitelist"]
            and (
                event.get_group_id() and event.get_group_id() not in cfg["ar_whitelist"]
            )
        ):
            return False
        match cfg["ar_method"]:
            case "possibility_reply":
                trig = random.random() < cfg["ar_possibility"]
                return trig
        return False

    async def _render_group_message(
        self,
        event: AstrMessageEvent,
        cfg: dict,
        sender_name: str | None = None,
    ) -> str:
        """Render one group message in the legacy LTM style."""
        datetime_str = datetime.datetime.now().strftime("%H:%M:%S")
        display_name = sender_name or event.get_sender_name() or event.get_sender_id()
        parts = [f"[{display_name}/{datetime_str}]: "]

        for comp in event.get_messages():
            if isinstance(comp, Plain):
                parts.append(f" {comp.text}")
            elif isinstance(comp, Image):
                if cfg["image_caption"]:
                    try:
                        url = comp.url if comp.url else comp.file
                        if not url:
                            raise Exception("图片 URL 为空")
                        caption = await self.get_image_caption(
                            url,
                            cfg["image_caption_provider_id"],
                            cfg["image_caption_prompt"],
                        )
                        parts.append(f" [Image: {caption}]")
                    except Exception as e:
                        logger.error(f"获取图片描述失败: {e}")
                        parts.append(" [Image]")
                else:
                    parts.append(" [Image]")
            elif isinstance(comp, At):
                parts.append(f" [At: {comp.name or comp.qq}]")
            else:
                comp_type = getattr(comp, "type", comp.__class__.__name__)
                parts.append(f" [{comp_type}]")

        return "".join(parts)

    async def _components_to_dict(self, components) -> list[dict]:
        content = []
        for comp in components:
            try:
                content.append(await self._component_to_json_safe_dict(comp))
            except Exception as e:
                logger.warning(f"Failed to serialize group flow message component: {e}")
        return content

    async def _component_to_json_safe_dict(self, comp) -> dict:
        if hasattr(comp, "to_dict"):
            data = comp.to_dict()
            if inspect.isawaitable(data):
                data = await data
        elif hasattr(comp, "toDict"):
            data = comp.toDict()
        else:
            data = {"type": comp.__class__.__name__, "data": {}}
        return await self._json_safe(data)

    async def _json_safe(self, value):
        if hasattr(value, "to_dict"):
            return await self._component_to_json_safe_dict(value)
        if hasattr(value, "toDict"):
            return await self._json_safe(value.toDict())
        if isinstance(value, dict):
            return {k: await self._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [await self._json_safe(item) for item in value]
        return value

    async def _message_content_to_dict(self, event: AstrMessageEvent) -> list[dict]:
        return await self._components_to_dict(event.get_messages())

    def _truncate_flow_message_text(self, message: str, max_chars: int) -> str:
        if max_chars <= 0:
            return message
        return message[:max_chars]

    async def _record_flow_message(
        self,
        event: AstrMessageEvent,
        rendered_text: str,
        role: str = "user",
        content: list[dict] | None = None,
    ) -> int | None:
        cfg = self.cfg(event)
        if not self._is_flow_mode(event, cfg):
            return None
        flow_session_id = self._flow_session_id(event)
        record = await self.context.group_message_flow_manager.insert_record(
            platform_id=event.get_platform_id(),
            flow_session_id=flow_session_id,
            group_id=event.get_group_id() or None,
            sender_id=event.get_sender_id() if role == "user" else event.get_self_id(),
            sender_name=event.get_sender_name() if role == "user" else "You",
            role=role,
            content=content
            if content is not None
            else await self._message_content_to_dict(event),
            rendered_text=rendered_text,
        )
        await self.context.group_message_flow_manager.prune_records(
            flow_session_id,
            cfg["flow_max_records"],
        )
        return record.id

    async def handle_message(self, event: AstrMessageEvent) -> None:
        """仅支持群聊"""
        if event.get_message_type() == MessageType.GROUP_MESSAGE:
            cfg = self.cfg(event)
            final_message = await self._render_group_message(event, cfg)

            if cfg["enable_active_reply"] or not self._is_flow_mode(event, cfg):
                self._append_sliding_message(event, final_message, cfg["max_cnt"])

            if self._is_flow_mode(event, cfg):
                record_id = await self._record_flow_message(event, final_message)
                if record_id:
                    event.set_extra("_group_message_flow_record_id", record_id)

    async def _inject_flow_delta(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        cfg: dict,
    ) -> None:
        if not req.conversation:
            return
        flow_session_id = self._flow_session_id(event)
        cursor = await self.context.group_message_flow_manager.get_cursor(
            flow_session_id,
            req.conversation.cid,
        )
        after_id = cursor.last_record_id if cursor else 0
        current_record_id = event.get_extra("_group_message_flow_record_id")
        if isinstance(current_record_id, int) and current_record_id > 0:
            before_id = current_record_id
            next_cursor_id = current_record_id
        else:
            before_id = None
            next_cursor_id = (
                await self.context.group_message_flow_manager.get_latest_record_id(
                    flow_session_id
                )
            )

        records = await self.context.group_message_flow_manager.get_records_after(
            flow_session_id=flow_session_id,
            after_id=after_id,
            before_id=before_id,
            limit=cfg["flow_max_delta_messages"],
        )
        if records:
            chats_str = "\n---\n".join(
                self._truncate_flow_message_text(
                    record.rendered_text,
                    cfg["flow_max_message_chars"],
                )
                for record in records
            )
            req.system_prompt += (
                "\n<group_messages_delta>\n"
                "You are now in a chatroom. New group messages since the last turn:\n"
                f"{chats_str}\n"
                "</group_messages_delta>"
            )

        event.set_extra(
            "_group_message_flow_pending_cursor",
            {
                "platform_id": event.get_platform_id(),
                "flow_session_id": flow_session_id,
                "conversation_id": req.conversation.cid,
                "last_record_id": next_cursor_id,
            },
        )

    async def _commit_pending_flow_cursor(
        self,
        event: AstrMessageEvent,
        llm_resp: LLMResponse,
    ) -> None:
        if not llm_resp or llm_resp.role == "err":
            return

        pending = event.get_extra("_group_message_flow_pending_cursor")
        if not isinstance(pending, dict):
            return

        platform_id = str(pending.get("platform_id") or "")
        flow_session_id = str(pending.get("flow_session_id") or "")
        conversation_id = str(pending.get("conversation_id") or "")
        last_record_id = int(pending.get("last_record_id") or 0)
        if not platform_id or not flow_session_id or not conversation_id:
            return

        await self.context.group_message_flow_manager.set_cursor(
            platform_id=platform_id,
            flow_session_id=flow_session_id,
            conversation_id=conversation_id,
            last_record_id=last_record_id,
        )

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """当触发 LLM 请求前，调用此方法修改 req"""
        cfg = self.cfg(event)
        if cfg["enable_active_reply"]:
            if event.unified_msg_origin not in self.session_chats:
                return
            chats_str = "\n---\n".join(self.session_chats[event.unified_msg_origin])
            prompt = req.prompt
            req.prompt = (
                f"You are now in a chatroom. The chat history is as follows:\n{chats_str}"
                f"\nNow, a new message is coming: `{prompt}`. "
                "Please react to it. Only output your response and do not output any other information. "
                "You MUST use the SAME language as the chatroom is using."
            )
            req.contexts = []  # 清空上下文，当使用了主动回复，所有聊天记录都在一个prompt中。
        elif self._is_flow_mode(event, cfg):
            await self._inject_flow_delta(event, req, cfg)
        else:
            if event.unified_msg_origin not in self.session_chats:
                return
            chats_str = "\n---\n".join(self.session_chats[event.unified_msg_origin])
            req.system_prompt += (
                "You are now in a chatroom. The chat history is as follows: \n"
            )
            req.system_prompt += chats_str

    async def after_req_llm(
        self, event: AstrMessageEvent, llm_resp: LLMResponse
    ) -> None:
        cfg = self.cfg(event)
        if self._is_flow_mode(event, cfg) and not cfg["enable_active_reply"]:
            await self._commit_pending_flow_cursor(event, llm_resp)
            return
        if event.unified_msg_origin not in self.session_chats:
            return

        if llm_resp.completion_text:
            final_message = f"[You/{datetime.datetime.now().strftime('%H:%M:%S')}]: {llm_resp.completion_text}"
            logger.debug(
                f"Recorded AI response: {event.unified_msg_origin} | {final_message}"
            )
            self._append_sliding_message(event, final_message, cfg["max_cnt"])

    async def record_bot_message(self, event: AstrMessageEvent) -> None:
        cfg = self.cfg(event)
        if not self._is_flow_mode(event, cfg):
            return
        if not cfg["flow_record_bot_messages"]:
            return

        result = event.get_result()
        if not result or not result.chain:
            return
        if result.result_content_type in {
            ResultContentType.LLM_RESULT,
            ResultContentType.STREAMING_RESULT,
            ResultContentType.STREAMING_FINISH,
        }:
            return

        datetime_str = datetime.datetime.now().strftime("%H:%M:%S")
        rendered_text = f"[You/{datetime_str}]: {result.get_plain_text(True)}"
        await self._record_flow_message(
            event,
            rendered_text,
            role="bot",
            content=await self._components_to_dict(result.chain),
        )
