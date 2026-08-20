import asyncio
import json
import threading
import zipfile
from pathlib import Path

import pytest

from astrbot.core.updator import NoPublishedCoreReleaseError
from astrbot.dashboard.api import updates as updates_api
from astrbot.dashboard.services import update_service as update_service_module
from astrbot.dashboard.services.update_service import UpdateService, UpdateServiceError


class _ControlledUpdater:
    def __init__(self, *, failure_stage: str | None = None) -> None:
        self.failure_stage = failure_stage
        self.failure_error: Exception | None = None
        self.calls: list[str] = []
        self.download_started = asyncio.Event()
        self.allow_download = asyncio.Event()
        self.allow_download.set()
        self.apply_started = asyncio.Event()
        self.allow_apply = threading.Event()
        self.allow_apply.set()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def download_update_package(self, *, path: Path, progress_callback, **kwargs):
        del kwargs
        self._loop = asyncio.get_running_loop()
        self.calls.append("download")
        self.download_started.set()
        await self.allow_download.wait()
        if self.failure_stage == "download":
            raise self.failure_error or RuntimeError("download failed")
        if self.failure_stage == "verify":
            path.write_bytes(b"not a zip")
            return path
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("astrbot/__init__.py", "")
        progress_callback({"percent": 1, "downloaded": 1, "total": 1, "speed": 1})
        return path

    def apply_update_package(self, _path: Path) -> None:
        self.calls.append("apply")
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self.apply_started.set)
        self.allow_apply.wait()
        if self.failure_stage == "apply":
            raise self.failure_error or RuntimeError("apply failed")


class _ControlledLifecycle:
    def __init__(self, *, failure_stage: str | None = None) -> None:
        self.failure_stage = failure_stage
        self.calls: list[str] = []

    async def restart(self) -> None:
        self.calls.append("restart")
        if self.failure_stage == "restart":
            raise RuntimeError("restart failed")


class _ControlledPipInstall:
    def __init__(self, *, failure_stage: str | None = None) -> None:
        self.failure_stage = failure_stage
        self.calls: list[str] = []

    async def __call__(self, *args, **kwargs) -> None:
        del args, kwargs
        self.calls.append("dependencies")
        if self.failure_stage == "dependencies":
            raise RuntimeError("dependency install failed")


def _make_service(
    monkeypatch,
    tmp_path: Path,
    *,
    failure_stage: str | None = None,
    max_progress_records: int | None = None,
) -> tuple[
    UpdateService, _ControlledUpdater, _ControlledLifecycle, _ControlledPipInstall
]:
    monkeypatch.setattr(
        update_service_module,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        update_service_module,
        "is_desktop_managed_backend",
        lambda: False,
    )
    updater = _ControlledUpdater(failure_stage=failure_stage)
    lifecycle = _ControlledLifecycle(failure_stage=failure_stage)
    pip_install = _ControlledPipInstall(failure_stage=failure_stage)
    kwargs = {}
    if max_progress_records is not None:
        kwargs["max_progress_records"] = max_progress_records
    service = UpdateService(
        updater,
        lifecycle,
        pip_install_func=pip_install,
        demo_mode=False,
        clear_site_data_headers={},
        **kwargs,
    )
    return service, updater, lifecycle, pip_install


async def _cancel_remaining_update_tasks(service: UpdateService) -> None:
    tasks = list(service._update_tasks.values())
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def test_update_api_service_error_redacts_logs_and_keeps_generic_envelope(caplog):
    response = updates_api._service_error(
        UpdateServiceError(
            "api_key=top-secret Bearer token-123 "
            "https://internal.example/path C:\\private\\secret.txt"
        )
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "status": "error",
        "message": "An internal error has occurred.",
        "data": None,
    }
    assert "top-secret" not in caplog.text
    assert "token-123" not in caplog.text
    assert "internal.example" not in caplog.text
    assert "C:\\private\\secret.txt" not in caplog.text


