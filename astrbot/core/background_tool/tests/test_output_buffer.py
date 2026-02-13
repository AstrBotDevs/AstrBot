"""OutputBuffer 单元测试"""

from astrbot.core.background_tool.output_buffer import OutputBuffer


class TestOutputBuffer:
    """测试输出缓冲区"""

    def setup_method(self):
        """每个测试前重置缓冲区"""
        self.buffer = OutputBuffer(max_lines=100)

    def test_append_line(self):
        """测试追加行"""
        self.buffer.append("task-001", "line 1")
        self.buffer.append("task-001", "line 2")

        lines = self.buffer.get_all("task-001")

        assert len(lines) == 2
        assert lines[0] == "line 1"
        assert lines[1] == "line 2"

    def test_get_all_empty(self):
        """测试获取空缓冲区"""
        lines = self.buffer.get_all("nonexistent")
        assert lines == []

    def test_get_recent(self):
        """测试获取最近N行"""
        for i in range(10):
            self.buffer.append("task-002", f"line {i}")

        recent = self.buffer.get_recent("task-002", n=3)

        assert len(recent) == 3
        assert recent[0] == "line 7"
        assert recent[1] == "line 8"
        assert recent[2] == "line 9"

    def test_get_recent_less_than_n(self):
        """测试获取最近N行（实际行数少于N）"""
        self.buffer.append("task-003", "line 1")
        self.buffer.append("task-003", "line 2")

        recent = self.buffer.get_recent("task-003", n=10)

        assert len(recent) == 2

    def test_clear(self):
        """测试清空缓冲区"""
        self.buffer.append("task-004", "line 1")
        self.buffer.append("task-004", "line 2")

        self.buffer.clear("task-004")

        assert self.buffer.get_all("task-004") == []

    def test_max_lines_limit(self):
        """测试最大行数限制"""
        buffer = OutputBuffer(max_lines=5)

        for i in range(10):
            buffer.append("task-005", f"line {i}")

        lines = buffer.get_all("task-005")

        assert len(lines) == 5
        # 应该保留最后5行
        assert lines[0] == "line 5"
        assert lines[4] == "line 9"

    def test_multiple_tasks(self):
        """测试多任务隔离"""
        self.buffer.append("task-A", "A line 1")
        self.buffer.append("task-B", "B line 1")
        self.buffer.append("task-A", "A line 2")

        lines_a = self.buffer.get_all("task-A")
        lines_b = self.buffer.get_all("task-B")

        assert len(lines_a) == 2
        assert len(lines_b) == 1
        assert lines_a[0] == "A line 1"
        assert lines_b[0] == "B line 1"

    def test_line_count(self):
        """测试行数统计"""
        assert self.buffer.line_count("task-006") == 0

        self.buffer.append("task-006", "line 1")
        self.buffer.append("task-006", "line 2")

        assert self.buffer.line_count("task-006") == 2
