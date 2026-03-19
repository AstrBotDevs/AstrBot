from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from astrbot import logger
from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.context.token_counter import EstimateTokenCounter
from astrbot.core.agent.message import Message
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.po import ConversationV2
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import Provider

if TYPE_CHECKING:
    from astrbot.core.provider.manager import ProviderManager


@dataclass
class _CompactionStats:
    scanned: int = 0
    compacted: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass
class _EligibilityResult:
    eligible: bool
    messages: list[Message]
    before_tokens: int


@dataclass
class _RoundResult:
    messages: list[Message]
    changed: bool
    rounds: int


class _MessageHistoryParser:
    def parse(self, history: Iterable[Any]) -> list[Message]:
        parsed: list[Message] = []
        for item in history:
            if not isinstance(item, dict):
                continue

            try:
                parsed.append(Message.model_validate(item))
                continue
            except Exception:
                pass

            fallback = self.sanitize_message_dict(item)
            if not fallback:
                continue
            try:
                parsed.append(Message.model_validate(fallback))
            except Exception:
                continue

        return parsed

    def sanitize_message_dict(self, item: dict[str, Any]) -> dict[str, Any] | None:
        role = str(item.get("role", "")).strip().lower()
        if role not in {"system", "user", "assistant", "tool"}:
            return None

        result: dict[str, Any] = {"role": role}

        if role == "assistant" and isinstance(item.get("tool_calls"), list):
            result["tool_calls"] = item["tool_calls"]

        if role == "tool" and item.get("tool_call_id"):
            result["tool_call_id"] = str(item.get("tool_call_id"))

        content = item.get("content")
        if content is None and role == "assistant" and result.get("tool_calls"):
            result["content"] = None
            return result

        result["content"] = self.sanitize_content(content, role)

        if result["content"] is None and not (
            role == "assistant" and result.get("tool_calls")
        ):
            return None

        return result

    def sanitize_content(self, content: Any, role: str) -> str | list[dict] | None:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            return self.sanitize_list_content(content)

        if content is None:
            if role == "assistant":
                return None
            return ""

        dumped = self.safe_json(content)
        return dumped if dumped is not None else str(content)

    def sanitize_list_content(self, content: list[Any]) -> str | list[dict]:
        parts: list[dict[str, Any]] = []
        fallback_texts: list[str] = []

        for part in content:
            if isinstance(part, str):
                if part.strip():
                    fallback_texts.append(part)
                continue
            if not isinstance(part, dict):
                txt = self.safe_json(part)
                if txt:
                    fallback_texts.append(txt)
                continue
            self.sanitize_content_part(part, parts, fallback_texts)

        if fallback_texts:
            parts.insert(0, {"type": "text", "text": "\n".join(fallback_texts)})

        if parts:
            return parts
        return ""

    def sanitize_content_part(
        self,
        part: dict[str, Any],
        parts: list[dict[str, Any]],
        fallback_texts: list[str],
    ) -> None:
        part_type = str(part.get("type", "")).strip()
        if part_type == "text":
            text_val = part.get("text")
            if text_val is not None:
                parts.append({"type": "text", "text": str(text_val)})
            return

        if part_type == "image_url":
            image_obj = part.get("image_url")
            if isinstance(image_obj, dict) and image_obj.get("url"):
                image_part: dict[str, Any] = {
                    "type": "image_url",
                    "image_url": {"url": str(image_obj.get("url"))},
                }
                if image_obj.get("id"):
                    image_part["image_url"]["id"] = str(image_obj.get("id"))
                parts.append(image_part)
            return

        if part_type == "audio_url":
            audio_obj = part.get("audio_url")
            if isinstance(audio_obj, dict) and audio_obj.get("url"):
                audio_part: dict[str, Any] = {
                    "type": "audio_url",
                    "audio_url": {"url": str(audio_obj.get("url"))},
                }
                if audio_obj.get("id"):
                    audio_part["audio_url"]["id"] = str(audio_obj.get("id"))
                parts.append(audio_part)
            return

        if part_type == "think":
            think = part.get("think")
            if think:
                fallback_texts.append(str(think))
            return

        raw_text = part.get("text") or part.get("content")
        if raw_text:
            fallback_texts.append(str(raw_text))
        else:
            dumped = self.safe_json(part)
            if dumped:
                fallback_texts.append(dumped)

    @staticmethod
    def safe_json(value: Any) -> str | None:
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return None