@pytest.mark.asyncio
async def test_update_project_coalesces_a_running_progress_id(monkeypatch, tmp_path):
    service, updater, _lifecycle, _pip_install = _make_service(monkeypatch, tmp_path)
    updater.allow_download.clear()

    try:
        first = await service.update_project(
            {"progress_id": "same-id", "reboot": False}
        )
        await updater.download_started.wait()
        second = await service.update_project(
            {"progress_id": "same-id", "reboot": False}
        )

        assert first.data == {"id": "same-id", "status": "running"}
        assert second.message == "更新任务正在进行中。"
        assert len(service._update_tasks) == 1
        assert updater.calls == ["download"]

        updater.allow_download.set()
        await service._update_tasks["same-id"]
        assert "same-id" not in service._update_tasks
    finally:
        await _cancel_remaining_update_tasks(service)


@pytest.mark.asyncio
@pytest.mark.parametrize("attempt", range(3))
async def test_old_done_callback_cannot_remove_a_replacement_task(
    monkeypatch, tmp_path, attempt: int
):
    del attempt
    service, updater, _lifecycle, _pip_install = _make_service(monkeypatch, tmp_path)
    updater.allow_download.clear()
    callback_ran = asyncio.Event()

    assert hasattr(service, "_discard_update_task")

    async def complete_immediately() -> None:
        return None

    old_task = asyncio.create_task(complete_immediately(), name="old-update-task")
    await old_task
    service._update_tasks["same-id"] = old_task

    def old_done_callback(task: asyncio.Task) -> None:
        service._discard_update_task("same-id", task)
        callback_ran.set()

    old_task.add_done_callback(old_done_callback)
    try:
        await service.update_project({"progress_id": "same-id", "reboot": False})
        replacement = service._update_tasks["same-id"]

        await callback_ran.wait()

        assert service._update_tasks["same-id"] is replacement
        assert not replacement.done()
    finally:
        updater.allow_download.set()
        await _cancel_remaining_update_tasks(service)


@pytest.mark.asyncio
async def test_update_service_shutdown_cancels_owned_tasks_and_marks_progress(
    monkeypatch,
    tmp_path,
):
    service, updater, _lifecycle, _pip_install = _make_service(monkeypatch, tmp_path)
    updater.allow_download.clear()

    try:
        await service.update_project({"progress_id": "shutdown", "reboot": False})
        task = service._update_tasks["shutdown"]
        await updater.download_started.wait()

        await service.shutdown()

        assert task.cancelled()
        assert service._update_tasks == {}
        assert service.update_progress["shutdown"]["status"] == "error"
        assert service.update_progress["shutdown"]["message"] == "更新任务已取消。"
    finally:
        updater.allow_download.set()
        await _cancel_remaining_update_tasks(service)


@pytest.mark.asyncio
async def test_update_service_shutdown_waits_for_owned_apply_thread(
    monkeypatch,
    tmp_path,
):
    service, updater, _lifecycle, _pip_install = _make_service(monkeypatch, tmp_path)
    updater.allow_apply.clear()
    shutdown: asyncio.Task | None = None

    try:
        await service.update_project({"progress_id": "threaded", "reboot": False})
        update_task = service._update_tasks["threaded"]
        await updater.apply_started.wait()

        shutdown_entered = asyncio.Event()
        shutdown_finished = asyncio.Event()

        async def stop_service() -> None:
            shutdown_entered.set()
            await service.shutdown()
            shutdown_finished.set()

        shutdown = asyncio.create_task(stop_service(), name="shutdown-update-service")
        await shutdown_entered.wait()

        assert not shutdown_finished.is_set()
        assert not update_task.done()

        updater.allow_apply.set()
        await shutdown

        assert update_task.cancelled()
        assert service._update_tasks == {}
        assert service.update_progress["threaded"]["status"] == "error"
    finally:
        updater.allow_apply.set()
        if shutdown is not None and not shutdown.done():
            shutdown.cancel()
        if shutdown is not None:
            await asyncio.gather(shutdown, return_exceptions=True)
        await _cancel_remaining_update_tasks(service)


