import asyncio
import datetime
import inspect
import json
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

"""
聊天记忆增强 (LTM v2)
"""

CHATROOM_SYSTEM_NOTE = (
    "You are now in a chatroom. "
    "Chat history messages below use the format '[username/time]: content'. "
    "Your own messages are presented via the standard assistant role.\n"
)

MAX_MSGS_PER_USER_SEGMENT = 50
MAX_CHARS_PER_USER_SEGMENT = 3000
MAX_RAW_BYTES = 500_000
DEFAULT_HISTORY_TOOL_RESULT_MAX_CHARS = 8192
SUMMARY_RETRY_COOLDOWN = 5

TOOL_CALL_PREFIX = "<T:CALL>"
TOOL_RES_PREFIX = "<T:RES"
BOT_MARKER = "<BOT/"


class LongTermMemory:
    DEFAULT_MAX_GROUP_MESSAGES = 50
    DEFAULT_GROUP_ICL_TOKEN_BUDGET = 4000

    def __init__(self, acm: AstrBotConfigManager, context: star.Context) -> None:
        self.acm = acm
        self.context = context

        self.session_chats: dict[str, list[str]] = defaultdict(list)
        self._locks: dict[str, asyncio.Lock] = {}

        self.raw_records: dict[str, deque[str]] = defaultdict(deque)
        self._raw_cursor: dict[str, int] = defaultdict(int)
        self.contexts: dict[str, list[dict[str, Any]]] = defaultdict(list)

        self._persisted_tool_call_ids: dict[str, set[str]] = defaultdict(set)
        self._persisted_tool_result_ids: dict[str, set[str]] = defaultdict(set)

        self.summaries: dict[str, str] = defaultdict(str)
        self._summary_next_retry: dict[str, int] = defaultdict(int)
        self._summary_in_progress: set[str] = set()

    def _get_lock(self, umo: str) -> asyncio.Lock:
        lock = self._locks.get(umo)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[umo] = lock
        return lock

    def cfg(self, event: AstrMessageEvent) -> dict[str, Any]:
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        ltm_cfg = cfg["provider_ltm_settings"]

        max_cnt = self._coerce_positive_int(
            ltm_cfg.get("group_message_max_cnt"),
            self.DEFAULT_MAX_GROUP_MESSAGES,
        )
        group_icl_token_budget = self._coerce_positive_int(
            ltm_cfg.get("group_icl_token_budget"),
            self.DEFAULT_GROUP_ICL_TOKEN_BUDGET,
        )
        flow_max_records = self._coerce_non_negative_int(
            ltm_cfg.get("group_flow_max_records"),
            5000,
        )
        flow_max_delta_messages = self._coerce_positive_int(
            ltm_cfg.get("group_flow_max_delta_messages"),
            200,
        )
        flow_max_message_chars = self._coerce_positive_int(
            ltm_cfg.get("group_flow_max_message_chars"),
            1000,
        )

        image_caption_prompt = cfg["provider_settings"].get("image_caption_prompt", "")
        image_caption_provider_id = ltm_cfg.get("image_caption_provider_id", "")
        image_caption = bool(ltm_cfg.get("image_caption")) and bool(
            image_caption_provider_id
        )

        active_reply = ltm_cfg["active_reply"]
        ltm_compaction_strategy = ltm_cfg.get("ltm_compaction_strategy", "truncate")
        ltm_max_rounds = self._coerce_positive_int(ltm_cfg.get("ltm_max_rounds"), 80)
        ltm_truncate_drop_rounds = self._coerce_positive_int(
            ltm_cfg.get("ltm_truncate_drop_rounds"),
            50,
        )
        ltm_summary_trigger_rounds = self._coerce_positive_int(
            ltm_cfg.get("ltm_summary_trigger_rounds"),
            80,
        )
        ltm_summary_keep_recent_rounds = self._coerce_positive_int(
            ltm_cfg.get("ltm_summary_keep_recent_rounds"),
            30,
        )
        history_tool_result_max_chars = self._coerce_positive_int(
            ltm_cfg.get("history_tool_result_max_chars"),
            DEFAULT_HISTORY_TOOL_RESULT_MAX_CHARS,
        )
        ltm_max_msgs_per_user_segment = self._coerce_positive_int(
            ltm_cfg.get("ltm_max_msgs_per_user_segment"),
            MAX_MSGS_PER_USER_SEGMENT,
        )
        ltm_max_chars_per_user_segment = self._coerce_positive_int(
            ltm_cfg.get("ltm_max_chars_per_user_segment"),
            MAX_CHARS_PER_USER_SEGMENT,
        )

        return {
            "group_icl_enable": ltm_cfg.get("group_icl_enable", False),
            "group_context_mode": ltm_cfg.get("group_context_mode", "sliding_window"),
            "max_cnt": max_cnt,
            "group_icl_token_budget": group_icl_token_budget,
            "flow_max_records": flow_max_records,
            "flow_max_delta_messages": flow_max_delta_messages,
            "flow_max_message_chars": flow_max_message_chars,
            "flow_record_bot_messages": ltm_cfg.get(
                "group_flow_record_bot_messages", False
            ),
            "image_caption": image_caption,
            "image_caption_prompt": image_caption_prompt,
            "image_caption_provider_id": image_caption_provider_id,
            "history_tool_result_truncate": ltm_cfg.get(
                "history_tool_result_truncate",
                True,
            ),
            "history_tool_result_max_chars": history_tool_result_max_chars,
            "enable_active_reply": active_reply.get("enable", False),
            "ar_method": active_reply["method"],
            "ar_possibility": active_reply["possibility_reply"],
            "ar_prompt": active_reply.get("prompt", ""),
            "ar_whitelist": active_reply.get("whitelist", []),
            "ltm_compaction_strategy": ltm_compaction_strategy,
            "ltm_max_rounds": ltm_max_rounds,
            "ltm_truncate_drop_rounds": ltm_truncate_drop_rounds,
            "ltm_summary_trigger_rounds": ltm_summary_trigger_rounds,
            "ltm_summary_keep_recent_rounds": ltm_summary_keep_recent_rounds,
            "ltm_summary_provider_id": ltm_cfg.get("ltm_summary_provider_id", ""),
            "ltm_summary_prompt": ltm_cfg.get("ltm_summary_prompt", ""),
            "ltm_raw_records_max_bytes": self._coerce_positive_int(
                ltm_cfg.get("ltm_raw_records_max_bytes"),
                MAX_RAW_BYTES,
            ),
            "ltm_max_msgs_per_user_segment": ltm_max_msgs_per_user_segment,
            "ltm_max_chars_per_user_segment": ltm_max_chars_per_user_segment,
        }

    @staticmethod
    def _coerce_positive_int(value: Any, default: int) -> int:
        try:
            return max(1, int(value if value is not None else default))
        except (TypeError, ValueError) as exc:
            logger.error(exc)
            return max(1, default)

    @staticmethod
    def _coerce_non_negative_int(value: Any, default: int) -> int:
        try:
            return max(0, int(value if value is not None else default))
        except (TypeError, ValueError) as exc:
            logger.error(exc)
            return max(0, default)

    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        chinese_count = len([char for char in text if "\u4e00" <= char <= "\u9fff"])
        other_count = len(text) - chinese_count
        return int(chinese_count * 0.6 + other_count * 0.3)

    def _trim_text_to_token_budget(self, text: str, token_budget: int) -> str:
        marker = "[truncated]\n"
        marker_tokens = self._estimate_text_tokens(marker)
        if self._estimate_text_tokens(text) <= token_budget:
            return text
        if token_budget <= marker_tokens:
            return marker.strip()

        low = 0
        high = len(text)
        best = ""
        target_budget = token_budget - marker_tokens
        while low <= high:
            mid = (low + high) // 2
            candidate = text[-mid:] if mid else ""
            if self._estimate_text_tokens(candidate) <= target_budget:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1

        result = f"{marker}{best}"
        while result and self._estimate_text_tokens(result) > token_budget:
            result = result[:-1]
        return result

    def _build_chats_context(
        self,
        chats: list[str],
        token_budget: int,
    ) -> tuple[str, int, int]:
        separator = "\n---\n"
        separator_tokens = self._estimate_text_tokens(separator)
        selected: list[str] = []
        total_tokens = 0

        for chat in reversed(chats):
            chat_tokens = self._estimate_text_tokens(chat)
            extra_tokens = chat_tokens + (separator_tokens if selected else 0)
            if selected and total_tokens + extra_tokens > token_budget:
                break
            if not selected and chat_tokens > token_budget:
                trimmed = self._trim_text_to_token_budget(chat, token_budget)
                return trimmed, len(chats) - 1, self._estimate_text_tokens(trimmed)
            selected.append(chat)
            total_tokens += extra_tokens

        selected.reverse()
        omitted = len(chats) - len(selected)
        chats_str = separator.join(selected)
        if omitted > 0:
            omitted_notice = (
                f"[{omitted} earlier group messages omitted due to token budget]"
            )
            chats_str = f"{omitted_notice}{separator}{chats_str}"
            total_tokens += (
                self._estimate_text_tokens(omitted_notice) + separator_tokens
            )
        if total_tokens > token_budget:
            chats_str = self._trim_text_to_token_budget(chats_str, token_budget)
            total_tokens = self._estimate_text_tokens(chats_str)
        return chats_str, omitted, total_tokens

    def _is_flow_mode(
        self, event: AstrMessageEvent, cfg: dict[str, Any] | None = None
    ) -> bool:
        cfg = cfg or self.cfg(event)
        return (
            bool(cfg.get("group_icl_enable"))
            and cfg.get("group_context_mode") == "flow"
            and self._message_type(event) == MessageType.GROUP_MESSAGE
        )

    @staticmethod
    def _message_type(event: AstrMessageEvent) -> MessageType | None:
        getter = getattr(event, "get_message_type", None)
        if callable(getter):
            return getter()
        return None

    @staticmethod
    def _event_extra(event: AstrMessageEvent, key: str, default: Any = None) -> Any:
        getter = getattr(event, "get_extra", None)
        if callable(getter):
            return getter(key, default)
        return default

    @staticmethod
    def _set_event_extra(event: AstrMessageEvent, key: str, value: Any) -> None:
        setter = getattr(event, "set_extra", None)
        if callable(setter):
            setter(key, value)

    @staticmethod
    def _call_event_str(event: AstrMessageEvent, name: str, default: str = "") -> str:
        getter = getattr(event, name, None)
        if not callable(getter):
            return default
        value = getter()
        return value if isinstance(value, str) else default

    def _flow_session_id(self, event: AstrMessageEvent) -> str:
        group_id = self._call_event_str(event, "get_group_id")
        if group_id:
            return (
                f"{self._call_event_str(event, 'get_platform_id')}:"
                f"{MessageType.GROUP_MESSAGE.value}:{group_id}"
            )
        return event.unified_msg_origin

    def _append_sliding_message(
        self,
        event: AstrMessageEvent,
        message: str,
        max_cnt: int,
    ) -> None:
        logger.debug("ltm | %s | %s", event.unified_msg_origin, message)
        self.session_chats[event.unified_msg_origin].append(message)
        if len(self.session_chats[event.unified_msg_origin]) > max_cnt:
            self.session_chats[event.unified_msg_origin].pop(0)

    async def remove_session(self, event: AstrMessageEvent) -> int:
        umo = event.unified_msg_origin
        cnt = 0
        if umo in self.session_chats:
            cnt = len(self.session_chats[umo])
            del self.session_chats[umo]

        if self._is_flow_mode(event):
            await self.reset_flow_cursor(event)

        async with self._get_lock(umo):
            cnt = max(cnt, len(self.raw_records.get(umo, deque())))
            self.raw_records.pop(umo, None)
            self.contexts.pop(umo, None)
            self._raw_cursor.pop(umo, None)
            self._persisted_tool_call_ids.pop(umo, None)
            self._persisted_tool_result_ids.pop(umo, None)
            self._summary_next_retry.pop(umo, None)
            self.summaries.pop(umo, None)
            self._summary_in_progress.discard(umo)
        return cnt

    async def reset_flow_cursor(self, event: AstrMessageEvent) -> None:
        conversation_manager = getattr(self.context, "conversation_manager", None)
        flow_manager = getattr(self.context, "group_message_flow_manager", None)
        if conversation_manager is None or flow_manager is None:
            return

        curr_cid = await conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
        if not curr_cid:
            return

        flow_session_id = self._flow_session_id(event)
        latest_id = await flow_manager.get_latest_record_id(flow_session_id)
        await flow_manager.set_cursor(
            platform_id=self._call_event_str(event, "get_platform_id"),
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

    async def need_active_reply(self, event: AstrMessageEvent) -> bool:
        cfg = self.cfg(event)
        if not cfg["enable_active_reply"]:
            return False
        if self._message_type(event) != MessageType.GROUP_MESSAGE:
            return False
        if event.is_at_or_wake_command:
            return False
        if cfg["ar_whitelist"] and (
            event.unified_msg_origin not in cfg["ar_whitelist"]
            and (
                self._call_event_str(event, "get_group_id")
                and self._call_event_str(event, "get_group_id")
                not in cfg["ar_whitelist"]
            )
        ):
            return False
        match cfg["ar_method"]:
            case "possibility_reply":
                return random.random() < cfg["ar_possibility"]
        return False

    async def _render_group_message(
        self,
        event: AstrMessageEvent,
        cfg: dict[str, Any],
        sender_name: str | None = None,
    ) -> str:
        datetime_str = datetime.datetime.now().strftime("%H:%M:%S")
        display_name = sender_name or self._resolve_sender_name(event)
        parts = [f"[{display_name}/{datetime_str}]: "]

        for comp in event.get_messages():
            if isinstance(comp, Plain):
                parts.append(f" {comp.text}")
            elif isinstance(comp, Image):
                if cfg["image_caption"]:
                    logger.warning(
                        "Group ICL image caption is enabled. umo=%s, provider=%s",
                        event.unified_msg_origin,
                        cfg["image_caption_provider_id"],
                    )
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
                    except Exception as exc:
                        logger.error("获取图片描述失败: %s", exc)
                        parts.append(" [Image]")
                else:
                    parts.append(" [Image]")
            elif isinstance(comp, At):
                parts.append(f" [At: {comp.name or comp.qq}]")
            else:
                comp_type = getattr(comp, "type", comp.__class__.__name__)
                parts.append(f" [{comp_type}]")

        return "".join(parts)

    @staticmethod
    def _resolve_sender_name(event: AstrMessageEvent) -> str:
        get_sender_name = getattr(event, "get_sender_name", None)
        if callable(get_sender_name):
            sender_name = get_sender_name()
            if isinstance(sender_name, str) and sender_name:
                return sender_name

        message_obj = getattr(event, "message_obj", None)
        sender = getattr(message_obj, "sender", None)
        nickname = getattr(sender, "nickname", None)
        if isinstance(nickname, str) and nickname:
            return nickname

        get_sender_id = getattr(event, "get_sender_id", None)
        if callable(get_sender_id):
            sender_id = get_sender_id()
            if isinstance(sender_id, str) and sender_id:
                return sender_id
        return "unknown"

    async def _components_to_dict(self, components: list[Any]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        for comp in components:
            try:
                content.append(await self._component_to_json_safe_dict(comp))
            except Exception as exc:
                logger.warning(
                    "Failed to serialize group flow message component: %s",
                    exc,
                )
        return content

    async def _component_to_json_safe_dict(self, comp: Any) -> dict[str, Any]:
        if hasattr(comp, "to_dict"):
            data = comp.to_dict()
            if inspect.isawaitable(data):
                data = await data
        elif hasattr(comp, "toDict"):
            data = comp.toDict()
        else:
            data = {"type": comp.__class__.__name__, "data": {}}
        value = await self._json_safe(data)
        return value if isinstance(value, dict) else {"value": value}

    async def _json_safe(self, value: Any) -> Any:
        if hasattr(value, "to_dict"):
            return await self._component_to_json_safe_dict(value)
        if hasattr(value, "toDict"):
            return await self._json_safe(value.toDict())
        if isinstance(value, dict):
            return {key: await self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [await self._json_safe(item) for item in value]
        return value

    async def _message_content_to_dict(
        self,
        event: AstrMessageEvent,
    ) -> list[dict[str, Any]]:
        return await self._components_to_dict(event.get_messages())

    @staticmethod
    def _truncate_flow_message_text(message: str, max_chars: int) -> str:
        if max_chars <= 0:
            return message
        return message[:max_chars]

    async def _record_flow_message(
        self,
        event: AstrMessageEvent,
        rendered_text: str,
        role: str = "user",
        content: list[dict[str, Any]] | None = None,
    ) -> int | None:
        cfg = self.cfg(event)
        if not self._is_flow_mode(event, cfg):
            return None
        flow_manager = getattr(self.context, "group_message_flow_manager", None)
        if flow_manager is None:
            return None

        flow_session_id = self._flow_session_id(event)
        record = await flow_manager.insert_record(
            platform_id=self._call_event_str(event, "get_platform_id"),
            flow_session_id=flow_session_id,
            group_id=self._call_event_str(event, "get_group_id") or None,
            sender_id=(
                self._call_event_str(event, "get_sender_id")
                if role == "user"
                else self._call_event_str(event, "get_self_id")
            ),
            sender_name=self._resolve_sender_name(event) if role == "user" else "You",
            role=role,
            content=content
            if content is not None
            else await self._message_content_to_dict(event),
            rendered_text=rendered_text,
        )
        await flow_manager.prune_records(flow_session_id, cfg["flow_max_records"])
        return record.id

    async def handle_message(self, event: AstrMessageEvent) -> None:
        if self._message_type(event) != MessageType.GROUP_MESSAGE:
            return

        cfg = self.cfg(event)
        final_message = await self._render_group_message(event, cfg)

        if cfg["enable_active_reply"] or not self._is_flow_mode(event, cfg):
            self._append_sliding_message(event, final_message, cfg["max_cnt"])

        if self._is_flow_mode(event, cfg):
            record_id = await self._record_flow_message(event, final_message)
            if record_id:
                self._set_event_extra(event, "_group_message_flow_record_id", record_id)
            return

        umo = event.unified_msg_origin
        async with self._get_lock(umo):
            raw_idx = len(self.raw_records[umo])
            self._set_event_extra(event, "_ltm_raw_idx", raw_idx)
            self.raw_records[umo].append(final_message)
            self._trim_raw_records(
                umo,
                max_bytes=cfg.get("ltm_raw_records_max_bytes", MAX_RAW_BYTES),
            )

    async def _inject_flow_delta(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        cfg: dict[str, Any],
    ) -> None:
        if not req.conversation:
            return
        flow_manager = getattr(self.context, "group_message_flow_manager", None)
        if flow_manager is None:
            return

        flow_session_id = self._flow_session_id(event)
        cursor = await flow_manager.get_cursor(flow_session_id, req.conversation.cid)
        after_id = cursor.last_record_id if cursor else 0
        current_record_id = self._event_extra(event, "_group_message_flow_record_id")
        if isinstance(current_record_id, int) and current_record_id > 0:
            before_id = current_record_id
            next_cursor_id = current_record_id
        else:
            before_id = None
            next_cursor_id = await flow_manager.get_latest_record_id(flow_session_id)

        records = await flow_manager.get_records_after(
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

        self._set_event_extra(
            event,
            "_group_message_flow_pending_cursor",
            {
                "platform_id": self._call_event_str(event, "get_platform_id"),
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

        pending = self._event_extra(event, "_group_message_flow_pending_cursor")
        if not isinstance(pending, dict):
            return

        platform_id = str(pending.get("platform_id") or "")
        flow_session_id = str(pending.get("flow_session_id") or "")
        conversation_id = str(pending.get("conversation_id") or "")
        last_record_id = int(pending.get("last_record_id") or 0)
        if not platform_id or not flow_session_id or not conversation_id:
            return

        flow_manager = getattr(self.context, "group_message_flow_manager", None)
        if flow_manager is None:
            return
        await flow_manager.set_cursor(
            platform_id=platform_id,
            flow_session_id=flow_session_id,
            conversation_id=conversation_id,
            last_record_id=last_record_id,
        )

    async def after_req_llm(
        self,
        event: AstrMessageEvent,
        llm_resp: LLMResponse,
    ) -> None:
        await self._commit_pending_flow_cursor(event, llm_resp)

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        cfg = self.cfg(event)
        umo = event.unified_msg_origin

        if cfg["enable_active_reply"]:
            if umo not in self.session_chats:
                return
            chats_str, omitted, estimated_tokens = self._build_chats_context(
                self.session_chats[umo],
                cfg["group_icl_token_budget"],
            )
            self._log_omitted_context(event, omitted, estimated_tokens, cfg)
            prompt = req.prompt
            req.prompt = (
                f"You are now in a chatroom. The chat history is as follows:\n{chats_str}"
                f"\nNow, a new message is coming: `{prompt}`. "
                "Please react to it. Only output your response and do not output any other information. "
                "You MUST use the SAME language as the chatroom is using."
            )
            req.contexts = []
            return

        if self._is_flow_mode(event, cfg):
            await self._inject_flow_delta(event, req, cfg)
            return

        prompt_idx = self._event_extra(event, "_ltm_raw_idx", -1)
        if isinstance(prompt_idx, int) and prompt_idx >= 0 and umo in self.raw_records:
            async with self._get_lock(umo):
                raw_list = list(self.raw_records[umo])
                cursor = self._raw_cursor[umo]
                new_raw = raw_list[cursor:prompt_idx] if prompt_idx > cursor else []

                if new_raw:
                    new_segs = _build_segments(
                        new_raw,
                        cfg["ltm_max_msgs_per_user_segment"],
                        cfg["ltm_max_chars_per_user_segment"],
                    )
                    self.contexts[umo].extend(new_segs)
                    self._raw_cursor[umo] = prompt_idx

                ctxs: list[dict[str, Any]] = list(req.contexts or [])
                summary = self.summaries.get(umo, "")
                if summary:
                    ctxs.append(
                        {
                            "role": "system",
                            "content": (
                                "[System note: The following is a compressed summary of "
                                "older messages in this group chat, generated to help you "
                                "maintain context. Prioritise facts from recent verbatim "
                                "messages over this summary if they conflict.]\n"
                                "--- BEGIN GROUP CHAT MEMORY SUMMARY ---\n"
                                + summary
                                + "\n--- END GROUP CHAT MEMORY SUMMARY ---"
                            ),
                        }
                    )

                ctxs.extend(self.contexts[umo])
                req.contexts = ctxs
                req.conversation = None
                if CHATROOM_SYSTEM_NOTE not in req.system_prompt:
                    req.system_prompt += CHATROOM_SYSTEM_NOTE
            return

        if umo in self.session_chats:
            chats_str, omitted, estimated_tokens = self._build_chats_context(
                self.session_chats[umo],
                cfg["group_icl_token_budget"],
            )
            self._log_omitted_context(event, omitted, estimated_tokens, cfg)
            req.extra_user_content_parts.append(
                TextPart(
                    text=(
                        "Use the following recent group chat context only as background "
                        "for this request.\n"
                        "[Group Chat Context]\n"
                        "Recent group chat messages, newest messages are kept when truncated:\n"
                        f"{chats_str}"
                    )
                ).mark_as_temp()
            )

    def _log_omitted_context(
        self,
        event: AstrMessageEvent,
        omitted: int,
        estimated_tokens: int,
        cfg: dict[str, Any],
    ) -> None:
        if omitted <= 0:
            return
        logger.warning(
            "Group ICL context truncated by token budget. umo=%s, omitted=%s, estimated_tokens=%s, budget=%s",
            event.unified_msg_origin,
            omitted,
            estimated_tokens,
            cfg["group_icl_token_budget"],
        )

    async def on_agent_done(
        self,
        event: AstrMessageEvent,
        run_context: Any,
        resp: LLMResponse | None,
    ) -> None:
        cfg = self.cfg(event)
        if self._is_flow_mode(event, cfg) and not cfg["enable_active_reply"]:
            if resp is not None:
                await self._commit_pending_flow_cursor(event, resp)
            return

        umo = event.unified_msg_origin
        compact_ctx: dict[str, Any] | None = None

        async with self._get_lock(umo):
            if umo not in self.raw_records:
                return

            time_str = datetime.datetime.now().strftime("%H:%M:%S")
            for msg in getattr(run_context, "messages", []):
                if msg.role == "assistant" and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tc_dict = tc if isinstance(tc, dict) else tc.model_dump()
                        tc_id = tc_dict["id"]
                        if tc_id in self._persisted_tool_call_ids[umo]:
                            continue
                        self._persisted_tool_call_ids[umo].add(tc_id)
                        args = tc_dict["function"]["arguments"]
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except (json.JSONDecodeError, TypeError):
                                pass
                        call_entry = {
                            "id": tc_id,
                            "name": tc_dict["function"]["name"],
                            "args": args,
                        }
                        self.raw_records[umo].append(
                            f"<T:CALL>{json.dumps(call_entry, ensure_ascii=False)}</T:CALL>"
                        )
                elif msg.role == "tool":
                    tool_call_id = msg.tool_call_id
                    if tool_call_id in self._persisted_tool_result_ids[umo]:
                        continue
                    self._persisted_tool_result_ids[umo].add(tool_call_id)
                    content = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )
                    if cfg["history_tool_result_truncate"]:
                        content = _truncate_tool_result_for_history(
                            content,
                            cfg["history_tool_result_max_chars"],
                        )
                    self.raw_records[umo].append(
                        f"<T:RES id={tool_call_id}>{content}</T:RES>"
                    )

            if resp and resp.completion_text:
                self.raw_records[umo].append(
                    f"<BOT/{time_str}>: {resp.completion_text}"
                )

            raw_list = list(self.raw_records[umo])
            cursor = self._raw_cursor[umo]
            remaining = raw_list[cursor:]
            if remaining:
                new_segs = _build_segments(
                    remaining,
                    cfg["ltm_max_msgs_per_user_segment"],
                    cfg["ltm_max_chars_per_user_segment"],
                )
                self.contexts[umo].extend(new_segs)
                self._raw_cursor[umo] = len(raw_list)

            rounds = _split_into_rounds(self.contexts[umo])
            strategy = cfg.get("ltm_compaction_strategy", "truncate")
            if strategy == "llm_summary":
                compact_ctx = self._prepare_summary_compaction(umo, cfg, rounds)
            else:
                self._apply_truncate_compaction(umo, cfg, rounds)

            if not compact_ctx:
                self._trim_raw_records(
                    umo,
                    max_bytes=cfg.get("ltm_raw_records_max_bytes", MAX_RAW_BYTES),
                )

        if compact_ctx:
            logger.info(
                "LTM summary: starting compaction (umo=%s, rounds=%d, old=%d)",
                umo,
                compact_ctx["snapshot_round_count"],
                len(compact_ctx["old_rounds"]),
            )
            compact_ctx["summary_text"] = await self._generate_llm_summary(
                umo,
                compact_ctx,
            )
            async with self._get_lock(umo):
                self._apply_llm_summary(umo, compact_ctx)
                self._trim_raw_records(
                    umo,
                    max_bytes=cfg.get("ltm_raw_records_max_bytes", MAX_RAW_BYTES),
                )
                self._summary_in_progress.discard(umo)

    def _prepare_summary_compaction(
        self,
        umo: str,
        cfg: dict[str, Any],
        rounds: list[list[dict[str, Any]]],
    ) -> dict[str, Any] | None:
        trigger = cfg.get("ltm_summary_trigger_rounds", 80)
        if len(rounds) <= trigger or umo in self._summary_in_progress:
            return None

        provider_id = cfg.get("ltm_summary_provider_id", "")
        provider = (
            self.context.get_provider_by_id(provider_id)
            if provider_id
            else self.context.get_using_provider(umo)
        )
        if provider is None or not isinstance(provider, Provider):
            logger.warning(
                "LTM summary 没有可用的 provider (umo=%s, configured=%s)",
                umo,
                provider_id or "(auto)",
            )
            return None

        next_retry = self._summary_next_retry.get(umo, 0)
        if len(rounds) < next_retry:
            logger.debug(
                "LTM summary 冷却中 (umo=%s, rounds=%d, 允许=%d)",
                umo,
                len(rounds),
                next_retry,
            )
            return None

        keep_recent = cfg.get("ltm_summary_keep_recent_rounds", 30)
        old_rounds = rounds[:-keep_recent]
        recent_rounds = rounds[-keep_recent:]
        if not old_rounds:
            return None

        self._summary_in_progress.add(umo)
        return {
            "provider": provider,
            "prompt": cfg.get("ltm_summary_prompt", ""),
            "old_rounds": old_rounds,
            "recent_rounds": recent_rounds,
            "existing_summary": self.summaries.get(umo, ""),
            "snapshot_round_count": len(rounds),
        }

    def _apply_truncate_compaction(
        self,
        umo: str,
        cfg: dict[str, Any],
        rounds: list[list[dict[str, Any]]],
    ) -> None:
        max_rounds = cfg.get("ltm_max_rounds", 80)
        drop_rounds = cfg.get("ltm_truncate_drop_rounds", 50)
        if len(rounds) <= max_rounds:
            return
        safe_drop = min(drop_rounds, len(rounds) - 1)
        kept = rounds[safe_drop:]
        self.contexts[umo] = [seg for rnd in kept for seg in rnd]

    async def _generate_llm_summary(self, umo: str, ctx: dict[str, Any]) -> str | None:
        if not ctx.get("old_rounds"):
            return None

        old_text = _rounds_to_text(ctx["old_rounds"])
        existing_summary = ctx["existing_summary"]
        instruction = ctx["prompt"] or (
            "Merge the older conversation rounds below into the existing "
            "group-chat memory summary. "
            "Preserve: user identities (names, nicknames, roles), recurring topics, "
            "decisions made, preferences expressed, and unresolved tasks or questions. "
            "Drop: transient greetings, small talk, and redundant confirmations. "
            "Keep the summary concise and factual. "
            "Output only the updated summary text, with no preamble or meta-commentary."
        )
        summary_prompt = (
            f"{instruction}\n\n"
            f"Existing memory summary:\n{existing_summary or '(none)'}\n\n"
            "--- BEGIN OLDER CONVERSATION ROUNDS ---\n"
            f"{old_text}\n"
            "--- END OLDER CONVERSATION ROUNDS ---"
        )

        try:
            resp = await ctx["provider"].text_chat(
                prompt=summary_prompt,
                session_id=uuid.uuid4().hex,
                persist=False,
            )
            summary_text = resp.completion_text.strip()
            if not summary_text:
                logger.warning(
                    "LTM LLM summary 返回空文本，跳过本次压缩 (umo=%s, provider=%s)",
                    umo,
                    ctx["provider"],
                )
                return None
            logger.info(
                "LTM summary: compaction completed (umo=%s, summary_len=%d)",
                umo,
                len(summary_text),
            )
            return summary_text
        except Exception:
            logger.warning("LTM LLM summary 失败，保留原始 contexts", exc_info=True)
            return None

    def _apply_llm_summary(self, umo: str, ctx: dict[str, Any]) -> None:
        summary_text = ctx.get("summary_text")
        if not summary_text:
            current_rounds = _split_into_rounds(self.contexts[umo])
            self._summary_next_retry[umo] = len(current_rounds) + SUMMARY_RETRY_COOLDOWN
            return

        self.summaries[umo] = summary_text
        current_rounds = _split_into_rounds(self.contexts[umo])
        snapshot_count = ctx["snapshot_round_count"]
        new_rounds = current_rounds[snapshot_count:]
        self.contexts[umo] = [seg for rnd in ctx["recent_rounds"] for seg in rnd] + [
            seg for rnd in new_rounds for seg in rnd
        ]
        self._summary_next_retry.pop(umo, None)

    def _trim_raw_records(self, umo: str, max_bytes: int = MAX_RAW_BYTES) -> None:
        dq = self.raw_records[umo]
        cursor = self._raw_cursor[umo]

        while dq and cursor > 0:
            dq.popleft()
            cursor -= 1
        self._raw_cursor[umo] = cursor

        total = sum(len(item) for item in dq)
        while total > max_bytes and dq:
            removed = dq.popleft()
            total -= len(removed)
            if cursor > 0:
                cursor -= 1
        self._raw_cursor[umo] = max(0, cursor)

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


def _build_segments(
    raw_lines: list[str],
    max_msgs_per_user_segment: int = MAX_MSGS_PER_USER_SEGMENT,
    max_chars_per_user_segment: int = MAX_CHARS_PER_USER_SEGMENT,
) -> list[dict[str, Any]]:
    if not raw_lines:
        return []

    segments: list[dict[str, Any]] = []
    user_buf: list[str] = []
    tool_calls_buf: list[dict[str, Any]] = []

    def flush_user() -> None:
        if not user_buf:
            return
        truncated = _truncate_user_segment(
            user_buf,
            max_msgs_per_user_segment,
            max_chars_per_user_segment,
        )
        segments.append({"role": "user", "content": "\n".join(truncated)})
        user_buf.clear()

    def flush_tool_calls() -> None:
        if not tool_calls_buf:
            return
        segments.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls_buf.copy(),
            }
        )
        tool_calls_buf.clear()

    for line in raw_lines:
        if line.startswith(TOOL_CALL_PREFIX):
            flush_user()
            tool_call = _parse_tool_call(line)
            if tool_call:
                tool_calls_buf.append(tool_call)
            else:
                user_buf.append(line)
        elif line.startswith(TOOL_RES_PREFIX):
            flush_user()
            flush_tool_calls()
            tool_result = _parse_tool_result(line)
            if tool_result:
                segments.append(tool_result)
            else:
                user_buf.append(line)
        elif line.startswith(BOT_MARKER):
            flush_user()
            flush_tool_calls()
            content = _extract_bot_content(line)
            if content is not None:
                segments.append({"role": "assistant", "content": content})
            else:
                user_buf.append(line)
        else:
            user_buf.append(line)

    flush_user()
    flush_tool_calls()
    return segments


def _parse_tool_call(line: str) -> dict[str, Any] | None:
    inner = _extract_tag_content(line, TOOL_CALL_PREFIX, "</T:CALL>")
    if not inner:
        return None
    try:
        tool_call = json.loads(inner)
        if not isinstance(tool_call, dict):
            return None
        tool_call_id = tool_call["id"]
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
    return {
        "id": tool_call_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(tool_args, ensure_ascii=False),
        },
    }


def _parse_tool_result(line: str) -> dict[str, str] | None:
    rest = line[len(TOOL_RES_PREFIX) :].strip()
    gt = rest.find(">")
    if gt == -1:
        return None
    id_part = rest[:gt]
    content = rest[gt + 1 :]
    if content.endswith("</T:RES>"):
        content = content[: -len("</T:RES>")]
    if not id_part.startswith("id="):
        return None
    tool_call_id = id_part[3:]
    if not tool_call_id:
        return None
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _truncate_tool_result_for_history(content: str, max_chars: int) -> str:
    if max_chars <= 0 or len(content) <= max_chars:
        return content

    omitted = len(content) - max_chars
    marker = f"\n...[TRUNCATED {omitted} chars]..."
    if len(marker) >= max_chars:
        return content[:max_chars]
    return content[: max_chars - len(marker)] + marker


def _extract_bot_content(line: str) -> str | None:
    idx = line.find(">: ")
    if idx == -1:
        return None
    return line[idx + 3 :].strip()


def _extract_tag_content(line: str, start_tag: str, end_tag: str) -> str | None:
    if not line.startswith(start_tag) or not line.endswith(end_tag):
        return None
    return line[len(start_tag) : -len(end_tag)].strip()


def _truncate_user_segment(
    lines: list[str],
    max_msgs: int = MAX_MSGS_PER_USER_SEGMENT,
    max_chars: int = MAX_CHARS_PER_USER_SEGMENT,
) -> list[str]:
    result: list[str] = []
    total = 0
    for line in reversed(lines):
        if len(result) >= max_msgs:
            break
        if total + len(line) > max_chars and result:
            break
        result.append(line)
        total += len(line) + 1
    result.reverse()
    return result


def _split_into_rounds(contexts: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    rounds: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for segment in contexts:
        if segment.get("role") == "user" and current:
            rounds.append(current)
            current = []
        current.append(segment)
    if current:
        rounds.append(current)
    return rounds


def _rounds_to_text(rounds: list[list[dict[str, Any]]]) -> str:
    lines: list[str] = []
    for index, round_segments in enumerate(rounds, 1):
        lines.append(f"--- Round {index} ---")
        for segment in round_segments:
            role = segment.get("role", "?")
            content = segment.get("content") or segment.get("tool_calls") or ""
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)
            lines.append(f"[{role}] {content}")
    return "\n".join(lines)
