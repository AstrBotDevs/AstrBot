"""ResponseBuilder 单元测试"""

import json
from unittest.mock import MagicMock

import pytest


class TestResponseBuilder:
    """ResponseBuilder 测试类"""

    @pytest.fixture
    def mock_message_chain(self):
        """创建模拟的 MessageChain"""
        chain = MagicMock()
        chain.get_plain_text.return_value = "Hello, World!"
        chain.chain = []
        return chain

    def test_build_success_basic(self, mock_message_chain):
        """测试构建基本成功响应"""
        from astrbot.core.platform.sources.cli.message.response_builder import (
            ResponseBuilder,
        )

        response = ResponseBuilder.build_success(mock_message_chain, "req123")
        result = json.loads(response)

        assert result["status"] == "success"
        assert result["response"] == "Hello, World!"
        assert result["request_id"] == "req123"
        assert result["images"] == []

    def test_build_success_with_extra(self, mock_message_chain):
        """测试构建带额外字段的成功响应"""
        from astrbot.core.platform.sources.cli.message.response_builder import (
            ResponseBuilder,
        )

        extra = {"custom_field": "custom_value"}
        response = ResponseBuilder.build_success(mock_message_chain, "req123", extra)
        result = json.loads(response)

        assert result["custom_field"] == "custom_value"

    def test_build_error_basic(self):
        """测试构建基本错误响应"""
        from astrbot.core.platform.sources.cli.message.response_builder import (
            ResponseBuilder,
        )

        response = ResponseBuilder.build_error("Something went wrong")
        result = json.loads(response)

        assert result["status"] == "error"
        assert result["error"] == "Something went wrong"
        assert "request_id" not in result

    def test_build_error_with_request_id(self):
        """测试构建带 request_id 的错误响应"""
        from astrbot.core.platform.sources.cli.message.response_builder import (
            ResponseBuilder,
        )

        response = ResponseBuilder.build_error("Error", request_id="req123")
        result = json.loads(response)

        assert result["request_id"] == "req123"

    def test_build_error_with_error_code(self):
        """测试构建带错误代码的错误响应"""
        from astrbot.core.platform.sources.cli.message.response_builder import (
            ResponseBuilder,
        )

        response = ResponseBuilder.build_error(
            "Unauthorized", request_id="req123", error_code="AUTH_FAILED"
        )
        result = json.loads(response)

        assert result["error_code"] == "AUTH_FAILED"

    def test_build_success_with_url_image(self):
        """测试构建带 URL 图片的成功响应"""
        from astrbot.core.message.components import Image
        from astrbot.core.platform.sources.cli.message.response_builder import (
            ResponseBuilder,
        )

        chain = MagicMock()
        chain.get_plain_text.return_value = "Image response"

        # 创建 URL 图片组件
        image = Image(file="https://example.com/image.png")
        chain.chain = [image]

        response = ResponseBuilder.build_success(chain, "req123")
        result = json.loads(response)

        assert len(result["images"]) == 1
        assert result["images"][0]["type"] == "url"
        assert result["images"][0]["url"] == "https://example.com/image.png"

    def test_build_success_chinese_text(self, mock_message_chain):
        """测试构建中文文本响应"""
        from astrbot.core.platform.sources.cli.message.response_builder import (
            ResponseBuilder,
        )

        mock_message_chain.get_plain_text.return_value = "你好，世界！"

        response = ResponseBuilder.build_success(mock_message_chain, "req123")
        result = json.loads(response)

        assert result["response"] == "你好，世界！"