@pytest.mark.asyncio
async def test_run_threaded_reaps_executor_work_after_repeated_cancellation(
    monkeypatch,
):
    """A second owner cancellation cannot detach its active executor task."""
    service = UpdateService.__new__(UpdateService)
    loop = asyncio.get_running_loop()
    thread_started = asyncio.Event()
    allow_thread_exit = threading.Event()
    cleanup_waiting = asyncio.Event()
    original_create_task = asyncio.create_task
    original_shield = asyncio.shield
    thread_tasks: list[asyncio.Task] = []
    shield_calls = 0

    def block_thread() -> None:
        loop.call_soon_threadsafe(thread_started.set)
        allow_thread_exit.wait()

    def capture_thread_task(coroutine, *args, **kwargs) -> asyncio.Task:
        task = original_create_task(coroutine, *args, **kwargs)
        thread_tasks.append(task)
        return task

    def observe_shield(task):
        nonlocal shield_calls
        shield_calls += 1
        if shield_calls == 2:
            cleanup_waiting.set()
        return original_shield(task)

    with monkeypatch.context() as patch:
        patch.setattr(
            update_service_module.asyncio,
            "create_task",
            capture_thread_task,
        )
        patch.setattr(update_service_module.asyncio, "shield", observe_shield)
        owner = original_create_task(
            service._run_threaded(block_thread),
            name="double-cancel-update-thread-owner",
        )
        try:
            await thread_started.wait()
            owner.cancel()
            await cleanup_waiting.wait()

            owner.cancel()
            next_turn = loop.create_future()
            loop.call_soon(next_turn.set_result, None)
            await next_turn

            assert not owner.done()
            assert len(thread_tasks) == 1
            assert not thread_tasks[0].done()

            allow_thread_exit.set()
            with pytest.raises(asyncio.CancelledError):
                await owner
            assert thread_tasks[0].done()
        finally:
            allow_thread_exit.set()
            await asyncio.gather(owner, *thread_tasks, return_exceptions=True)


def test_update_service_prunes_old_terminal_progress_records(monkeypatch, tmp_path):
    service, _updater, _lifecycle, _pip_install = _make_service(
        monkeypatch,
        tmp_path,
        max_progress_records=2,
    )

    service._init_update_progress("old", "")
    service.update_progress["old"]["status"] = "success"
    service._init_update_progress("active", "")
    service._init_update_progress("new", "")

    assert list(service.update_progress) == ["active", "new"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_stage", "reboot", "expected_stage", "expected_calls"),
    [
        ("download", False, "core", ["download"]),
        ("verify", False, "verify", ["download"]),
        ("apply", False, "apply", ["download", "apply"]),
        ("dependencies", True, "dependencies", ["download", "apply", "dependencies"]),
        (
            "restart",
            True,
            "restart",
            ["download", "apply", "dependencies", "restart"],
        ),
    ],
)
async def test_update_project_marks_each_failed_stage_and_cleans_temp_directory(
    monkeypatch,
    tmp_path,
    failure_stage: str,
    reboot: bool,
    expected_stage: str,
    expected_calls: list[str],
):
    service, updater, lifecycle, pip_install = _make_service(
        monkeypatch,
        tmp_path,
        failure_stage=failure_stage,
    )
    progress_id = f"failed-{failure_stage}"

    try:
        await service.update_project({"progress_id": progress_id, "reboot": reboot})
        task = service._update_tasks[progress_id]
        await task

        progress = service.update_progress[progress_id]
        assert progress_id not in service._update_tasks
        assert progress["status"] == "error"
        assert progress["stage"] == expected_stage
        assert progress["stages"][expected_stage]["status"] == "error"
        assert updater.calls + pip_install.calls + lifecycle.calls == expected_calls
        assert list((tmp_path / "updates").glob("project-update-*")) == []
        if failure_stage == "dependencies":
            assert progress["message"] == "依赖更新失败，未执行重启。"
            assert lifecycle.calls == []
    finally:
        await _cancel_remaining_update_tasks(service)


