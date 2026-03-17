"""Schedule-specific SDK types.

本模块定义定时任务相关的 SDK 类型，主要为 ScheduleContext 提供数据结构。

ScheduleContext 包含：
- schedule_id: 调度任务唯一标识
- plugin_id: 所属插件 ID
- handler_id: 对应 handler 的标识
- trigger_kind: 触发类型（cron / interval / once）
- cron: cron 表达式（仅 cron 类型）
- interval_seconds: 间隔秒数（仅 interval 类型）
- scheduled_at: 计划执行时间（仅 once 类型）

使用方式：
通过 @on_schedule 装饰器注册的 handler 可通过参数注入获取 ScheduleContext。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ScheduleContext:
    schedule_id: str
    plugin_id: str
    handler_id: str
    trigger_kind: str
    cron: str | None = None
    interval_seconds: int | None = None
    scheduled_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ScheduleContext:
        schedule = payload.get("schedule")
        if not isinstance(schedule, dict):
            raise ValueError("schedule payload is required")
        return cls(
            schedule_id=str(schedule.get("schedule_id", "")),
            plugin_id=str(schedule.get("plugin_id", "")),
            handler_id=str(schedule.get("handler_id", "")),
            trigger_kind=str(schedule.get("trigger_kind", "")),
            cron=(
                str(schedule["cron"]) if isinstance(schedule.get("cron"), str) else None
            ),
            interval_seconds=(
                int(schedule["interval_seconds"])
                if isinstance(schedule.get("interval_seconds"), int)
                else None
            ),
            scheduled_at=(
                str(schedule["scheduled_at"])
                if isinstance(schedule.get("scheduled_at"), str)
                else None
            ),
        )


__all__ = ["ScheduleContext"]