class PeriodicContextCompactionScheduler:
    """Periodically compact conversation history and persist summarized history back to DB.

    This upgrades existing "compress-on-overflow" behavior into proactive, scheduled
    conversation-body compaction to keep long sessions lightweight.
    """

    _DEFAULTS = {
        "enabled": False,
        "interval_minutes": 30,
        "startup_delay_seconds": 120,
        "max_conversations_per_run": 8,
        "max_scan_per_run": 120,
        "scan_page_size": 40,
        "min_idle_minutes": 15,
        "min_messages": 14,
        "target_tokens": 4096,
        "trigger_tokens": 6144,
        "max_rounds": 3,
        "truncate_turns": 1,
        "keep_recent": 6,
        "provider_id": "",
        "instruction": "",
        "dry_run": False,
    }

    def __init__(
        self,
        config_manager: AstrBotConfigManager,
        conversation_manager: ConversationManager,
        provider_manager: ProviderManager,
    ) -> None:
        self.config_manager = config_manager
        self.conversation_manager = conversation_manager
        self.provider_manager = provider_manager
        self._stop_event = asyncio.Event()
        self._running_lock = asyncio.Lock()
        self._token_counter = EstimateTokenCounter()
        self._history_parser = _MessageHistoryParser()
        self._bootstrapped = False
        self._last_report: dict[str, Any] | None = None
        self._last_started_at: str | None = None
        self._last_finished_at: str | None = None
        self._last_error: str | None = None

    def get_status(self) -> dict[str, Any]:
        cfg = self._load_config()
        return {
            "running": self._running_lock.locked(),
            "bootstrapped": self._bootstrapped,
            "stop_requested": self._stop_event.is_set(),
            "config": cfg,
            "last_started_at": self._last_started_at,
            "last_finished_at": self._last_finished_at,
            "last_error": self._last_error,
            "last_report": self._last_report,
        }

    async def run(self) -> None:
        logger.info("[ContextCompact] scheduler started")
        while not self._stop_event.is_set():
            cfg = self._load_config()
            wait_seconds = self._resolve_wait_seconds(cfg)

            if not cfg["enabled"]:
                await self._sleep_or_stop(wait_seconds)
                continue

            if not self._bootstrapped:
                self._bootstrapped = True
                startup_delay = max(0, int(cfg["startup_delay_seconds"]))
                if startup_delay > 0:
                    logger.info(
                        "[ContextCompact] startup delay: %ss before first run",
                        startup_delay,
                    )
                    await self._sleep_or_stop(startup_delay)
                    if self._stop_event.is_set():
                        break

            try:
                report = await self.run_once(reason="scheduled")
                logger.info(
                    "[ContextCompact] run done(%s): scanned=%s compacted=%s skipped=%s failed=%s elapsed=%.2fs",
                    report.get("reason", "unknown"),
                    report.get("scanned", 0),
                    report.get("compacted", 0),
                    report.get("skipped", 0),
                    report.get("failed", 0),
                    report.get("elapsed_sec", 0.0),
                )
            except Exception as exc:
                self._last_error = str(exc)
                logger.error(
                    "[ContextCompact] scheduler run error: %s",
                    exc,
                    exc_info=True,
                )

            await self._sleep_or_stop(wait_seconds)

        logger.info("[ContextCompact] scheduler stopped")

    async def stop(self) -> None:
        self._stop_event.set()

    async def run_once(
        self,
        reason: str = "manual",
        max_conversations_override: int | None = None,
    ) -> dict[str, Any]:
        """Run one compaction sweep.

        Exposed so future admin command/cron endpoints can trigger ad-hoc compaction.
        """
        async with self._running_lock:
            self._last_started_at = self._now_iso()
            cfg = self._load_config()
            started = time.monotonic()
            stats = _CompactionStats()

            if not cfg["enabled"] and reason == "scheduled":
                report = {
                    "reason": reason,
                    "scanned": 0,
                    "compacted": 0,
                    "skipped": 0,
                    "failed": 0,
                    "elapsed_sec": 0.0,
                    "message": "disabled",
                }
                self._last_report = report
                self._last_finished_at = self._now_iso()
                self._last_error = None
                return report

            max_to_compact, max_to_scan, scan_page_size = self._resolve_run_limits(
                cfg,
                max_conversations_override,
            )

            async for conv in self._iter_candidate_conversations(scan_page_size):
                if (
                    self._stop_event.is_set()
                    or stats.scanned >= max_to_scan
                    or stats.compacted >= max_to_compact
                ):
                    break

                stats.scanned += 1
                outcome = await self._compact_one_conversation(conv, cfg)
                self._record_outcome(stats, outcome)

            elapsed = time.monotonic() - started
            report = {
                "reason": reason,
                "scanned": stats.scanned,
                "compacted": stats.compacted,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "elapsed_sec": elapsed,
            }
            self._last_report = report
            self._last_finished_at = self._now_iso()
            self._last_error = None
            return report

    @staticmethod
    def _resolve_run_limits(
        cfg: dict[str, Any],
        max_conversations_override: int | None,
    ) -> tuple[int, int, int]:
        max_to_compact = max(1, int(cfg["max_conversations_per_run"]))
        if max_conversations_override is not None:
            max_to_compact = max(1, int(max_conversations_override))
        max_to_scan = max(max_to_compact, int(cfg["max_scan_per_run"]))
        scan_page_size = max(10, int(cfg["scan_page_size"]))
        return max_to_compact, max_to_scan, scan_page_size

    async def _iter_candidate_conversations(
        self,
        scan_page_size: int,
    ) -> AsyncIterator[ConversationV2]:
        page = 1
        while not self._stop_event.is_set():
            conversations, total = await self.conversation_manager.db.get_filtered_conversations(
                page=page,
                page_size=scan_page_size,
            )
            if not conversations:
                break

            for conv in conversations:
                if self._stop_event.is_set():
                    return
                yield conv

            if page * scan_page_size >= total:
                break
            page += 1

    @staticmethod
    def _record_outcome(stats: _CompactionStats, outcome: str) -> None:
        if outcome == "compacted":
            stats.compacted += 1
        elif outcome == "skipped":
            stats.skipped += 1
        else:
            stats.failed += 1

    async def _sleep_or_stop(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    @staticmethod
    def _resolve_wait_seconds(cfg: dict[str, Any]) -> int:
        return max(1, int(cfg["interval_minutes"])) * 60

    def _load_config(self) -> dict[str, Any]:
        raw_cfg = self._load_raw_config()

        cfg = dict(self._DEFAULTS)
        cfg.update(raw_cfg)

        # normalize
        cfg["enabled"] = self._to_bool(cfg.get("enabled"), False)
        self._normalize_int(cfg, "interval_minutes", 30, 1)
        self._normalize_int(cfg, "startup_delay_seconds", 120, 0)
        self._normalize_int(cfg, "max_conversations_per_run", 8, 1)
        self._normalize_int(cfg, "max_scan_per_run", 120, 1)
        self._normalize_int(cfg, "scan_page_size", 40, 10)
        self._normalize_int(cfg, "min_idle_minutes", 15, 0)
        self._normalize_int(cfg, "min_messages", 14, 2)
        self._normalize_int(cfg, "target_tokens", 4096, 512)
        self._normalize_trigger_tokens(cfg, raw_cfg)
        self._normalize_int(cfg, "max_rounds", 3, 1)
        self._normalize_int(cfg, "truncate_turns", 1, 1)
        self._normalize_int(cfg, "keep_recent", 6, 0)
        cfg["provider_id"] = str(cfg.get("provider_id", "") or "").strip()
        cfg["instruction"] = str(cfg.get("instruction", "") or "").strip()
        cfg["dry_run"] = self._to_bool(cfg.get("dry_run"), False)

        return cfg

    def _load_raw_config(self) -> dict[str, Any]:
        default_conf = self.config_manager.default_conf
        provider_settings = default_conf.get("provider_settings", {})
        raw_cfg = provider_settings.get("periodic_context_compaction", {})
        if isinstance(raw_cfg, dict):
            return raw_cfg
        return {}

    def _normalize_int(
        self,
        cfg: dict[str, Any],
        key: str,
        default: int,
        min_value: int,
    ) -> int:
        cfg[key] = self._to_int(cfg.get(key), default, min_value)
        return cfg[key]

    def _normalize_trigger_tokens(
        self,
        cfg: dict[str, Any],
        raw_cfg: dict[str, Any],
    ) -> int:
        trigger_default = max(int(cfg["target_tokens"] * 1.5), cfg["target_tokens"] + 1)
        raw_trigger = raw_cfg.get("trigger_tokens")
        if raw_trigger is None or (isinstance(raw_trigger, str) and not raw_trigger):
            cfg["trigger_tokens"] = trigger_default
        else:
            cfg["trigger_tokens"] = self._to_int(raw_trigger, trigger_default, 512)
        if cfg["trigger_tokens"] <= cfg["target_tokens"]:
            cfg["trigger_tokens"] = cfg["target_tokens"] + 1
        return cfg["trigger_tokens"]

    async def _compact_one_conversation(
        self,
        conv: ConversationV2,
        cfg: dict[str, Any],
    ) -> str:
        eligibility = self._check_eligibility(conv, cfg)
        if not eligibility.eligible:
            return "skipped"

        provider = await self._resolve_provider(cfg, conv.user_id)
        if not provider:
            return "failed"

        round_result = await self._run_compaction_rounds(
            messages=eligibility.messages,
            provider=provider,
            cfg=cfg,
        )
        if not round_result.changed:
            return "skipped"

        after_tokens = self._token_counter.count_tokens(round_result.messages)
        if after_tokens >= eligibility.before_tokens:
            return "skipped"

        if cfg["dry_run"]:
            self._log_dry_run(conv, eligibility.before_tokens, after_tokens, round_result)
            return "skipped"

        persisted = await self._persist_compacted_history(
            conv=conv,
            compressed=round_result.messages,
            after_tokens=after_tokens,
        )
        if not persisted:
            return "failed"

        self._log_compacted(
            conv,
            eligibility.before_tokens,
            after_tokens,
            round_result,
        )
        return "compacted"

    def _check_eligibility(
        self,
        conv: ConversationV2,
        cfg: dict[str, Any],
    ) -> _EligibilityResult:
        history = conv.content
        if not isinstance(history, list) or len(history) < cfg["min_messages"]:
            return _EligibilityResult(eligible=False, messages=[], before_tokens=0)

        if not self._is_idle_enough(conv.updated_at, cfg["min_idle_minutes"]):
            return _EligibilityResult(eligible=False, messages=[], before_tokens=0)

        messages = self._parse_history(history)
        if len(messages) < cfg["min_messages"]:
            return _EligibilityResult(eligible=False, messages=[], before_tokens=0)

        trusted_usage = conv.token_usage if isinstance(conv.token_usage, int) else 0
        before_tokens = self._token_counter.count_tokens(messages, trusted_usage)
        if before_tokens < cfg["trigger_tokens"]:
            return _EligibilityResult(eligible=False, messages=[], before_tokens=0)

        return _EligibilityResult(
            eligible=True,
            messages=messages,
            before_tokens=before_tokens,
        )

    async def _run_compaction_rounds(
        self,
        messages: list[Message],
        provider: Provider,
        cfg: dict[str, Any],
    ) -> _RoundResult:
        compressed = messages
        changed = False
        rounds = 0
        instruction = self._resolve_instruction(cfg)

        for _ in range(cfg["max_rounds"]):
            current_tokens = self._token_counter.count_tokens(compressed)
            if current_tokens <= cfg["target_tokens"]:
                break

            manager = self._build_context_manager(cfg, provider, instruction)
            rounds += 1
            next_messages = await manager.process(compressed)
            if self._messages_equal(compressed, next_messages):
                break

            compressed = next_messages
            changed = True

        return _RoundResult(messages=compressed, changed=changed, rounds=rounds)

    @staticmethod
    def _build_context_manager(
        cfg: dict[str, Any],
        provider: Provider,
        instruction: str,
    ) -> ContextManager:
        return ContextManager(
            ContextConfig(
                max_context_tokens=cfg["target_tokens"],
                enforce_max_turns=-1,
                truncate_turns=cfg["truncate_turns"],
                llm_compress_keep_recent=cfg["keep_recent"],
                llm_compress_instruction=instruction,
                llm_compress_provider=provider,
            )
        )

    async def _persist_compacted_history(
        self,
        conv: ConversationV2,
        compressed: list[Message],
        after_tokens: int,
    ) -> bool:
        try:
            await self.conversation_manager.update_conversation(
                unified_msg_origin=conv.user_id,
                conversation_id=conv.conversation_id,
                history=[msg.model_dump(exclude_none=True) for msg in compressed],
                token_usage=after_tokens,
            )
        except Exception as exc:
            logger.error(
                "[ContextCompact] update failed: cid=%s user=%s err=%s",
                conv.conversation_id,
                conv.user_id,
                exc,
                exc_info=True,
            )
            return False
        return True

    @staticmethod
    def _log_dry_run(
        conv: ConversationV2,
        before_tokens: int,
        after_tokens: int,
        round_result: _RoundResult,
    ) -> None:
        logger.info(
            "[ContextCompact] dry-run: cid=%s user=%s tokens=%s->%s rounds=%s",
            conv.conversation_id,
            conv.user_id,
            before_tokens,
            after_tokens,
            round_result.rounds,
        )

    @staticmethod
    def _log_compacted(
        conv: ConversationV2,
        before_tokens: int,
        after_tokens: int,
        round_result: _RoundResult,
    ) -> None:
        logger.info(
            "[ContextCompact] compacted cid=%s user=%s tokens=%s->%s rounds=%s",
            conv.conversation_id,
            conv.user_id,
            before_tokens,
            after_tokens,
            round_result.rounds,
        )

    async def _resolve_provider(
        self,
        cfg: dict[str, Any],
        umo: str,
    ) -> Provider | None:
        provider = None

        if cfg["provider_id"]:
            provider = await self.provider_manager.get_provider_by_id(cfg["provider_id"])
        else:
            provider = self.provider_manager.get_using_provider(
                provider_type=ProviderType.CHAT_COMPLETION,
                umo=umo,
            )
            if provider is None:
                provider = self.provider_manager.get_using_provider(
                    provider_type=ProviderType.CHAT_COMPLETION,
                    umo=None,
                )

        if not isinstance(provider, Provider):
            logger.warning(
                "[ContextCompact] provider unavailable for umo=%s provider_id=%s",
                umo,
                cfg["provider_id"],
            )
            return None
        return provider

    def _resolve_instruction(self, cfg: dict[str, Any]) -> str:
        if cfg["instruction"]:
            return cfg["instruction"]

        provider_settings = self.config_manager.default_conf.get("provider_settings", {})
        base_instruction = provider_settings.get("llm_compress_instruction", "")
        if isinstance(base_instruction, str) and base_instruction.strip():
            return base_instruction.strip()
        return ""

    @staticmethod
    def _is_idle_enough(updated_at: datetime | None, min_idle_minutes: int) -> bool:
        if min_idle_minutes <= 0:
            return True
        if updated_at is None:
            return True
        now = datetime.now(timezone.utc)
        at = updated_at
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return (now - at).total_seconds() >= (min_idle_minutes * 60)

    def _parse_history(self, history: Iterable[Any]) -> list[Message]:
        return self._history_parser.parse(history)

    def _sanitize_message_dict(self, item: dict[str, Any]) -> dict[str, Any] | None:
        return self._history_parser.sanitize_message_dict(item)

    def _sanitize_content(self, content: Any, role: str) -> str | list[dict] | None:
        return self._history_parser.sanitize_content(content, role)

    def _sanitize_list_content(self, content: list[Any]) -> str | list[dict]:
        return self._history_parser.sanitize_list_content(content)

    def _sanitize_content_part(
        self,
        part: dict[str, Any],
        parts: list[dict[str, Any]],
        fallback_texts: list[str],
    ) -> None:
        self._history_parser.sanitize_content_part(part, parts, fallback_texts)

    @staticmethod
    def _messages_equal(a: list[Message], b: list[Message]) -> bool:
        if len(a) != len(b):
            return False
        return [m.model_dump(exclude_none=True) for m in a] == [
            m.model_dump(exclude_none=True) for m in b
        ]

    @staticmethod
    def _safe_json(value: Any) -> str | None:
        return _MessageHistoryParser.safe_json(value)

    @staticmethod
    def _to_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _to_int(value: Any, default: int, min_value: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = default
        return max(parsed, min_value)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
