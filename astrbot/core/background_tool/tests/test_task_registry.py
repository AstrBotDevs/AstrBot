"""TaskRegistry 单元测试"""

import pytest
import time
from astrbot.core.background_tool.task_state import BackgroundTask, TaskStatus
from astrbot.core.background_tool.task_registry import TaskRegistry


class TestTaskRegistry:
    """测试任务注册表"""

    def setup_method(self):
        """每个测试前重置注册表"""
        self.registry = TaskRegistry()
        self.registry.clear()

    def test_register_task(self):
        """测试注册任务"""
        task = BackgroundTask(
            task_id="test-001",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )

        task_id = self.registry.register(task)

        assert task_id == "test-001"
        assert self.registry.get("test-001") is not None

    def test_get_task(self):
        """测试获取任务"""
        task = BackgroundTask(
            task_id="test-002",
            tool_name="test_tool",
            tool_args={"key": "value"},
            session_id="platform:group:123",
        )
        self.registry.register(task)

        retrieved = self.registry.get("test-002")

        assert retrieved is not None
        assert retrieved.task_id == "test-002"
        assert retrieved.tool_args == {"key": "value"}

    def test_get_nonexistent_task(self):
        """测试获取不存在的任务"""
        result = self.registry.get("nonexistent")
        assert result is None

    def test_get_by_session(self):
        """测试按会话获取任务"""
        task1 = BackgroundTask(
            task_id="test-003",
            tool_name="tool1",
            tool_args={},
            session_id="session-A",
        )
        task2 = BackgroundTask(
            task_id="test-004",
            tool_name="tool2",
            tool_args={},
            session_id="session-A",
        )
        task3 = BackgroundTask(
            task_id="test-005",
            tool_name="tool3",
            tool_args={},
            session_id="session-B",
        )

        self.registry.register(task1)
        self.registry.register(task2)
        self.registry.register(task3)

        session_a_tasks = self.registry.get_by_session("session-A")

        assert len(session_a_tasks) == 2
        assert all(t.session_id == "session-A" for t in session_a_tasks)

    def test_get_running_tasks(self):
        """测试获取运行中的任务"""
        task1 = BackgroundTask(
            task_id="test-006",
            tool_name="tool1",
            tool_args={},
            session_id="session-A",
        )
        task2 = BackgroundTask(
            task_id="test-007",
            tool_name="tool2",
            tool_args={},
            session_id="session-A",
        )

        self.registry.register(task1)
        self.registry.register(task2)

        # 启动第一个任务
        task1.start()

        running = self.registry.get_running_tasks("session-A")

        assert len(running) == 1
        assert running[0].task_id == "test-006"

    def test_update_task(self):
        """测试更新任务"""
        task = BackgroundTask(
            task_id="test-008",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )
        self.registry.register(task)

        success = self.registry.update(
            "test-008",
            status=TaskStatus.RUNNING,
        )

        assert success
        updated = self.registry.get("test-008")
        assert updated.status == TaskStatus.RUNNING

    def test_remove_task(self):
        """测试删除任务"""
        task = BackgroundTask(
            task_id="test-009",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )
        self.registry.register(task)

        success = self.registry.remove("test-009")

        assert success
        assert self.registry.get("test-009") is None

    def test_remove_nonexistent_task(self):
        """测试删除不存在的任务"""
        success = self.registry.remove("nonexistent")
        assert not success

    def test_count(self):
        """测试任务计数"""
        assert self.registry.count() == 0

        task = BackgroundTask(
            task_id="test-010",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )
        self.registry.register(task)

        assert self.registry.count() == 1
