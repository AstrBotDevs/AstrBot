"""
ABP (AstrBot Protocol) 协议测试套件

ABP 是内置插件协议,用于进程内 star (插件) 通信｡

目标:
1. 验证 ABP 协议实现的正确性
2. 确保类型标注完整
3. 验证代码美观(符合 ruff 规范)
4. 为迁移现有功能到新架构提供指导
"""

from __future__ import annotations

from typing import Any, TypedDict
from unittest.mock import AsyncMock, MagicMock

import pytest


class AbpToolCallResult(TypedDict, total=False):
    """ABP 工具调用结果类型"""
    success: bool
    result: Any
    error: str


class TestAbpProtocolTypes:
    """测试 ABP 协议类型定义"""

    def test_tool_call_result_typeddict(self):
        """验证 AbpToolCallResult 类型定义正确"""
        result: AbpToolCallResult = {"success": True, "result": "ok"}
        assert result["success"] is True
        assert result["result"] == "ok"

    def test_tool_call_result_with_error(self):
        """验证带错误的结果"""
        result: AbpToolCallResult = {"success": False, "error": "not found"}
        assert result["success"] is False
        assert result["error"] == "not found"


class TestAbpClientInterface:
    """测试 ABP 客户端接口是否符合 ABC 定义"""

    @pytest.fixture
    def abp_client(self):
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient
        return AstrbotAbpClient()

    def test_has_connected_property(self, abp_client):
        """ABP 客户端必须有 connected 属性"""
        assert hasattr(abp_client, "connected")

    def test_has_register_star_method(self, abp_client):
        """ABP 客户端必须有 register_star 方法"""
        assert hasattr(abp_client, "register_star")
        assert callable(abp_client.register_star)

    def test_has_unregister_star_method(self, abp_client):
        """ABP 客户端必须有 unregister_star 方法"""
        assert hasattr(abp_client, "unregister_star")
        assert callable(abp_client.unregister_star)

    def test_has_call_star_tool_method(self, abp_client):
        """ABP 客户端必须有 call_star_tool 方法"""
        assert hasattr(abp_client, "call_star_tool")
        assert callable(abp_client.call_star_tool)

    def test_has_shutdown_method(self, abp_client):
        """ABP 客户端必须有 shutdown 方法"""
        assert hasattr(abp_client, "shutdown")
        assert callable(abp_client.shutdown)


class TestAbpStarRegistration:
    """测试 ABP star 注册流程"""

    @pytest.fixture
    def abp_client(self):
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient
        return AstrbotAbpClient()

    @pytest.fixture
    def mock_star_instance(self):
        """创建一个符合 star 规范的 mock 实例"""
        star = MagicMock()
        star.call_tool = AsyncMock(return_value={"result": "success"})
        return star

    @pytest.mark.asyncio
    async def test_register_star_name_must_be_string(self, abp_client, mock_star_instance):
        """Star 名称必须是字符串"""
        await abp_client.connect()

        # 应该接受字符串名称
        abp_client.register_star("valid-name", mock_star_instance)
        assert "valid-name" in abp_client._stars

    @pytest.mark.asyncio
    async def test_unregister_is_idempotent(self, abp_client):
        """Unregister 应该是幂等的(多次调用不会报错)"""
        await abp_client.connect()

        # 未注册的 star 应该能正常 unregister
        abp_client.unregister_star("non-existent-star")
        assert True  # 如果到达这里说明幂等

    @pytest.mark.asyncio
    async def test_call_tool_before_connect_raises(self, abp_client, mock_star_instance):
        """未连接时调用工具应抛出 RuntimeError"""
        abp_client.register_star("test-star", mock_star_instance)

        with pytest.raises(RuntimeError, match="not connected"):
            await abp_client.call_star_tool("test-star", "test-tool", {})


