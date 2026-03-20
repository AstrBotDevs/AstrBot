from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core import logger
from astrbot.core.context_compaction_scheduler import PeriodicContextCompactionScheduler


class ContextCompactionCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    def _get_scheduler(self) -> PeriodicContextCompactionScheduler | None:
        scheduler = getattr(self.context, "context_compaction_scheduler", None)
        if isinstance(scheduler, PeriodicContextCompactionScheduler):
            return scheduler
        return None

    async def status(self, event: AstrMessageEvent) -> None:
        scheduler = self._get_scheduler()
        if not scheduler:
            await event.send(
                MessageChain().message("定时上下文压缩调度器不可用。"),
            )
            return

        status = scheduler.get_status()
        cfg = status.get("config", {})
        last = status.get("last_report") or {}
        trigger_tokens = cfg.get("trigger_tokens", "?")
        trigger_ratio = cfg.get("trigger_min_context_ratio", "?")
        if isinstance(trigger_tokens, int) and trigger_tokens <= 0:
            if isinstance(trigger_ratio, (int, float)):
                trigger_text = f"自动({trigger_ratio}x模型上下文或目标长度估算)"
            else:
                trigger_text = "自动(基于目标长度估算)"
        else:
            trigger_text = str(trigger_tokens)

        lines = ["定时上下文压缩状态："]
        lines.append(
            f"启用={self._yes_no(bool(cfg.get('enabled', False)))}"
            f" | 运行中={self._yes_no(bool(status.get('running', False)))}"
            f" | 停止请求={self._yes_no(bool(status.get('stop_requested', False)))}"
        )
        lines.append(
            f"间隔={cfg.get('interval_minutes', '?')}分钟"
            f" | 每轮最多压缩={cfg.get('max_conversations_per_run', '?')}"
            f" | 每轮最多扫描={cfg.get('max_scan_per_run', '?')}"
        )
        lines.append(
            f"触发Token={trigger_text}"
            f" | 目标Token={cfg.get('target_tokens', '?')}"
            f" | 最大轮次={cfg.get('max_rounds', '?')}"
        )

        if last:
            lines.append(
                f"最近任务[{last.get('reason', 'unknown')}]"
                f" scanned={last.get('scanned', 0)}"
                f" compacted={last.get('compacted', 0)}"
                f" skipped={last.get('skipped', 0)}"
                f" failed={last.get('failed', 0)}"
                f" elapsed={last.get('elapsed_sec', 0.0):.2f}s"
            )
        else:
            lines.append("最近任务：暂无")

        if status.get("last_started_at"):
            lines.append(f"最近开始：{status.get('last_started_at')}")
        if status.get("last_finished_at"):
            lines.append(f"最近结束：{status.get('last_finished_at')}")
        if status.get("last_error"):
            lines.append(f"最近错误：{status.get('last_error')}")

        await event.send(MessageChain().message("\n".join(lines)))

    async def run(self, event: AstrMessageEvent, limit: int | None = None) -> None:
        scheduler = self._get_scheduler()
        if not scheduler:
            await event.send(
                MessageChain().message("定时上下文压缩调度器不可用。"),
            )
            return

        if limit is not None and limit < 1:
            await event.send(MessageChain().message("limit 必须 >= 1。"))
            return

        try:
            report = await scheduler.run_once(
                reason="manual_command",
                max_conversations_override=limit,
            )
        except Exception as exc:
            logger.error("ctxcompact run failed: %s", exc, exc_info=True)
            await event.send(MessageChain().message("触发压缩失败，请查看服务端日志。"))
            return

        msg = (
            "手动触发完成："
            f"scanned={report.get('scanned', 0)} "
            f"compacted={report.get('compacted', 0)} "
            f"skipped={report.get('skipped', 0)} "
            f"failed={report.get('failed', 0)} "
            f"elapsed={report.get('elapsed_sec', 0.0):.2f}s"
        )
        await event.send(MessageChain().message(msg))

    @staticmethod
    def _yes_no(value: bool) -> str:
        return "是" if value else "否"
