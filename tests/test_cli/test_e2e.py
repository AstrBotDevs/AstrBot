"""CLI端到端测试 - 验证完整消息处理流程"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest


class TestCLIEndToEnd:
    """CLI端到端测试类"""

    @pytest.fixture
    def mock_context(self):
        """创建模拟的上下文"""
        ctx = MagicMock()
        ctx.register_platform = MagicMock()
        return ctx

    @pytest.fixture
    def mock_config(self):
        """创建模拟的配置"""
        return {
            "id": "cli_test",
            "enable": True,
            "mode": "socket",
            "socket_type": "tcp",
            "tcp_port": 0,
            "session_ttl": 30,
            "use_isolated_sessions": False,
        }

    @pytest.mark.asyncio
    async def test_message_converter_to_event_flow(self):
        """测试消息转换到事件的完整流程"""
        from astrbot.core.platform.platform_metadata import PlatformMetadata
        from astrbot.core.platform.sources.cli.cli_event import CLIMessageEvent
        from astrbot.core.platform.sources.cli.message.converter import MessageConverter

        # 1. 创建消息转换器
        converter = MessageConverter()

        # 2. 转换输入消息
        message = converter.convert("Hello, AstrBot!")

        # 3. 验证消息结构
        assert message.message_str == "Hello, AstrBot!"
        assert message.session_id == "cli_session"
        assert message.sender.user_id == "cli_user"

        # 4. 创建事件
        platform_meta = PlatformMetadata(
            name="cli", description="CLI Platform", id="cli_test"
        )
        output_queue = asyncio.Queue()

        event = CLIMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=platform_meta,
            session_id=message.session_id,
            output_queue=output_queue,
        )

        # 5. 验证事件属性
        assert event.message_str == "Hello, AstrBot!"
        assert event.session_id == "cli_session"

    @pytest.mark.asyncio
    async def test_response_builder_with_message_chain(self):
        """测试响应构建器处理消息链"""
        from astrbot.core.message.components import Image, Plain
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot.core.platform.sources.cli.message.response_builder import (
            ResponseBuilder,
        )

        # 1. 创建消息链
        chain = MessageChain()
        chain.chain = [
            Plain("Hello!"),
            Image(file="https://example.com/image.png"),
        ]
        chain.get_plain_text = MagicMock(return_value="Hello!")

        # 2. 构建响应
        response = ResponseBuilder.build_success(chain, "req123")
        result = json.loads(response)

        # 3. 验证响应结构
        assert result["status"] == "success"
        assert result["response"] == "Hello!"
        assert result["request_id"] == "req123"
        assert len(result["images"]) == 1
        assert result["images"][0]["type"] == "url"
        assert result["images"][0]["url"] == "https://example.com/image.png"

    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """测试会话生命周期"""
        from astrbot.core.platform.sources.cli.session.session_manager import (
            SessionManager,
        )

        # 1. 创建会话管理器（启用）
        manager = SessionManager(ttl=30, enabled=True)

        # 2. 注册会话
        manager.register("session_1")
        manager.register("session_2")

        # 3. 验证会话存在（通过检查是否过期）
        assert manager.is_expired("session_1") is False
        assert manager.is_expired("session_2") is False

        # 4. 验证未注册的会话被视为过期
        assert manager.is_expired("nonexistent") is True

    @pytest.mark.asyncio
    async def test_token_validation_flow(self):
        """测试Token验证流程"""
        import tempfile

        from astrbot.core.platform.sources.cli.config.token_manager import TokenManager

        # 使用临时目录避免影响真实token文件
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "astrbot.core.platform.sources.cli.config.token_manager.get_astrbot_data_path"
            ) as mock_path:
                mock_path.return_value = tmpdir

                # 1. 创建Token管理器（会自动生成token）
                manager = TokenManager()
                token = manager.token

                # 2. 验证token已生成
                assert token is not None
                assert len(token) > 0

                # 3. 验证正确Token
                assert manager.validate(token) is True

                # 4. 验证错误Token
                assert manager.validate("wrong_token") is False

                # 5. 验证空Token
                assert manager.validate("") is False

    @pytest.mark.asyncio
    async def test_cli_event_send_to_queue(self):
        """测试CLI事件发送到队列"""
        from astrbot.core.message.components import Plain
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot.core.platform.platform_metadata import PlatformMetadata
        from astrbot.core.platform.sources.cli.cli_event import CLIMessageEvent
        from astrbot.core.platform.sources.cli.message.converter import MessageConverter

        # 1. 使用MessageConverter创建真实的消息对象
        converter = MessageConverter()
        message_obj = converter.convert("Test")

        platform_meta = PlatformMetadata(
            name="cli", description="CLI Platform", id="cli_test"
        )
        output_queue = asyncio.Queue()

        event = CLIMessageEvent(
            message_str="Test",
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id="test_session",
            output_queue=output_queue,
        )

        # 2. 创建响应消息链
        response_chain = MessageChain()
        response_chain.chain = [Plain("Response")]

        # 3. 发送响应（无response_future时直接放入队列）
        result = await event.send(response_chain)

        # 4. 验证结果
        assert result["success"] is True

        # 5. 验证队列中有消息
        queued_message = await output_queue.get()
        assert queued_message == response_chain

    @pytest.mark.asyncio
    async def test_image_processor_pipeline(self):
        """测试图片处理管道"""
        import base64
        import os
        import tempfile

        from astrbot.core.message.components import Image, Plain
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ChainPreprocessor,
            ImageExtractor,
            ImageProcessor,
        )

        # 1. 创建临时图片文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            f.write(b"fake image data")
            temp_path = f.name

        try:
            # 2. 测试本地文件转base64
            base64_data = ImageProcessor.local_file_to_base64(temp_path)
            assert base64_data == base64.b64encode(b"fake image data").decode("utf-8")

            # 3. 创建混合消息链
            chain = MagicMock()
            chain.chain = [
                Plain("Hello"),
                Image(file="https://example.com/remote.png"),
                Image(file=f"file:///{temp_path}"),
            ]

            # 4. 提取图片信息
            images = ImageExtractor.extract(chain)
            assert len(images) == 2
            assert images[0].type == "url"
            assert images[0].url == "https://example.com/remote.png"

            # 5. 预处理消息链（本地文件转base64）
            local_image = Image(file=f"file:///{temp_path}")
            preprocess_chain = MagicMock()
            preprocess_chain.chain = [local_image]

            ChainPreprocessor.preprocess(preprocess_chain)

            # 验证本地文件已转换为base64
            assert local_image.file.startswith("base64://")

        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_error_response_building(self):
        """测试错误响应构建"""
        from astrbot.core.platform.sources.cli.message.response_builder import (
            ResponseBuilder,
        )

        # 1. 基本错误
        response = ResponseBuilder.build_error("Something went wrong")
        result = json.loads(response)
        assert result["status"] == "error"
        assert result["error"] == "Something went wrong"

        # 2. 带request_id的错误
        response = ResponseBuilder.build_error("Auth failed", request_id="req123")
        result = json.loads(response)
        assert result["request_id"] == "req123"

        # 3. 带错误代码的错误
        response = ResponseBuilder.build_error(
            "Unauthorized", request_id="req123", error_code="AUTH_FAILED"
        )
        result = json.loads(response)
        assert result["error_code"] == "AUTH_FAILED"

    @pytest.mark.asyncio
    async def test_isolated_session_creation(self):
        """测试隔离会话创建"""
        from astrbot.core.platform.sources.cli.message.converter import MessageConverter

        converter = MessageConverter()

        # 1. 不启用隔离
        msg1 = converter.convert("Test", request_id="req1", use_isolated_session=False)
        assert msg1.session_id == "cli_session"

        # 2. 启用隔离
        msg2 = converter.convert("Test", request_id="req2", use_isolated_session=True)
        assert msg2.session_id == "cli_session_req2"

        # 3. 启用隔离但无request_id
        msg3 = converter.convert("Test", request_id=None, use_isolated_session=True)
        assert msg3.session_id == "cli_session"

        # 4. 不同request_id产生不同session
        msg4 = converter.convert("Test", request_id="req3", use_isolated_session=True)
        assert msg4.session_id == "cli_session_req3"
        assert msg2.session_id != msg4.session_id