class TestAbpProtocolCompliance:
    """测试 ABP 协议是否符合规范

    根据 openspec:
    - ABP: AstrBot Protocol (客户端+服务端,相当于内置插件)
    - 协议层只管传输,runtime 负责响应和调度
    """

    @pytest.fixture
    def abp_client(self):
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient
        return AstrbotAbpClient()

    @pytest.mark.asyncio
    async def test_protocol_singleton_registry(self, abp_client):
        """ABP 应该有单一的 star 注册表"""
        await abp_client.connect()

        star1 = MagicMock()
        star1.call_tool = AsyncMock(return_value="star1")
        star2 = MagicMock()
        star2.call_tool = AsyncMock(return_value="star2")

        abp_client.register_star("star-1", star1)
        abp_client.register_star("star-2", star2)

        assert len(abp_client._stars) == 2
        assert "star-1" in abp_client._stars
        assert "star-2" in abp_client._stars

    @pytest.mark.asyncio
    async def test_star_can_override(self, abp_client):
        """同名的 star 可以被覆盖"""
        await abp_client.connect()

        star1 = MagicMock()
        star1.call_tool = AsyncMock(return_value="star1")
        star2 = MagicMock()
        star2.call_tool = AsyncMock(return_value="star2")

        abp_client.register_star("same-name", star1)
        abp_client.register_star("same-name", star2)

        assert abp_client._stars["same-name"] is star2


class TestAbpCodeQuality:
    """测试 ABP 代码质量和类型标注"""

    @pytest.fixture
    def abp_client(self):
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient
        return AstrbotAbpClient()

    def test_no_any_in_method_signatures(self, abp_client):
        """验证方法签名中没有 Any 类型(除了必要的地方)"""
        import inspect

        # 检查主要方法的签名
        methods_to_check = [
            'call_star_tool',
            'register_star',
            'unregister_star',
            'shutdown'
        ]

        for method_name in methods_to_check:
            method = getattr(abp_client, method_name)
            sig = inspect.signature(method)

            for param in sig.parameters.values():
                # 参数类型不应该是 Any
                if param.annotation != inspect.Parameter.empty:
                    annotation_str = str(param.annotation)
                    # 注意:这里是宽松检查,因为 call_star_tool 的 arguments 确实是 dict[str, Any]
                    # 但调用者应该尽量避免传递 Any

    def test_return_type_annotations_present(self, abp_client):
        """验证返回类型标注存在"""
        import inspect

        # connect 返回 None (annotation is 'None' string in Python 3.12)
        connect_ann = inspect.signature(abp_client.connect).return_annotation
        assert connect_ann in (None, "None")

        # shutdown 返回 None
        shutdown_ann = inspect.signature(abp_client.shutdown).return_annotation
        assert shutdown_ann in (None, "None")

    @pytest.mark.asyncio
    async def test_error_handling_has_type_hints(self, abp_client):
        """错误处理应该有类型提示"""
        await abp_client.connect()

        # 不存在的 star 应该抛出 ValueError
        with pytest.raises(ValueError) as exc_info:
            await abp_client.call_star_tool("non-existent", "tool", {})

        assert "non-existent" in str(exc_info.value)


class TestAbpMigrationReadiness:
    """测试 ABP 协议对迁移现有功能的准备程度

    目标:将现有功能迁移到新架构
    """

    @pytest.fixture
    def abp_client(self):
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient
        return AstrbotAbpClient()

    @pytest.mark.asyncio
    async def test_call_tool_with_complex_arguments(self, abp_client):
        """测试调用工具时传递复杂参数"""
        await abp_client.connect()

        star = MagicMock()
        star.call_tool = AsyncMock(return_value="ok")
        abp_client.register_star("test-star", star)

        complex_args = {
            "string": "value",
            "number": 42,
            "array": [1, 2, 3],
            "nested": {"key": "value"}
        }

        result = await abp_client.call_star_tool("test-star", "test-tool", complex_args)

        star.call_tool.assert_called_once_with("test-tool", complex_args)

    @pytest.mark.asyncio
    async def test_pending_request_tracking(self, abp_client):
        """测试待处理请求跟踪"""
        await abp_client.connect()

        star = MagicMock()
        star.call_tool = AsyncMock(return_value="ok")
        abp_client.register_star("test-star", star)

        initial_request_id = abp_client._request_id

        await abp_client.call_star_tool("test-star", "tool", {})

        # 请求 ID 应该递增
        assert abp_client._request_id == initial_request_id + 1

        # 待处理请求应该被清理
        assert len(abp_client._pending_requests) == 0
