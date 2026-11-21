import asyncio
import gc
import warnings

import pytest

from astrbot.dashboard.services.chunked_upload_service import ChunkedUploadService


def test_cleanup_start_without_loop_does_not_leak_coroutine(tmp_path):
    service = ChunkedUploadService(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        service.ensure_cleanup_task_started()
        gc.collect()
    assert service._cleanup_task is None
    assert not [item for item in caught if "was never awaited" in str(item.message)]


@pytest.mark.asyncio
async def test_cleanup_start_inside_loop_creates_only_one_task(tmp_path):
    service = ChunkedUploadService(tmp_path)
    service.ensure_cleanup_task_started()
    task = service._cleanup_task
    try:
        service.ensure_cleanup_task_started()
        assert task is not None and service._cleanup_task is task
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
