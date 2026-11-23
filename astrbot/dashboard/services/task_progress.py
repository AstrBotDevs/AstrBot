"""Shared progress state transitions for dashboard jobs."""

from __future__ import annotations


class UpdateProgressMixin:
    """Keep update stages consistent across dashboard adapters."""

    update_progress: dict[str, dict]

    def _init_update_progress(self, progress_id: str, version: str | None) -> None:
        self.update_progress[progress_id] = {
            "id": progress_id,
            "status": "running",
            "stage": "preparing",
            "version": version or "latest",
            "message": "正在准备更新...",
            "overall_percent": 0,
            "stages": {
                "dashboard": self._empty_stage("pending"),
                "core": self._empty_stage("pending"),
            },
        }

    @staticmethod
    def _empty_stage(status: str = "pending") -> dict:
        return {
            "status": status,
            "downloaded": 0,
            "total": 0,
            "percent": 0,
            "speed": 0,
        }

    def _set_update_stage(
        self,
        progress_id: str,
        stage: str,
        status: str,
        message: str,
        overall_percent: int | None = None,
    ) -> None:
        progress = self.update_progress.get(progress_id)
        if not progress:
            return
        progress["stage"] = stage
        progress["message"] = message
        progress["stages"].setdefault(stage, self._empty_stage())
        progress["stages"][stage]["status"] = status
        if overall_percent is not None:
            progress["overall_percent"] = overall_percent


class BackupProgressMixin:
    """Keep backup task results, callbacks, and progress in one implementation."""

    backup_tasks: dict[str, dict]
    backup_progress: dict[str, dict]

    def _init_task(self, task_id: str, task_type: str, status: str = "pending") -> None:
        self.backup_tasks[task_id] = {
            "type": task_type,
            "status": status,
            "result": None,
            "error": None,
        }
        self.backup_progress[task_id] = {
            "status": status,
            "stage": "waiting",
            "current": 0,
            "total": 100,
            "message": "",
        }

    def _set_task_result(
        self,
        task_id: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        if task_id in self.backup_tasks:
            self.backup_tasks[task_id]["status"] = status
            self.backup_tasks[task_id]["result"] = result
            self.backup_tasks[task_id]["error"] = error
        if task_id in self.backup_progress:
            self.backup_progress[task_id]["status"] = status

    def _update_progress(
        self,
        task_id: str,
        *,
        status: str | None = None,
        stage: str | None = None,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        update_task_progress(
            self.backup_progress,
            task_id,
            status=status,
            stage=stage,
            current=current,
            total=total,
            message=message,
        )

    def _make_progress_callback(self, task_id: str):
        async def _callback(
            stage: str,
            current: int,
            total: int,
            message: str = "",
        ) -> None:
            self._update_progress(
                task_id,
                status="processing",
                stage=stage,
                current=current,
                total=total,
                message=message,
            )

        return _callback


def update_task_progress(
    progress_by_task: dict[str, dict],
    task_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    current: int | None = None,
    total: int | None = None,
    message: str | None = None,
) -> None:
    """Apply supplied progress fields to an existing task only."""
    if task_id not in progress_by_task:
        return
    progress = progress_by_task[task_id]
    if status is not None:
        progress["status"] = status
    if stage is not None:
        progress["stage"] = stage
    if current is not None:
        progress["current"] = current
    if total is not None:
        progress["total"] = total
    if message is not None:
        progress["message"] = message


def task_progress_response(
    task_id: str,
    task_info: dict,
    progress_by_task: dict[str, dict],
    *,
    include_type: bool = False,
) -> dict:
    """Serialize the visible state of a background dashboard task."""
    status = task_info["status"]
    if include_type:
        response_data = {
            "task_id": task_id,
            "type": task_info["type"],
            "status": status,
        }
    else:
        response_data = {"task_id": task_id, "status": status}
    if status == "processing" and task_id in progress_by_task:
        response_data["progress"] = progress_by_task[task_id]
    if status == "completed":
        response_data["result"] = task_info["result"]
    if status == "failed":
        response_data["error"] = task_info["error"]
    return response_data
