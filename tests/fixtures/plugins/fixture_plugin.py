"""
测试插件 - 用于插件系统测试

这是一个最小化的测试插件，用于验证插件系统的功能。
"""

from astrbot.api import llm_tool, star
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter


@star.register("test_plugin", "AstrBot Team", "测试插件 - 用于插件系统测试", "1.0.0")
class TestPlugin(star.Star):
    """测试插件类"""

    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.initialized = True

    async def terminate(self) -> None:
        """插件终止"""
        self.initialized = False

    @filter.command("test_cmd")
    async def test_command(self, event: AstrMessageEvent) -> None:
        """测试命令处理器。"""
        event.set_result(MessageEventResult().message("测试命令执行成功"))

    @llm_tool("test_tool")
    async def test_llm_tool(self, query: str) -> str:
        """测试 LLM 工具。

        Args:
            query(string): 查询内容。
        """
        return f"测试工具执行成功: {query}"

    @filter.regex(r"^test_regex_(.+)$")
    async def test_regex_handler(self, event: AstrMessageEvent) -> None:
        """测试正则处理器。"""
        event.set_result(MessageEventResult().message("正则匹配成功"))
