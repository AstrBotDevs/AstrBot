"""MessageConverter 单元测试"""

import pytest


class TestMessageConverter:
    """MessageConverter 测试类"""

    @pytest.fixture
    def converter(self):
        """创建 MessageConverter 实例"""
        from astrbot.core.platform.sources.cli.message.converter import MessageConverter

        return MessageConverter()

    def test_convert_basic_text(self, converter):
        """测试基本文本转换"""
        message = converter.convert("Hello, World!")

        assert message.message_str == "Hello, World!"
        assert message.self_id == "cli_bot"
        assert message.session_id == "cli_session"
        assert message.sender.user_id == "cli_user"
        assert message.sender.nickname == "CLI User"

    def test_convert_with_request_id_no_isolation(self, converter):
        """测试带 request_id 但不启用隔离"""
        message = converter.convert(
            "Test", request_id="req123", use_isolated_session=False
        )

        # 不启用隔离时，使用默认 session_id
        assert message.session_id == "cli_session"

    def test_convert_with_isolated_session(self, converter):
        """测试启用会话隔离"""
        message = converter.convert(
            "Test", request_id="req123", use_isolated_session=True
        )

        # 启用隔离时，session_id 包含 request_id
        assert message.session_id == "cli_session_req123"

    def test_convert_isolated_without_request_id(self, converter):
        """测试启用隔离但无 request_id"""
        message = converter.convert("Test", request_id=None, use_isolated_session=True)

        # 无 request_id 时，使用默认 session_id
        assert message.session_id == "cli_session"

    def test_convert_message_has_id(self, converter):
        """测试消息有唯一 ID"""
        message1 = converter.convert("Test1")
        message2 = converter.convert("Test2")

        assert message1.message_id is not None
        assert message2.message_id is not None
        assert message1.message_id != message2.message_id

    def test_convert_message_has_plain_component(self, converter):
        """测试消息包含 Plain 组件"""
        from astrbot.core.message.components import Plain

        message = converter.convert("Hello")

        assert len(message.message) == 1
        assert isinstance(message.message[0], Plain)
        assert message.message[0].text == "Hello"

    def test_custom_default_session_id(self):
        """测试自定义默认 session_id"""
        from astrbot.core.platform.sources.cli.message.converter import MessageConverter

        converter = MessageConverter(default_session_id="custom_session")
        message = converter.convert("Test")

        assert message.session_id == "custom_session"

    def test_custom_user_info(self):
        """测试自定义用户信息"""
        from astrbot.core.platform.sources.cli.message.converter import MessageConverter

        converter = MessageConverter(
            user_id="custom_user",
            user_nickname="Custom User",
        )
        message = converter.convert("Test")

        assert message.sender.user_id == "custom_user"
        assert message.sender.nickname == "Custom User"
