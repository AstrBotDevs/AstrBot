from __future__ import annotations

from typing import Protocol

from .models import SubagentTaskData


class SubagentHooks(Protocol):
    async def on_task_enqueued(self, task: SubagentTaskData) -> None: ...

    async def on_task_started(self, task: SubagentTaskData) -> None: ...

    async def on_task_retrying(
        self,
        task: SubagentTaskData,
        *,
        delay_seconds: float,
        error_class: str,
        error: Exception,
    ) -> None: ...

    async def on_task_succeeded(self, task: SubagentTaskData, result: str) -> None: ...

    async def on_task_failed(
        self, task: SubagentTaskData, *, error_class: str, error: Exception
    ) -> None: ...

    async def on_task_canceled(self, task_id: str) -> None: ...

    async def on_task_result_ignored(
        self, task: SubagentTaskData, *, reason: str
    ) -> None: ...


class NoopSubagentHooks:
    async def on_task_enqueued(self, task: SubagentTaskData) -> None:
        _ = task

    async def on_task_started(self, task: SubagentTaskData) -> None:
        _ = task

    async def on_task_retrying(
        self,
        task: SubagentTaskData,
        *,
        delay_seconds: float,
        error_class: str,
        error: Exception,
    ) -> None:
        _ = task
        _ = delay_seconds
        _ = error_class
        _ = error

    async def on_task_succeeded(self, task: SubagentTaskData, result: str) -> None:
        _ = task
        _ = result

    async def on_task_failed(
        self, task: SubagentTaskData, *, error_class: str, error: Exception
    ) -> None:
        _ = task
        _ = error_class
        _ = error

    async def on_task_canceled(self, task_id: str) -> None:
        _ = task_id

    async def on_task_result_ignored(
        self, task: SubagentTaskData, *, reason: str
    ) -> None:
        _ = task
        _ = reason
