"""TaskState 单元测试"""

import pytest
import time
from astrbot.core.background_tool.task_state import (
    BackgroundTask,
    TaskStatus,
)


class TestTaskStatus:
    """测试任务状态枚举"""

    def test_status_values(self):
        """测试状态值"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestBackgroundTask:
    """测试后台任务数据结构"""

    def test_create_task(self):
        """测试创建任务"""
        task = BackgroundTask(
            task_id="test-001",
            tool_name="test_tool",
            tool_args={"param1": "value1"},
            session_id="platform:group:123",
        )

        assert task.task_id == "test-001"
        assert task.tool_name == "test_tool"
        assert task.tool_args == {"param1": "value1"}
        assert task.session_id == "platform:group:123"
        assert task.status == TaskStatus.PENDING
        assert task.result is None
        assert task.error is None
        assert len(task.output_log) == 0

    def test_task_start(self):
        """测试任务开始"""
        task = BackgroundTask(
            task_id="test-002",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )

        task.start()

        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None
        assert task.started_at <= time.time()

    def test_task_complete(self):
        """测试任务完成"""
        task = BackgroundTask(
            task_id="test-003",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )

        task.start()
        task.complete("success result")

        assert task.status == TaskStatus.COMPLETED
        assert task.result == "success result"
        assert task.completed_at is not None

    def test_task_fail(self):
        """测试任务失败"""
        task = BackgroundTask(
            task_id="test-004",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )

        task.start()
        task.fail("error message")

        assert task.status == TaskStatus.FAILED
        assert task.error == "error message"
        assert task.completed_at is not None

    def test_task_cancel(self):
        """测试任务取消"""
        task = BackgroundTask(
            task_id="test-005",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )

        task.start()
        task.cancel()

        assert task.status == TaskStatus.CANCELLED
        assert task.completed_at is not None

    def test_append_output(self):
        """测试追加输出日志"""
        task = BackgroundTask(
            task_id="test-006",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )

        task.append_output("line 1")
        task.append_output("line 2")

        assert len(task.output_log) == 2
        assert task.output_log[0] == "line 1"
        assert task.output_log[1] == "line 2"

    def test_to_dict(self):
        """测试序列化为字典"""
        task = BackgroundTask(
            task_id="test-007",
            tool_name="test_tool",
            tool_args={"key": "value"},
            session_id="platform:group:123",
        )

        d = task.to_dict()

        assert d["task_id"] == "test-007"
        assert d["tool_name"] == "test_tool"
        assert d["status"] == "pending"
        assert d["tool_args"] == {"key": "value"}

    def test_is_finished(self):
        """测试是否已完成"""
        task = BackgroundTask(
            task_id="test-008",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )

        assert not task.is_finished()

        task.start()
        assert not task.is_finished()

        task.complete("done")
        assert task.is_finished()