@pytest.mark.asyncio
async def test_update_project_marks_all_completed_stages_and_reclaims_task(
    monkeypatch,
    tmp_path,
):
    service, updater, lifecycle, pip_install = _make_service(monkeypatch, tmp_path)

    try:
        await service.update_project({"progress_id": "success", "reboot": True})
        await service._update_tasks["success"]

        progress = service.update_progress["success"]
        assert progress["status"] == "success"
        assert progress["stage"] == "done"
        assert progress["overall_percent"] == 100
        assert {
            stage: details["status"] for stage, details in progress["stages"].items()
        } == {
            "core": "done",
            "verify": "done",
            "apply": "done",
            "dependencies": "done",
            "restart": "done",
        }
        assert updater.calls + pip_install.calls + lifecycle.calls == [
            "download",
            "apply",
            "dependencies",
            "restart",
        ]
        assert "success" not in service._update_tasks
        assert list((tmp_path / "updates").glob("project-update-*")) == []
    finally:
        await _cancel_remaining_update_tasks(service)


@pytest.mark.asyncio
async def test_update_project_redacts_stage_failure_logs(monkeypatch, tmp_path, caplog):
    service, updater, _lifecycle, _pip_install = _make_service(
        monkeypatch,
        tmp_path,
        failure_stage="download",
    )
    updater.failure_error = RuntimeError(
        "api_key=top-secret Bearer token-123 "
        "https://internal.example/path C:\\private\\secret.txt"
    )

    try:
        await service.update_project({"progress_id": "redacted", "reboot": False})
        await service._update_tasks["redacted"]

        assert service.update_progress["redacted"]["status"] == "error"
        assert "top-secret" not in caplog.text
        assert "token-123" not in caplog.text
        assert "internal.example" not in caplog.text
        assert "C:\\private\\secret.txt" not in caplog.text
    finally:
        await _cancel_remaining_update_tasks(service)


@pytest.mark.asyncio
async def test_update_project_cancellation_cleans_temporary_directory(
    monkeypatch, tmp_path
):
    service, updater, _lifecycle, _pip_install = _make_service(monkeypatch, tmp_path)
    updater.allow_download.clear()

    try:
        await service.update_project({"progress_id": "cancelled", "reboot": False})
        task = service._update_tasks["cancelled"]
        await updater.download_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        progress = service.update_progress["cancelled"]
        assert progress["status"] == "error"
        assert progress["stage"] == "core"
        assert progress["stages"]["core"]["status"] == "error"
        assert list((tmp_path / "updates").glob("project-update-*")) == []
    finally:
        updater.allow_download.set()
        await _cancel_remaining_update_tasks(service)


@pytest.mark.asyncio
async def test_update_service_rejects_new_records_when_capacity_has_only_running_tasks(
    monkeypatch,
    tmp_path,
):
    service, _updater, _lifecycle, _pip_install = _make_service(
        monkeypatch,
        tmp_path,
        max_progress_records=1,
    )
    service._init_update_progress("active", "")

    with pytest.raises(UpdateServiceError, match="更新任务过多"):
        await service.update_project({"progress_id": "new", "reboot": False})

    assert list(service.update_progress) == ["active"]


@pytest.mark.asyncio
async def test_check_update_reports_unpublished_fork_releases(monkeypatch, tmp_path):
    service, updater, _lifecycle, _pip_install = _make_service(monkeypatch, tmp_path)

    async def fake_check_update(*args, **kwargs):
        del args, kwargs
        raise NoPublishedCoreReleaseError(
            "当前 fork 未发布可供 Dashboard 下载的 Core Release。请通过更新源码 checkout 升级。"
        )

    updater.check_update = fake_check_update
    result = await service.check_update()
    assert result.data["has_new_version"] is False
    assert "未发布可供 Dashboard 下载" in (result.message or "")
