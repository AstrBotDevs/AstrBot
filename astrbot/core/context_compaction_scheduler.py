from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from astrbot import logger
from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.context.token_counter import EstimateTokenCounter
from astrbot.core.agent.message import Message
from astrbot.core.agent.message_history_parser import MessageHistoryParser
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.default import PERIODIC_CONTEXT_COMPACTION_DEFAULTS
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
class _RoundResult:
    messages: list[Message]
    changed: bool
    rounds: int


EligibilityInfo = tuple[list[Message], int]


@dataclass
class _RunStatus:
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    report: dict[str, Any] | None = None


@dataclass(frozen=True)
class CompactionConfig:
    enabled: bool
    interval_minutes: int
    startup_delay_seconds: int
    max_conversations_per_run: int
    max_scan_per_run: int
    scan_page_size: int
    min_idle_minutes: int
    min_messages: int
    target_tokens: int
    trigger_tokens: int
    max_rounds: int
    truncate_turns: int
    keep_recent: int
    provider_id: str
    instruction: str
    dry_run: bool

    @classmethod
    def from_default_conf(
        cls,
        default_conf: dict[str, Any],
    ) -> CompactionConfig:
        defaults = PERIODIC_CONTEXT_COMPACTION_DEFAULTS
        provider_settings = default_conf.get("provider_settings", {}) or {}
        raw_cfg = provider_settings.get("periodic_context_compaction", {}) or {}
        if not isinstance(raw_cfg, dict):
            raw_cfg = {}

        cfg = dict(defaults)
        cfg.update(raw_cfg)

        target_tokens = cls._to_int(cfg.get("target_tokens"), 4096, 512)
        raw_trigger = raw_cfg.get("trigger_tokens")
        trigger_default = max(int(target_tokens * 1.5), target_tokens + 1)
        if raw_trigger is None or (isinstance(raw_trigger, str) and not raw_trigger):
            trigger_tokens = trigger_default
        else:
            trigger_tokens = cls._to_int(raw_trigger, trigger_default, 512)
        if trigger_tokens <= target_tokens:
            trigger_tokens = target_tokens + 1

        return cls(
            enabled=cls._to_bool(cfg.get("enabled"), False),
            interval_minutes=cls._to_int(cfg.get("interval_minutes"), 30, 1),
            startup_delay_seconds=cls._to_int(cfg.get("startup_delay_seconds"), 120, 0),
            max_conversations_per_run=cls._to_int(
                cfg.get("max_conversations_per_run"),
                8,
                1,
            ),
            max_scan_per_run=cls._to_int(cfg.get("max_scan_per_run"), 120, 1),
            scan_page_size=cls._to_int(cfg.get("scan_page_size"), 40, 10),
            min_idle_minutes=cls._to_int(cfg.get("min_idle_minutes"), 15, 0),
            min_messages=cls._to_int(cfg.get("min_messages"), 14, 2),
            target_tokens=target_tokens,
            trigger_tokens=trigger_tokens,
            max_rounds=cls._to_int(cfg.get("max_rounds"), 3, 1),
            truncate_turns=cls._to_int(cfg.get("truncate_turns"), 1, 1),
            keep_recent=cls._to_int(cfg.get("keep_recent"), 6, 0),
            provider_id=str(cfg.get("provider_id", "") or "").strip(),
            instruction=str(cfg.get("instruction", "") or "").strip(),
            dry_run=cls._to_bool(cfg.get("dry_run"), False),
        )

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


