import asyncio
import datetime
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
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager

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
        image_caption_prompt = cfg["provider_settings"]["image_caption_prompt"]
        image_caption_provider_id = ltm_cfg.get("image_caption_provider_id")
        image_caption = ltm_cfg["image_caption"] and bool(image_caption_provider_id)
        history_tool_result_truncate = ltm_cfg.get("history_tool_result_truncate", True)
        history_tool_result_max_chars = int(
            ltm_cfg.get(
                "history_tool_result_max_chars",
                DEFAULT_HISTORY_TOOL_RESULT_MAX_CHARS,
            )
            or DEFAULT_HISTORY_TOOL_RESULT_MAX_CHARS
        )
        active_reply = ltm_cfg["active_reply"]
        enable_active_reply = active_reply.get("enable", False)
        ar_method = active_reply["method"]
        ar_possibility = active_reply["possibility_reply"]
        ar_prompt = active_reply.get("prompt", "")
        ar_whitelist = active_reply.get("whitelist", [])
        # LTM compaction
        ltm_compaction_strategy = ltm_cfg.get("ltm_compaction_strategy", "truncate")
        ltm_max_rounds = ltm_cfg.get("ltm_max_rounds", 80)
        ltm_truncate_drop_rounds = ltm_cfg.get("ltm_truncate_drop_rounds", 50)
        ltm_summary_trigger_rounds = ltm_cfg.get("ltm_summary_trigger_rounds", 80)
        ltm_summary_keep_recent_rounds = ltm_cfg.get(
            "ltm_summary_keep_recent_rounds", 30
        )
        ltm_summary_provider_id = ltm_cfg.get("ltm_summary_provider_id", "")
        ltm_summary_prompt = ltm_cfg.get("ltm_summary_prompt", "")
        return {
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
        }

    # =========================================================================
    # 图片描述
    # =========================================================================

    async def get_image_caption(
        self,
        image_url: str,
        image_caption_provider_id: str,
        image_caption_prompt: str,
    ) -> str:
        if not image_caption_provider_id:
            provider = self.context.get_using_provider()
        else:
            provider = self.context.get_provider_by_id(image_caption_provider_id)
            if not provider:
                raise Exception(f"没有找到 ID 为 {image_caption_provider_id} 的提供商")
        if not isinstance(provider, Provider):
            raise Exception(f"提供商类型错误({type(provider)})，无法获取图片描述")
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

    # =========================================================================
    # 会话清理
    # =========================================================================

    async def remove_session(self, event: AstrMessageEvent) -> int:
        """清理指定群的全部 LTM 状态。返回被清理的 raw_records 条数。"""
        umo = event.unified_msg_origin
        async with self._get_lock(umo):
            cnt = len(self.raw_records.get(umo, deque()))
            self.raw_records.pop(umo, None)
            self.contexts.pop(umo, None)
            self._raw_cursor.pop(umo, None)
            self._persisted_tool_call_ids.pop(umo, None)
            self._persisted_tool_result_ids.pop(umo, None)
            self._summary_next_retry.pop(umo, None)
            self.summaries.pop(umo, None)
            self._locks.pop(umo, None)
            return cnt

    # =========================================================================
    # 消息记录 (on_message 调用)
    # =========================================================================

    async def handle_message(self, event: AstrMessageEvent) -> None:
        """仅记录原始消息到 raw_records，不构建 contexts。"""
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return

        umo = event.unified_msg_origin
        async with self._get_lock(umo):
            # 记录写入前索引 → on_req_llm 精确排除
            raw_idx = len(self.raw_records[umo])
            event.set_extra("_ltm_raw_idx", raw_idx)

            datetime_str = datetime.datetime.now().strftime("%H:%M:%S")
            parts = [f"[{event.message_obj.sender.nickname}/{datetime_str}]: "]
            cfg = self.cfg(event)

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
                    else:
                        parts.append(" [Image]")
                elif isinstance(comp, At):
                    parts.append(f" [At: {comp.name}]")

            final_message = "".join(parts)
            logger.debug(f"ltm | {umo} | {final_message}")
            self.raw_records[umo].append(final_message)

    # =========================================================================
    # LLM 请求前（on_llm_request 钩子 → decorate_llm_req 调用）
    # =========================================================================

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """增量构建 contexts 并注入到 req。ContextManager 由 agent runner 自动调用。"""
        umo = event.unified_msg_origin
        prompt_idx = event.get_extra("_ltm_raw_idx", -1)
        if prompt_idx < 0:
            return

        async with self._get_lock(umo):
            if umo not in self.raw_records:
                return

            raw_list = list(self.raw_records[umo])
            cursor = self._raw_cursor[umo]
            new_raw = raw_list[cursor:prompt_idx] if prompt_idx > cursor else []

            if new_raw:
                new_segs = _build_segments(new_raw)
                self.contexts[umo].extend(new_segs)
                self._raw_cursor[umo] = prompt_idx

            # 前置保留 Persona 已注入的 begin_dialogs
            existing_contexts = req.contexts or []
            ctxs: list[dict] = list(existing_contexts)

            # Inject LTM summary if available (LLM summary compaction strategy).
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

    # =========================================================================
    # Agent 完成后（on_agent_done 钩子 → main.py 调用）
    # =========================================================================

    async def on_agent_done(
        self,
        event: AstrMessageEvent,
        run_context,  # ContextWrapper
        resp: LLMResponse,
    ) -> None:
        """记录工具链 + bot 回复到 raw_records，闭合段，裁剪。"""
        umo = event.unified_msg_origin
        cfg = self.cfg(event)

        async with self._get_lock(umo):
            if umo not in self.raw_records:
                return

            time_str = datetime.datetime.now().strftime("%H:%M:%S")

            # 1. 提取工具链 → raw_records（按 tool_call_id 去重，避免历史重复注入）
            for msg in run_context.messages:
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
                                pass  # keep raw string if JSON is malformed
                        call_entry = {
                            "id": tc_id,
                            "name": tc_dict["function"]["name"],
                            "args": args,
                        }
                        self.raw_records[umo].append(
                            f"<T:CALL>{json.dumps(call_entry, ensure_ascii=False)}</T:CALL>"
                        )
                elif msg.role == "tool":
                    if msg.tool_call_id in self._persisted_tool_result_ids[umo]:
                        continue
                    self._persisted_tool_result_ids[umo].add(msg.tool_call_id)
                    content = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )
                    if cfg["history_tool_result_truncate"]:
                        content = _truncate_tool_result_for_history(
                            content, cfg["history_tool_result_max_chars"]
                        )
                    self.raw_records[umo].append(
                        f"<T:RES id={msg.tool_call_id}>{content}</T:RES>"
                    )

            # 最终文本回复
            if resp and resp.completion_text:
                self.raw_records[umo].append(
                    f"<BOT/{time_str}>: {resp.completion_text}"
                )

            # 2. 构建本轮全部未消费 raw 为 contexts 段（含 @bot prompt）
            raw_list = list(self.raw_records[umo])
            cursor = self._raw_cursor[umo]
            remaining = raw_list[cursor:]  # 从 prompt_idx 开始，含 @bot 行
            if remaining:
                new_segs = _build_segments(remaining)
                self.contexts[umo].extend(new_segs)
                self._raw_cursor[umo] = len(raw_list)

            # 2b. LTM persistent compaction — either turn-based truncation OR
            # LLM summary, mutually exclusive.  Both use high-water / low-water
            # to avoid per-round churn.
            strategy = cfg.get("ltm_compaction_strategy", "truncate")
            rounds = _split_into_rounds(self.contexts[umo])

            if strategy == "llm_summary":
                provider_id = cfg.get("ltm_summary_provider_id", "")
                trigger = cfg.get("ltm_summary_trigger_rounds", 80)
                keep_recent = cfg.get("ltm_summary_keep_recent_rounds", 30)
                if len(rounds) > trigger:
                    # Resolve provider: explicit ID first, fallback to
                    # current chat model for this group (umo).
                    if provider_id:
                        provider = self.context.get_provider_by_id(provider_id)
                    else:
                        provider = self.context.get_using_provider(umo)
                    if provider is None or not isinstance(provider, Provider):
                        logger.warning(
                            "LTM summary 没有可用的 provider (umo=%s, configured=%s)",
                            umo,
                            provider_id or "(auto)",
                        )
                    else:
                        next_retry = self._summary_next_retry.get(umo, 0)
                        if len(rounds) < next_retry:
                            logger.debug(
                                "LTM summary 冷却中 (umo=%s, rounds=%d, 允许=%d)",
                                umo,
                                len(rounds),
                                next_retry,
                            )
                        else:
                            await self._compact_with_llm_summary(
                                event,
                                provider,
                                keep_recent,
                                cfg.get("ltm_summary_prompt", ""),
                                rounds,
                            )
            else:
                max_rounds = cfg.get("ltm_max_rounds", 80)
                drop_rounds = cfg.get("ltm_truncate_drop_rounds", 50)
                if len(rounds) > max_rounds:
                    safe_drop = min(drop_rounds, len(rounds) - 1)
                    kept = rounds[safe_drop:]
                    self.contexts[umo] = [seg for rnd in kept for seg in rnd]

            # 3. 裁剪 raw_records
            self._trim_raw_records(
                umo, max_bytes=cfg.get("ltm_raw_records_max_bytes", MAX_RAW_BYTES)
            )

    # =========================================================================
    # LTM compaction
    # =========================================================================

    async def _compact_with_llm_summary(
        self,
        event: AstrMessageEvent,
        provider: Provider,
        keep_recent: int,
        prompt: str,
        rounds: list[list[dict]],
    ) -> None:
        """Compress old rounds into a persistent summary using an LLM."""
        umo = event.unified_msg_origin
        old_rounds = rounds[:-keep_recent]
        recent_rounds = rounds[-keep_recent:]
        if not old_rounds:
            return

        old_text = _rounds_to_text(old_rounds)
        existing_summary = self.summaries.get(umo, "")

        logger.info(
            "LTM summary: starting compaction (umo=%s, rounds=%d, old=%d)",
            umo,
            len(rounds),
            len(old_rounds),
        )

        instruction = prompt or (
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
            resp = await provider.text_chat(
                prompt=summary_prompt,
                session_id=uuid.uuid4().hex,
                persist=False,
            )
            summary_text = resp.completion_text.strip()
            if not summary_text:
                logger.warning(
                    "LTM LLM summary 返回空文本，跳过本次压缩 (umo=%s, provider=%s)",
                    umo,
                    provider,
                )
                self._summary_next_retry[umo] = len(rounds) + SUMMARY_RETRY_COOLDOWN
                return
            self.summaries[umo] = summary_text
            self.contexts[umo] = [seg for rnd in recent_rounds for seg in rnd]
            self._summary_next_retry.pop(umo, None)
            logger.info(
                "LTM summary: compaction completed (umo=%s, summary_len=%d)",
                umo,
                len(summary_text),
            )
        except Exception:
            logger.warning("LTM LLM summary 失败，保留原始 contexts", exc_info=True)
            self._summary_next_retry[umo] = len(rounds) + SUMMARY_RETRY_COOLDOWN

    # =========================================================================
    # 裁剪
    # =========================================================================

    def _trim_raw_records(self, umo: str, max_bytes: int = MAX_RAW_BYTES) -> None:
        """仅淘汰 cursor 之前的条目。cursor 之后的绝不碰。"""
        dq = self.raw_records[umo]
        cursor = self._raw_cursor[umo]

        # 1. 无条件清除 cursor 之前的条目（已消费）
        while dq and cursor > 0:
            dq.popleft()
            cursor -= 1
        self._raw_cursor[umo] = cursor

        # 2. 按大小继续从前面淘汰（限制极端情况的总内存）
        total = sum(len(s.encode()) for s in dq)
        while total > max_bytes and dq:
            removed = dq.popleft()
            total -= len(removed.encode())
            if cursor > 0:
                cursor -= 1
        self._raw_cursor[umo] = max(0, cursor)


# =============================================================================
# _build_segments — 从 raw lines 构建 OpenAI 格式 contexts 段
# =============================================================================


def _build_segments(raw_lines: list[str]) -> list[dict]:
    """从 raw strings 构建 OpenAI 格式 contexts 段。

    规则：
    1. <T:CALL>json</T:CALL> → 连续多条合并为一个 assistant(tool_calls)
    2. <T:RES id=xxx>content</T:RES> → tool 消息，tool_call_id 配对
    3. <BOT/时间>: content → assistant（纯文本）
    4. 其它行 → user（合并为段，段内裁剪 MAX_MSGS/MAX_CHARS）
    """
    if not raw_lines:
        return []

    segments: list[dict] = []
    user_buf: list[str] = []
    tool_calls_buf: list[dict] = []

    def flush_user():
        if not user_buf:
            return
        truncated = _truncate_user_segment(user_buf)
        segments.append({"role": "user", "content": "\n".join(truncated)})
        user_buf.clear()

    def flush_tool_calls():
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
            tc_data = _parse_tool_call(line)
            if tc_data:
                tool_calls_buf.append(tc_data)
        elif line.startswith(TOOL_RES_PREFIX):
            flush_user()
            flush_tool_calls()
            tool_msg = _parse_tool_result(line)
            if tool_msg:
                segments.append(tool_msg)
        elif line.startswith(BOT_MARKER):
            flush_user()
            flush_tool_calls()
            content = _extract_bot_content(line)
            if content:
                segments.append({"role": "assistant", "content": content})
        else:
            user_buf.append(line)

    flush_user()
    flush_tool_calls()
    return segments


# =============================================================================
# 解析 helper
# =============================================================================


def _parse_tool_call(line: str) -> dict | None:
    """<T:CALL>{"id":"x","name":"f","args":{...}}</T:CALL> → tool_call dict"""
    inner = _extract_tag_content(line, TOOL_CALL_PREFIX, "</T:CALL>")
    if not inner:
        return None
    try:
        tc = json.loads(inner)
        tc_id = tc["id"]
        tc_name = tc["name"]
        tc_args = tc["args"]
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
    return {
        "id": tc_id,
        "type": "function",
        "function": {
            "name": tc_name,
            "arguments": json.dumps(tc_args, ensure_ascii=False),
        },
    }


def _parse_tool_result(line: str) -> dict | None:
    """<T:RES id=xxx>content</T:RES> → {"role":"tool", ...}"""
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
    tc_id = id_part[3:]
    return {"role": "tool", "tool_call_id": tc_id, "content": content}


def _truncate_tool_result_for_history(content: str, max_chars: int) -> str:
    """Truncate a single tool result before persisting into LTM history."""
    if max_chars <= 0 or len(content) <= max_chars:
        return content

    omitted = len(content) - max_chars
    marker = f"\n...[TRUNCATED {omitted} chars]..."
    if len(marker) >= max_chars:
        return content[:max_chars]

    head_len = max_chars - len(marker)
    return content[:head_len] + marker


def _extract_bot_content(line: str) -> str | None:
    """<BOT/HH:MM:SS>: content → content"""
    idx = line.find(">: ")
    if idx == -1:
        return None
    return line[idx + 3 :].strip()


def _extract_tag_content(line: str, start_tag: str, end_tag: str) -> str | None:
    """<TAG>content</TAG> → content"""
    if not line.endswith(end_tag):
        return None
    return line[len(start_tag) : -len(end_tag)].strip()


def _truncate_user_segment(lines: list[str]) -> list[str]:
    """段内裁剪：保留最近 N 条，不超字符上限。从段内最早的消息开始丢弃。"""
    result: list[str] = []
    total = 0
    for line in reversed(lines):
        if len(result) >= MAX_MSGS_PER_USER_SEGMENT:
            break
        if total + len(line) > MAX_CHARS_PER_USER_SEGMENT and result:
            break
        result.append(line)
        total += len(line) + 1  # +1 for \n
    result.reverse()
    return result


# =============================================================================
# _split_into_rounds — LTM compaction helper
# =============================================================================


def _split_into_rounds(contexts: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split a flat contexts list into logical rounds.

    A round begins at a ``user`` segment and includes all subsequent
    ``assistant`` / ``tool`` segments until the next ``user`` segment.
    """
    rounds: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for seg in contexts:
        if seg.get("role") == "user" and current:
            rounds.append(current)
            current = []
        current.append(seg)
    if current:
        rounds.append(current)
    return rounds


def _rounds_to_text(rounds: list[list[dict[str, Any]]]) -> str:
    """Render rounds into a plain-text string for LLM summarisation."""
    lines: list[str] = []
    for i, rnd in enumerate(rounds, 1):
        lines.append(f"--- Round {i} ---")
        for seg in rnd:
            role = seg.get("role", "?")
            content = seg.get("content") or seg.get("tool_calls") or ""
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)
            lines.append(f"[{role}] {content}")
    return "\n".join(lines)