class PeriodicContextCompactionScheduler:
    """Periodically compact conversation history and persist summarized history back to DB.

    This upgrades existing "compress-on-overflow" behavior into proactive, scheduled
    conversation-body compaction to keep long sessions lightweight.
    """

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
        self._history_parser = MessageHistoryParser()
        self._bootstrapped = False
        self._last_status = _RunStatus()

    def get_status(self) -> dict[str, Any]:
        cfg = self._load_config()
        return {
            "running": self._running_lock.locked(),
            "bootstrapped": self._bootstrapped,
            "stop_requested": self._stop_event.is_set(),
            "config": asdict(cfg),
            "last_started_at": self._last_status.started_at,
            "last_finished_at": self._last_status.finished_at,
            "last_error": self._last_status.error,
            "last_report": self._last_status.report,
            "last_status": asdict(self._last_status),
        }

    async def run(self) -> None:
        logger.info("[ContextCompact] scheduler started")
        while not self._stop_event.is_set():
            cfg = self._load_config()
            wait_seconds = max(1, int(cfg.interval_minutes)) * 60

            if not cfg.enabled:
                await self._sleep_or_stop(wait_seconds)
                continue

            if not self._bootstrapped:
                self._bootstrapped = True
                startup_delay = max(0, int(cfg.startup_delay_seconds))
                if startup_delay > 0:
                    logger.info(
                        "[ContextCompact] startup delay: %ss before first run",
                        startup_delay,
                    )
                    await self._sleep_or_stop(startup_delay)
                    if self._stop_event.is_set():
                        break

            try:
                report = await self.run_once(reason="scheduled", cfg=cfg)
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
                finished = self._now_iso()
                self._update_last_status(
                    finished_at=finished,
                    error=str(exc),
                )
                if self._last_status.started_at is None:
                    self._last_status.started_at = finished
                if self._last_status.report is None:
                    self._last_status.report = {}
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
        cfg: CompactionConfig | None = None,
    ) -> dict[str, Any]:
        """Run one compaction sweep.

        Exposed so future admin command/cron endpoints can trigger ad-hoc compaction.
        """
        async with self._running_lock:
            started_at = self._now_iso()
            self._last_status.started_at = started_at
            self._last_status.finished_at = None
            if cfg is None:
                cfg = self._load_config()
            started = time.monotonic()
            stats = _CompactionStats()

            if not cfg.enabled and reason == "scheduled":
                report = {
                    "reason": reason,
                    "scanned": 0,
                    "compacted": 0,
                    "skipped": 0,
                    "failed": 0,
                    "elapsed_sec": 0.0,
                    "message": "disabled",
                }
                self._update_last_status(
                    started_at=started_at,
                    finished_at=self._now_iso(),
                    report=report,
                    error=None,
                )
                return report

            max_to_compact, max_to_scan, scan_page_size = self._resolve_run_limits(
                cfg,
                max_conversations_override,
            )

            async for conv in self._iter_candidate_conversations(
                scan_page_size=scan_page_size,
                cfg=cfg,
            ):
                if (
                    self._stop_event.is_set()
                    or stats.scanned >= max_to_scan
                    or stats.compacted >= max_to_compact
                ):
                    break

                stats.scanned += 1
                outcome = await self._compact_one_conversation(conv, cfg)
                if outcome == "compacted":
                    stats.compacted += 1
                elif outcome == "skipped":
                    stats.skipped += 1
                else:
                    stats.failed += 1

            elapsed = time.monotonic() - started
            report = {
                "reason": reason,
                "scanned": stats.scanned,
                "compacted": stats.compacted,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "elapsed_sec": elapsed,
            }
            self._update_last_status(
                started_at=started_at,
                finished_at=self._now_iso(),
                report=report,
                error=None,
            )
            return report

    @staticmethod
    def _resolve_run_limits(
        cfg: CompactionConfig,
        max_conversations_override: int | None,
    ) -> tuple[int, int, int]:
        max_to_compact = max(1, int(cfg.max_conversations_per_run))
        if max_conversations_override is not None:
            max_to_compact = max(1, int(max_conversations_override))
        max_to_scan = max(max_to_compact, int(cfg.max_scan_per_run))
        scan_page_size = max(10, int(cfg.scan_page_size))
        return max_to_compact, max_to_scan, scan_page_size

    async def _iter_candidate_conversations(
        self,
        scan_page_size: int,
        cfg: CompactionConfig,
    ) -> AsyncIterator[ConversationV2]:
        updated_before: datetime | None = None
        if cfg.min_idle_minutes > 0:
            updated_before = datetime.now(timezone.utc) - timedelta(
                minutes=int(cfg.min_idle_minutes),
            )

        page = 1
        while not self._stop_event.is_set():
            conversations, total = await self.conversation_manager.db.get_filtered_conversations(
                page=page,
                page_size=scan_page_size,
                updated_before=updated_before,
                min_messages=cfg.min_messages,
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

    def _update_last_status(
        self,
        *,
        started_at: str | None = None,
        finished_at: str | None = None,
        error: str | None = None,
        report: dict[str, Any] | None = None,
    ) -> None:
        if started_at is not None:
            self._last_status.started_at = started_at
        if finished_at is not None:
            self._last_status.finished_at = finished_at
        self._last_status.error = error
        if report is not None:
            self._last_status.report = report

    async def _sleep_or_stop(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    def _load_config(self) -> CompactionConfig:
        return CompactionConfig.from_default_conf(
            default_conf=self.config_manager.default_conf,
        )

    async def _compact_one_conversation(
        self,
        conv: ConversationV2,
        cfg: CompactionConfig,
    ) -> str:
        eligibility = self._check_eligibility(conv, cfg)
        if eligibility is None:
            return "skipped"
        messages, before_tokens = eligibility

        provider = await self._resolve_provider(cfg, conv.user_id)
        if not provider:
            return "failed"

        round_result = await self._run_compaction_rounds(
            messages=messages,
            provider=provider,
            cfg=cfg,
        )
        if not round_result.changed:
            return "skipped"

        after_tokens = self._token_counter.count_tokens(round_result.messages)
        if after_tokens >= before_tokens:
            return "skipped"

        if cfg.dry_run:
            self._log_dry_run(conv, before_tokens, after_tokens, round_result)
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
            before_tokens,
            after_tokens,
            round_result,
        )
        return "compacted"

    def _check_eligibility(
        self,
        conv: ConversationV2,
        cfg: CompactionConfig,
    ) -> EligibilityInfo | None:
        history = conv.content
        if not isinstance(history, list) or len(history) < cfg.min_messages:
            return None

        if not self._is_idle_enough(conv.updated_at, cfg.min_idle_minutes):
            return None

        messages = self._history_parser.parse(history)
        if len(messages) < cfg.min_messages:
            return None

        trusted_usage = conv.token_usage if isinstance(conv.token_usage, int) else 0
        before_tokens = self._token_counter.count_tokens(messages, trusted_usage)
        if before_tokens < cfg.trigger_tokens:
            return None

        return messages, before_tokens

    async def _run_compaction_rounds(
        self,
        messages: list[Message],
        provider: Provider,
        cfg: CompactionConfig,
    ) -> _RoundResult:
        compressed = messages
        changed = False
        rounds = 0
        instruction = self._resolve_instruction(cfg)
        manager = self._build_context_manager(cfg, provider, instruction)

        for _ in range(cfg.max_rounds):
            current_tokens = self._token_counter.count_tokens(compressed)
            if current_tokens <= cfg.target_tokens:
                break

            rounds += 1
            next_messages = await manager.process(compressed)
            if self._messages_equal(compressed, next_messages):
                break

            compressed = next_messages
            changed = True

        return _RoundResult(messages=compressed, changed=changed, rounds=rounds)

    @staticmethod
    def _build_context_manager(
        cfg: CompactionConfig,
        provider: Provider,
        instruction: str,
    ) -> ContextManager:
        return ContextManager(
            ContextConfig(
                max_context_tokens=cfg.target_tokens,
                enforce_max_turns=-1,
                truncate_turns=cfg.truncate_turns,
                llm_compress_keep_recent=cfg.keep_recent,
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
        cfg: CompactionConfig,
        umo: str,
    ) -> Provider | None:
        provider = None

        if cfg.provider_id:
            provider = await self.provider_manager.get_provider_by_id(cfg.provider_id)
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
                cfg.provider_id,
            )
            return None
        return provider

    def _resolve_instruction(self, cfg: CompactionConfig) -> str:
        if cfg.instruction:
            return cfg.instruction

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

    @staticmethod
    def _messages_equal(a: list[Message], b: list[Message]) -> bool:
        if len(a) != len(b):
            return False
        return [m.model_dump(exclude_none=True) for m in a] == [
            m.model_dump(exclude_none=True) for m in b
        ]

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
